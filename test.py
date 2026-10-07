#!/usr/bin/env python3
"""
Lightweight Pure Google GApps Builder & Tester
Extracts genuine GApps across Android 9 to 15 (supporting EROFS, EXT4, Android Sparse & Super Partitions).
Generates clean, genuine Recovery Flashable ZIPs (TWRP / OrangeFox / Lineage Recovery).
"""

import os
import sys
import shutil
import argparse
import check_updates
from core.downloader import download_file
from core.extractor import extract_partition_from_container
from core.packager import structure_gapps_hierarchy, create_flashable_zip


def build_gapps_lightweight(zip_path: str, android_version: str = "13.0.0", arch: str = "arm64", out_dir: str = "."):
    """
    Extracts and packages GApps from a local container zip file.
    """
    print("\n" + "=" * 75)
    print(f"🚀 BUILDING PURE GAPPS: GoogleGapps-{android_version}-{arch}.zip")
    print("=" * 75)

    work_dir = f"/tmp/test_pure_gapps_{android_version}_{arch}"
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir, exist_ok=True)

    extracted_raw_dir = os.path.join(work_dir, "extracted_raw")
    gapps_pkg_dir = os.path.join(work_dir, "gapps_package")

    try:
        # Step 1: Extract partition images
        print(f"[*] Step 1: Extracting partitions from container: {zip_path}")
        extract_partition_from_container(zip_path, work_dir, extracted_raw_dir)

        # Step 2: Structure GApps filesystem hierarchy & native libs
        print(f"[*] Step 2: Structuring genuine GApps hierarchy...")
        included_apks = structure_gapps_hierarchy(extracted_raw_dir, gapps_pkg_dir, android_version, arch)

        # Step 3: Verify APK collection
        apk_count = len(included_apks)
        print(f"[*] Step 3: Verification - Collected {apk_count} genuine Google APKs.")
        if apk_count == 0:
            raise RuntimeError(f"CRITICAL ERROR: 0 APKs collected for Android {android_version} ({arch})!")

        # Step 4: Create final ZIP package
        os.makedirs(out_dir, exist_ok=True)
        final_zip_name = f"GoogleGapps-{android_version}-{arch}.zip"
        final_zip_path = os.path.join(out_dir, final_zip_name)
        
        print(f"[*] Step 4: Generating Recovery Flashable ZIP: {final_zip_name}...")
        create_flashable_zip(gapps_pkg_dir, final_zip_path)

        pkg_size_mb = os.path.getsize(final_zip_path) / (1024 * 1024)
        print("\n" + "=" * 75)
        print(f"🎉 SUCCESS! Genuine Flashable GApps Package Created:")
        print(f"   File Name : {final_zip_name}")
        print(f"   Full Path : {os.path.abspath(final_zip_path)}")
        print(f"   File Size : {pkg_size_mb:.2f} MB")
        print(f"   Total APKs: {apk_count} genuine Google Apps")
        print("=" * 75 + "\n")
        return final_zip_path

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Lightweight Google GApps Downloader & Builder")
    parser.add_argument("-v", "--version", help="Android version (e.g. 9.0.0, 10.0.0, 11.0.0, 12.0.0, 13.0.0, 14.0.0, 15.0.0)")
    parser.add_argument("-a", "--arch", default="arm64", choices=["arm64", "x86_64", "arm"], help="Target Architecture (default: arm64)")
    parser.add_argument("-f", "--file", dest="existing_file", help="Path to already downloaded ZIP to build from")
    parser.add_argument("-b", "--build", action="store_true", help="Extract and build the final release ZIP package")
    parser.add_argument("-o", "--output", default=".", help="Output directory for generated GApps package")
    parser.add_argument("-l", "--list", action="store_true", help="List all available Google Android versions and URLs")
    args = parser.parse_args()

    if args.existing_file:
        if not os.path.exists(args.existing_file):
            print(f"[!] Error: File not found at '{args.existing_file}'")
            sys.exit(1)
        ver = args.version if args.version else "13.0.0"
        build_gapps_lightweight(args.existing_file, android_version=ver, arch=args.arch, out_dir=args.output)
        return

    print("[*] Querying official Google repositories...")
    latest_images = check_updates.fetch_google_repository_metadata()
    
    if args.list:
        print("\nAvailable Android Versions:")
        for k, v in sorted(latest_images.items()):
            print(f"  • Android {v['android_version']:<7} [{v['arch']:<6}] -> {v['url']}")
        return

    android_version = args.version
    if not android_version:
        versions_available = sorted(list(set(v['android_version'] for v in latest_images.values())))
        print("\nAvailable Versions:")
        for idx, ver in enumerate(versions_available, 1):
            print(f"  [{idx}] Android {ver}")
            
        try:
            choice = input(f"\nEnter Android Version number (e.g. {versions_available[-1]}): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(versions_available):
                android_version = versions_available[int(choice) - 1]
            else:
                android_version = choice
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)

    if not android_version.endswith(".0"):
        if android_version.count(".") == 0:
            android_version = f"{android_version}.0.0"
        elif android_version.count(".") == 1:
            android_version = f"{android_version}.0"

    arch = args.arch
    target_key = f"{android_version}-{arch}"
    
    target_data = latest_images.get(target_key)
    if not target_data:
        print(f"[!] Error: Target '{target_key}' not found in Google repository.")
        sys.exit(1)

    url = target_data["url"]
    filename = os.path.basename(url)
    dest_path = os.path.join(os.getcwd(), filename)

    if not os.path.exists(dest_path):
        print(f"[*] Downloading {filename} via Turbo Downloader...")
        download_file(url, dest_path)
    else:
        file_size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        print(f"\n[✓] Using existing downloaded image: {filename} ({file_size_mb:.2f} MB)")

    build_gapps_lightweight(dest_path, android_version=android_version, arch=arch, out_dir=args.output)


if __name__ == "__main__":
    main()
