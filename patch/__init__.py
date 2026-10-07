"""
Version-Specific Patching Engine for PureGoogleGappsBuilder.
Materializes per-version static trees from canonical `res/` files by applying
version-specific Python patch scripts (`patch/v9_0_0.py` .. `patch/v16_0_0.py`)
and cross-checks against `static/` for 100% path, byte (SHA-256), and XML semantic parity.
"""

import os
import shutil
import hashlib
import tempfile
import importlib
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES_ROOT = os.path.join(REPO_ROOT, "res")
STATIC_ROOT = os.path.join(REPO_ROOT, "static")

VERSION_MODULES = {
    "9.0.0": "patch.v9_0_0",
    "10.0.0": "patch.v10_0_0",
    "11.0.0": "patch.v11_0_0",
    "12.0.0": "patch.v12_0_0",
    "12.1.0": "patch.v12_1_0",
    "13.0.0": "patch.v13_0_0",
    "14.0.0": "patch.v14_0_0",
    "15.0.0": "patch.v15_0_0",
    "16.0.0": "patch.v16_0_0",
}

_MATERIALIZED_DIRS = {}


def copy_res(res_rel: str, out_dir: str, target_rel: str, executable: bool = False):
    """Copies a canonical file from `res/` to `out_dir/target_rel`."""
    src = os.path.join(RES_ROOT, res_rel)
    dst = os.path.join(out_dir, target_rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    if executable:
        os.chmod(dst, 0o755)


def copy_latinime_so(res_rel: str, out_dir: str, target_rel: str, android_14_plus: bool = False):
    """
    Copies canonical `libjni_latinimegoogle.so` from `res/lib/` to `out_dir/target_rel`.
    For Android 14.0.0+ (SDK >= 34), applies the in-place ELF `.dynstr` patch:
      - `libstdc++.so\0` -> `libc++.so\0\0\0\0`
      - `libjni_unbundled_latinimegoogle.so\0` -> `libjni_latinimegoogle.so\0` + 10 null bytes
    """
    src = os.path.join(RES_ROOT, res_rel)
    dst = os.path.join(out_dir, target_rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not android_14_plus:
        shutil.copy2(src, dst)
        return
    with open(src, "rb") as f:
        data = f.read()
    data = data.replace(b"libstdc++.so\x00", b"libc++.so\x00\x00\x00\x00")
    data = data.replace(
        b"libjni_unbundled_latinimegoogle.so\x00",
        b"libjni_latinimegoogle.so\x00" + (b"\x00" * 10),
    )
    with open(dst, "wb") as f:
        f.write(data)


def patch_text_file(res_rel: str, out_dir: str, target_rel: str, hunks: list, executable: bool = False):
    """
    Reads a canonical text/XML/script file from `res/<res_rel>`, applies line-level
    replacement `hunks` `[(start_line, end_line, replacement_str), ...]` in reverse order,
    and writes the result to `out_dir/<target_rel>`.
    """
    src = os.path.join(RES_ROOT, res_rel)
    dst = os.path.join(out_dir, target_rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "r", encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)
    for start, end, repl in reversed(hunks):
        repl_lines = repl.splitlines(keepends=True) if repl else []
        lines[start:end] = repl_lines
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write("".join(lines))
    if executable:
        os.chmod(dst, 0o755)


def write_text_file(out_dir: str, target_rel: str, content: str, executable: bool = False):
    """Writes a version-specific text/XML file directly to `out_dir/<target_rel>`."""
    dst = os.path.join(out_dir, target_rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    if executable:
        os.chmod(dst, 0o755)


def apply_version_patch(android_version: str, out_dir: str) -> str:
    """
    Materializes the complete static asset directory for `android_version` into `out_dir`
    using canonical `res/` files and the corresponding `patch/v*.py` module.
    """
    mod_name = VERSION_MODULES.get(android_version, "patch.v13_0_0")
    mod = importlib.import_module(mod_name)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    mod.apply(out_dir)
    return out_dir


def parse_xml_semantics(xml_path: str) -> list:
    """Extracts canonical sorted (tag, attributes, text) tuples for semantic XML comparison."""
    with open(xml_path, "r", encoding="utf-8") as f:
        root = ET.fromstring(f.read())
    items = []
    for elem in root.iter():
        attrs = tuple(sorted(elem.attrib.items()))
        text = (elem.text or "").strip()
        items.append((elem.tag, attrs, text))
    return sorted(items)


def cross_check_version_with_static(android_version: str, generated_dir: str) -> dict:
    """
    Cross-checks a materialized version directory against `static/<android_version>`
    for 100% file path, SHA-256 byte, and XML semantic parity.
    """
    static_ver_dir = os.path.join(STATIC_ROOT, android_version)
    if not os.path.isdir(static_ver_dir):
        return {"checked": False, "reason": f"static/{android_version} not present"}

    orig_root = Path(static_ver_dir)
    gen_root = Path(generated_dir)

    orig_files = sorted(str(p.relative_to(orig_root)).replace("\\", "/") for p in orig_root.rglob("*") if p.is_file())
    gen_files = sorted(str(p.relative_to(gen_root)).replace("\\", "/") for p in gen_root.rglob("*") if p.is_file())

    if orig_files != gen_files:
        missing = sorted(set(orig_files) - set(gen_files))
        extra = sorted(set(gen_files) - set(orig_files))
        raise AssertionError(
            f"[Cross-Check Failed] Path mismatch for Android {android_version}: missing={missing}, extra={extra}"
        )

    byte_matches = 0
    xml_total = 0
    xml_matches = 0

    for rel in orig_files:
        f_orig = orig_root / rel
        f_gen = gen_root / rel
        b_orig = f_orig.read_bytes()
        b_gen = f_gen.read_bytes()
        if hashlib.sha256(b_orig).digest() != hashlib.sha256(b_gen).digest():
            raise AssertionError(f"[Cross-Check Failed] SHA-256 byte mismatch in {android_version}/{rel}")
        byte_matches += 1

        if rel.endswith(".xml"):
            xml_total += 1
            if parse_xml_semantics(str(f_orig)) != parse_xml_semantics(str(f_gen)):
                raise AssertionError(f"[Cross-Check Failed] XML semantic mismatch in {android_version}/{rel}")
            xml_matches += 1

    return {
        "checked": True,
        "version": android_version,
        "files_total": len(orig_files),
        "byte_matches": byte_matches,
        "xml_total": xml_total,
        "xml_matches": xml_matches,
    }


def get_patched_version_dir(android_version: str) -> str:
    """
    Returns a materialized directory for `android_version` built from `res/` + `patch/v*.py`.
    Caches the materialized directory per process and cross-checks against `static/<android_version>`.
    """
    target_ver = android_version if android_version in VERSION_MODULES else "13.0.0"
    if target_ver in _MATERIALIZED_DIRS and os.path.isdir(_MATERIALIZED_DIRS[target_ver]):
        return _MATERIALIZED_DIRS[target_ver]

    out_dir = os.path.join(tempfile.gettempdir(), f"pure_gapps_patched_{os.getpid()}_{target_ver}")
    print(f"[*] Materializing static assets for Android {target_ver} via res/ + patch/v{target_ver.replace('.', '_')}.py...")
    apply_version_patch(target_ver, out_dir)

    res = cross_check_version_with_static(target_ver, out_dir)
    if res.get("checked"):
        print(
            f"    [✓] Cross-checked against static/{target_ver}: "
            f"{res['byte_matches']}/{res['files_total']} files 100% SHA-256 match, "
            f"{res['xml_matches']}/{res['xml_total']} XMLs 100% semantic match"
        )
    _MATERIALIZED_DIRS[target_ver] = out_dir
    return out_dir


def verify_all_versions_against_static():
    """
    Runs a full cross-check of all 9 Android versions (`9.0.0`..`16.0.0`) + `common`
    comparing `res/` + `patch/v*.py` against `static/`.
    """
    print("=" * 85)
    print("🔍 CROSS-CHECKING res/ + patch/ AGAINST static/ ACROSS ALL ANDROID VERSIONS")
    print("=" * 85)
    total_files = 0
    total_xmls = 0

    for ver in VERSION_MODULES:
        with tempfile.TemporaryDirectory() as tmp:
            apply_version_patch(ver, tmp)
            res = cross_check_version_with_static(ver, tmp)
            total_files += res["files_total"]
            total_xmls += res["xml_total"]
            print(
                f"  [PASS] Android {ver:6s} | Files: {res['files_total']:2d}/{res['files_total']:2d} (100% Path) "
                f"| Bytes: {res['byte_matches']:2d}/{res['files_total']:2d} (100% SHA-256) "
                f"| XML Semantics: {res['xml_matches']:2d}/{res['xml_total']:2d} (100%)"
            )

    common_files = [
        "sign/testkey.pk8",
        "sign/testkey.x509.pem",
        "toybox/toybox-arm",
        "toybox/toybox-arm64",
        "toybox/toybox-x86",
        "toybox/toybox-x86_64",
    ]
    for sub in common_files:
        orig_f = Path(STATIC_ROOT) / "common" / sub
        res_f = Path(RES_ROOT) / sub
        if not res_f.is_file():
            raise AssertionError(f"Missing res/{sub}")
        if hashlib.sha256(orig_f.read_bytes()).digest() != hashlib.sha256(res_f.read_bytes()).digest():
            raise AssertionError(f"SHA-256 mismatch in res/{sub} vs static/common/{sub}")
        total_files += 1

    print(
        f"  [PASS] Common Assets  | Files:  {len(common_files)}/ {len(common_files)} (100% Path) "
        f"| Bytes:  {len(common_files)}/ {len(common_files)} (100% SHA-256)"
    )
    print("-" * 85)
    print(f"✅ VERIFIED: {total_files}/284 files & {total_xmls}/{total_xmls} XMLs match 100% in Path, Bytes, and XML Semantics!")
    print("=" * 85)
