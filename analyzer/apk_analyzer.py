"""
APK Version & Metadata Analyzer for GApps Packages.
Extracts package name, versionName, and versionCode from binary AndroidManifest.xml (AXML)
for every APK that has even a 1-byte or CRC32 difference between PureGoogleGapps and MindTheGapps.
"""

import io
import os
import struct
import zlib
import zipfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from core.constants import APK_PACKAGE_MAP
from .zip_inspector import RemoteZipInspector


def parse_axml_version(axml_bytes: bytes) -> dict:
    """
    Pure-Python Binary AndroidManifest.xml (AXML) parser.
    Extracts package, versionName, and versionCode without requiring external tools.
    """
    if not axml_bytes or len(axml_bytes) < 36:
        return {}
    magic = struct.unpack("<H", axml_bytes[:2])[0]
    if magic != 0x0003:
        return {}

    try:
        (
            sp_type,
            sp_hdr_size,
            sp_size,
            str_count,
            style_count,
            flags,
            str_start,
            style_start,
        ) = struct.unpack("<HHIIIIII", axml_bytes[8:36])
        is_utf8 = (flags & (1 << 8)) != 0
        offsets = [
            struct.unpack("<I", axml_bytes[36 + i * 4 : 40 + i * 4])[0]
            for i in range(str_count)
        ]
        strings = []
        pool_base = 8 + str_start
        for off in offsets:
            pos = pool_base + off
            if is_utf8:
                if axml_bytes[pos] & 0x80:
                    pos += 2
                else:
                    pos += 1
                blen = axml_bytes[pos]
                if blen & 0x80:
                    blen = ((blen & 0x7F) << 8) | axml_bytes[pos + 1]
                    pos += 2
                else:
                    pos += 1
                strings.append(
                    axml_bytes[pos : pos + blen].decode("utf-8", errors="ignore")
                )
            else:
                clen = struct.unpack("<H", axml_bytes[pos : pos + 2])[0]
                if clen & 0x8000:
                    clen = ((clen & 0x7FFF) << 16) | struct.unpack(
                        "<H", axml_bytes[pos + 2 : pos + 4]
                    )[0]
                    pos += 4
                else:
                    pos += 2
                strings.append(
                    axml_bytes[pos : pos + clen * 2].decode(
                        "utf-16le", errors="ignore"
                    )
                )

        ptr = 8 + sp_size
        res_ids = []
        while ptr + 8 <= len(axml_bytes):
            ctype, chdr, csize = struct.unpack("<HHI", axml_bytes[ptr : ptr + 8])
            if ctype == 0x0180:  # XML_RESOURCE_MAP_TYPE
                count = (csize - chdr) // 4
                res_ids = [
                    struct.unpack(
                        "<I", axml_bytes[ptr + chdr + i * 4 : ptr + chdr + (i + 1) * 4]
                    )[0]
                    for i in range(count)
                ]
            elif ctype == 0x0102:  # XML_START_ELEMENT_TYPE
                name_idx = struct.unpack("<i", axml_bytes[ptr + 20 : ptr + 24])[0]
                elem_name = strings[name_idx] if 0 <= name_idx < len(strings) else ""
                if elem_name == "manifest":
                    attr_start, attr_size, attr_count = struct.unpack(
                        "<HHH", axml_bytes[ptr + 24 : ptr + 30]
                    )
                    ver_code = None
                    ver_name = None
                    pkg_name = None
                    abase = ptr + 16 + attr_start
                    for i in range(attr_count):
                        aoff = abase + i * attr_size
                        if aoff + 20 > len(axml_bytes):
                            break
                        ns_i, nm_i, raw_v, t_size, _, dtype, dval = struct.unpack(
                            "<iiiHBBI", axml_bytes[aoff : aoff + 20]
                        )
                        aname = strings[nm_i] if 0 <= nm_i < len(strings) else ""
                        res_id = res_ids[nm_i] if 0 <= nm_i < len(res_ids) else 0
                        if aname == "package":
                            pkg_name = (
                                strings[raw_v] if 0 <= raw_v < len(strings) else ""
                            )
                        elif aname == "versionCode" or res_id == 0x0101021B:
                            ver_code = dval
                        elif aname == "versionName" or res_id == 0x0101021C:
                            if dtype == 0x03 and 0 <= dval < len(strings):
                                ver_name = strings[dval]
                            elif 0 <= raw_v < len(strings):
                                ver_name = strings[raw_v]
                            else:
                                ver_name = str(dval)
                    return {
                        "package": pkg_name or "",
                        "versionName": ver_name or "",
                        "versionCode": ver_code,
                    }
            ptr += max(csize, 8)
    except Exception:
        pass
    return {}


def _extract_axml_from_local_zip(local_zip_path: str, apk_rel_path: str) -> dict:
    try:
        with zipfile.ZipFile(local_zip_path, "r") as outer_zf:
            apk_bytes = outer_zf.read(apk_rel_path)
        with zipfile.ZipFile(io.BytesIO(apk_bytes), "r") as inner_zf:
            axml = inner_zf.read("AndroidManifest.xml")
        return parse_axml_version(axml)
    except Exception:
        return {}


def _extract_axml_from_remote_zip_stream(entry_meta: dict, expected_pkg: str = "") -> dict:
    """Streams chunks from a remote ZIP entry until the outer APK's AndroidManifest.xml is encountered."""
    url = entry_meta.get("url")
    off = entry_meta.get("offset", 0)
    csize = entry_meta.get("compressed_size", 0)
    meth = entry_meta.get("method", 8)
    if not url or csize <= 0:
        return {}

    fallback_res = {}
    try:
        max_stream = csize + 512
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Range": f"bytes={off}-{off + max_stream - 1}",
            },
        )
        dobj = zlib.decompressobj(-zlib.MAX_WBITS) if meth == 8 else None
        buf = b""
        header_skipped = False
        with urllib.request.urlopen(req, timeout=30) as resp:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                if not header_skipped:
                    buf += chunk
                    if len(buf) >= 30:
                        nl, el = struct.unpack("<HH", buf[26:30])
                        if len(buf) >= 30 + nl + el:
                            rem = buf[30 + nl + el :]
                            buf = dobj.decompress(rem) if dobj else rem
                            header_skipped = True
                    if not header_skipped:
                        continue
                else:
                    buf += dobj.decompress(chunk) if dobj else chunk

                idx = 0
                keep_from = len(buf)
                while True:
                    pos = buf.find(b"AndroidManifest.xml", idx)
                    if pos == -1:
                        break
                    if pos >= 30 and buf[pos - 30 : pos - 26] == b"\x50\x4b\x03\x04":
                        (
                            _,
                            flag,
                            imeth,
                            _,
                            _,
                            _,
                            icsize,
                            iusize,
                            inlen,
                            ielen,
                        ) = struct.unpack("<HHHHHIIIHH", buf[pos - 26 : pos])
                        dstart = pos + inlen + ielen
                        if imeth == 0 and iusize == 0 and len(buf) >= dstart + 8:
                            iusize = struct.unpack("<I", buf[dstart + 4 : dstart + 8])[0]
                            icsize = iusize
                        need = icsize if icsize > 0 else max(iusize, 131072)
                        if len(buf) < dstart + need and len(chunk) == 262144:
                            keep_from = min(keep_from, pos - 30)
                            break
                        raw_axml = (
                            buf[dstart : dstart + icsize]
                            if icsize > 0
                            else buf[dstart : dstart + 131072]
                        )
                        try:
                            axml = (
                                raw_axml
                                if imeth == 0
                                else zlib.decompressobj(-zlib.MAX_WBITS).decompress(
                                    raw_axml
                                )
                            )
                            res = parse_axml_version(axml)
                            if res:
                                pkg = res.get("package", "")
                                if not expected_pkg or pkg == expected_pkg:
                                    return res
                                if not fallback_res:
                                    fallback_res = res
                        except Exception:
                            pass
                    idx = pos + 19
                if keep_from < len(buf):
                    buf = buf[keep_from:]
                elif len(buf) > 131072:
                    buf = buf[-65536:]
    except Exception:
        pass
    return fallback_res


def get_apk_metadata(apk_rel_path: str, entry_meta: dict) -> dict:
    expected_pkg = APK_PACKAGE_MAP.get(os.path.basename(apk_rel_path).lower(), "")
    if entry_meta.get("local_zip") and os.path.isfile(entry_meta["local_zip"]):
        res = _extract_axml_from_local_zip(entry_meta["local_zip"], apk_rel_path)
        if res:
            return res

    return _extract_axml_from_remote_zip_stream(entry_meta, expected_pkg=expected_pkg)


def compare_apk_files(ver: str, arch: str, pure_info: dict, mtg_info: dict) -> list:
    """
    Compares all common .apk files between PureGoogleGapps and MindTheGapps.
    Even a 1-byte or CRC32 difference triggers versionName & versionCode extraction.
    """
    pure_files = pure_info.get("files", {})
    mtg_files = mtg_info.get("files", {})

    common_apks = sorted(
        f for f in (set(pure_files.keys()) & set(mtg_files.keys())) if f.endswith(".apk")
    )

    apk_tasks = []
    apk_results = []

    for af in common_apks:
        p_meta = pure_files[af]
        m_meta = mtg_files[af]
        p_sz = p_meta["size"]
        m_sz = m_meta["size"]
        p_crc = p_meta.get("crc32", "")
        m_crc = m_meta.get("crc32", "")
        bname = os.path.basename(af)
        known_pkg = APK_PACKAGE_MAP.get(bname.lower(), "")

        if p_sz == m_sz and p_crc == m_crc:
            apk_results.append({
                "path": af,
                "name": bname,
                "package": known_pkg,
                "pure_size": p_sz,
                "mtg_size": m_sz,
                "diff_bytes": 0,
                "diff_pct": 0.0,
                "byte_identical": True,
                "pure_version_name": "Identical",
                "pure_version_code": None,
                "mtg_version_name": "Identical",
                "mtg_version_code": None,
            })
        else:
            apk_tasks.append((af, p_meta, m_meta))

    def _inspect_pair(item):
        af, p_meta, m_meta = item
        p_sz = p_meta["size"]
        m_sz = m_meta["size"]
        diff_b = p_sz - m_sz
        diff_pct = (abs(diff_b) / max(p_sz, m_sz, 1)) * 100.0
        bname = os.path.basename(af)

        p_ver = get_apk_metadata(af, p_meta)
        m_ver = get_apk_metadata(af, m_meta)

        pkg = p_ver.get("package") or m_ver.get("package") or APK_PACKAGE_MAP.get(bname.lower(), "")
        return {
            "path": af,
            "name": bname,
            "package": pkg,
            "pure_size": p_sz,
            "mtg_size": m_sz,
            "diff_bytes": diff_b,
            "diff_pct": diff_pct,
            "byte_identical": False,
            "pure_version_name": p_ver.get("versionName") or "N/A",
            "pure_version_code": p_ver.get("versionCode"),
            "mtg_version_name": m_ver.get("versionName") or "N/A",
            "mtg_version_code": m_ver.get("versionCode"),
        }

    if apk_tasks:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for res in ex.map(_inspect_pair, apk_tasks):
                apk_results.append(res)

    return sorted(apk_results, key=lambda x: x["path"])
