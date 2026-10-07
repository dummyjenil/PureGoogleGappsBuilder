"""
Report Generator for PureGoogleGappsBuilder Analyzer.
Produces structured Markdown, Text, and JSON reports with:
  1. Overall Release Tree Summary Table
  2. Per-Package APK Version & Size Table (every APK with even 1 byte difference)
  3. Per-Package XML Semantic Diff Table & Exact Parsed Tag/Permission Breakdown
"""

import os
import re
import json


def format_size(b: int) -> str:
    sign = "-" if b < 0 else ""
    b = abs(b)
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024.0:
            return f"{sign}{b:.1f} {unit}" if unit != "B" else f"{sign}{int(b)} B"
        b /= 1024.0
    return f"{sign}{b:.1f} TB"


def _fmt_ver(vname: str, vcode) -> str:
    if not vname or vname == "N/A":
        return f"code:{vcode}" if vcode else "N/A"
    short_v = vname.split(" ")[0]
    if vcode:
        return f"{short_v} ({vcode})"
    return short_v


def generate_reports(
    comparison_results: list,
    json_path: str = "gapps_comparison_report.json",
    txt_path: str = "gapps_comparison_report.txt",
    md_path: str = "gapps_comparison_report.md",
):
    """Writes JSON, plain-text, and Markdown table reports and prints console output."""
    lines_txt = []
    lines_md = []

    def log_txt(msg: str = ""):
        print(msg)
        clean = re.sub(r"\033\[[0-9;]*m", "", msg)
        lines_txt.append(clean)

    # 1. Header & Overall Summary Table
    log_txt("=" * 95)
    log_txt("🔍 GAPPS DEEP COMPARATOR: PureGoogleGapps vs MindTheGapps (Tree + XML + APK Versions)")
    log_txt("=" * 95)
    log_txt(
        f"{'Target Version & Arch':<25} | {'Pure Size':<11} | {'MTG Size':<11} | {'XML Status':<20} | {'Tree Status'}"
    )
    log_txt("-" * 95)

    lines_md.append("# 🔍 GApps Deep Comparison Report (PureGoogleGapps vs MindTheGapps)\n")
    lines_md.append("## 1. Overall Release Summary\n")
    lines_md.append("| Android Version | Arch | Pure Size | MTG Size | Files (Pure/MTG) | XML Status | Tree Status |")
    lines_md.append("| :--- | :--- | :---: | :---: | :---: | :---: | :--- |")

    for comp in comparison_results:
        ver = comp["version"]
        arch = comp["arch"]
        xml_diffs = [
            x for x in comp.get("xml_comparisons", []) if not x.get("semantic_identical", True)
        ]
        xml_status = (
            "100% Semantic Match"
            if not xml_diffs
            else f"{len(xml_diffs)} XML(s) w/ Extra Perms"
        )
        tree_ok = comp["is_perfect_tree_match"]
        status_str = (
            "\033[1;32m[✓ 100% MATCH]\033[0m"
            if tree_ok
            else f"\033[1;33m[⚠ {len(comp['only_in_pure']) + len(comp['only_in_mtg'])} DIFFS]\033[0m"
        )
        md_tree = "✅ 100% Match" if tree_ok else f"⚠️ {len(comp['only_in_pure']) + len(comp['only_in_mtg'])} Diffs"

        log_txt(
            f"Android {ver:<7} ({arch:<6}) | {comp['pure_size_mb']:>6.1f} MB   | {comp['mtg_size_mb']:>6.1f} MB   | {xml_status:<20} | {status_str}"
        )
        lines_md.append(
            f"| **{ver}** | `{arch}` | {comp['pure_size_mb']:.1f} MB | {comp['mtg_size_mb']:.1f} MB | `{comp['pure_total_files']}/{comp['mtg_total_files']}` | {xml_status} | {md_tree} |"
        )

    log_txt("=" * 95)
    lines_md.append("\n---\n## 2. Detailed Per-Package Breakdown (XML Parsed Diffs & APK Versions)\n")

    # 2. Detailed Breakdown Per Package
    for comp in comparison_results:
        ver = comp["version"]
        arch = comp["arch"]
        log_txt(f"\n📦 ANDROID {ver} ({arch}) — Pure: {comp['pure_size_mb']:.2f} MB ({comp['pure_total_files']} files) vs MTG: {comp['mtg_size_mb']:.2f} MB ({comp['mtg_total_files']} files)")
        log_txt("-" * 95)

        lines_md.append(f"### 📦 Android {ver} (`{arch}`)\n")

        if not comp["is_perfect_tree_match"]:
            if comp["only_in_pure"]:
                log_txt(f"  + Files ONLY in PureGoogleGapps ({len(comp['only_in_pure'])}):")
                lines_md.append("**Files ONLY in PureGoogleGapps:**")
                for f in comp["only_in_pure"]:
                    log_txt(f"      + {f}")
                    lines_md.append(f"- `+ {f}`")
            if comp["only_in_mtg"]:
                log_txt(f"  - Files ONLY in MindTheGapps ({len(comp['only_in_mtg'])}):")
                lines_md.append("**Files ONLY in MindTheGapps:**")
                for f in comp["only_in_mtg"]:
                    log_txt(f"      - {f}")
                    lines_md.append(f"- `- {f}`")
            lines_md.append("")

        # XML Comparison Table (Any XML with even 1 byte difference is shown in detail)
        xml_list = comp.get("xml_comparisons", [])
        diff_xmls = [x for x in xml_list if not x["byte_identical"]]
        ident_xml_count = len(xml_list) - len(diff_xmls)

        log_txt(f"  [XML Analysis] {ident_xml_count}/{len(xml_list)} XML files are 100% Byte-Identical.")
        lines_md.append(f"#### 📄 XML Analysis (`{ident_xml_count}/{len(xml_list)}` Byte-Identical)\n")

        if diff_xmls:
            lines_md.append("| XML File | Pure Size | MTG Size | Diff | Parsed Semantic Status |")
            lines_md.append("| :--- | :---: | :---: | :---: | :--- |")
            for x in diff_xmls:
                db = x["pure_size"] - x["mtg_size"]
                sign = "+" if db > 0 else ""
                log_txt(
                    f"    • {x['path']} (Pure: {x['pure_size']} B vs MTG: {x['mtg_size']} B, {sign}{db} B) -> {x['status']}"
                )
                lines_md.append(
                    f"| `{os.path.basename(x['path'])}` | {x['pure_size']} B | {x['mtg_size']} B | `{sign}{db} B` | {x['status']} |"
                )
                for item in x.get("added_in_pure", []):
                    log_txt(f"        + [Added in Pure]   {item}")
                for item in x.get("missing_in_pure", []):
                    log_txt(f"        - [Missing in Pure] {item}")
            lines_md.append("")
            for x in diff_xmls:
                if x.get("added_in_pure") or x.get("missing_in_pure"):
                    lines_md.append(f"<details><summary>Parsed XML Diffs in <code>{x['path']}</code></summary>\n\n```diff")
                    for item in x.get("added_in_pure", []):
                        lines_md.append(f"+ {item}")
                    for item in x.get("missing_in_pure", []):
                        lines_md.append(f"- {item}")
                    lines_md.append("```\n</details>\n")

        # APK Comparison Table (Any APK with even 1 byte or CRC difference)
        apk_list = comp.get("apk_comparisons", [])
        diff_apks = [a for a in apk_list if not a["byte_identical"]]
        ident_apk_count = len(apk_list) - len(diff_apks)

        log_txt(f"  [APK Analysis] {ident_apk_count}/{len(apk_list)} APKs are 100% Byte-Identical.")
        lines_md.append(f"#### 📱 APK Version & Size Comparison (`{ident_apk_count}/{len(apk_list)}` Byte-Identical)\n")

        if diff_apks:
            log_txt(
                f"    {'APK Name':<32} | {'Pure Version (Code)':<28} | {'MTG Version (Code)':<28} | {'Pure Size':<10} | {'MTG Size':<10}"
            )
            log_txt("    " + "-" * 118)
            lines_md.append("| APK File | Package Name | Pure Version (`versionCode`) | MTG Version (`versionCode`) | Pure Size | MTG Size | Size Diff |")
            lines_md.append("| :--- | :--- | :--- | :--- | :---: | :---: | :---: |")

            for a in diff_apks:
                pv = _fmt_ver(a["pure_version_name"], a["pure_version_code"])
                mv = _fmt_ver(a["mtg_version_name"], a["mtg_version_code"])
                psz = format_size(a["pure_size"])
                msz = format_size(a["mtg_size"])
                dsz = format_size(a["diff_bytes"])
                if a["diff_bytes"] > 0 and not dsz.startswith("+"):
                    dsz = "+" + dsz
                log_txt(
                    f"    {a['name']:<32} | {pv:<28} | {mv:<28} | {psz:<10} | {msz:<10}"
                )
                lines_md.append(
                    f"| `{a['name']}` | `{a.get('package') or '-'}` | `{pv}` | `{mv}` | {psz} | {msz} | `{dsz}` |"
                )
            lines_md.append("")

    with open(json_path, "w") as f:
        json.dump(comparison_results, f, indent=2)
    with open(txt_path, "w") as f:
        f.write("\n".join(lines_txt) + "\n")
    with open(md_path, "w") as f:
        f.write("\n".join(lines_md) + "\n")

    print("\n" + "=" * 95)
    print(f"🎉 Reports saved to:\n   - {os.path.abspath(json_path)}\n   - {os.path.abspath(txt_path)}\n   - {os.path.abspath(md_path)}")
    print("=" * 95 + "\n")
