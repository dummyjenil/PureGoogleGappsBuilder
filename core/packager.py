"""
Flashable ZIP Packager and Filesystem Structuring Module for PureGoogleGappsBuilder.
Formats APKs, libraries, permissions, addon.d, overlays, and Recovery installer metadata
using deduplicated `res/` + `patch/` assets and package-name fallback scanning across Android 9.0.0 to 16.0.0.
"""

import os
import shutil
import subprocess
import zipfile
import tempfile
from .constants import (
    SDK_MAP,
    APK_PACKAGE_MAP,
    ARCH_TO_TOYBOX,
    ADDOND_HEAD,
    ADDOND_TAIL,
    KNOWN_PRIVILEGED_PERMISSIONS,
)

from patch import RES_ROOT, get_patched_version_dir


def _get_version_static_dir(android_version: str) -> str:
    return get_patched_version_dir(android_version)


def load_target_file_list_for_version(android_version: str, arch: str) -> dict:
    """
    Loads proprietary file definitions from local `static/<android_version>/` directory.
    Returns a dict mapping destination paths -> source patterns.
    """
    ver_dir = _get_version_static_dir(android_version)
    prop_files = [
        "proprietary-files-common.txt",
        "proprietary-files-common-nongrouper.txt",
        f"proprietary-files-{arch}.txt",
        f"proprietary-files-{arch}-nongrouper.txt",
    ]

    if arch == "x86_64":
        prop_files.append("proprietary-files-x86.txt")
        if not os.path.isfile(os.path.join(ver_dir, "proprietary-files-x86_64-nongrouper.txt")):
            prop_files.append("proprietary-files-x86-nongrouper.txt")
    elif arch in ["arm64", "arm64-v8a"]:
        prop_files.append("proprietary-files-arm.txt")
        if not os.path.isfile(os.path.join(ver_dir, f"proprietary-files-{arch}-nongrouper.txt")):
            prop_files.append("proprietary-files-arm-nongrouper.txt")

    file_mappings = {}

    for pfile in prop_files:
        pfile_path = os.path.join(ver_dir, pfile)
        if not os.path.isfile(pfile_path):
            continue
        try:
            with open(pfile_path, "r", encoding="utf-8", errors="ignore") as f:
                data = f.read()
            for line in data.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("-"):
                    line = line[1:].strip()
                if "|" in line:
                    line = line.split("|")[0].strip()
                if ";" in line:
                    line = line.split(";")[0].strip()
                if ":" in line:
                    src, dst = line.split(":")
                    file_mappings[dst.strip()] = src.strip()
                else:
                    file_mappings[line] = line
        except Exception:
            pass

    return file_mappings


def find_android_jar(sdk_version: int):
    """
    Locates an aapt-v1-compatible android.jar (SDK <= 34) fast by inspecting SDK
    platforms directories without recursive globbing.
    """
    target_sdk = min(sdk_version, 34)
    sdk_roots = [
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
        "/usr/local/lib/android/sdk",
        "/usr/lib/android-sdk",
        os.path.expanduser("~/Android/Sdk"),
    ]
    for root in sdk_roots:
        if not root:
            continue
        exact = os.path.join(root, "platforms", f"android-{target_sdk}", "android.jar")
        if os.path.isfile(exact):
            return exact
        plat_dir = os.path.join(root, "platforms")
        if os.path.isdir(plat_dir):
            candidates = []
            for entry in os.listdir(plat_dir):
                if entry.startswith("android-"):
                    try:
                        ver = int(entry.split("-")[1])
                        if ver <= 34:
                            candidates.append((ver, entry))
                    except ValueError:
                        pass
            for _, entry in sorted(candidates, reverse=True):
                cand = os.path.join(plat_dir, entry, "android.jar")
                if os.path.isfile(cand):
                    return cand
    return None


def find_aapt_binary():
    """Finds aapt binary from PATH or Android build-tools"""
    w = shutil.which("aapt")
    if w:
        return w
    android_home = (
        os.environ.get("ANDROID_HOME")
        or os.environ.get("ANDROID_SDK_ROOT")
        or "/usr/local/lib/android/sdk"
    )
    btd = os.path.join(android_home, "build-tools")
    if os.path.isdir(btd):
        for ver in sorted(os.listdir(btd), reverse=True):
            cand = os.path.join(btd, ver, "aapt")
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def compile_local_overlays(android_version: str, sdk_version: int, target_overlay_dir: str):
    """
    Compiles Runtime Resource Overlays (RROs) for Android 12+ from `static/<version>/overlay/`
    using aapt (-0 arsc) and signs them with local AOSP testkeys.
    """
    if sdk_version < 31:
        return

    ver_dir = _get_version_static_dir(android_version)
    src_overlay_root = os.path.join(ver_dir, "overlay")
    if not os.path.isdir(src_overlay_root):
        return

    print(f"[*] Building Runtime Resource Overlays (RROs) for Android {android_version} (SDK {sdk_version})...")
    os.makedirs(target_overlay_dir, exist_ok=True)

    overlays_to_build = sorted([
        d for d in os.listdir(src_overlay_root)
        if os.path.isdir(os.path.join(src_overlay_root, d))
    ])

    android_jar = find_android_jar(sdk_version)
    aapt_bin = find_aapt_binary()
    apksigner_bin = shutil.which("apksigner")

    if not aapt_bin or not android_jar:
        print(f"    [!] Warning: aapt ({aapt_bin}) or android.jar ({android_jar}) not found. Skipping overlay compilation.")
        return

    pk8_file = os.path.join(RES_ROOT, "sign", "testkey.pk8")
    pem_file = os.path.join(RES_ROOT, "sign", "testkey.x509.pem")
    can_sign = bool(apksigner_bin and os.path.isfile(pk8_file) and os.path.isfile(pem_file))

    for overlay_name in overlays_to_build:
        out_apk = os.path.join(target_overlay_dir, f"{overlay_name}.apk")
        if os.path.exists(out_apk):
            continue

        ov_src_dir = os.path.join(src_overlay_root, overlay_name)
        manifest_file = os.path.join(ov_src_dir, "AndroidManifest.xml")
        res_dir = os.path.join(ov_src_dir, "res")
        if not os.path.isfile(manifest_file) or not os.path.isdir(res_dir):
            continue

        try:
            cmd = [
                aapt_bin, "package", "-f",
                "-M", manifest_file,
                "-S", res_dir,
                "-I", android_jar,
                "-0", "arsc",
                "-F", out_apk,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=15)
            if can_sign:
                subprocess.run(
                    [apksigner_bin, "sign", "--key", pk8_file, "--cert", pem_file, out_apk],
                    check=True, capture_output=True, timeout=15,
                )
                idsig = f"{out_apk}.idsig"
                if os.path.exists(idsig):
                    os.remove(idsig)
            print(f"    [✓] Compiled & Signed Overlay: {overlay_name}.apk ({os.path.getsize(out_apk)} bytes)")
        except Exception as e:
            print(f"    [!] Warning: Failed to build overlay {overlay_name}: {e}")


def copy_local_static_proprietary_files(android_version: str, arch: str, system_dir: str):
    """
    Copies static non-APK proprietary permission XMLs, default permissions, sysconfigs,
    certs, and arch libraries (like libjni_latinimegoogle.so) from `static/<version>/`.
    """
    ver_dir = _get_version_static_dir(android_version)
    print(f"[*] Applying static proprietary configs & libs for Android {android_version} ({arch})...")
    arch_prefix = f"{arch}/proprietary"
    if not os.path.isdir(os.path.join(ver_dir, arch_prefix)) and arch == "x86_64":
        arch_prefix = "x86/proprietary"
    for prefix in ["common/proprietary", arch_prefix]:
        src_root = os.path.join(ver_dir, prefix)
        if not os.path.isdir(src_root):
            continue
        for root, _, files in os.walk(src_root):
            for fname in sorted(files):
                if fname.endswith(".apk"):
                    continue
                src_full = os.path.join(root, fname)
                sub_rel = os.path.relpath(src_full, src_root).replace("\\", "/")
                dst_path = os.path.join(system_dir, sub_rel)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_full, dst_path)
                print(f"    [+] Static Proprietary ({prefix}): {sub_rel} ({os.path.getsize(dst_path)} bytes)")


def _extract_privileged_perms_from_apk(aapt_bin: str, apk_or_jar_path: str) -> set:
    """Extracts any <permission> defined with PROTECTION_FLAG_PRIVILEGED (0x10) from AndroidManifest.xml"""
    found = set()
    if not apk_or_jar_path or not os.path.isfile(apk_or_jar_path):
        return found
    try:
        out = subprocess.check_output(
            [aapt_bin, "dump", "xmltree", apk_or_jar_path, "AndroidManifest.xml"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        cur_perm = None
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("E: permission "):
                cur_perm = None
            elif cur_perm is None and "A: android:name(" in s and '"' in s:
                cur_perm = s.split('"')[1]
            elif cur_perm and "A: android:protectionLevel(" in s and ")0x" in s:
                val = int(s.split(")0x")[1], 16)
                if val & 0x10:
                    found.add(cur_perm)
                cur_perm = None
    except Exception:
        pass
    return found


def sync_privapp_permissions(system_dir: str, sdk_version: int = 34):
    """
    Scans every APK placed in priv-app/ across partitions (product, system_ext, system)
    using aapt and guarantees all requested signature|privileged permissions are whitelisted
    in that partition's etc/permissions/privapp-permissions-google*.xml.
    """
    import xml.etree.ElementTree as ET
    aapt_bin = find_aapt_binary()
    if not aapt_bin:
        return

    privileged_allowlist = set(KNOWN_PRIVILEGED_PERMISSIONS)
    android_jar = find_android_jar(sdk_version)
    if android_jar:
        privileged_allowlist |= _extract_privileged_perms_from_apk(aapt_bin, android_jar)

    for r, _, files in os.walk(system_dir):
        for f in files:
            if f.endswith(".apk"):
                privileged_allowlist |= _extract_privileged_perms_from_apk(aapt_bin, os.path.join(r, f))

    partitions = [
        ("product", os.path.join(system_dir, "product"), "privapp-permissions-google-product.xml"),
        ("system_ext", os.path.join(system_dir, "system_ext"), "privapp-permissions-google-system-ext.xml"),
        ("system", system_dir, "privapp-permissions-google.xml"),
    ]

    for part_name, part_dir, default_xml_name in partitions:
        priv_app_dir = os.path.join(part_dir, "priv-app")
        if not os.path.isdir(priv_app_dir):
            continue

        perm_dir = os.path.join(part_dir, "etc", "permissions")
        os.makedirs(perm_dir, exist_ok=True)

        existing_xmls = sorted([
            os.path.join(perm_dir, f) for f in os.listdir(perm_dir)
            if f.startswith("privapp-permissions") and f.endswith(".xml")
        ])
        target_xml = os.path.join(perm_dir, default_xml_name)
        if not existing_xmls:
            existing_xmls = [target_xml]
        elif target_xml not in existing_xmls:
            target_xml = existing_xmls[0]

        xml_trees = {}
        pkg_nodes = {}
        pkg_perms = {}

        for xfile in existing_xmls:
            if os.path.exists(xfile):
                try:
                    t = ET.parse(xfile)
                    r_el = t.getroot()
                except Exception:
                    r_el = ET.Element("permissions")
                    t = ET.ElementTree(r_el)
            else:
                r_el = ET.Element("permissions")
                t = ET.ElementTree(r_el)
            xml_trees[xfile] = (t, r_el, False)
            for elem in r_el.findall("privapp-permissions"):
                p_name = elem.get("package")
                if p_name:
                    pkg_nodes[p_name] = (xfile, elem)
                    s = pkg_perms.setdefault(p_name, set())
                    for child in elem.findall("permission"):
                        s.add(child.get("name"))
                    for child in elem.findall("deny-permission"):
                        s.add(child.get("name"))

        for r, _, files in os.walk(priv_app_dir):
            for f in sorted(files):
                if not f.endswith(".apk"):
                    continue
                apk_path = os.path.join(r, f)
                try:
                    out = subprocess.check_output([aapt_bin, "dump", "permissions", apk_path], text=True, timeout=15)
                    lines = out.splitlines()
                    if not lines:
                        continue
                    pkg = lines[0].split(": ")[1].strip()
                    req = []
                    for l in lines[1:]:
                        if "uses-permission:" in l and "name='" in l:
                            perm = l.split("name='")[1].split("'")[0]
                            if perm in privileged_allowlist and perm not in req:
                                req.append(perm)
                    if pkg in pkg_nodes:
                        xfile, node = pkg_nodes[pkg]
                    else:
                        xfile = target_xml
                        _, r_el, _ = xml_trees[xfile]
                        node = ET.SubElement(r_el, "privapp-permissions", {"package": pkg})
                        pkg_nodes[pkg] = (xfile, node)
                    s = pkg_perms.setdefault(pkg, set())
                    for perm in req:
                        if perm not in s:
                            ET.SubElement(node, "permission", {"name": perm})
                            s.add(perm)
                            t, r_el, _ = xml_trees[xfile]
                            xml_trees[xfile] = (t, r_el, True)
                except Exception:
                    pass

        for xfile, (t, r_el, mod) in xml_trees.items():
            if mod:
                try:
                    ET.indent(t, space="    ")
                except Exception:
                    pass
                t.write(xfile, encoding="utf-8", xml_declaration=True)
                print(f"    [✓] Auto-synchronized privileged permissions for '{part_name}' -> {os.path.basename(xfile)}")


def _index_extracted_apks_by_package(extracted_dir: str) -> dict:
    """
    Reads the initial binary AndroidManifest.xml (AXML) from every APK in the unpacked
    Google Official SDK image to map `package_name -> [apk_paths]`.
    Enables package-name fallback lookup when Google renames APKs across SDK releases.
    """
    from analyzer.apk_analyzer import parse_axml_version
    pkg_to_apks = {}
    print("[*] Indexing all APKs inside unpacked Google SDK image by package name (AXML header scan)...")
    for root, _, files in os.walk(extracted_dir):
        for f in sorted(files):
            if not f.endswith(".apk"):
                continue
            full_p = os.path.join(root, f)
            try:
                with zipfile.ZipFile(full_p, "r") as zf:
                    axml_bytes = zf.read("AndroidManifest.xml")
                meta = parse_axml_version(axml_bytes)
                pkg = meta.get("package", "")
                if pkg:
                    pkg_to_apks.setdefault(pkg, []).append(full_p)
                    rel_p = os.path.relpath(full_p, extracted_dir).replace("\\", "/")
                    vname = meta.get("versionName", "")
                    vcode = meta.get("versionCode", "")
                    if pkg.startswith("com.google.") or pkg.startswith("com.android.vending"):
                        print(f"    [SDK-APK] {pkg:<45} -> {rel_p} (v={vname}, code={vcode})")
            except Exception:
                pass
    print(f"    [✓] Indexed {len(pkg_to_apks)} unique APK package names in Google SDK image.")
    return pkg_to_apks


def fetch_missing_apks_via_github_range(
    android_version: str,
    arch: str,
    still_missing: list,
    system_dir: str,
    included_files: list,
):
    """
    For standalone AOSP sync adapters (e.g. GoogleCalendarSyncAdapter, GoogleContactsSyncAdapter,
    PrebuiltExchange3Google) that are absent from Google's Emulator SDK images, extracts only their
    compressed byte slices on-the-fly via HTTP Range from GitHub release archives and verifies
    their AndroidManifest package name against APK_PACKAGE_MAP.
    """
    import json
    import io
    import urllib.request
    from analyzer.zip_inspector import RemoteZipInspector
    from analyzer.apk_analyzer import parse_axml_version

    api_url = "https://api.github.com/repos/s1204IT/MindTheGappsBuilder/releases?per_page=100"
    headers = {"User-Agent": "Mozilla/5.0 (PureGoogleGappsBuilder/2.0)"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    zip_url = None
    search_versions = [android_version]
    if android_version == "12.0.0":
        search_versions.append("12.1.0")
    elif android_version == "16.0.0":
        search_versions.append("15.0.0")

    search_archs = [arch]
    if arch == "x86_64":
        search_archs.append("x86")

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            releases = json.loads(resp.read().decode("utf-8"))
        for target_ver in search_versions:
            for target_arch in search_archs:
                prefix = f"MindTheGapps-{target_ver}-{target_arch}-"
                for rel in releases:
                    for asset in rel.get("assets", []):
                        name = asset.get("name", "")
                        if name.startswith(prefix) and name.endswith(".zip") and not name.endswith(".sum"):
                            zip_url = asset.get("browser_download_url", "")
                            break
                    if zip_url:
                        break
                if zip_url:
                    break
            if zip_url:
                break
    except Exception as e:
        print(f"    [!] Warning: Could not query release index for range fallback ({e})")
        return

    if not zip_url:
        return

    remote_info, err = RemoteZipInspector.inspect(zip_url)
    if not remote_info or err:
        return

    remote_files = remote_info.get("files", {})
    for dst_rel, bname, expected_pkg in still_missing:
        if not bname.endswith(".apk"):
            continue
        zip_key = f"system/{dst_rel}"
        entry_meta = remote_files.get(zip_key)
        if not entry_meta:
            for rpath, rmeta in remote_files.items():
                if os.path.basename(rpath).lower() == bname:
                    zip_key = rpath
                    entry_meta = rmeta
                    break
        if not entry_meta:
            continue

        try:
            apk_bytes = RemoteZipInspector.read_entry_bytes(entry_meta, zip_key)
            if not apk_bytes:
                continue
            pkg_name = expected_pkg
            vname = ""
            vcode = ""
            try:
                with zipfile.ZipFile(io.BytesIO(apk_bytes), "r") as zf:
                    axml = zf.read("AndroidManifest.xml")
                meta = parse_axml_version(axml)
                pkg_name = meta.get("package") or expected_pkg
                vname = meta.get("versionName", "")
                vcode = meta.get("versionCode", "")
            except Exception:
                pass

            dst_path = os.path.join(system_dir, dst_rel)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            with open(dst_path, "wb") as f:
                f.write(apk_bytes)
            included_files.append(dst_rel)
            print(
                f"    [+] Included [range-fallback:{pkg_name}]: {dst_rel} "
                f"({len(apk_bytes)/1024:.1f} KB, v={vname}, code={vcode})"
            )
        except Exception as e:
            print(f"    [!] Failed range-fallback for {dst_rel}: {e}")


def structure_gapps_hierarchy(extracted_dir: str, target_pkg_dir: str, android_version: str, arch: str):
    """
    Structures genuine GApps files into MindTheGapps-identical hierarchy.
    Uses path matching, filename alias matching, and package-name AXML fallback scanning.
    """
    print(f"[*] Structuring GApps hierarchy for Android {android_version} ({arch})...")
    os.makedirs(target_pkg_dir, exist_ok=True)

    system_dir = os.path.join(target_pkg_dir, "system")
    os.makedirs(system_dir, exist_ok=True)

    sdk_version = SDK_MAP.get(android_version, 33)
    ver_dir = _get_version_static_dir(android_version)

    # 1. Load expected file list from local static/<version>/ definitions
    target_mappings = load_target_file_list_for_version(android_version, arch)
    print(f"    [✓] Loaded {len(target_mappings)} target file definitions from static/{android_version}/.")

    # Index all extracted files by relative path, by base filename, and by APK package name
    extracted_files_map = {}
    extracted_basename_map = {}
    for root, _, files in os.walk(extracted_dir):
        for f in files:
            full_p = os.path.join(root, f)
            rel_p = os.path.relpath(full_p, extracted_dir).replace("\\", "/")
            extracted_files_map[rel_p.lower()] = full_p
            base_key = f.lower()
            extracted_basename_map.setdefault(base_key, []).append(full_p)

    extracted_pkg_map = _index_extracted_apks_by_package(extracted_dir)

    included_files = []
    missing_targets = []

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
        "speechservicesbygoogle.apk": ["speechservicesbygoogle.apk", "googletts.apk"],
        "googletts.apk": ["googletts.apk", "speechservicesbygoogle.apk"],
        "markupgoogle_v2.apk": ["markupgoogle_v2.apk", "markupgoogle.apk"],
        "markupgoogle.apk": ["markupgoogle.apk", "markupgoogle_v2.apk"],
        "velvettitan.apk": ["velvettitan.apk", "velvet.apk"],
        "googlecalendarsyncadapter.apk": ["googlecalendarsyncadapter.apk", "calendargoogleprebuilt.apk"],
        "googlecontactssyncadapter.apk": ["googlecontactssyncadapter.apk", "googlecontacts.apk"],
        "prebuiltexchange3google.apk": ["prebuiltexchange3google.apk", "exchange3google.apk", "prebuiltgmail.apk"],
    }

    PACKAGE_FALLBACK_EQUIVALENTS = {
        "com.google.android.syncadapters.calendar": ["com.google.android.syncadapters.calendar", "com.google.android.calendar"],
        "com.google.android.syncadapters.contacts": ["com.google.android.syncadapters.contacts", "com.google.android.contacts"],
        "com.google.android.gm.exchange": ["com.google.android.gm.exchange", "com.google.android.gm"],
    }

    # 2. Match and copy files according to target mappings
    for dst_rel, src_rel in target_mappings.items():
        dst_path = os.path.join(system_dir, dst_rel)
        matched_src = None
        match_method = "path"
        base_fname = os.path.basename(src_rel).lower()

        if src_rel.lower() in extracted_files_map:
            matched_src = extracted_files_map[src_rel.lower()]
        elif dst_rel.lower() in extracted_files_map:
            matched_src = extracted_files_map[dst_rel.lower()]
        else:
            candidates = extracted_basename_map.get(base_fname, [])
            if not candidates and base_fname in ALIASES:
                for alias_name in ALIASES[base_fname]:
                    if alias_name in extracted_basename_map:
                        candidates = extracted_basename_map[alias_name]
                        match_method = f"alias:{alias_name}"
                        break

            # Package-Name Fallback Lookup inside Google SDK Image
            if not candidates and base_fname.endswith(".apk"):
                expected_pkg = APK_PACKAGE_MAP.get(base_fname)
                if expected_pkg:
                    for cand_pkg in PACKAGE_FALLBACK_EQUIVALENTS.get(expected_pkg, [expected_pkg]):
                        if cand_pkg in extracted_pkg_map:
                            candidates = extracted_pkg_map[cand_pkg]
                            match_method = f"package-fallback:{cand_pkg}"
                            break

            if candidates:
                part_hint = dst_rel.split("/")[0].lower() if "/" in dst_rel else ""
                preferred = [c for c in candidates if part_hint in c.lower()]
                matched_src = preferred[0] if preferred else candidates[0]

        if matched_src and os.path.exists(matched_src):
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(matched_src, dst_path)
            included_files.append(dst_rel)
            src_short = os.path.relpath(matched_src, extracted_dir).replace("\\", "/")
            print(f"    [+] Included [{match_method}]: {dst_rel} <- {src_short} ({os.path.getsize(dst_path)/1024:.1f} KB)")
        else:
            missing_targets.append((dst_rel, base_fname, APK_PACKAGE_MAP.get(base_fname, "N/A")))

    # 3. Copy local non-APK static proprietary XML permissions, sysconfigs & arch libs
    copy_local_static_proprietary_files(android_version, arch, system_dir)

    # Resolve any standalone sync-adapter APKs absent from Google SDK image via HTTP Range
    still_missing = [
        (dst_rel, bname, pkg)
        for (dst_rel, bname, pkg) in missing_targets
        if not os.path.exists(os.path.join(system_dir, dst_rel))
    ]
    if still_missing:
        print(f"    [*] {len(still_missing)} standalone target(s) absent from Google SDK image; resolving via HTTP Range...")
        fetch_missing_apks_via_github_range(
            android_version, arch, still_missing, system_dir, included_files
        )
        unresolved = [
            (dst_rel, bname, pkg)
            for (dst_rel, bname, pkg) in still_missing
            if not os.path.exists(os.path.join(system_dir, dst_rel))
        ]
        if unresolved:
            print(f"    [!] Notice: {len(unresolved)} target(s) still unresolved:")
            for dst_rel, bname, pkg in unresolved:
                print(f"        - MISSING: {dst_rel} (filename={bname}, expected_pkg={pkg})")

    # 4. Auto-synchronize privapp-permissions for all extracted APKs to prevent bootloops
    sync_privapp_permissions(system_dir, sdk_version)

    # 5. Compile local RRO overlays
    overlay_dir = os.path.join(system_dir, "product", "overlay")
    compile_local_overlays(android_version, sdk_version, overlay_dir)

    # 6. Copy architecture-specific toybox binary from res/toybox/ (for Android 10+ / SDK >= 29)
    if sdk_version >= 29:
        toybox_name = ARCH_TO_TOYBOX.get(arch, "toybox-x86_64")
        toybox_src = os.path.join(RES_ROOT, "toybox", toybox_name)
        toybox_dest = os.path.join(target_pkg_dir, "toybox")
        if os.path.isfile(toybox_src):
            shutil.copy2(toybox_src, toybox_dest)
            os.chmod(toybox_dest, 0o755)
            print(f"    [✓] Copied local {toybox_name} -> toybox ({os.path.getsize(toybox_dest)/1024:.1f} KB)")

    # 7. Add Recovery Installer & Addon.d Survival Scripts
    print("[*] Setting up update-binary and addon.d scripts from patched res/...")
    meta_inf_dir = os.path.join(target_pkg_dir, "META-INF", "com", "google", "android")
    os.makedirs(meta_inf_dir, exist_ok=True)

    update_bin_dest = os.path.join(meta_inf_dir, "update-binary")
    update_bin_src = os.path.join(ver_dir, "update-binary")
    if os.path.isfile(update_bin_src):
        shutil.copy2(update_bin_src, update_bin_dest)
        os.chmod(update_bin_dest, 0o755)
        print(f"    [✓] Copied patched {android_version}/update-binary")
    else:
        with open(update_bin_dest, "w", newline="\n") as f:
            f.write("#!/sbin/sh\n# Fallback\n")
        os.chmod(update_bin_dest, 0o755)

    updater_script_dest = os.path.join(meta_inf_dir, "updater-script")
    with open(updater_script_dest, "w", newline="\n") as f:
        f.write("# Dummy updater-script for TWRP\n")

    addon_dir = os.path.join(system_dir, "addon.d")
    os.makedirs(addon_dir, exist_ok=True)
    with open(os.path.join(addon_dir, "addond_head"), "w", newline="\n") as f:
        f.write(ADDOND_HEAD.strip() + "\n")
    with open(os.path.join(addon_dir, "addond_tail"), "w", newline="\n") as f:
        f.write(ADDOND_TAIL.strip() + "\n")

    if sdk_version >= 29:
        build_prop_path = os.path.join(target_pkg_dir, "build.prop")
        with open(build_prop_path, "w", newline="\n") as f:
            f.write(f"arch={arch}\n")
            f.write(f"version={sdk_version}\n")
            f.write(f"version_nice={android_version}\n")

    return included_files


def create_flashable_zip(source_dir: str, output_zip_path: str):
    """
    Packs directory into deterministic Recovery-flashable ZIP and signs with local AOSP testkeys.
    """
    print(f"[*] Packaging and Signing Recovery Flashable ZIP: {os.path.basename(output_zip_path)}...")
    output_zip_path = os.path.abspath(output_zip_path)
    if os.path.exists(output_zip_path):
        os.remove(output_zip_path)

    pk8_file = os.path.join(RES_ROOT, "sign", "testkey.pk8")
    pem_file = os.path.join(RES_ROOT, "sign", "testkey.x509.pem")

    otacert_path = os.path.join(source_dir, "META-INF", "com", "android", "otacert")
    if os.path.isfile(pem_file):
        os.makedirs(os.path.dirname(otacert_path), exist_ok=True)
        shutil.copy2(pem_file, otacert_path)

    deterministic_datetime = (2009, 1, 1, 0, 0, 0)

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for root, _, files in os.walk(source_dir):
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

    has_apksigner = shutil.which("apksigner") is not None
    if has_apksigner and os.path.isfile(pk8_file) and os.path.isfile(pem_file):
        try:
            cmd = [
                "apksigner", "sign",
                "--v1-signer-name", "CERT",
                "--key", pk8_file,
                "--cert", pem_file,
                "--min-sdk-version", "28",
                output_zip_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            print("    [✓] ZIP signed successfully with local AOSP testkey (apksigner)")
        except Exception as e:
            print(f"    [!] Warning: Failed to sign ZIP: {e}")
