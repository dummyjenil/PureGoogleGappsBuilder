"""
Flashable ZIP Packager and Filesystem Structuring Module for PureGoogleGappsBuilder.
Formats APKs, libraries, permissions, addon.d, overlays, and Recovery installer metadata
to match MindTheGapps standard across Android 9.0.0 to 15.0.0.
"""

import os
import sys
import shutil
import subprocess
import zipfile
import datetime
import urllib.request
import json
import tempfile
from .constants import (
    BRANCH_MAP,
    SDK_MAP,
    ARCH_TO_TOYBOX,
    ADDOND_HEAD,
    ADDOND_TAIL,
)

GITLAB_RAW_BASE = "https://gitlab.com/MindTheGapps/vendor_gapps/-/raw"
GITLAB_API_BASE = "https://gitlab.com/api/v4/projects/MindTheGapps%2Fvendor_gapps/repository"


def fetch_url_bytes(url: str, timeout: int = 15) -> bytes:
    """Fetch raw bytes from a URL with browser User-Agent and timeout"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (PureGappsBuilder/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_target_file_list_for_branch(branch: str, arch: str) -> dict:
    """
    Fetches proprietary file definitions from MindTheGapps branch dynamically.
    Returns a dict mapping destination paths -> source patterns.
    """
    prop_files = [
        "proprietary-files-common.txt",
        "proprietary-files-common-nongrouper.txt",
        f"proprietary-files-{arch}.txt",
        f"proprietary-files-{arch}-nongrouper.txt",
    ]
    
    # Alternate arch names fallback (e.g. x86_64 vs x86)
    if arch == "x86_64":
        prop_files.append("proprietary-files-x86.txt")
    elif arch in ["arm64", "arm64-v8a"]:
        prop_files.append("proprietary-files-arm.txt")

    file_mappings = {}

    for pfile in prop_files:
        url = f"{GITLAB_RAW_BASE}/{branch}/{pfile}"
        try:
            data = fetch_url_bytes(url).decode("utf-8", errors="ignore")
            for line in data.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Strip hash
                if "|" in line:
                    line = line.split("|")[0].strip()
                # Strip flags
                if ";" in line:
                    line = line.split(";")[0].strip()
                # Check remap (src:dst)
                if ":" in line:
                    src, dst = line.split(":")
                    file_mappings[dst.strip()] = src.strip()
                else:
                    file_mappings[line] = line
        except Exception:
            pass

    return file_mappings


def find_android_jar(sdk_version: int):
    """Locates android.jar fast without expensive directory globbing"""
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "/usr/local/lib/android/sdk"
    user_sdk = os.path.expanduser("~/Android/Sdk")
    
    candidates = [
        f"{android_home}/platforms/android-{sdk_version}/android.jar",
        f"{android_home}/platforms/android-35/android.jar",
        f"{android_home}/platforms/android-34/android.jar",
        f"{android_home}/platforms/android-33/android.jar",
        f"{user_sdk}/platforms/android-{sdk_version}/android.jar",
        f"{user_sdk}/platforms/android-35/android.jar",
        f"{user_sdk}/platforms/android-34/android.jar",
        f"/usr/local/lib/android/sdk/platforms/android-{sdk_version}/android.jar",
        f"/usr/local/lib/android/sdk/platforms/android-35/android.jar",
        f"/usr/local/lib/android/sdk/platforms/android-34/android.jar",
        f"/usr/lib/android-sdk/platforms/android-{sdk_version}/android.jar",
        f"/usr/lib/android-sdk/platforms/android-34/android.jar"
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def find_aapt_binary():
    """Finds aapt binary from PATH or Android build-tools"""
    w = shutil.which("aapt")
    if w:
        return w
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "/usr/local/lib/android/sdk"
    btd = os.path.join(android_home, "build-tools")
    if os.path.isdir(btd):
        for ver in sorted(os.listdir(btd), reverse=True):
            cand = os.path.join(btd, ver, "aapt")
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def compile_or_fetch_overlays(branch: str, sdk_version: int, target_overlay_dir: str):
    """
    Compiles Runtime Resource Overlays (RROs) for Android 12+ using aapt
    """
    if sdk_version < 31:
        return  # Overlays are only present in Android 12 (API 31)+

    print(f"[*] Building Runtime Resource Overlays (RROs) for branch '{branch}' (SDK {sdk_version})...")
    os.makedirs(target_overlay_dir, exist_ok=True)

    # Check which overlays exist in the branch
    tree_url = f"{GITLAB_API_BASE}/tree?ref={branch}&path=overlay&per_page=100"
    overlays_to_build = []
    try:
        data = json.loads(fetch_url_bytes(tree_url, timeout=10).decode("utf-8"))
        overlays_to_build = [x["name"] for x in data if x.get("type") == "tree"]
    except Exception:
        # Fallback standard overlays for Android 12+
        overlays_to_build = ["GmsOverlay", "GmsSettingsProviderOverlay"]
        if sdk_version >= 33:
            overlays_to_build.extend(["GmsSettingsOverlay", "GmsSetupWizardOverlay"])

    android_jar = find_android_jar(sdk_version)
    aapt_bin = find_aapt_binary()

    if not aapt_bin or not android_jar:
        print(f"    [!] Warning: aapt ({aapt_bin}) or android.jar ({android_jar}) not found. Skipping overlay compilation.")
        return

    for overlay_name in overlays_to_build:
        out_apk = os.path.join(target_overlay_dir, f"{overlay_name}.apk")
        if os.path.exists(out_apk):
            continue

        base_overlay_url = f"{GITLAB_RAW_BASE}/{branch}/overlay/{overlay_name}"
        try:
            with tempfile.TemporaryDirectory() as td:
                manifest_data = fetch_url_bytes(f"{base_overlay_url}/AndroidManifest.xml", timeout=10)
                manifest_file = os.path.join(td, "AndroidManifest.xml")
                with open(manifest_file, "wb") as f:
                    f.write(manifest_data)

                res_val_dir = os.path.join(td, "res", "values")
                os.makedirs(res_val_dir, exist_ok=True)

                # List value XMLs
                vals_tree_url = f"{GITLAB_API_BASE}/tree?ref={branch}&path=overlay/{overlay_name}/res/values"
                vdata = json.loads(fetch_url_bytes(vals_tree_url, timeout=10).decode("utf-8"))
                for vitem in vdata:
                    vname = vitem["name"]
                    vbytes = fetch_url_bytes(f"{base_overlay_url}/res/values/{vname}", timeout=10)
                    with open(os.path.join(res_val_dir, vname), "wb") as vf:
                        vf.write(vbytes)

                cmd = [aapt_bin, "package", "-M", manifest_file, "-S", os.path.join(td, "res"), "-I", android_jar, "-F", out_apk]
                subprocess.run(cmd, check=True, capture_output=True, timeout=15)
                print(f"    [✓] Compiled Overlay: {overlay_name}.apk ({os.path.getsize(out_apk)} bytes)")
        except Exception as e:
            print(f"    [!] Warning: Failed to build overlay {overlay_name}: {e}")


def structure_gapps_hierarchy(extracted_dir: str, target_pkg_dir: str, android_version: str, arch: str):
    """
    Structures genuine GApps files into MindTheGapps-identical hierarchy.
    Strictly follows MindTheGapps component definitions to avoid bloat and duplicate APKs.
    """
    print(f"[*] Structuring MindTheGapps hierarchy for Android {android_version} ({arch})...")
    os.makedirs(target_pkg_dir, exist_ok=True)

    system_dir = os.path.join(target_pkg_dir, "system")
    os.makedirs(system_dir, exist_ok=True)

    branch = BRANCH_MAP.get(android_version, "upsilon")
    sdk_version = SDK_MAP.get(android_version, 33)

    # 1. Fetch expected file list from MindTheGapps branch definitions
    target_mappings = fetch_target_file_list_for_branch(branch, arch)
    print(f"    [✓] Loaded {len(target_mappings)} target file definitions from branch '{branch}'.")

    # Index all extracted files by relative path and by base filename
    extracted_files_map = {}
    extracted_basename_map = {}
    for root, dirs, files in os.walk(extracted_dir):
        for f in files:
            full_p = os.path.join(root, f)
            rel_p = os.path.relpath(full_p, extracted_dir).replace("\\", "/")
            extracted_files_map[rel_p.lower()] = full_p
            base_key = f.lower()
            if base_key not in extracted_basename_map:
                extracted_basename_map[base_key] = []
            extracted_basename_map[base_key].append(full_p)

    included_files = []

    # Alias mapping for prebuilt names in Google images
    ALIASES = {
        "gmscore.apk": ["prebuiltgmscore.apk", "gmscore.apk"],
        "prebuiltgmscore.apk": ["gmscore.apk", "prebuiltgmscore.apk"],
        "googlerestore.apk": ["googlerestoreprebuilt.apk", "googlerestore.apk"],
        "googlerestoreprebuilt.apk": ["googlerestore.apk", "googlerestoreprebuilt.apk"],
        "setupwizard.apk": ["setupwizardprebuilt.apk", "setupwizard.apk"],
        "setupwizardprebuilt.apk": ["setupwizard.apk", "setupwizardprebuilt.apk"],
        "androidautostub.apk": ["androidautostubprebuilt.apk", "androidautostub.apk"],
        "androidautostubprebuilt.apk": ["androidautostub.apk", "androidautostubprebuilt.apk"],
        "googlepartnersetup.apk": ["partnersetupprebuilt.apk", "googlepartnersetup.apk"],
        "partnersetupprebuilt.apk": ["googlepartnersetup.apk", "partnersetupprebuilt.apk"],
        "wellbeing.apk": ["wellbeingprebuilt.apk", "wellbeing.apk"],
        "wellbeingprebuilt.apk": ["wellbeing.apk", "wellbeingprebuilt.apk"],
    }

    # 2. Match and copy files according to MindTheGapps targets (strictly no duplicates)
    for dst_rel, src_rel in target_mappings.items():
        dst_path = os.path.join(system_dir, dst_rel)
        matched_src = None

        # Check exact relative path
        if src_rel.lower() in extracted_files_map:
            matched_src = extracted_files_map[src_rel.lower()]
        elif dst_rel.lower() in extracted_files_map:
            matched_src = extracted_files_map[dst_rel.lower()]
        else:
            base_fname = os.path.basename(src_rel).lower()
            candidates = extracted_basename_map.get(base_fname, [])
            
            # Check aliases if direct candidate not found
            if not candidates and base_fname in ALIASES:
                for alias_name in ALIASES[base_fname]:
                    if alias_name in extracted_basename_map:
                        candidates = extracted_basename_map[alias_name]
                        break

            if candidates:
                part_hint = dst_rel.split("/")[0].lower() if "/" in dst_rel else ""
                preferred = [c for c in candidates if part_hint in c.lower()]
                matched_src = preferred[0] if preferred else candidates[0]

        if matched_src and os.path.exists(matched_src):
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(matched_src, dst_path)
            included_files.append(dst_rel)
            print(f"    [+] Included: {dst_rel} ({os.path.getsize(dst_path)/1024:.1f} KB)")

    # 3. Compile / fetch RRO overlays
    overlay_dir = os.path.join(system_dir, "product", "overlay")
    compile_or_fetch_overlays(branch, sdk_version, overlay_dir)

    # 4. Download architecture-specific toybox binary
    toybox_name = ARCH_TO_TOYBOX.get(arch, "toybox-x86_64")
    toybox_url = f"{GITLAB_RAW_BASE}/{branch}/{toybox_name}"
    toybox_dest = os.path.join(target_pkg_dir, "toybox")
    print(f"[*] Downloading {toybox_name} for Recovery installation environment...")
    try:
        tbytes = fetch_url_bytes(toybox_url, timeout=15)
        with open(toybox_dest, "wb") as f:
            f.write(tbytes)
        os.chmod(toybox_dest, 0o755)
        print(f"    [✓] Saved toybox: {os.path.getsize(toybox_dest)/1024:.1f} KB")
    except Exception as e:
        print(f"    [!] Warning: Could not download toybox: {e}")

    # 5. Add Recovery Installer & Addon.d Survival Scripts
    print("[*] Setting up update-binary and addon.d scripts...")
    meta_inf_dir = os.path.join(target_pkg_dir, "META-INF", "com", "google", "android")
    os.makedirs(meta_inf_dir, exist_ok=True)

    update_bin_dest = os.path.join(meta_inf_dir, "update-binary")
    update_bin_url = f"{GITLAB_RAW_BASE}/{branch}/build/meta/com/google/android/update-binary"
    try:
        ubytes = fetch_url_bytes(update_bin_url, timeout=15)
        with open(update_bin_dest, "wb") as f:
            f.write(ubytes)
        os.chmod(update_bin_dest, 0o755)
        print("    [✓] Fetched official MindTheGapps update-binary")
    except Exception:
        # Fallback built-in update-binary
        with open(update_bin_dest, "w", newline="\n") as f:
            f.write("#!/sbin/sh\n# Fallback\n")
        os.chmod(update_bin_dest, 0o755)

    updater_script_dest = os.path.join(meta_inf_dir, "updater-script")
    with open(updater_script_dest, "w", newline="\n") as f:
        f.write("# Dummy updater-script for TWRP\n")

    # Addon.d survival script templates
    addon_dir = os.path.join(system_dir, "addon.d")
    os.makedirs(addon_dir, exist_ok=True)
    with open(os.path.join(addon_dir, "addond_head"), "w", newline="\n") as f:
        f.write(ADDOND_HEAD.strip() + "\n")
    with open(os.path.join(addon_dir, "addond_tail"), "w", newline="\n") as f:
        f.write(ADDOND_TAIL.strip() + "\n")

    # Build prop info (exact MTG format)
    build_prop_path = os.path.join(target_pkg_dir, "build.prop")
    with open(build_prop_path, "w", newline="\n") as f:
        f.write(f"arch={arch}\n")
        f.write(f"version={sdk_version}\n")
        f.write(f"version_nice={android_version}\n")

    return included_files


def create_flashable_zip(source_dir: str, output_zip_path: str):
    """
    Packs directory into deterministic Recovery-flashable ZIP and signs with AOSP testkeys.
    """
    print(f"[*] Packaging and Signing Recovery Flashable ZIP: {os.path.basename(output_zip_path)}...")
    output_zip_path = os.path.abspath(output_zip_path)
    if os.path.exists(output_zip_path):
        os.remove(output_zip_path)

    # Use standard fixed date for reproducibility (2009-01-01)
    deterministic_datetime = (2009, 1, 1, 0, 0, 0)

    # 1. Create standard Deflate ZIP
    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in sorted(files):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_dir).replace("\\", "/")
                
                zinfo = zipfile.ZipInfo(filename=rel_path, date_time=deterministic_datetime)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                if file in ["update-binary", "toybox", "70-gapps.sh", "30-gapps.sh"] or file.endswith(".sh"):
                    zinfo.external_attr = 0o755 << 16
                else:
                    zinfo.external_attr = 0o644 << 16

                with open(full_path, "rb") as f_in:
                    zipf.writestr(zinfo, f_in.read())

    # 2. Sign with standard AOSP testkey using apksigner
    has_apksigner = shutil.which("apksigner") is not None
    if has_apksigner:
        try:
            with tempfile.TemporaryDirectory() as td:
                pk8_file = os.path.join(td, "testkey.pk8")
                pem_file = os.path.join(td, "testkey.x509.pem")

                with open(pk8_file, "wb") as f:
                    f.write(fetch_url_bytes(f"{GITLAB_RAW_BASE}/upsilon/build/sign/testkey.pk8", timeout=10))
                with open(pem_file, "wb") as f:
                    f.write(fetch_url_bytes(f"{GITLAB_RAW_BASE}/upsilon/build/sign/testkey.x509.pem", timeout=10))

                cmd = ["apksigner", "sign", "--key", pk8_file, "--cert", pem_file, "--min-sdk-version", "28", output_zip_path]
                subprocess.run(cmd, check=True, capture_output=True, timeout=30)
                print("    [✓] ZIP signed successfully with AOSP testkey (apksigner)")
        except Exception as e:
            print(f"    [!] Warning: Failed to sign ZIP: {e}")
