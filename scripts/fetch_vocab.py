"""下载 V2 词表：基础词（初中/高中/四级）、CET-6、补充词（考研/托福/SAT）。

用法：python scripts/fetch_vocab.py [--proxy http://127.0.0.1:7897]
"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "vocab"

BASE = "https://raw.githubusercontent.com/Pleniluner/English-vocabulary/master/"
FILES = {
    "junior": "1 初中-乱序.txt",
    "senior": "2 高中-乱序.txt",
    "cet4": "3 四级-乱序.txt",
    "cet6": "4 六级-乱序.txt",
    "kaoyan": "5 考研-乱序.txt",
    "toefl": "6 托福-乱序.txt",
    "sat": "7 SAT-乱序.txt",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="", help="HTTP 代理，例如 http://127.0.0.1:7897")
    args = ap.parse_args()

    if args.proxy:
        handler = urllib.request.ProxyHandler({"http": args.proxy, "https": args.proxy})
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()

    OUT.mkdir(parents=True, exist_ok=True)
    for key, name in FILES.items():
        url = BASE + urllib.parse.quote(name)
        dest = OUT / f"{key}.txt"
        if dest.exists() and dest.stat().st_size > 1000:
            print(f"skip {key}（已存在 {dest.stat().st_size // 1024} KB）")
            continue
        try:
            with opener.open(url, timeout=90) as r:
                dest.write_bytes(r.read())
            print(f"ok   {key:8} {dest.stat().st_size // 1024:6} KB -> {dest}")
        except Exception as exc:
            print(f"FAIL {key:8} {exc}")
            sys.exit(1)


if __name__ == "__main__":
    main()
