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
from core.constants import BRANCH_MAP
from .zip_inspector import RemoteZipInspector

GITLAB_RAW_BASE = "https://gitlab.com/MindTheGapps/vendor_gapps/-/raw"


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


def _extract_axml_from_gitlab_raw_apk(branch: str, arch: str, apk_rel_path: str) -> dict:
    """Uses two tiny HTTP Range requests (~20KB total) on MindTheGapps GitLab raw APK."""
    sub_rel = apk_rel_path[len("system/") :] if apk_rel_path.startswith("system/") else apk_rel_path
    candidates = [
        f"{GITLAB_RAW_BASE}/{branch}/{arch}/proprietary/{sub_rel}",
        f"{GITLAB_RAW_BASE}/{branch}/common/proprietary/{sub_rel}",
    ]
    for url in candidates:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status not in (200, 206):
                    continue
                final_url = r.geturl()
                cr = r.headers.get("Content-Range", "")
                size = (
                    int(cr.split("/")[-1])
                    if "/" in cr
                    else int(r.headers.get("Content-Length", 0))
                )
            if size <= 0:
                continue
            tail_len = min(size, 65536)
            tail, _ = RemoteZipInspector.fetch_range(
                final_url, size - tail_len, size - 1, timeout=10
            )
            eocd = tail.rfind(b"\x50\x4b\x05\x06")
            if eocd == -1:
                continue
            _, _, _, _, cd_size, cd_off, _ = struct.unpack(
                "<HHHHIIH", tail[eocd + 4 : eocd + 22]
            )
            if cd_off < size - tail_len:
                cd, _ = RemoteZipInspector.fetch_range(
                    final_url, cd_off, cd_off + cd_size - 1, timeout=10
                )
            else:
                cd = tail[
                    cd_off - (size - len(tail)) : cd_off - (size - len(tail)) + cd_size
                ]
            ptr = 0
            while ptr + 46 <= len(cd):
                if cd[ptr : ptr + 4] != b"\x50\x4b\x01\x02":
                    break
                (
                    _,
                    _,
                    _,
                    _,
                    meth,
                    _,
                    _,
                    crc,
                    csize,
                    usize,
                    nlen,
                    elen,
                    clen,
                    _,
                    _,
                    _,
                    off,
                ) = struct.unpack("<IHHHHHHIIIHHHHHII", cd[ptr : ptr + 46])
                name = cd[ptr + 46 : ptr + 46 + nlen].decode("utf-8", errors="ignore")
                if name == "AndroidManifest.xml":
                    raw, _ = RemoteZipInspector.fetch_range(
                        final_url, off, off + 30 + 128 + csize, timeout=10
                    )
                    nl, el = struct.unpack("<HH", raw[26:30])
                    comp = raw[30 + nl + el : 30 + nl + el + csize]
                    axml = (
                        comp
                        if meth == 0
                        else zlib.decompress(comp, -zlib.MAX_WBITS)
                    )
                    res = parse_axml_version(axml)
                    if res:
                        return res
                ptr += 46 + nlen + elen + clen
        except Exception:
            continue
    return {}


def _extract_axml_from_remote_zip_stream(entry_meta: dict) -> dict:
    """Streams chunks from a remote ZIP entry until AndroidManifest.xml is encountered."""
    url = entry_meta.get("url")
    off = entry_meta.get("offset", 0)
    csize = entry_meta.get("compressed_size", 0)
    meth = entry_meta.get("method", 8)
    if not url or csize <= 0:
        return {}

    try:
        # Cap stream range to 16MB max so huge APKs don't stall remote runs
        max_stream = min(csize + 512, 16 * 1024 * 1024)
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            while True:
                chunk = resp.read(65536)
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
                        need = icsize if icsize > 0 else max(iusize, 65536)
                        if len(buf) >= dstart + need or len(chunk) < 65536:
                            raw_axml = (
                                buf[dstart : dstart + icsize]
                                if icsize > 0
                                else buf[dstart:]
                            )
                            axml = (
                                raw_axml
                                if imeth == 0
                                else zlib.decompressobj(-zlib.MAX_WBITS).decompress(
                                    raw_axml
                                )
                            )
                            res = parse_axml_version(axml)
                            if res:
                                return res
                    idx = pos + 19
                if len(buf) > 4 * 1024 * 1024 and b"AndroidManifest.xml" not in buf:
                    buf = buf[-131072:]
    except Exception:
        pass
    return {}


def get_apk_metadata(
    apk_rel_path: str, entry_meta: dict, branch: str, arch: str, is_mtg: bool
) -> dict:
    if entry_meta.get("local_zip") and os.path.isfile(entry_meta["local_zip"]):
        res = _extract_axml_from_local_zip(entry_meta["local_zip"], apk_rel_path)
        if res:
            return res

    if is_mtg:
        res = _extract_axml_from_gitlab_raw_apk(branch, arch, apk_rel_path)
        if res:
            return res

    return _extract_axml_from_remote_zip_stream(entry_meta)


def compare_apk_files(ver: str, arch: str, pure_info: dict, mtg_info: dict) -> list:
    """
    Compares all common .apk files between PureGoogleGapps and MindTheGapps.
    Even a 1-byte or CRC32 difference triggers versionName & versionCode extraction.
    """
    branch = BRANCH_MAP.get(ver, "tau")
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

        if p_sz == m_sz and p_crc == m_crc:
            apk_results.append({
                "path": af,
                "name": os.path.basename(af),
                "package": "",
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

        p_ver = get_apk_metadata(af, p_meta, branch, arch, is_mtg=False)
        m_ver = get_apk_metadata(af, m_meta, branch, arch, is_mtg=True)

        pkg = p_ver.get("package") or m_ver.get("package") or ""
        return {
            "path": af,
            "name": os.path.basename(af),
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
