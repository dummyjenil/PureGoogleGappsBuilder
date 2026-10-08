"""
Lightweight HTTP Range & Local ZIP Inspector.
Reads ZIP Central Directories and extracts individual entry bytes (XMLs, manifests)
either from a local ZIP (during CI matrix builds) or remotely via HTTP Range requests.
"""

import os
import struct
import zlib
import zipfile
import urllib.request


class RemoteZipInspector:
    """Inspects local or remote ZIP archives and extracts specific entries on demand."""

    @staticmethod
    def fetch_range(url: str, start: int, end: int, timeout: int = 20):
        import time
        last_err = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (FastGappsComparator/2.0)",
                        "Range": f"bytes={start}-{end}",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read(), resp.geturl()
            except Exception as e:
                last_err = e
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
        raise last_err

    @staticmethod
    def inspect(url: str, timeout: int = 20):
        """Reads remote ZIP Central Directory via HTTP Range (~64KB-512KB)."""
        import time
        last_err = None
        for attempt in range(4):
            try:
                total_size = 0
                final_url = url
                r_req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (FastGappsComparator/2.0)",
                        "Range": "bytes=0-0",
                    },
                )
                with urllib.request.urlopen(r_req, timeout=timeout) as resp:
                    final_url = resp.geturl()
                    cr = resp.headers.get("Content-Range")
                    if cr and "/" in cr:
                        total_size = int(cr.split("/")[-1])
                    else:
                        content_len = resp.headers.get("Content-Length")
                        total_size = int(content_len) if content_len else 0

                if total_size == 0:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "Mozilla/5.0 (FastGappsComparator/2.0)"}
                    )
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        final_url = resp.geturl()
                        content_len = resp.headers.get("Content-Length")
                        total_size = int(content_len) if content_len else 0

                if total_size == 0:
                    return None, "Unable to determine remote file size"

                tail_len = min(total_size, 512 * 1024)
                tail_data, _ = RemoteZipInspector.fetch_range(
                    final_url, total_size - tail_len, total_size - 1, timeout=timeout
                )

                files = RemoteZipInspector._parse_cd(tail_data, total_size, final_url)
                if not files:
                    raise RuntimeError("Parsed 0 entries from remote ZIP central directory")

                return {
                    "total_size_bytes": total_size,
                    "size_mb": total_size / (1024 * 1024),
                    "files": files,
                    "source_url": final_url,
                    "local_path": None,
                }, None
            except Exception as e:
                last_err = e
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
        return None, str(last_err)

    @staticmethod
    def inspect_local(path: str):
        """Inspects a local ZIP file on disk (used during GitHub Actions matrix jobs)."""
        try:
            total_size = os.path.getsize(path)
            file_map = {}
            with zipfile.ZipFile(path, "r") as zf:
                for info in zf.infolist():
                    if not info.is_dir():
                        name = info.filename.replace("\\", "/")
                        file_map[name] = {
                            "size": info.file_size,
                            "compressed_size": info.compress_size,
                            "crc32": f"{info.CRC:08x}",
                            "method": info.compress_type,
                            "offset": info.header_offset,
                            "url": None,
                            "local_zip": path,
                        }
            return {
                "total_size_bytes": total_size,
                "size_mb": total_size / (1024 * 1024),
                "files": file_map,
                "source_url": f"local://{path}",
                "local_path": path,
            }, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def _parse_cd(data: bytes, file_size: int, final_url: str):
        eocd_pos = data.rfind(b"\x50\x4b\x05\x06")
        if eocd_pos == -1 or eocd_pos + 22 > len(data):
            return {}

        (
            disk_num,
            start_disk,
            entries_disk,
            total_entries,
            cd_size,
            cd_offset,
            comment_len,
        ) = struct.unpack("<HHHHIIH", data[eocd_pos + 4 : eocd_pos + 22])

        tail_start_offset = file_size - len(data)
        cd_start_in_buf = cd_offset - tail_start_offset

        if cd_start_in_buf < 0 or cd_start_in_buf + cd_size > len(data):
            cd_bytes, _ = RemoteZipInspector.fetch_range(
                final_url, cd_offset, cd_offset + cd_size - 1
            )
        else:
            cd_bytes = data[cd_start_in_buf : cd_start_in_buf + cd_size]

        file_map = {}
        ptr = 0

        while ptr + 46 <= len(cd_bytes):
            if cd_bytes[ptr : ptr + 4] != b"\x50\x4b\x01\x02":
                break

            (
                sig,
                ver_m,
                ver_n,
                flags,
                meth,
                mtime,
                mdate,
                crc,
                csize,
                usize,
                nlen,
                elen,
                clen,
                dnum,
                iattr,
                eattr,
                off,
            ) = struct.unpack("<IHHHHHHIIIHHHHHII", cd_bytes[ptr : ptr + 46])

            name = (
                cd_bytes[ptr + 46 : ptr + 46 + nlen]
                .decode("utf-8", errors="ignore")
                .replace("\\", "/")
            )
            is_dir = name.endswith("/") or (eattr >> 16) & 0o040000 != 0

            if not is_dir:
                file_map[name] = {
                    "size": usize,
                    "compressed_size": csize,
                    "crc32": f"{crc:08x}",
                    "method": meth,
                    "offset": off,
                    "url": final_url,
                    "local_zip": None,
                }

            ptr += 46 + nlen + elen + clen

        return file_map

    @staticmethod
    def read_entry_bytes(entry_meta: dict, rel_path: str) -> bytes:
        """Reads uncompressed bytes of a single file inside a local or remote ZIP, or a local file."""
        if entry_meta.get("local_file") and os.path.isfile(entry_meta["local_file"]):
            with open(entry_meta["local_file"], "rb") as f:
                return f.read()

        if entry_meta.get("local_zip") and os.path.isfile(entry_meta["local_zip"]):
            with zipfile.ZipFile(entry_meta["local_zip"], "r") as zf:
                return zf.read(rel_path)

        url = entry_meta.get("url")
        off = entry_meta.get("offset", 0)
        csize = entry_meta.get("compressed_size", 0)
        meth = entry_meta.get("method", 8)
        if not url:
            return b""

        raw, _ = RemoteZipInspector.fetch_range(url, off, off + 30 + 256 + csize)
        if len(raw) < 30 or raw[:4] != b"\x50\x4b\x03\x04":
            return b""
        nlen, elen = struct.unpack("<HH", raw[26:30])
        comp = raw[30 + nlen + elen : 30 + nlen + elen + csize]
        if meth == 0:
            return comp
        return zlib.decompress(comp, -zlib.MAX_WBITS)

