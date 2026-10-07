"""
Partition and File Extraction Module for PureGoogleGappsBuilder
Handles GPT Dynamic Super Partitions, EROFS, EXT4, Sparse Images, and Native Libraries.
"""

import os
import sys
import glob
import struct
import shutil
import subprocess
import zipfile
from core.constants import TARGET_APP_PATTERNS, EXCLUDED_AOSP_APPS, ABI_TO_LIB_DIR


def is_genuine_google_file(filename: str, rel_path: str) -> bool:
    """Filter out AOSP OS system apps, emulator overlays, and retain only genuine Google GApps"""
    fl = filename.lower()
    rl = rel_path.lower()
    
    # Exclude emulator overlays, RROs, test stubs, base AOSP OS apps
    if "overlay" in rl or "rro" in rl or "emulator" in fl or "ranchu" in fl or "cutout" in fl or "goldfish" in fl or "wallpaper" in fl:
        return False
    if fl in EXCLUDED_AOSP_APPS:
        return False
        
    # Match genuine Google apps / services
    if fl.endswith(".apk"):
        return any(pat.lower().strip("*") in fl for pat in TARGET_APP_PATTERNS if not pat.startswith("*permissions") and not pat.startswith("*sysconfig") and not pat.startswith("*framework")) or "gms" in fl or "phonesky" in fl or "wellbeing" in fl or "talkback" in fl
        
    if fl.endswith(".xml"):
        return ("google" in fl or "gms" in fl or "maps" in fl or "widevine" in fl or "dialer" in fl) and ("permissions" in rl or "sysconfig" in rl or "default-permissions" in rl)
        
    if fl.endswith(".jar"):
        return ("google" in fl or "maps" in fl or "media.effects" in fl) and "framework" in rl
        
    return False


def extract_native_libs_from_apk(apk_path: str, abi: str):
    """Extract matching architecture native libs (.so) from APK into correct Android system directory"""
    lib_dir_name = ABI_TO_LIB_DIR.get(abi, abi)
    apk_dir = os.path.dirname(apk_path)
    target_lib_dir = os.path.join(apk_dir, "lib", lib_dir_name)
    
    possible_abi_names = ["arm64-v8a", "arm64"] if abi in ["arm64", "arm64-v8a"] else [abi]
    if abi in ["arm", "armeabi-v7a"]:
        possible_abi_names = ["armeabi-v7a", "armeabi", "arm"]

    try:
        with zipfile.ZipFile(apk_path, "r") as z:
            matching_entries = []
            for candidate in possible_abi_names:
                entries = [f for f in z.namelist() if f.startswith(f"lib/{candidate}/") and f.endswith(".so")]
                if entries:
                    matching_entries = entries
                    break
                    
            if matching_entries:
                os.makedirs(target_lib_dir, exist_ok=True)
                for entry in matching_entries:
                    filename = os.path.basename(entry)
                    dest_so = os.path.join(target_lib_dir, filename)
                    with z.open(entry) as src, open(dest_so, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                print(f"      -> Extracted {len(matching_entries)} native libs ({lib_dir_name}) for {os.path.basename(apk_path)}", flush=True)
    except Exception as e:
        print(f"[!] Warning: Could not extract native libs from {apk_path}: {e}", flush=True)


def unpack_partition_filesystem(partition_img_path: str, dest_dir: str) -> bool:
    """
    Universal Partition Extractor supporting EROFS (Android 15), EXT4 (Android 9-14), & Sparse images
    with real-time verbose logs.
    """
    os.makedirs(dest_dir, exist_ok=True)
    img_size_mb = os.path.getsize(partition_img_path) / (1024 * 1024)
    print(f"    [*] Inspecting Partition: {os.path.basename(partition_img_path)} ({img_size_mb:.1f} MB)...", flush=True)
    raw_img = partition_img_path

    # 1. Check for Android Sparse Magic: 0xED26FF3A
    try:
        with open(partition_img_path, "rb") as f:
            magic = f.read(4)
        if magic == b"\x3a\xff\x26\xed":
            print(f"        -> [Format: Android Sparse Image] Unpacking with simg2img...", flush=True)
            unsparse_img = f"{partition_img_path}_raw.img"
            res = subprocess.run(["simg2img", partition_img_path, unsparse_img], capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(unsparse_img):
                print(f"        [✓] Unsparsed successfully -> {os.path.getsize(unsparse_img)/1024/1024:.1f} MB", flush=True)
                raw_img = unsparse_img
            else:
                print(f"        [!] simg2img info: {res.stderr.strip()}", flush=True)
    except Exception as e:
        print(f"        [!] Sparse check exception: {e}", flush=True)

    # 2. Check header format (EROFS vs EXT4)
    is_erofs = False
    try:
        with open(raw_img, "rb") as f:
            hdr = f.read(2048)
            if len(hdr) >= 1028 and hdr[1024:1028] == b"\xe2\xe1\xf5\xe0":
                is_erofs = True
    except Exception:
        pass

    # 3. Method 1: fsck.erofs (for EROFS images)
    if is_erofs:
        print(f"        -> [Format: EROFS Filesystem] Extracting with fsck.erofs...", flush=True)
        try:
            res = subprocess.run(["fsck.erofs", f"--extract={dest_dir}", raw_img], capture_output=True, text=True)
            if res.returncode == 0 and any(os.scandir(dest_dir)):
                print(f"        [✓] Extracted EROFS partition successfully with fsck.erofs", flush=True)
                if raw_img != partition_img_path and os.path.exists(raw_img):
                    os.remove(raw_img)
                return True
            else:
                print(f"        [!] fsck.erofs info: {res.stderr.strip() or res.stdout.strip()}", flush=True)
        except Exception as e:
            print(f"        [!] fsck.erofs error: {e}", flush=True)

    # 4. Method 2: Linux Loop Mount (Supports EXT4 + EROFS natively)
    mount_point = f"/tmp/mnt_gapps_{os.getpid()}_{os.path.basename(partition_img_path)}"
    os.makedirs(mount_point, exist_ok=True)
    mounted = False
    try:
        mount_res = subprocess.run(["sudo", "mount", "-o", "loop,ro", raw_img, mount_point], capture_output=True, text=True)
        if mount_res.returncode == 0:
            mounted = True
            print(f"        -> [Mount] Loop-mounted partition ({'EROFS' if is_erofs else 'EXT4'}) successfully.", flush=True)
            copied_count = 0
            for root, dirs, files in os.walk(mount_point):
                for f in files:
                    rel_p = os.path.relpath(os.path.join(root, f), mount_point)
                    if is_genuine_google_file(f, rel_p):
                        full_p = os.path.join(root, f)
                        dst_p = os.path.join(dest_dir, rel_p)
                        os.makedirs(os.path.dirname(dst_p), exist_ok=True)
                        shutil.copy2(full_p, dst_p)
                        copied_count += 1
            print(f"        [✓] Collected {copied_count} genuine files via loop mount.", flush=True)
            return True
        else:
            print(f"        [!] Loop mount info: {mount_res.stderr.strip()}", flush=True)
    except Exception as e:
        print(f"        [!] Loop mount info: {e}", flush=True)
    finally:
        if mounted:
            subprocess.run(["sudo", "umount", "-f", mount_point], capture_output=True)
            shutil.rmtree(mount_point, ignore_errors=True)

    # 5. Method 3: 7z (for EXT4 partitions)
    print(f"        -> [7z] Extracting EXT4 partition with 7z...", flush=True)
    try:
        cmd = ["7z", "x", "-y", "-r", f"-o{dest_dir}", raw_img] + TARGET_APP_PATTERNS
        res = subprocess.run(cmd, capture_output=True, text=True)
        if any(os.scandir(dest_dir)):
            print(f"        [✓] Extracted EXT4 partition successfully with 7z", flush=True)
            if raw_img != partition_img_path and os.path.exists(raw_img):
                os.remove(raw_img)
            return True
        else:
            print(f"        [!] 7z extraction produced 0 matched files. Output: {res.stderr.strip() or res.stdout[-250:] if res.stdout else ''}", flush=True)
    except Exception as e:
        print(f"        [!] 7z extraction error: {e}", flush=True)

    if raw_img != partition_img_path and os.path.exists(raw_img):
        os.remove(raw_img)
        
    has_files = any(os.scandir(dest_dir))
    return has_files


def extract_partition_from_container(zip_path: str, work_dir: str, dest_extract_dir: str):
    """
    Extracts system, product, and system_ext partitions from Google SDK ZIP container
    using accelerated decompression and direct disk random access.
    """
    container_img_path = None
    has_7z = shutil.which("7z") is not None

    print("[*] Unpacking primary image from Google container...", flush=True)
    
    # Accelerated 7z extraction of *.img from zip container (2-3 seconds vs 60 seconds)
    if has_7z:
        print("    [⚡] Accelerating container decompression with multi-threaded 7-Zip...", flush=True)
        cmd = ["7z", "e", "-y", f"-o{work_dir}", zip_path, "*.img"]
        subprocess.run(cmd, capture_output=True, text=True)
        
        found_imgs = glob.glob(os.path.join(work_dir, "*.img"))
        if found_imgs:
            # Prioritize system.img if present
            sys_imgs = [img for img in found_imgs if "system" in os.path.basename(img).lower()]
            container_img_path = sys_imgs[0] if sys_imgs else found_imgs[0]
            print(f"    [✓] Container image unpacked to disk: {os.path.basename(container_img_path)} ({os.path.getsize(container_img_path)/1024/1024:.1f} MB)", flush=True)

    # Fallback to python extraction if 7z not available or failed
    if not container_img_path or not os.path.exists(container_img_path):
        with zipfile.ZipFile(zip_path, "r") as z:
            img_members = [f for f in z.namelist() if f.endswith("system.img")]
            if not img_members:
                img_members = [f for f in z.namelist() if f.endswith(".img")]
            if not img_members:
                raise RuntimeError(f"No .img partition found in Google container: {zip_path}")
                
            main_img_name = img_members[0]
            container_img_path = os.path.join(work_dir, os.path.basename(main_img_name))
            print(f"    [*] Extracting {main_img_name} to disk via stream...", flush=True)
            with z.open(main_img_name) as src, open(container_img_path, "wb") as dst:
                shutil.copyfileobj(src, dst, length=16*1024*1024)
            print(f"    [✓] Extracted: {container_img_path} ({os.path.getsize(container_img_path)/1024/1024:.1f} MB)", flush=True)

    # Parse Partition Table / Super / Direct image from the real file on disk
    try:
        with open(container_img_path, "rb") as img_f:
            img_f.seek(512)
            gpt_hdr = img_f.read(92)
            super_offset = 0
            has_super = False
            
            if gpt_hdr[:8] == b"EFI PART":
                img_f.seek(1024)
                gpt_entries = img_f.read(128 * 128)
                for i in range(128):
                    entry = gpt_entries[i*128:(i+1)*128]
                    if entry[:16] == b"\x00" * 16:
                        continue
                    first_lba, last_lba = struct.unpack("<QQ", entry[32:48])
                    name = entry[56:128].decode("utf-16le", errors="ignore").rstrip("\x00")
                    if name.lower() == "super":
                        super_offset = first_lba * 512
                        has_super = True
                        break

            temp_partition_img = os.path.join(work_dir, "target_partition.img")
            
            if has_super:
                print(f"[*] Super Partition detected at offset {super_offset}. Parsing dynamic partitions...", flush=True)
                img_f.seek(super_offset + 12288)
                hdr = img_f.read(128)
                magic, major, minor, hdr_size, hdr_sha, tbls_size, tbls_sha, p_off, p_num, p_sz, e_off, e_num, e_sz, g_off, g_num, g_sz, b_off, b_num, b_sz = struct.unpack("<IHHI32sI32sIIIIIIIIIIII", hdr[:128])
                tbls = img_f.read(tbls_size)
                
                available_parts = {}
                for i in range(p_num):
                    p_data = tbls[p_off + i*p_sz : p_off + (i+1)*p_sz]
                    part_name = p_data[:36].decode("utf-8", errors="ignore").rstrip("\x00").lower()
                    attr, f_ext, n_ext, grp = struct.unpack("<IIII", p_data[36:52])
                    available_parts[part_name] = (f_ext, n_ext)
                
                print(f"    -> Found dynamic partitions in Super table: {list(available_parts.keys())}", flush=True)
                targets_to_extract = [p for p in ["product", "system_ext", "system"] if p in available_parts]
                
                for part_choice in targets_to_extract:
                    f_ext, n_ext = available_parts[part_choice]
                    print(f"    -> Extracting '{part_choice}' dynamic partition ({n_ext} extents)...", flush=True)
                    
                    with open(temp_partition_img, "wb") as out_f:
                        for ei in range(f_ext, f_ext + n_ext):
                            e_data = tbls[e_off + ei*e_sz : e_off + (ei+1)*e_sz]
                            n_sec, t_type, t_data, t_src = struct.unpack("<QIIQ", e_data[:24])
                            ext_off = super_offset + t_data * 512
                            ext_bytes = n_sec * 512
                            
                            img_f.seek(ext_off)
                            rem = ext_bytes
                            while rem > 0:
                                chunk = img_f.read(min(rem, 16 * 1024 * 1024))
                                if not chunk:
                                    break
                                out_f.write(chunk)
                                rem -= len(chunk)
                                
                    unpack_partition_filesystem(temp_partition_img, dest_extract_dir)
                    if os.path.exists(temp_partition_img):
                        os.remove(temp_partition_img)
            else:
                # Direct sparse / EXT4 container (Android 9)
                print("[*] Direct system.img partition (No Super partition). Unpacking filesystem...", flush=True)
                unpack_partition_filesystem(container_img_path, dest_extract_dir)
    finally:
        # Free up disk space immediately
        if container_img_path and os.path.exists(container_img_path):
            os.remove(container_img_path)
