"""
Deep XML Parser & Semantic Comparator for GApps Packages.
Inspects EVERY .xml file in PureGoogleGapps vs MindTheGapps.
If even 1 byte or CRC32 differs, fetches and parses both XML trees to report exact
permission/feature/config additions or removals.
"""

import xml.etree.ElementTree as ET
from .zip_inspector import RemoteZipInspector


def _extract_xml_semantic_map(xml_bytes: bytes) -> dict:
    """
    Parses an Android XML config (privapp-permissions, default-permissions, sysconfig, etc.)
    into a normalized dict: { group_key: set(items) } for exact semantic diffing.
    """
    result = {}
    text = xml_bytes.decode("utf-8", errors="ignore").strip()
    if not text:
        return result

    root = ET.fromstring(text)
    for elem in root:
        tag = elem.tag
        if tag == "privapp-permissions":
            pkg = elem.get("package", "unknown")
            key = f"privapp:{pkg}"
            s = result.setdefault(key, set())
            for child in elem:
                if child.tag in ("permission", "deny-permission") and child.get("name"):
                    prefix = "deny:" if child.tag == "deny-permission" else ""
                    s.add(f"{prefix}{child.get('name')}")
        elif tag == "exception":
            pkg = elem.get("package", "unknown")
            key = f"default-perm:{pkg}"
            s = result.setdefault(key, set())
            for child in elem:
                if child.tag == "permission" and child.get("name"):
                    fixed = child.get("fixed", "")
                    s.add(f"{child.get('name')} (fixed={fixed})" if fixed else child.get("name"))
        else:
            key = f"<{tag}>"
            s = result.setdefault(key, set())
            attrs = " ".join(f'{k}="{v}"' for k, v in sorted(elem.attrib.items()))
            children_str = ";".join(
                f"{c.tag}(" + " ".join(f'{ck}="{cv}"' for ck, cv in sorted(c.attrib.items())) + ")"
                for c in elem
            )
            desc = f"{tag}[{attrs}]" + (f"{{{children_str}}}" if children_str else "")
            s.add(desc)
    return result


def compare_xml_files(pure_info: dict, mtg_info: dict) -> list:
    """
    Compares all common .xml files between PureGoogleGapps and MindTheGapps.
    Even a 1-byte or CRC32 difference triggers full XML extraction and semantic diffing.
    """
    pure_files = pure_info.get("files", {})
    mtg_files = mtg_info.get("files", {})
    common_xmls = sorted(
        f for f in (set(pure_files.keys()) & set(mtg_files.keys())) if f.endswith(".xml")
    )

    xml_reports = []
    for xf in common_xmls:
        p_meta = pure_files[xf]
        m_meta = mtg_files[xf]
        p_sz = p_meta["size"]
        m_sz = m_meta["size"]
        p_crc = p_meta.get("crc32", "")
        m_crc = m_meta.get("crc32", "")

        if p_sz == m_sz and p_crc == m_crc:
            xml_reports.append({
                "path": xf,
                "pure_size": p_sz,
                "mtg_size": m_sz,
                "byte_identical": True,
                "semantic_identical": True,
                "status": "100% Byte-Identical",
                "added_in_pure": [],
                "missing_in_pure": [],
            })
            continue

        # Even 1 byte or CRC difference -> extract and parse both XMLs!
        added_in_pure = []
        missing_in_pure = []
        semantic_identical = False
        status = "Modified"

        try:
            p_bytes = RemoteZipInspector.read_entry_bytes(p_meta, xf)
            m_bytes = RemoteZipInspector.read_entry_bytes(m_meta, xf)
            if p_bytes == m_bytes:
                xml_reports.append({
                    "path": xf,
                    "pure_size": p_sz,
                    "mtg_size": m_sz,
                    "byte_identical": True,
                    "semantic_identical": True,
                    "status": "100% Byte-Identical",
                    "added_in_pure": [],
                    "missing_in_pure": [],
                })
                continue

            p_map = _extract_xml_semantic_map(p_bytes)
            m_map = _extract_xml_semantic_map(m_bytes)
            all_keys = sorted(set(p_map.keys()) | set(m_map.keys()))

            for k in all_keys:
                p_set = p_map.get(k, set())
                m_set = m_map.get(k, set())
                label = k.split(":", 1)[1] if ":" in k else k
                for item in sorted(p_set - m_set):
                    added_in_pure.append(f"{label}: {item}")
                for item in sorted(m_set - p_set):
                    missing_in_pure.append(f"{label}: {item}")

            semantic_identical = len(added_in_pure) == 0 and len(missing_in_pure) == 0
            if semantic_identical:
                status = "100% Semantic Match (Formatting Only)"
            else:
                parts = []
                if added_in_pure:
                    parts.append(f"+{len(added_in_pure)} in Pure")
                if missing_in_pure:
                    parts.append(f"-{len(missing_in_pure)} in Pure")
                status = ", ".join(parts)
        except Exception as e:
            status = f"Parse Error ({e})"

        xml_reports.append({
            "path": xf,
            "pure_size": p_sz,
            "mtg_size": m_sz,
            "byte_identical": False,
            "semantic_identical": semantic_identical,
            "status": status,
            "added_in_pure": added_in_pure,
            "missing_in_pure": missing_in_pure,
        })

    return xml_reports

