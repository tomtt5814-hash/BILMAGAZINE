"""杂志渲染：把文章数据渲染成自包含 HTML（内联 CSS + base64 封面）。"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config

TPL_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(TPL_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

ICONS = {
    "eye": '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    "wave": '<svg viewBox="0 0 24 24"><path d="M2 12h3l2-6 3 12 3-9 2 6h7"/></svg>',
    "grid": '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>',
    "compass": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/></svg>',
    "leaf": '<svg viewBox="0 0 24 24"><path d="M20 4S8 4 5 11c-2 5 2 9 2 9s4 2 8-1c4-3 5-15 5-15z"/><path d="M7 20c1-6 5-10 9-12"/></svg>',
    "spark": '<svg viewBox="0 0 24 24"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18"/></svg>',
}
ICON_ORDER = ["eye", "wave", "compass", "grid", "leaf", "spark"]


def _data_uri(path: Path | str | None) -> str:
    if not path:
        return ""
    path = Path(path)
    if not path.exists() or not path.is_file():
        return ""
    ext = path.suffix.lower().lstrip(".") or "jpeg"
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _paragraphs(body: str) -> list[str]:
    blocks = [b.strip() for b in body.replace("\r", "").split("\n\n") if b.strip()]
    out: list[str] = []
    for b in blocks:
        if b.startswith("#") or b.startswith("- ") or b.startswith("* "):
            b = b.lstrip("#-* ").strip()
        out.append(b)
    return out


def _pull_quote(paragraphs: list[str]) -> str:
    """挑一句最有画面感的短句做拉引。"""
    cands = []
    for p in paragraphs:
        for s in p.replace("!", "!|").replace("?", "?|").replace(". ", ".|").split("|"):
            s = s.strip()
            words = s.split()
            if 8 <= len(words) <= 22:
                cands.append((len(words), s))
    if not cands:
        return ""
    cands.sort(key=lambda x: abs(x[0] - 14))
    return cands[0][1]


def render_magazine(day: str, issue: int, headline: str, lede: str, articles: list[dict],
                    bloggers: list[str], cold_fact: str) -> tuple[str, dict]:
    prepared = []
    for i, a in enumerate(articles):
        paras = _paragraphs(a.get("body", ""))
        dropcap = ""
        if paras:
            first = paras[0]
            m = re.search(r"[A-Za-z]", first)
            if m and m.start() == 0:
                dropcap = first[0]
                paras[0] = first[1:]
        prepared.append(
            {
                "bvid": a.get("bvid", ""),
                "title": a.get("title", ""),
                "author": a.get("author", ""),
                "pubdate_human": a.get("pubdate_human", ""),
                "cover_data": a.get("cover_data") or _data_uri(a.get("cover_path")),
                "caption": a.get("caption", "视频封面"),
                "paragraphs": paras,
                "dropcap": dropcap,
                "pull": a.get("pull") or _pull_quote(paras),
                "url": a.get("url", ""),
                "rpid": a.get("rpid") or "",
                "icon_svg": ICONS[ICON_ORDER[i % len(ICON_ORDER)]],
            }
        )
    html = _env.get_template("magazine.html").render(
        m={
            "day": day,
            "issue": f"{issue:03d}",
            "headline": headline,
            "lede": lede,
            "articles": prepared,
            "bloggers": bloggers,
            "cold_fact": cold_fact,
            "generated_at": config_now(),
        }
    )
    meta = {
        "day": day,
        "issue": issue,
        "headline": headline,
        "lede": lede,
        "count": len(prepared),
        "bloggers": bloggers,
        "titles": [a["title"] for a in prepared],
        "bvids": [a["bvid"] for a in prepared],
    }
    return html, meta


def config_now() -> str:
    import time

    return time.strftime("%Y-%m-%d %H:%M")
