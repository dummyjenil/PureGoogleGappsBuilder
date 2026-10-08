#!/usr/bin/env python3
"""
Modular GApps ZIP Tree, XML & APK Version Analyzer & Comparator.
Uses the `analyzer/` package (`zip_inspector`, `xml_analyzer`, `apk_analyzer`, `report_generator`)
to perform deep comparison between PureGoogleGappsBuilder and MindTheGappsBuilder:
  1. Full file-tree comparison
  2. Deep XML semantic comparison (parses any XML with even 1 byte or CRC difference)
  3. APK versionName & versionCode comparison (for any APK with even 1 byte or CRC difference)

Supports:
  - Per-Matrix Build Mode: `--version 13.0.0 --arch x86_64 --local-zip out.zip --save-fragment frag.json`
  - Final Merge & Publish Mode: `--merge-fragments fragments_dir`
  - Standalone Remote Mode: `python3 analyze_all_releases.py`
"""

import os
import json
import argparse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from analyzer import (
    RemoteZipInspector,
    compare_xml_files,
    compare_apk_files,
    generate_reports,
)

MTG_API = "https://api.github.com/repos/s1204IT/MindTheGappsBuilder/releases?per_page=100"
_PURE_REPO = os.environ.get("GITHUB_REPOSITORY") or "dummyjenil/PureGoogleGappsBuilder"
PURE_API = f"https://api.github.com/repos/{_PURE_REPO}/releases?per_page=10"


def fetch_releases_json(api_url: str):
    headers = {"User-Agent": "Mozilla/5.0 (FastGappsComparator/2.0)"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(api_url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_package_version_and_arch(name: str):
    clean_name = name.replace(".zip", "")
    parts = clean_name.split("-")
    if len(parts) >= 3:
        return parts[1], parts[2]
    return None, None


def compare_two_packages(ver: str, arch: str, pure_info: dict, mtg_info: dict) -> dict:
    pure_files = pure_info["files"]
    mtg_files = mtg_info["files"]

    only_pure = set(pure_files.keys()) - set(mtg_files.keys())
    only_mtg = set(mtg_files.keys()) - set(pure_files.keys())
    common = set(pure_files.keys()) & set(mtg_files.keys())

    size_diffs = []
    for f in common:
        p_sz = pure_files[f]["size"]
        m_sz = mtg_files[f]["size"]
        if p_sz != m_sz:
            diff_pct = (abs(p_sz - m_sz) / max(p_sz, m_sz, 1)) * 100
            if diff_pct > 5.0 and abs(p_sz - m_sz) > 1024:
                size_diffs.append((f, p_sz, m_sz, diff_pct))

    xml_comparisons = compare_xml_files(pure_info, mtg_info)
    apk_comparisons = compare_apk_files(ver, arch, pure_info, mtg_info)

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
        "is_perfect_tree_match": len(only_pure) == 0 and len(only_mtg) == 0,
        "xml_comparisons": xml_comparisons,
        "apk_comparisons": apk_comparisons,
    }


def _discover_remote_packages():
    pure_packages = {}
    try:
        pure_releases = fetch_releases_json(PURE_API)
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
                            "release_tag": rel.get("tag_name", ""),
                            "local_path": None,
                        }
    except Exception as e:
        print(f"[!] Note: Could not fetch remote PureGoogleGapps releases ({e})")

    mtg_packages = {}
    mtg_releases = fetch_releases_json(MTG_API)
    for rel in mtg_releases:
        tag = rel.get("tag_name", "")
        for asset in rel.get("assets", []):
            name = asset.get("name", "")
            if (
                name.startswith("MindTheGapps-")
                and name.endswith(".zip")
                and not name.endswith(".sum")
            ):
                ver, arch = parse_package_version_and_arch(name)
                if ver and arch:
                    key = (ver, arch)
                    if key not in mtg_packages:
                        mtg_packages[key] = {
                            "name": name,
                            "url": asset.get("browser_download_url", ""),
                            "size_bytes": asset.get("size", 0),
                            "release_tag": tag,
                        }

    return pure_packages, mtg_packages


def _sort_key(item: dict):
    ver = item.get("version", "0.0.0")
    parts = [int(p) if p.isdigit() else 0 for p in ver.split(".")]
    return (parts, item.get("arch", ""))


def enforce_strict_release_gate(comparison_results: list):
    """
    Strictly verifies that every analyzed package in `comparison_results` achieves:
      - 100% file-tree match (`only_in_pure == []` and `only_in_mtg == []`)
      - Zero missing XML permissions/entries (`missing_in_pure == []` across all XMLs)
    Exits with non-zero status if any package fails the release gate.
    """
    if not comparison_results:
        print("[!] CRITICAL: Release gate failed — 0 comparison results produced!")
        raise SystemExit(1)

    for item in comparison_results:
        ver = item.get("version")
        arch = item.get("arch")
        only_pure = item.get("only_in_pure", [])
        only_mtg = item.get("only_in_mtg", [])
        missing_xml_items = []
        for xc in item.get("xml_comparisons", []):
            for m in xc.get("missing_in_pure", []):
                missing_xml_items.append(f"{xc.get('path')}: {m}")

        print(
            f"[Strict Release Gate] Android {ver} ({arch}): "
            f"missing_files={len(only_mtg)}, extra_files={len(only_pure)}, "
            f"missing_xml_entries={len(missing_xml_items)}"
        )
        if only_mtg or only_pure or missing_xml_items:
            print(f"[!] CRITICAL: Release gate FAILED for Android {ver} ({arch})!")
            if only_mtg:
                print(f"    - Missing files: {only_mtg}")
            if only_pure:
                print(f"    - Extra files: {only_pure}")
            if missing_xml_items:
                print(f"    - Missing XML entries: {missing_xml_items[:10]}")
            raise SystemExit(1)

    print("[✓] Strict 100% Release Gate Passed!")


def run_comparison(
    target_ver: str = None,
    target_arch: str = None,
    local_dir: str = None,
    local_zip: str = None,
    save_fragment: str = None,
    merge_fragments: str = None,
    strict_gate: bool = False,
):
    # Pre-load any per-matrix fragments if --merge-fragments is provided
    merged_map = {}
    if merge_fragments and os.path.isdir(merge_fragments):
        for root, _, files in os.walk(merge_fragments):
            for fname in sorted(files):
                if fname.endswith(".json"):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r") as f:
                            data = json.load(f)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if "version" in item and "arch" in item:
                                merged_map[(item["version"], item["arch"])] = item
                                print(
                                    f"[✓] Loaded matrix fragment: Android {item['version']} ({item['arch']})"
                                )
                    except Exception as e:
                        print(f"[!] Warning: Could not load fragment {fpath}: {e}")

    pure_packages, mtg_packages = _discover_remote_packages()

    if local_dir and os.path.isdir(local_dir):
        for fname in sorted(os.listdir(local_dir)):
            if fname.startswith("GoogleGapps-") and fname.endswith(".zip"):
                ver, arch = parse_package_version_and_arch(fname)
                if ver and arch:
                    fpath = os.path.join(local_dir, fname)
                    pure_packages[(ver, arch)] = {
                        "name": fname,
                        "url": f"local://{fpath}",
                        "size_bytes": os.path.getsize(fpath),
                        "release_tag": "local-build",
                        "local_path": fpath,
                    }

    if local_zip and os.path.isfile(local_zip):
        fname = os.path.basename(local_zip)
        ver, arch = parse_package_version_and_arch(fname)
        ver = target_ver or ver
        arch = target_arch or arch
        if ver and arch:
            pure_packages[(ver, arch)] = {
                "name": fname,
                "url": f"local://{local_zip}",
                "size_bytes": os.path.getsize(local_zip),
                "release_tag": "local-matrix",
                "local_path": local_zip,
            }

    def _resolve_mtg_baseline(v: str, a: str):
        if (v, a) in mtg_packages:
            return mtg_packages[(v, a)]
        if v == "12.0.0":
            if ("12.1.0", a) in mtg_packages:
                return mtg_packages[("12.1.0", a)]
        if v == "16.0.0":
            if ("15.0.0", a) in mtg_packages:
                return mtg_packages[("15.0.0", a)]
        if a == "x86_64" and (v, "x86") in mtg_packages:
            return mtg_packages[(v, "x86")]
        return None

    all_keys = sorted(set(pure_packages.keys()) | set(mtg_packages.keys()))
    matching_pairs = []

    for key in all_keys:
        ver, arch = key
        if target_ver and ver != target_ver:
            continue
        if target_arch and arch != target_arch:
            continue
        if key in merged_map:
            continue  # Already analyzed during the matrix job!
        if key in pure_packages:
            m_pkg = _resolve_mtg_baseline(ver, arch)
            if m_pkg:
                matching_pairs.append((ver, arch, pure_packages[key], m_pkg))

    inspected_data = {}
    urls_to_fetch = {}
    for ver, arch, p_pkg, m_pkg in matching_pairs:
        if p_pkg.get("local_path"):
            res, err = RemoteZipInspector.inspect_local(p_pkg["local_path"])
            if res:
                inspected_data[p_pkg["url"]] = res
            else:
                print(f"[!] Warning: Failed to read local zip {p_pkg['name']}: {err}")
        else:
            urls_to_fetch[p_pkg["url"]] = p_pkg["name"]
        urls_to_fetch[m_pkg["url"]] = m_pkg["name"]

    if urls_to_fetch:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(RemoteZipInspector.inspect, url): url
                for url in urls_to_fetch
            }
            for future in as_completed(futures):
                url = futures[future]
                name = urls_to_fetch[url]
                res, err = future.result()
                if res:
                    inspected_data[url] = res
                else:
                    print(f"[!] Warning: Failed to read metadata for {name}: {err}")

    for ver, arch, p_pkg, m_pkg in matching_pairs:
        p_res = inspected_data.get(p_pkg["url"])
        m_res = inspected_data.get(m_pkg["url"])
        if not p_res or not m_res:
            continue
        print(f"[*] Analyzing XMLs & APK Versions for Android {ver} ({arch})...")
        comp = compare_two_packages(ver, arch, p_res, m_res)
        merged_map[(ver, arch)] = comp

    comparison_results = sorted(merged_map.values(), key=_sort_key)

    if save_fragment:
        os.makedirs(os.path.dirname(os.path.abspath(save_fragment)), exist_ok=True)
        with open(save_fragment, "w") as f:
            json.dump(comparison_results, f, indent=2)
        print(f"[✓] Saved matrix analysis fragment to: {save_fragment}")

    generate_reports(comparison_results)

    if strict_gate:
        enforce_strict_release_gate(comparison_results)


def main():
    parser = argparse.ArgumentParser(
        description="Modular GApps ZIP Tree, XML & APK Version Analyzer"
    )
    parser.add_argument("--version", help="Filter specific Android version (e.g. 13.0.0)")
    parser.add_argument("--arch", help="Filter specific architecture (e.g. x86_64, arm64)")
    parser.add_argument("--local-dir", help="Directory containing built GoogleGapps-*.zip files")
    parser.add_argument("--local-zip", help="Path to a single built GoogleGapps-*.zip file (Matrix Mode)")
    parser.add_argument("--save-fragment", help="Save per-matrix JSON analysis fragment to path")
    parser.add_argument("--merge-fragments", help="Merge all per-matrix JSON fragments from directory")
    parser.add_argument("--strict-gate", action="store_true", help="Fail with exit code 1 if tree or XML parity is not 100%%")
    args = parser.parse_args()

    run_comparison(
        target_ver=args.version,
        target_arch=args.arch,
        local_dir=args.local_dir,
        local_zip=args.local_zip,
        save_fragment=args.save_fragment,
        merge_fragments=args.merge_fragments,
        strict_gate=args.strict_gate,
    )


if __name__ == "__main__":
    main()
