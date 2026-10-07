#!/usr/bin/env python3
"""
Pure Google GApps Extractor & Universal Flashable Package Generator
Extracts 100% genuine Google Apps directly from Google's official Android SDK Emulator images.
Generates TWRP / Recovery Flashable ZIPs with OTA/addon.d survival support and correct ABI mappings.
Universal support for EROFS (Android 15), EXT4 (Android 9-14), Sparse Images, & Dynamic Super Partitions.
"""

import os
import sys
import shutil
import argparse
from core.downloader import download_file
from core.extractor import extract_partition_from_container
from core.packager import structure_gapps_hierarchy, create_flashable_zip


def build_pure_gapps(android_version: str, arch: str, abi: str, url: str, out_dir: str = "out"):
    """
    Builds a flashable GApps package from official Google SDK image.
    """
    print(f"\n{'='*75}")
    print(f"🚀 BUILDING PURE GAPPS: GoogleGapps-{android_version}-{arch}.zip")
    print(f"{'='*75}")
    
    # Use /tmp on host/runner for large disk space
    work_dir = f"/tmp/pure_gapps_{android_version}_{arch}"
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir, exist_ok=True)
    
    downloaded_zip = os.path.join(work_dir, "google_sysimg.zip")
    extracted_raw_dir = os.path.join(work_dir, "extracted_raw")
    gapps_pkg_dir = os.path.join(work_dir, "gapps_package")

    try:
        # Step 1: Download Google Official System Image Container
        print(f"[*] Step 1: Downloading official Google image from:\n    {url}")
        download_file(url, downloaded_zip)

        # Step 2: Unpack partitions (EROFS / EXT4 / Super GPT)
        print(f"[*] Step 2: Extracting system and product partitions from container...")
        extract_partition_from_container(downloaded_zip, work_dir, extracted_raw_dir)

        # Step 3: Structure GApps Filesystem, extract native libs, and add installer
        print(f"[*] Step 3: Structuring genuine GApps and generating installer scripts...")
        included_apks = structure_gapps_hierarchy(extracted_raw_dir, gapps_pkg_dir, android_version, arch)

        # Step 4: Verification Gate
        apk_count = len(included_apks)
        print(f"[*] Step 4: Verification - Successfully collected {apk_count} genuine Google APKs.")
        if apk_count == 0:
            raise RuntimeError(f"CRITICAL ERROR: 0 APKs collected for Android {android_version} ({arch})!")

        # Step 5: Final Package Creation with Ultra Deflate
        os.makedirs(out_dir, exist_ok=True)
        final_zip_name = f"GoogleGapps-{android_version}-{arch}.zip"
        final_zip_path = os.path.join(out_dir, final_zip_name)
        
        print(f"[*] Step 5: Creating final Flashable GApps package: {final_zip_name}...")
        create_flashable_zip(gapps_pkg_dir, final_zip_path)
        
        package_size_mb = os.path.getsize(final_zip_path) / (1024 * 1024)
        print(f"\n{'='*75}")
        print(f"🎉 SUCCESS! Genuine Flashable GApps Package Created:")
        print(f"   File Name : {final_zip_name}")
        print(f"   Full Path : {os.path.abspath(final_zip_path)}")
        print(f"   File Size : {package_size_mb:.2f} MB")
        print(f"   Total APKs: {apk_count} genuine Google Apps")
        print(f"{'='*75}\n")
        
        if package_size_mb < 5.0:
            raise RuntimeError(f"CRITICAL ERROR: Generated package size is unusually small ({package_size_mb:.2f} MB)!")
            
        return final_zip_path

    finally:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Extract 100% Pure GApps from Google Official Images")
    parser.add_argument("--android", required=True, help="Android Version (e.g. 13.0.0)")
    parser.add_argument("--arch", required=True, help="Architecture (e.g. x86_64, arm64)")
    parser.add_argument("--abi", default="x86_64", help="Target ABI (e.g. x86_64, arm64-v8a)")
    parser.add_argument("--url", required=True, help="Official dl.google.com image download URL")
    parser.add_argument("--out-dir", default="out", help="Output directory for generated packages")
    args = parser.parse_args()

    build_pure_gapps(args.android, args.arch, args.abi, args.url, args.out_dir)


if __name__ == "__main__":
    main()
