"""RSS 内容源（目前用于公众号：wechat2rss 的公开镜像）。

公众号本身没有 API，但 wechat2rss 把它转成了标准 RSS，条目里直接带全文 HTML，
图片走它的 img-proxy，所以抓下来即可用，不需要再回微信取页面。
"""

from __future__ import annotations

import hashlib
import re
import time
from email.utils import parsedate_to_datetime
from html import unescape

import httpx

from . import config

UA = config.UA


class RssError(Exception):
    pass


def _first(pat: str, text: str, flags: int = re.S) -> str:
    m = re.search(pat, text, flags)
    return m.group(1).strip() if m else ""


def item_id(link: str) -> str:
    """用 __biz+mid+idx 做去重 key；没有就按链接哈希。"""
    m = re.search(r"[?&]__biz=([^&]+).*?[?&]mid=(\d+).*?[?&]idx=(\d+)", link)
    if m:
        return "wx:" + hashlib.md5("|".join(m.groups()).encode()).hexdigest()[:16]
    return "rss:" + hashlib.md5(link.encode()).hexdigest()[:16]


def fetch_feed(url: str, limit: int = 20) -> list[dict]:
    try:
        r = httpx.get(url, timeout=45, headers={"User-Agent": UA}, follow_redirects=True)
    except Exception as exc:
        raise RssError(f"RSS 拉取失败：{exc}")
    if r.status_code != 200:
        raise RssError(f"RSS 返回 HTTP {r.status_code}")

    items: list[dict] = []
    for raw in re.findall(r"<item>(.*?)</item>", r.text, re.S)[:limit]:
        title = unescape(_first(r"<title><!\[CDATA\[(.*?)\]\]></title>", raw) or _first(r"<title>(.*?)</title>", raw))
        link = unescape(_first(r"<link>(.*?)</link>", raw))
        content = _first(r"<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>", raw)
        if not content:
            content = unescape(_first(r"<content:encoded>(.*?)</content:encoded>", raw))
        pub = _first(r"<pubDate>(.*?)</pubDate>", raw)
        ts = 0
        if pub:
            try:
                ts = int(parsedate_to_datetime(pub).timestamp())
            except Exception:
                ts = 0
        if not link or not content:
            continue
        items.append({
            "id": item_id(link),
            "url": link,
            "title": title or "（无标题）",
            "published": ts or int(time.time()),
            "html": content,
        })
    items.sort(key=lambda a: a["published"], reverse=True)
    return items


def html_to_text(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>|</section>|</div>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text).replace("\u00a0", " ").replace("\u200b", "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)
