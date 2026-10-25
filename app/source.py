"""B 站内容获取：订阅列表 -> 最新一期 BV；单视频信息；封面。"""

from __future__ import annotations

import hashlib
import re
import time
import urllib.parse
from pathlib import Path

import httpx

from . import config

NAV = "https://api.bilibili.com/x/web-interface/nav"
SPI = "https://api.bilibili.com/x/frontend/finger/spi"
SPACE = "https://api.bilibili.com/x/space/wbi/arc/search"
VIEW = "https://api.bilibili.com/x/web-interface/view"
PLAYER = "https://api.bilibili.com/x/player/v2"

_MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]


class SourceBlocked(Exception):
    """列表接口被风控拦截，需要登录 Cookie。"""


def parse_uid(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.isdigit():
        return text
    m = re.search(r"space\.bilibili\.com/(\d+)", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4,})\b", text)
    return m.group(1) if m else None


def parse_bvid(text: str) -> str | None:
    text = (text or "").strip()
    m = re.search(r"(BV[0-9A-Za-z]{10})", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[Bb][Vv][0-9A-Za-z]{10}", text or ""):
        return "BV" + text[2:]
    return None


class BiliClient:
    def __init__(self, cookie: str | None = None):
        self.cookie = (cookie if cookie is not None else config.BILI_COOKIE).strip()
        self.client = httpx.Client(
            headers={
                "User-Agent": config.UA,
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
            },
            timeout=25,
            follow_redirects=True,
        )
        if self.cookie:
            self.client.headers["Cookie"] = self.cookie
        self._mixin: str | None = None

    # ---- wbi ----
    def _ensure_mixin(self) -> str:
        if self._mixin:
            return self._mixin
        try:
            spi = self.client.get(SPI).json()["data"]
            self.client.cookies.set("buvid3", spi["b_3"], domain=".bilibili.com")
            self.client.cookies.set("buvid4", spi["b_4"], domain=".bilibili.com")
        except Exception:
            pass
        nav = self.client.get(NAV).json().get("data") or {}
        wbi = nav.get("wbi_img") or {}
        if "img_url" not in wbi:
            raise SourceBlocked("无法取得 wbi 签名密钥")
        img = wbi["img_url"].rsplit("/", 1)[-1].split(".")[0]
        sub = wbi["sub_url"].rsplit("/", 1)[-1].split(".")[0]
        self._mixin = "".join((img + sub)[i] for i in _MIXIN_TAB)[:32]
        return self._mixin

    def _sign(self, params: dict) -> dict:
        p = {k: str(v) for k, v in params.items()}
        p["wts"] = str(int(time.time()))
        items = sorted(p.items())
        p = {k: "".join(ch for ch in v if ch not in "!'()*") for k, v in items}
        query = urllib.parse.urlencode(p)
        p["w_rid"] = hashlib.md5((query + self._ensure_mixin()).encode()).hexdigest()
        return p

    # ---- 接口 ----
    def space_videos(self, mid: str, limit: int = 1) -> list[dict]:
        params = self._sign(
            {
                "mid": mid,
                "ps": max(limit, 1),
                "pn": 1,
                "order": "pubdate",
                "platform": "web",
                "web_location": 1550101,
                "dm_img_list": "[]",
                "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
                "dm_cover_img_str": "QU5HTEUgKEFNRCwgQU1EIFJhZGVvbiBSWCA3NjUwIEdSRSAoRHhFMTFfYnJpZGdlKSwgT3BlbkdMIDQuNik",
                "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
            }
        )
        r = self.client.get(SPACE, params=params)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("application/json"):
            raise SourceBlocked(
                f"B 站空间接口被风控拦截（HTTP {r.status_code}）。"
                "需要在 .env 里配置 BILI_COOKIE（浏览器登录后复制整条 Cookie）。"
            )
        data = r.json()
        if data.get("code") != 0:
            raise SourceBlocked(
                f"B 站空间接口返回 {data.get('code')}：{data.get('message')}。"
                "通常是没有登录 Cookie，或该 UP 主开启了隐私保护。"
            )
        vlist = ((data.get("data") or {}).get("list") or {}).get("vlist") or []
        out = []
        for v in vlist[:limit]:
            out.append(
                {
                    "bvid": v.get("bvid"),
                    "title": v.get("title"),
                    "duration": v.get("length"),
                    "pubdate": v.get("created"),
                    "cover": v.get("pic"),
                    "author": v.get("author"),
                }
            )
        return out

    def video_info(self, bvid: str) -> dict:
        r = self.client.get(VIEW, params={"bvid": bvid})
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"取视频信息失败：{data.get('code')} {data.get('message')}")
        d = data["data"]
        return {
            "bvid": d["bvid"],
            "aid": d["aid"],
            "cid": d["cid"],
            "title": d["title"],
            "desc": d.get("desc", ""),
            "duration": d.get("duration"),
            "pubdate": d.get("pubdate"),
            "cover": d.get("pic"),
            "author": d.get("owner", {}).get("name", ""),
            "uid": str(d.get("owner", {}).get("mid", "")),
            "pages": d.get("pages", []),
        }

    def subtitles(self, bvid: str, cid: int) -> list[dict]:
        r = self.client.get(PLAYER, params={"bvid": bvid, "cid": cid})
        data = r.json()
        if data.get("code") != 0:
            return []
        sub = ((data.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
        return [s for s in sub if s.get("subtitle_url")]

    def download_cover(self, url: str, dest: Path) -> bool:
        if not url:
            return False
        if url.startswith("//"):
            url = "https:" + url
        try:
            r = self.client.get(url, headers={"Referer": "https://www.bilibili.com/"})
            if r.status_code == 200 and r.content:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                return True
        except Exception:
            return False
        return False

    def fetch_subtitle_text(self, url: str) -> str:
        if url.startswith("//"):
            url = "https:" + url
        r = self.client.get(url)
        data = r.json()
        body = data.get("body") or []
        return "\n".join(seg.get("content", "").strip() for seg in body if seg.get("content"))
