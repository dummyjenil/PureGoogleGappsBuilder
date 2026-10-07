#!/usr/bin/env python3
"""
High-Performance Multi-threaded Remote GApps ZIP Analyzer with tqdm.
Scans all 12 releases and 100+ ZIP packages from s1204IT/MindTheGappsBuilder in seconds.
Uses concurrent single-shot HTTP Range requests to inspect ZIP Central Directories in memory.
"""

import os
import sys
import json
import struct
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


RELEASES_API = "https://api.github.com/repos/s1204IT/MindTheGappsBuilder/releases?per_page=100"


def parse_zip_central_directory(data: bytes, file_size: int):
    """
    Parses ZIP Central Directory bytes in memory without downloading payload.
    """
    eocd_pos = data.rfind(b"\x50\x4b\x05\x06")
    if eocd_pos == -1 or eocd_pos + 22 > len(data):
        return []

    disk_num, start_disk, entries_disk, total_entries, cd_size, cd_offset, comment_len = struct.unpack(
        "<HHHHIIH", data[eocd_pos+4 : eocd_pos+22]
    )

    tail_start_offset = file_size - len(data)
    cd_start_in_buf = cd_offset - tail_start_offset

    if cd_start_in_buf < 0 or cd_start_in_buf + cd_size > len(data):
        return []

    cd_bytes = data[cd_start_in_buf : cd_start_in_buf + cd_size]
    file_list = []
    ptr = 0

    while ptr + 46 <= len(cd_bytes):
        if cd_bytes[ptr:ptr+4] != b"\x50\x4b\x01\x02":
            break

        (
            sig, ver_m, ver_n, flags, meth,
            mtime, mdate, crc, csize, usize,
            nlen, elen, clen, dnum, iattr, eattr, off
        ) = struct.unpack("<IHHHHHHIIIHHHHHII", cd_bytes[ptr:ptr+46])

        name = cd_bytes[ptr+46 : ptr+46+nlen].decode("utf-8", errors="ignore")
        is_dir = name.endswith("/") or (eattr >> 16) & 0o040000 != 0

        file_list.append({
            "path": name,
            "size": usize,
            "compressed_size": csize,
            "is_dir": is_dir
        })

        ptr += 46 + nlen + elen + clen

    return file_list


def inspect_single_remote_zip(item: dict):
    """Fetches EOCD and central directory for a single ZIP asset"""
    url = item["url"]
    name = item["name"]
    tag = item["tag"]
    size_mb = item["size_mb"]

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (FastPureGappsAnalyzer)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            final_url = resp.geturl()
            total_size = int(resp.headers.get("Content-Length", 0))

        if total_size == 0:
            return name, {"error": "Empty file"}

        tail_len = min(total_size, 512 * 1024)
        range_req = urllib.request.Request(
            final_url,
            headers={
                "User-Agent": "Mozilla/5.0 (FastPureGappsAnalyzer)",
                "Range": f"bytes={total_size - tail_len}-{total_size - 1}"
            }
        )
        with urllib.request.urlopen(range_req, timeout=15) as resp:
            tail_data = resp.read()

        files = parse_zip_central_directory(tail_data, total_size)
        paths = [f["path"] for f in files if not f["is_dir"]]

        apks = [p for p in paths if p.endswith(".apk")]
        permissions = [p for p in paths if p.endswith(".xml") and "permission" in p]
        sysconfigs = [p for p in paths if p.endswith(".xml") and "sysconfig" in p]
        libs = [p for p in paths if p.endswith(".so")]

        has_update_binary = any("update-binary" in p for p in paths)
        has_build_prop = any(p.endswith("build.prop") for p in paths)
        has_addond = any("addon.d" in p for p in paths)
        has_toybox = any("toybox" in p for p in paths)

        app_names = [os.path.splitext(os.path.basename(apk))[0] for apk in apks]

        return name, {
            "tag": tag,
            "size_mb": size_mb,
            "total_files": len(paths),
            "apk_count": len(apks),
            "apks": sorted(app_names),
            "permissions_count": len(permissions),
            "sysconfigs_count": len(sysconfigs),
            "libs_count": len(libs),
            "meta": {
                "update_binary": has_update_binary,
                "build_prop": has_build_prop,
                "addon_d": has_addond,
                "toybox": has_toybox
            },
            "raw_paths": paths
        }
    except Exception as e:
        return name, {"error": str(e)}


def run_full_analysis():
    print("=" * 80)
    print("🚀 MULTI-THREADED GApps RELEASE ANALYZER (All 12 Releases)")
    print("=" * 80)
    print("[*] Fetching releases list from GitHub API...")

    req = urllib.request.Request(RELEASES_API, headers={"User-Agent": "Mozilla/5.0 (FastPureGappsAnalyzer)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        releases = json.loads(resp.read().decode("utf-8"))

    print(f"[✓] Retrieved {len(releases)} Releases successfully.\n")

    all_zip_assets = []
    for rel in releases:
        tag = rel.get("tag_name", "unknown")
        for asset in rel.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".zip") and not name.endswith(".zip.sha256sum") and not name.endswith(".zip.md5sum"):
                all_zip_assets.append({
                    "tag": tag,
                    "name": name,
                    "size_mb": asset.get("size", 0) / (1024 * 1024),
                    "url": asset.get("browser_download_url", "")
                })

    print(f"[*] Found {len(all_zip_assets)} Flashable ZIP assets.")
    print(f"[*] Analyzing all ZIP files concurrently with 8 parallel worker threads...\n")

    results = {}
    app_frequency = defaultdict(set)
    partition_breakdown = defaultdict(set)
    version_apk_matrix = defaultdict(lambda: defaultdict(set))

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(inspect_single_remote_zip, item): item for item in all_zip_assets}
        with tqdm(total=len(all_zip_assets), desc="Analyzing Releases", unit="zip", dynamic_ncols=True) as pbar:
            for future in as_completed(futures):
                item = futures[future]
                zip_name, data = future.result()
                results[zip_name] = data

                if "error" not in data:
                    # Update frequencies
                    for app in data["apks"]:
                        app_frequency[app].add(zip_name)

                        # Tag by Android version
                        parts = zip_name.split("-")
                        if len(parts) >= 3:
                            ver = parts[1]
                            arch = parts[2]
                            version_apk_matrix[ver][arch].add(app)

                    for path in data.get("raw_paths", []):
                        if path.startswith("system/") and "/" in path[7:]:
                            part = path.split("/")[1]
                            partition_breakdown[part].add(os.path.basename(path))

                pbar.set_postfix_str(f"{zip_name[:32]}... ({data.get('apk_count', 0)} APKs)")
                pbar.update(1)

    print("\n" + "=" * 80)
    print("📊 MASTER GApps APPS OCCURRENCE ACROSS ALL RELEASES")
    print("=" * 80)
    print(f"  {'App / Package Name':<35} | {'Present in %':<14} | {'ZIP Count'}")
    print("  " + "-" * 65)

    valid_zips = [k for k, v in results.items() if "error" not in v]
    total_valid = len(valid_zips)

    for app, zips in sorted(app_frequency.items(), key=lambda x: len(x[1]), reverse=True):
        pct = (len(zips) / total_valid) * 100 if total_valid else 0
        print(f"  {app:<35} | {pct:5.1f}%        | {len(zips)}/{total_valid}")

    print("\n" + "=" * 80)
    print("📱 ANDROID VERSION BREAKDOWN MATRIX")
    print("=" * 80)
    for ver in sorted(version_apk_matrix.keys(), reverse=True):
        print(f"\n  🔷 Android {ver}:")
        for arch in sorted(version_apk_matrix[ver].keys()):
            apps = sorted(list(version_apk_matrix[ver][arch]))
            print(f"     • {arch:<8} ({len(apps)} APKs): {', '.join(apps[:6])}{'...' if len(apps)>6 else ''}")

    # Save detailed JSON report
    report_file = "all_releases_analysis_report.json"
    with open(report_file, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 Complete Analysis Report of all 12 Releases Saved to: {os.path.abspath(report_file)}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_full_analysis()
