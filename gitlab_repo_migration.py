#!/usr/bin/env python3
"""
GitLab-to-GitHub Static Asset Migration Script for PureGoogleGappsBuilder.
Downloads ONLY non-APK static files (proprietary-files-*.txt, update-binary,
overlay XMLs, signing keys, toybox binaries, and static XML/JAR/cert/.so configs)
from MindTheGapps/vendor_gapps into `static/` using clean Android version numbers
(no codename/meta names like pi/pie/qoppa/rho/sigma/tau/upsilon/vic).

Strictly excludes all `.apk` files so 100% of APKs are sourced from official Google images.
"""

import os
import json
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

GITLAB_RAW_BASE = "https://gitlab.com/MindTheGapps/vendor_gapps/-/raw"
GITLAB_API_BASE = "https://gitlab.com/api/v4/projects/MindTheGapps%2Fvendor_gapps/repository"

VERSION_TO_UPSTREAM = {
    "9.0.0": "pi",
    "10.0.0": "qoppa",
    "11.0.0": "rho",
    "12.0.0": "sigma",
    "12.1.0": "sigma",
    "13.0.0": "tau",
    "14.0.0": "upsilon",
    "15.0.0": "vic",
    "16.0.0": "baklava",
}

ARCHS = ["arm", "arm64", "x86", "x86_64"]


def fetch_bytes(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (StaticMigrator/2.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def save_file(dst_path: str, data: bytes, executable: bool = False):
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "wb") as f:
        f.write(data)
    if executable:
        os.chmod(dst_path, 0o755)


def migrate_all(repo_root: str):
    static_root = os.path.join(repo_root, "static")
    if os.path.exists(static_root):
        shutil.rmtree(static_root)
    os.makedirs(static_root, exist_ok=True)

    url_cache = {}

    def download_cached(url: str) -> bytes:
        if url not in url_cache:
            url_cache[url] = fetch_bytes(url)
        return url_cache[url]

    # 1. Shared keys & toybox binaries in `static/common/`
    print("[*] Fetching shared signing keys & toybox binaries into static/common/...")
    for key_name in ["testkey.pk8", "testkey.x509.pem"]:
        raw = download_cached(f"{GITLAB_RAW_BASE}/upsilon/build/sign/{key_name}")
        save_file(os.path.join(static_root, "common", "sign", key_name), raw)

    for tb_name in ["toybox-arm", "toybox-arm64", "toybox-x86", "toybox-x86_64"]:
        raw = download_cached(f"{GITLAB_RAW_BASE}/upsilon/{tb_name}")
        save_file(os.path.join(static_root, "common", "toybox", tb_name), raw, executable=True)

    # 2. Per-version non-APK static files (using clean version names: 9.0.0 .. 16.0.0)
    for ver, branch in VERSION_TO_UPSTREAM.items():
        print(f"\n[*] Migrating non-APK static files for Android {ver} -> static/{ver}/...")
        ver_dir = os.path.join(static_root, ver)
        os.makedirs(ver_dir, exist_ok=True)

        # A. proprietary-files-*.txt
        prop_txts = ["proprietary-files-common.txt", "proprietary-files-common-nongrouper.txt"]
        for a in ARCHS:
            prop_txts.extend([f"proprietary-files-{a}.txt", f"proprietary-files-{a}-nongrouper.txt"])

        for pfile in prop_txts:
            try:
                raw = download_cached(f"{GITLAB_RAW_BASE}/{branch}/{pfile}")
                text = raw.decode("utf-8", errors="ignore")
                if ver == "15.0.0":
                    lines = [
                        l for l in text.splitlines()
                        if "FamilyLinkParentalControls" not in l and "sysconfig_contextual_search.xml" not in l
                    ]
                    if pfile in ("proprietary-files-arm64.txt", "proprietary-files-x86_64.txt"):
                        if not any("product/lib/libjni_latinimegoogle.so" in l for l in lines):
                            lines.append("product/lib/libjni_latinimegoogle.so")
                    if pfile == "proprietary-files-arm64-nongrouper.txt":
                        if not any("VelvetTitan.apk" in l for l in lines):
                            lines.append("product/priv-app/VelvetTitan/VelvetTitan.apk;OVERRIDES=Velvet;PRESIGNED")
                    text = "\n".join(lines) + "\n"
                save_file(os.path.join(ver_dir, pfile), text.encode("utf-8"))
                print(f"    [+] {ver}/{pfile}")
            except Exception:
                pass

        # B. update-binary
        try:
            ub = download_cached(f"{GITLAB_RAW_BASE}/{branch}/build/meta/com/google/android/update-binary")
            save_file(os.path.join(ver_dir, "update-binary"), ub, executable=True)
            print(f"    [+] {ver}/update-binary ({len(ub)} B)")
        except Exception as e:
            print(f"    [!] Warning: update-binary failed for {ver}: {e}")

        # C. RRO Overlays (Android 12+)
        try:
            ov_tree = json.loads(
                download_cached(f"{GITLAB_API_BASE}/tree?ref={branch}&path=overlay&recursive=true&per_page=100").decode("utf-8")
            )
            for item in ov_tree:
                if item.get("type") == "blob" and item["path"].endswith(".xml"):
                    p = item["path"]
                    raw = download_cached(f"{GITLAB_RAW_BASE}/{branch}/{p}")
                    save_file(os.path.join(ver_dir, p), raw)
                    print(f"    [+] {ver}/{p}")
        except Exception:
            pass

        # D. Non-APK static proprietary files (XMLs, JARs, certs, .rc, .so — strictly NO .apk)
        for prefix in ["common/proprietary"] + [f"{a}/proprietary" for a in ARCHS]:
            try:
                tree = json.loads(
                    download_cached(f"{GITLAB_API_BASE}/tree?ref={branch}&path={prefix}&recursive=true&per_page=100").decode("utf-8")
                )
            except Exception:
                continue

            to_fetch = []
            for item in tree:
                if item.get("type") != "blob":
                    continue
                rel_path = item["path"]
                if not rel_path.startswith(f"{prefix}/"):
                    continue
                # Strictly exclude ALL .apk files
                if rel_path.endswith(".apk"):
                    continue
                if ver == "15.0.0" and "sysconfig_contextual_search.xml" in rel_path:
                    continue
                to_fetch.append(rel_path)

            with ThreadPoolExecutor(max_workers=10) as ex:
                future_map = {
                    ex.submit(download_cached, f"{GITLAB_RAW_BASE}/{branch}/{rp}"): rp
                    for rp in to_fetch
                }
                for fut in as_completed(future_map):
                    rp = future_map[fut]
                    try:
                        content = fut.result()
                        save_file(os.path.join(ver_dir, rp), content)
                        print(f"    [+] {ver}/{rp} ({len(content)} B)")
                    except Exception as e:
                        print(f"    [!] Failed {ver}/{rp}: {e}")

        # For Android 15.0.0, include 32-bit product/lib/libjni_latinimegoogle.so for 100% tree parity
        if ver == "15.0.0":
            for arch_32 in ["arm64", "x86_64"]:
                rp_32 = f"{arch_32}/proprietary/product/lib/libjni_latinimegoogle.so"
                try:
                    c32 = download_cached(f"{GITLAB_RAW_BASE}/upsilon/{rp_32}")
                    save_file(os.path.join(ver_dir, rp_32), c32)
                    print(f"    [+] 15.0.0/{rp_32} ({len(c32)} B)")
                except Exception:
                    pass

    print("\n[✓] Non-APK static migration complete! Saved in:", static_root)


if __name__ == "__main__":
    target_repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PureGoogleGappsBuilder")
    migrate_all(target_repo)
