"""
Flashable ZIP Packager and Filesystem Structuring Module for PureGoogleGappsBuilder.
Formats APKs, libraries, permissions, addon.d, and Recovery installer metadata.
"""

import os
import sys
import shutil
import subprocess
import zipfile
import datetime
from .constants import PRIV_APPS_LIST, UPDATE_BINARY_SCRIPT, ADDOND_HEAD, ADDOND_TAIL
from .extractor import is_genuine_google_file, extract_native_libs_from_apk


def structure_gapps_hierarchy(extracted_dir: str, target_pkg_dir: str, android_version: str, arch: str):
    """
    Structures genuine GApps files into Android recovery flashable hierarchy.
    """
    print(f"[*] Structuring GApps filesystem hierarchy for Android {android_version} ({arch})...")
    os.makedirs(target_pkg_dir, exist_ok=True)
    
    system_dir = os.path.join(target_pkg_dir, "system")
    os.makedirs(system_dir, exist_ok=True)
    
    included_apks = []
    
    for root, dirs, files in os.walk(extracted_dir):
        for f in files:
            rel_p = os.path.relpath(os.path.join(root, f), extracted_dir)
            if not is_genuine_google_file(f, rel_p):
                continue
                
            src_file = os.path.join(root, f)
            apk_name = os.path.splitext(f)[0]
            
            # Destination mapping
            if f.endswith(".apk"):
                is_priv = any(p.lower() == apk_name.lower() or p.lower() in apk_name.lower() for p in PRIV_APPS_LIST)
                
                # Check partition origin
                if "product" in rel_p.lower():
                    dest_sub = os.path.join(system_dir, "product", "priv-app" if is_priv else "app", apk_name)
                elif "system_ext" in rel_p.lower():
                    dest_sub = os.path.join(system_dir, "system_ext", "priv-app" if is_priv else "app", apk_name)
                else:
                    dest_sub = os.path.join(system_dir, "priv-app" if is_priv else "app", apk_name)
                    
                os.makedirs(dest_sub, exist_ok=True)
                dest_apk = os.path.join(dest_sub, f)
                shutil.copy2(src_file, dest_apk)
                
                dest_rel = os.path.relpath(dest_apk, target_pkg_dir)
                print(f"    [+] Included APK: {f} -> {dest_rel}")
                included_apks.append(f)
                
                # Extract native libraries (.so)
                extract_native_libs_from_apk(dest_apk, arch)
                
            elif f.endswith(".xml"):
                if "permissions" in rel_p.lower():
                    dest_perm = os.path.join(system_dir, "etc", "permissions")
                    os.makedirs(dest_perm, exist_ok=True)
                    shutil.copy2(src_file, os.path.join(dest_perm, f))
                elif "sysconfig" in rel_p.lower():
                    dest_sys = os.path.join(system_dir, "etc", "sysconfig")
                    os.makedirs(dest_sys, exist_ok=True)
                    shutil.copy2(src_file, os.path.join(dest_sys, f))
                elif "default-permissions" in rel_p.lower():
                    dest_dp = os.path.join(system_dir, "etc", "default-permissions")
                    os.makedirs(dest_dp, exist_ok=True)
                    shutil.copy2(src_file, os.path.join(dest_dp, f))
                    
            elif f.endswith(".jar"):
                dest_fw = os.path.join(system_dir, "framework")
                os.makedirs(dest_fw, exist_ok=True)
                shutil.copy2(src_file, os.path.join(dest_fw, f))

    # Add Recovery Installer & Addon.d Survival Script
    print("[*] Adding TWRP/Recovery installer & addon.d survival script...")
    
    # 1. META-INF installer
    meta_inf_dir = os.path.join(target_pkg_dir, "META-INF", "com", "google", "android")
    os.makedirs(meta_inf_dir, exist_ok=True)
    
    update_bin = os.path.join(meta_inf_dir, "update-binary")
    with open(update_bin, "w", newline="\n") as f:
        f.write(UPDATE_BINARY_SCRIPT.strip() + "\n")
    os.chmod(update_bin, 0o755)
    
    updater_script = os.path.join(meta_inf_dir, "updater-script")
    with open(updater_script, "w", newline="\n") as f:
        f.write("# Dummy updater-script for TWRP\n")
        
    # 2. Addon.d survival script templates
    addon_dir = os.path.join(system_dir, "addon.d")
    os.makedirs(addon_dir, exist_ok=True)
    with open(os.path.join(addon_dir, "addond_head"), "w", newline="\n") as f:
        f.write(ADDOND_HEAD.strip() + "\n")
    with open(os.path.join(addon_dir, "addond_tail"), "w", newline="\n") as f:
        f.write(ADDOND_TAIL.strip() + "\n")
        
    # 3. Build prop info
    build_prop_path = os.path.join(target_pkg_dir, "build.prop")
    with open(build_prop_path, "w", newline="\n") as f:
        f.write(f"ro.gapps.version={android_version}\n")
        f.write(f"ro.gapps.arch={arch}\n")
        f.write(f"ro.gapps.type=pure_google\n")
        f.write(f"ro.gapps.date={datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')}\n")
        
    return included_apks


def create_flashable_zip(source_dir: str, output_zip_path: str):
    """
    Packs directory into maximum Deflate compressed Recovery-flashable ZIP.
    """
    print(f"[*] Packaging Recovery Flashable ZIP: {os.path.basename(output_zip_path)}...")
    if os.path.exists(output_zip_path):
        os.remove(output_zip_path)
        
    has_7z = shutil.which("7z") is not None
    
    if has_7z:
        print("    [⚡] Using 7-Zip Fast Deflate Compression (Multi-threaded, 100% Recovery Compatible)...", flush=True)
        # -mm=Deflate: Standard ZIP deflate (TWRP compatible)
        # -mx=5: Fast standard compression (2-3 seconds for ~300MB)
        # -mmt=on: All CPU cores in parallel
        cmd = [
            "7z", "a", "-tzip",
            "-mm=Deflate",
            "-mx=5",
            "-mmt=on",
            os.path.abspath(output_zip_path),
            "."
        ]
        res = subprocess.run(cmd, cwd=source_dir, capture_output=True, text=True)
        if res.returncode == 0:
            return
        else:
            print(f"    [!] 7z error: {res.stderr.strip()}. Falling back to Python zipfile...", flush=True)

    # Fallback Python zipfile with maximum standard Deflate level 9
    print("    [*] Packing with standard Python zipfile (level 9)...")
    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_dir)
                zinfo = zipfile.ZipInfo.from_file(full_path, rel_path)
                if file in ["update-binary", "70-gapps.sh"] or file.endswith(".sh"):
                    zinfo.external_attr = 0o755 << 16
                else:
                    zinfo.external_attr = 0o644 << 16
                with open(full_path, "rb") as f_in:
                    zipf.writestr(zinfo, f_in.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

