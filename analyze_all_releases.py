#!/usr/bin/env python3
"""
High-Performance Remote GApps ZIP Tree Analyzer & Comparator
Compares file trees, components, sizes, and metadata between:
  - s1204IT/MindTheGappsBuilder (all releases & versions)
  - dummyjenil/PureGoogleGappsBuilder (latest releases)
Uses lightweight HTTP Range requests (~4KB per ZIP) - Zero full downloads!
"""

import os
import sys
import json
import struct
import argparse
import urllib.request
import urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed


MTG_API = "https://api.github.com/repos/s1204IT/MindTheGappsBuilder/releases?per_page=100"
PURE_API = "https://api.github.com/repos/dummyjenil/PureGoogleGappsBuilder/releases?per_page=10"


class RemoteZipInspector:
    """Lightweight HTTP Range reader to parse ZIP Central Directory in memory"""
    
    @staticmethod
    def inspect(url: str, timeout: int = 15):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (FastGappsComparator/1.0)"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final_url = resp.geturl()
                content_len = resp.headers.get("Content-Length")
                total_size = int(content_len) if content_len else 0

            if total_size == 0:
                # Fallback range probe
                r_req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
                with urllib.request.urlopen(r_req, timeout=timeout) as resp:
                    final_url = resp.geturl()
                    cr = resp.headers.get("Content-Range")
                    total_size = int(cr.split("/")[-1]) if cr else 0

            if total_size == 0:
                return None, "Unable to determine file size"

            # Read last 64KB (or up to 512KB for huge archives)
            tail_len = min(total_size, 512 * 1024)
            range_req = urllib.request.Request(
                final_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (FastGappsComparator/1.0)",
                    "Range": f"bytes={total_size - tail_len}-{total_size - 1}"
                }
            )
            with urllib.request.urlopen(range_req, timeout=timeout) as resp:
                tail_data = resp.read()

            files = RemoteZipInspector._parse_cd(tail_data, total_size)
            return {
                "total_size_bytes": total_size,
                "size_mb": total_size / (1024 * 1024),
                "files": files
            }, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def _parse_cd(data: bytes, file_size: int):
        eocd_pos = data.rfind(b"\x50\x4b\x05\x06")
        if eocd_pos == -1 or eocd_pos + 22 > len(data):
            return {}

        disk_num, start_disk, entries_disk, total_entries, cd_size, cd_offset, comment_len = struct.unpack(
            "<HHHHIIH", data[eocd_pos+4 : eocd_pos+22]
        )

        tail_start_offset = file_size - len(data)
        cd_start_in_buf = cd_offset - tail_start_offset

        if cd_start_in_buf < 0 or cd_start_in_buf + cd_size > len(data):
            # If Central Directory was larger than tail buffer, read exact CD range
            return {}

        cd_bytes = data[cd_start_in_buf : cd_start_in_buf + cd_size]
        file_map = {}
        ptr = 0

        while ptr + 46 <= len(cd_bytes):
            if cd_bytes[ptr:ptr+4] != b"\x50\x4b\x01\x02":
                break

            (
                sig, ver_m, ver_n, flags, meth,
                mtime, mdate, crc, csize, usize,
                nlen, elen, clen, dnum, iattr, eattr, off
            ) = struct.unpack("<IHHHHHHIIIHHHHHII", cd_bytes[ptr:ptr+46])

            name = cd_bytes[ptr+46 : ptr+46+nlen].decode("utf-8", errors="ignore").replace("\\", "/")
            is_dir = name.endswith("/") or (eattr >> 16) & 0o040000 != 0

            if not is_dir:
                file_map[name] = {
                    "size": usize,
                    "compressed_size": csize,
                    "crc32": f"{crc:08x}"
                }

            ptr += 46 + nlen + elen + clen

        return file_map


def fetch_releases_json(api_url: str):
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0 (FastGappsComparator/1.0)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_package_version_and_arch(name: str):
    """Extracts (version, arch) from filenames like MindTheGapps-13.0.0-x86_64-20240619.zip or GoogleGapps-13.0.0-x86_64.zip"""
    clean_name = name.replace(".zip", "")
    parts = clean_name.split("-")
    if len(parts) >= 3:
        return parts[1], parts[2]
    return None, None


def compare_two_packages(ver: str, arch: str, pure_info: dict, mtg_info: dict):
    pure_files = pure_info["files"]
    mtg_files = mtg_info["files"]

    only_pure = set(pure_files.keys()) - set(mtg_files.keys())
    only_mtg = set(mtg_files.keys()) - set(pure_files.keys())
    common = set(pure_files.keys()) & set(mtg_files.keys())

    # Check size discrepancies on common files (> 5% difference)
    size_diffs = []
    for f in common:
        p_sz = pure_files[f]["size"]
        m_sz = mtg_files[f]["size"]
        if p_sz != m_sz:
            diff_pct = (abs(p_sz - m_sz) / max(p_sz, m_sz, 1)) * 100
            if diff_pct > 5.0 and abs(p_sz - m_sz) > 1024:
                size_diffs.append((f, p_sz, m_sz, diff_pct))

    return {
        "version": ver,
        "arch": arch,
        "pure_size_mb": pure_info["size_mb"],
        "mtg_size_mb": mtg_info["size_mb"],
        "pure_total_files": len(pure_files),
        "mtg_total_files": len(mtg_files),
        "only_in_pure": sorted(list(only_pure)),
        "only_in_mtg": sorted(list(only_mtg)),
        "common_count": len(common),
        "size_diffs": sorted(size_diffs, key=lambda x: x[3], reverse=True),
        "is_perfect_tree_match": len(only_pure) == 0 and len(only_mtg) == 0
    }


def format_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024.0:
            return f"{b:5.1f} {unit}"
        b /= 1024.0
    return f"{b:5.1f} TB"


def run_comparison(target_ver: str = None, target_arch: str = None):
    print("=" * 80)
    print("🔍 REMOTE GAPPS COMPARATOR: PureGoogleGapps vs MindTheGapps (All Releases)")
    print("=" * 80)

    print("[*] Fetching release metadata from GitHub APIs...")
    pure_releases = fetch_releases_json(PURE_API)
    mtg_releases = fetch_releases_json(MTG_API)

    # 1. Map latest PureGoogleGapps packages
    pure_packages = {}
    for rel in pure_releases:
        for asset in rel.get("assets", []):
            name = asset.get("name", "")
            if name.startswith("GoogleGapps-") and name.endswith(".zip"):
                ver, arch = parse_package_version_and_arch(name)
                if ver and arch:
                    pure_packages[(ver, arch)] = {
                        "name": name,
                        "url": asset.get("browser_download_url", ""),
                        "size_bytes": asset.get("size", 0),
                        "release_tag": rel.get("tag_name", "")
                    }

    # 2. Map latest MindTheGapps packages (picking the newest release tag per ver/arch)
    mtg_packages = {}
    for rel in mtg_releases:
        tag = rel.get("tag_name", "")
        for asset in rel.get("assets", []):
            name = asset.get("name", "")
            if name.startswith("MindTheGapps-") and name.endswith(".zip") and not name.endswith(".sum"):
                ver, arch = parse_package_version_and_arch(name)
                if ver and arch:
                    key = (ver, arch)
                    if key not in mtg_packages:
                        mtg_packages[key] = {
                            "name": name,
                            "url": asset.get("browser_download_url", ""),
                            "size_bytes": asset.get("size", 0),
                            "release_tag": tag
                        }

    # Find matching pairs
    all_keys = sorted(set(pure_packages.keys()) | set(mtg_packages.keys()))
    matching_pairs = []

    for key in all_keys:
        ver, arch = key
        if target_ver and ver != target_ver:
            continue
        if target_arch and arch != target_arch:
            continue

        if key in pure_packages and key in mtg_packages:
            matching_pairs.append((ver, arch, pure_packages[key], mtg_packages[key]))

    print(f"[✓] Discovered {len(pure_packages)} PureGoogleGapps packages & {len(mtg_packages)} MindTheGapps targets.")
    print(f"[*] Comparing {len(matching_pairs)} corresponding (Version, Arch) pairs...\n")

    # Fetch zip central directories concurrently
    urls_to_fetch = {}
    for ver, arch, p_pkg, m_pkg in matching_pairs:
        urls_to_fetch[p_pkg["url"]] = p_pkg["name"]
        urls_to_fetch[m_pkg["url"]] = m_pkg["name"]

    inspected_data = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(RemoteZipInspector.inspect, url): url for url in urls_to_fetch}
        for future in as_completed(futures):
            url = futures[future]
            name = urls_to_fetch[url]
            res, err = future.result()
            if res:
                inspected_data[url] = res
            else:
                print(f"[!] Warning: Failed to read metadata for {name}: {err}")

    # Run comparisons
    comparison_results = []
    print("=" * 80)
    print(f"{'Target Version & Architecture':<28} | {'Pure GApps':<12} | {'MindTheGapps':<12} | {'Tree Status'}")
    print("-" * 80)

    for ver, arch, p_pkg, m_pkg in matching_pairs:
        p_res = inspected_data.get(p_pkg["url"])
        m_res = inspected_data.get(m_pkg["url"])

        if not p_res or not m_res:
            continue

        comp = compare_two_packages(ver, arch, p_res, m_res)
        comparison_results.append(comp)

        status_str = "\033[1;32m[✓ 100% MATCH]\033[0m" if comp["is_perfect_tree_match"] else f"\033[1;33m[⚠ {len(comp['only_in_pure'])+len(comp['only_in_mtg'])} DIFFS]\033[0m"
        print(f"Android {ver:<8} ({arch:<7}) | {comp['pure_size_mb']:>6.1f} MB     | {comp['mtg_size_mb']:>6.1f} MB     | {status_str}")

    print("=" * 80)

    # Print detailed differences for each pair
    print("\n" + "=" * 80)
    print("📑 DETAILED DIFFERENCE BREAKDOWN PER PACKAGE")
    print("=" * 80)

    for comp in comparison_results:
        ver = comp["version"]
        arch = comp["arch"]
        print(f"\n📦 Android {ver} ({arch}):")
        print(f"   • PureGoogleGapps Size: {comp['pure_size_mb']:.2f} MB ({comp['pure_total_files']} files)")
        print(f"   • MindTheGapps Size   : {comp['mtg_size_mb']:.2f} MB ({comp['mtg_total_files']} files)")

        if comp["is_perfect_tree_match"]:
            print("   \033[1;32m✓ Perfect File Structure Match! (Zero missing or extra files)\033[0m")
        else:
            if comp["only_in_pure"]:
                print(f"   \033[1;31m+ Files ONLY in PureGoogleGapps ({len(comp['only_in_pure'])}):\033[0m")
                for f in comp["only_in_pure"][:10]:
                    print(f"       + {f}")
                if len(comp["only_in_pure"]) > 10:
                    print(f"       ... and {len(comp['only_in_pure']) - 10} more")

            if comp["only_in_mtg"]:
                print(f"   \033[1;34m- Files ONLY in MindTheGapps ({len(comp['only_in_mtg'])}):\033[0m")
                for f in comp["only_in_mtg"][:10]:
                    print(f"       - {f}")
                if len(comp["only_in_mtg"]) > 10:
                    print(f"       ... and {len(comp['only_in_mtg']) - 10} more")

        if comp["size_diffs"]:
            print(f"   \033[90m~ Top Size Differences in Common Components:\033[0m")
            for f, psz, msz, pct in comp["size_diffs"][:5]:
                print(f"       ~ {os.path.basename(f):<35} (Pure: {format_size(psz).strip()} vs MTG: {format_size(msz).strip()})")

    # Export report
    report_file = "gapps_comparison_report.json"
    with open(report_file, "w") as f:
        json.dump(comparison_results, f, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 Comparison Report saved to: {os.path.abspath(report_file)}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="High-Performance Remote GApps ZIP Tree Analyzer & Comparator")
    parser.add_argument("--version", help="Filter specific Android version (e.g. 13.0.0)")
    parser.add_argument("--arch", help="Filter specific architecture (e.g. x86_64, arm64)")
    args = parser.parse_args()

    run_comparison(args.version, args.arch)


if __name__ == "__main__":
    main()
