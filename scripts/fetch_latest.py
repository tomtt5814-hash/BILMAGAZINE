"""CLI：用已登录的浏览器抓 UP 主最新一期 BV 号。

用法：
  python scripts/fetch_latest.py --all-subscribed
  python scripts/fetch_latest.py 520819684 570064 --n 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import browser_source, store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("uids", nargs="*")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--all-subscribed", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.all_subscribed:
        items = [{"uid": b["uid"], "name": b["name"], "recent_n": b.get("recent_n", 1)}
                 for b in store.load_subs() if b.get("enabled", True)]
    else:
        items = [{"uid": u, "name": u, "recent_n": args.n} for u in args.uids]
    if not items:
        sys.exit("没有可检查的 UP 主")

    print(f"检查 {len(items)} 个 UP 主：", flush=True)
    result = browser_source.latest_bvs(items, args.n)
    for it in items:
        print(f"  {it.get('name') or it['uid']}: {', '.join(result.get(it['uid'], [])) or '未找到'}", flush=True)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"共 {sum(len(v) for v in result.values())} 个视频")


if __name__ == "__main__":
    main()
