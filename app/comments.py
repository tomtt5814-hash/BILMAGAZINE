"""B 站评论区：免登录读热评，嵌进杂志里。

只取顶层评论（不展开楼中楼），按点赞数排序；图片评论只保留文字部分。
"""

from __future__ import annotations

import httpx

from . import config

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}


def _aid(client: httpx.Client, bvid: str) -> int | None:
    try:
        r = client.get("https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid})
        j = r.json()
        if j.get("code") == 0:
            return int(j["data"]["aid"])
    except Exception:
        pass
    return None


def fetch_top_comments(bvid: str, limit: int = 5) -> list[dict]:
    """返回 [{author, like, text, rpid, ctime}]，失败返回空列表。"""
    if not bvid or not config.COMMENTS_ENABLED:
        return []
    try:
        with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as c:
            aid = _aid(c, bvid)
            if not aid:
                return []
            r = c.get(
                "https://api.bilibili.com/x/v2/reply",
                params={"type": 1, "oid": aid, "sort": 1, "ps": 20},
            )
            j = r.json()
            if j.get("code") != 0:
                return []
            replies = ((j.get("data") or {}).get("replies") or [])
    except Exception:
        return []

    out: list[dict] = []
    seen: set[str] = set()
    for rep in replies:
        try:
            text = (rep.get("content") or {}).get("message") or ""
            text = " ".join(text.split())
            if not text or len(text) < 4:
                continue
            key = text[:60]
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "author": (rep.get("member") or {}).get("uname") or "匿名",
                    "like": int(rep.get("like") or 0),
                    "text": text[:220],
                    "rpid": rep.get("rpid"),
                    "floor": rep.get("floor"),
                }
            )
        except Exception:
            continue
    out.sort(key=lambda x: -x["like"])
    return out[:limit]
