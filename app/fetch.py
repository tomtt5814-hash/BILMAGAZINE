"""音频下载（yt-dlp）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import config, hidewin


class DownloadError(Exception):
    pass


def download_audio(bvid: str, force: bool = False) -> Path:
    dest = config.MEDIA_DIR / bvid
    dest.mkdir(parents=True, exist_ok=True)
    existing = sorted(dest.glob("audio.*"))
    if existing and not force:
        return existing[0]

    url = f"https://www.bilibili.com/video/{bvid}"
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio/best",
        "--no-playlist",
        "--no-progress",
        "-o", str(dest / "audio.%(ext)s"),
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                          encoding="utf-8", errors="replace", **hidewin.quiet_kwargs())
    files = sorted(dest.glob("audio.*"))
    if proc.returncode != 0 or not files:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise DownloadError("；".join(tail) or "yt-dlp 未产出音频文件")
    return files[0]
