"""把最近一期杂志复制成前几天的「历史刊」，用于前端验收。

正文完全复用（不重新下载、不重新转写、不重新调用 LLM），只换日期与期号。
用法：python scripts/seed_days.py --days 2
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, magazine, store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2, help="往前复制几天")
    ap.add_argument("--source", default="", help="源日期 YYYY-MM-DD，默认取最新一期")
    args = ap.parse_args()

    mags = store.list_magazines()
    if not mags:
        sys.exit("还没有任何杂志，先生成一期")
    source_day = args.source or mags[0]["day"]
    meta = json.loads((config.MAGAZINE_DIR / f"daily-magazine-{source_day}.json").read_text(encoding="utf-8"))
    articles = meta.get("articles") or []
    if not articles:
        sys.exit("源杂志里没有正文数据（旧格式），请先重新生成一期")

    base = dt.date.fromisoformat(source_day)
    issue0 = int(meta.get("issue") or 1)
    for k in range(1, args.days + 1):
        day = (base - dt.timedelta(days=k)).isoformat()
        html, new_meta = magazine.render_magazine(
            day=day,
            issue=max(1, issue0 - k),
            headline=meta["headline"],
            lede=meta["lede"],
            articles=articles,
            bloggers=meta.get("bloggers") or [],
            cold_fact="whisper.cpp 的 Vulkan 后端让 AMD 显卡也能跑本地转写——这条管线每天只在你睡觉时启动一次。",
            headline_zh=meta.get("headline_zh", ""),
        )
        store.save_magazine(day, html, new_meta)
        first_cover = next((a.get("cover_path") for a in articles if a.get("cover_path")), "")
        if first_cover and Path(first_cover).exists():
            (config.MAGAZINE_DIR / f"thumb-{day}.jpg").write_bytes(Path(first_cover).read_bytes())
        print(f"{day}  第 {new_meta['issue']} 期  {new_meta['count']} 篇  -> daily-magazine-{day}.html")


if __name__ == "__main__":
    main()
