#!/usr/bin/env python3
"""
Direct Google Official SDK Repository Scanner & Update Checker
Connects directly to dl.google.com XML repository to detect latest official system image updates.
"""

import sys
import json
import os
import argparse
import urllib.request
import xml.etree.ElementTree as ET

GOOGLE_XML_URLS = [
    "https://dl.google.com/android/repository/sys-img/google_apis_playstore/sys-img2-3.xml",
    "https://dl.google.com/android/repository/sys-img/google_apis/sys-img2-3.xml",
    "https://dl.google.com/android/repository/sys-img/android/sys-img2-3.xml",
]

API_VERSION_MAP = {
    28: "9.0.0",
    29: "10.0.0",
    30: "11.0.0",
    31: "12.0.0",
    32: "12.1.0",
    33: "13.0.0",
    34: "14.0.0",
    35: "15.0.0",
    36: "16.0.0",
}

ARCH_MAP = {
    "x86_64": "x86_64",
    "x86": "x86",
    "arm64-v8a": "arm64",
    "armeabi-v7a": "arm"
}


def _parse_rev_tuple(rev_str: str) -> tuple:
    parts = []
    for p in (rev_str or "").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def fetch_google_repository_metadata():
    latest_images = {}
    
    headers = {"User-Agent": "Android-Studio/PureGappsChecker"}
    
    for url in GOOGLE_XML_URLS:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_data = resp.read()
                root = ET.fromstring(xml_data)
                
                for pkg in root.iter():
                    if not pkg.tag.endswith("remotePackage"):
                        continue
                        
                    path = pkg.attrib.get("path", "")
                    # Skip 16KB page-size experimental images (ps16k)
                    if "ps16k" in path.lower():
                        continue

                    api_level = None
                    abi = None
                    
                    for child in pkg.iter():
                        if child.tag.endswith("api-level"):
                            try:
                                api_level = int(child.text.split(".")[0])
                            except (ValueError, AttributeError):
                                pass
                        elif child.tag.endswith("abi"):
                            abi = child.text
                            
                    if api_level not in API_VERSION_MAP or abi not in ARCH_MAP:
                        continue
                        
                    arch_name = ARCH_MAP[abi]
                    # Prioritize Linux or generic (no host-os) archive
                    archive_candidates = pkg.findall(".//{*}archive")
                    archive = None
                    for arch_elem in archive_candidates:
                        host_elem = arch_elem.find(".//{*}host-os")
                        host_os = host_elem.text.strip().lower() if host_elem is not None and host_elem.text else ""
                        if host_os in ["linux", ""]:
                            archive = arch_elem
                            break
                    if archive is None and archive_candidates:
                        archive = archive_candidates[0]
                    if archive is None:
                        continue
                        
                    url_elem = archive.find(".//{*}url")
                    checksum_elem = archive.find(".//{*}checksum")
                    rev_elem = pkg.find(".//{*}revision")
                    
                    if url_elem is None or not url_elem.text:
                        continue
                        
                    file_url = url_elem.text.strip()
                    if "ps16k" in file_url.lower():
                        continue
                    if not file_url.startswith("http"):
                        base_prefix = url.rsplit("/", 1)[0]
                        file_url = f"{base_prefix}/{file_url}"
                        
                    revision_str = ""
                    if rev_elem is not None:
                        parts = [elem.text for elem in rev_elem if elem.text]
                        revision_str = ".".join(parts) if parts else (rev_elem.text or "")
                        
                    checksum = checksum_elem.text.strip() if checksum_elem is not None and checksum_elem.text else ""
                    
                    key = f"{API_VERSION_MAP[api_level]}-{arch_name}"
                    
                    # Prioritize Play Store images over generic google_apis, and higher revisions within same tier
                    is_playstore = "playstore" in path.lower() or "playstore" in file_url.lower()
                    existing = latest_images.get(key)
                    
                    should_replace = False
                    if existing is None:
                        should_replace = True
                    elif is_playstore and not existing.get("is_playstore", False):
                        should_replace = True
                    elif is_playstore == existing.get("is_playstore", False):
                        if _parse_rev_tuple(revision_str) > _parse_rev_tuple(existing.get("revision", "")):
                            should_replace = True

                    if should_replace:
                        latest_images[key] = {
                            "android_version": API_VERSION_MAP[api_level],
                            "api_level": api_level,
                            "arch": arch_name,
                            "abi": abi,
                            "url": file_url,
                            "revision": revision_str,
                            "checksum": checksum,
                            "is_playstore": is_playstore
                        }
        except Exception as e:
            print(f"[!] Warning: Failed to fetch {url}: {e}", file=sys.stderr)
            
    return latest_images


def main():
    parser = argparse.ArgumentParser(description="Check for latest Google System Image updates directly from Google")
    parser.add_argument("--state-file", default="latest_revisions.json", help="Path to state tracking JSON file")
    parser.add_argument("--force", action="store_true", help="Force update regardless of state change")
    parser.add_argument("--output-json", help="Save latest discovered versions metadata to JSON file")
    args = parser.parse_args()

    print("[*] Fetching official Google SDK XML repositories directly from dl.google.com...")
    latest_images = fetch_google_repository_metadata()
    
    if not latest_images:
        print("[!] Error: Could not retrieve images from Google repository.", file=sys.stderr)
        sys.exit(1)
        
    print(f"[✓] Discovered {len(latest_images)} official target packages directly from Google.")
    
    previous_state = {}
    if os.path.exists(args.state_file):
        try:
            with open(args.state_file, "r") as f:
                previous_state = json.load(f)
        except Exception as e:
            print(f"[!] Warning: Could not read previous state: {e}", file=sys.stderr)

    updated_targets = []
    
    for key, data in sorted(latest_images.items()):
        prev = previous_state.get(key)
        has_changed = False
        
        if prev is None:
            has_changed = True
            change_reason = "New Target"
        elif prev.get("checksum") != data["checksum"] or prev.get("revision") != data["revision"]:
            has_changed = True
            change_reason = f"Rev {prev.get('revision')} -> {data['revision']}"
        else:
            change_reason = "No Change"
            
        if has_changed or args.force:
            updated_targets.append(data)
            print(f"  [+] UPDATE: Android {data['android_version']} ({data['arch']}) - {change_reason}")
        else:
            print(f"  [-] UP-TO-DATE: Android {data['android_version']} ({data['arch']}) (Rev {data['revision']})")

    # Output for GitHub Actions
    has_updates = len(updated_targets) > 0
    github_output = os.getenv("GITHUB_OUTPUT")
    
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_updates={'true' if has_updates else 'false'}\n")
            f.write(f"update_count={len(updated_targets)}\n")
            
            # Create matrix include format
            matrix_includes = [
                {
                    "androidv": t["android_version"],
                    "api": t["api_level"],
                    "arch": t["arch"],
                    "abi": t["abi"],
                    "url": t["url"],
                    "revision": t["revision"],
                    "checksum": t["checksum"]
                }
                for t in (updated_targets if not args.force else list(latest_images.values()))
            ]
            f.write(f"matrix={json.dumps({'include': matrix_includes})}\n")

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(latest_images, f, indent=2)
            print(f"[✓] Saved latest state to {args.output_json}")

    print(f"\n[*] Update check completed: {len(updated_targets)} updates found.")


if __name__ == "__main__":
    main()
