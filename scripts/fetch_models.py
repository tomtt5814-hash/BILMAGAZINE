"""下载 SenseVoice-Small 本地转写模型（约 229 MB）。

用法：
    python scripts/fetch_models.py
    python scripts/fetch_models.py --source hf       # 官方 Hugging Face
    python scripts/fetch_models.py --force           # 强制重下

下载到 tools/sensevoice/，被 .gitignore 忽略，不会进入仓库。
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "tools" / "sensevoice"
REPO = "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
MIRROR = f"https://hf-mirror.com/{REPO}/resolve/main/"
OFFICIAL = f"https://huggingface.co/{REPO}/resolve/main/"
FILES = {
    "model.int8.onnx": 239_233_841,
    "tokens.txt": 315_894,
}


def _download(url: str, dest: Path, expected: int) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "bilmagazine-setup"})
    with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or expected)
        got = 0
        last = 0.0
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            now = time.time()
            if now - last > 5:
                pct = got * 100 // max(total, 1)
                print(f"\r  {dest.name}: {got / 1e6:6.1f} / {total / 1e6:6.1f} MB ({pct}%)", end="", flush=True)
                last = now
    print()
    if got < expected * 0.95:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name} 下载不完整：{got} / {expected} 字节")
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=("mirror", "hf"), default="mirror")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    base = MIRROR if args.source == "mirror" else OFFICIAL

    for name, expected in FILES.items():
        dest = DEST / name
        if dest.exists() and dest.stat().st_size >= expected * 0.95 and not args.force:
            print(f"  skip {name}（已存在 {dest.stat().st_size / 1e6:.1f} MB）")
            continue
        url = base + name
        for attempt in (1, 2):
            try:
                print(f"下载 {url}")
                _download(url, dest, expected)
                break
            except Exception as exc:  # noqa: BLE001 - 换源重试
                if attempt == 2:
                    print(f"失败：{exc}", file=sys.stderr)
                    return 1
                alt = OFFICIAL if base == MIRROR else MIRROR
                print(f"  镜像失败（{exc}），改试 {alt}")
                url = alt + name

    print(f"\n完成：{DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
