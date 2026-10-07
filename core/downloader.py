"""
High-Speed Image Downloader Module with aria2c Acceleration
"""

import os
import sys
import shutil
import urllib.request
import subprocess


def download_file(url: str, target_path: str):
    """
    Downloads Google Image using aria2c multi-connection acceleration or urllib fallback.
    """
    target_dir = os.path.dirname(os.path.abspath(target_path)) or "."
    target_name = os.path.basename(target_path)
    os.makedirs(target_dir, exist_ok=True)

    if os.path.exists(target_path) and os.path.getsize(target_path) > 100 * 1024 * 1024:
        print(f"    [✓] Using cached Google image: {target_path} ({os.path.getsize(target_path)/1024/1024:.1f} MB)")
        return

    print(f"[*] Downloading official Google image from:\n    {url}")

    # 1. Try turbo multi-connection download via aria2c
    if shutil.which("aria2c"):
        print("    [⚡] Turbo Download Engine: aria2c (16 parallel streams)")
        cmd = [
            "aria2c",
            "-x", "16",
            "-s", "16",
            "-k", "1M",
            "-j", "16",
            "--file-allocation=none",
            "--summary-interval=1",
            "--console-log-level=warn",
            "-d", target_dir,
            "-o", target_name,
            url
        ]
        try:
            res = subprocess.run(cmd)
            if res.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                print(f"[✓] Accelerated download complete: {target_path} ({os.path.getsize(target_path)/1024/1024:.1f} MB)")
                return
        except Exception as e:
            print(f"[!] aria2c download failed, falling back to standard stream: {e}")

    # 2. Standard streaming fallback
    headers = {"User-Agent": "Android-Studio/PureGappsDownloader"}
    req = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(req) as resp, open(target_path, "wb") as out_file:
        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        block_size = 2 * 1024 * 1024
        
        while True:
            buffer = resp.read(block_size)
            if not buffer:
                break
            downloaded += len(buffer)
            out_file.write(buffer)
            if total_size > 0:
                percent = (downloaded / total_size) * 100
                mb_down = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r    -> {mb_down:.1f} MB / {mb_total:.1f} MB ({percent:.1f}%)", end="", flush=True)
        print()
    print(f"[✓] Download complete: {target_path} ({os.path.getsize(target_path)/1024/1024:.1f} MB)")
