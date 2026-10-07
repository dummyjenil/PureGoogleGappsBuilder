"""
Partition and File Extraction Module for PureGoogleGappsBuilder
Handles GPT Dynamic Super Partitions, EROFS, EXT4, Sparse Images, and Genuine Google Component Detection.
"""

import os
import sys
import glob
import struct
import shutil
import subprocess
import zipfile
from core.constants import TARGET_APP_PATTERNS, EXCLUDED_AOSP_APPS


def is_genuine_google_file(filename: str, rel_path: str) -> bool:
    """Filter out AOSP OS system apps, emulator overlays, and retain genuine Google GApps"""
    fl = filename.lower()
    rl = rel_path.lower()
    
    # Exclude emulator test overlays, ranchu, goldfish, base AOSP OS apps
    if "emulator" in fl or "ranchu" in fl or "cutout" in fl or "goldfish" in fl or "wallpaper" in fl:
        return False
    if fl in EXCLUDED_AOSP_APPS:
        return False
        
    # Match LatinIME Google gesture library
    if "libjni_latinimegoogle" in fl and fl.endswith(".so"):
        return True
        
    # Match genuine Google apps / services
    if fl.endswith(".apk"):
        return any(pat.lower().strip("*") in fl for pat in TARGET_APP_PATTERNS if not pat.startswith("*permissions") and not pat.startswith("*sysconfig") and not pat.startswith("*framework")) or "gms" in fl or "phonesky" in fl or "wellbeing" in fl or "talkback" in fl or "dialer" in fl
        
    if fl.endswith(".xml"):
        return ("google" in fl or "gms" in fl or "maps" in fl or "widevine" in fl or "dialer" in fl or "mtg" in fl or "d2d" in fl) and ("permissions" in rl or "sysconfig" in rl or "default-permissions" in rl)
        
    if fl.endswith(".jar"):
        return ("google" in fl or "maps" in fl or "media.effects" in fl or "dialer" in fl) and "framework" in rl
        
    if fl.endswith(".der"):
        return "gms" in fl or "fsverity" in rl
        
    if fl == "gapps.rc":
        return True
        
    return False


def unpack_partition_filesystem(partition_img_path: str, dest_dir: str) -> bool:
    """
    Universal Partition Extractor supporting EROFS (Android 15), EXT4 (Android 9-14), & Sparse images
    using 100% non-root user-space tools (7z and fsck.erofs).
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

    # 4. Method 2: 7z extraction (for EXT4 partitions - fast and non-root)
    print(f"        -> [7z] Extracting EXT4 partition with 7z...", flush=True)
    try:
        cmd = ["7z", "x", "-y", "-r", f"-o{dest_dir}", raw_img]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if any(os.scandir(dest_dir)):
            print(f"        [✓] Extracted EXT4 partition successfully with 7z", flush=True)
            if raw_img != partition_img_path and os.path.exists(raw_img):
                os.remove(raw_img)
            return True
        else:
            print(f"        [!] 7z extraction info: {res.stderr.strip() or (res.stdout[-250:] if res.stdout else '')}", flush=True)
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
    
    # Accelerated 7z extraction of *.img from zip container
    if has_7z:
        print("    [⚡] Accelerating container decompression with multi-threaded 7-Zip...", flush=True)
        cmd = ["7z", "e", "-y", "-r", f"-o{work_dir}", zip_path, "*.img"]
        subprocess.run(cmd, capture_output=True, text=True)
        
        found_imgs = glob.glob(os.path.join(work_dir, "*.img"))
        if found_imgs:
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
                                
                    target_part_dir = os.path.join(dest_extract_dir, part_choice)
                    unpack_partition_filesystem(temp_partition_img, target_part_dir)
                    if os.path.exists(temp_partition_img):
                        os.remove(temp_partition_img)
            else:
                # Direct sparse / EXT4 container (Android 9)
                print("[*] Direct system.img partition (No Super partition). Unpacking filesystem...", flush=True)
                unpack_partition_filesystem(container_img_path, os.path.join(dest_extract_dir, "system"))
    finally:
        if container_img_path and os.path.exists(container_img_path):
            os.remove(container_img_path)
