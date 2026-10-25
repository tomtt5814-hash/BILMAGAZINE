"""微信公众号内容源。

没有公开 API，走两条路：
  1. 直接给文章链接（mp.weixin.qq.com/s/...）—— 最稳，抓页面里的 js_content；
  2. 按公众号名自动找最新文章 —— 搜狗微信搜索，还原它的跳转 JS，再抓正文。

注意：搜狗的结果有时效签名，链接不能长期缓存；只用来「发现新文章」。
"""

from __future__ import annotations

import hashlib
import re
import time
from html import unescape

import httpx

from . import config

UA = config.UA
SOGOU = "https://weixin.sogou.com/weixin"


class WeChatError(Exception):
    pass


def article_id(url: str) -> str:
    """稳定的去重 key：__biz+mid+idx 优先，其次 /s/<短码>，最后整段 URL 的哈希。"""
    m = re.search(r"[?&]__biz=([^&]+).*?[?&]mid=(\d+).*?[?&]idx=(\d+)", url)
    if m:
        return "wx:" + hashlib.md5("|".join(m.groups()).encode()).hexdigest()[:16]
    short = re.search(r"/s/([A-Za-z0-9_-]{8,})", url)
    if short:
        return "wx:" + hashlib.md5(short.group(1).encode()).hexdigest()[:16]
    # 搜狗给的是签名地址，同一篇文章每次签名不同，只能靠抓取后的 canonical id
    return ""


def canonical_id(html: str, fallback: str) -> str:
    """从文章 HTML 里取稳定身份：biz/mid/idx/sn，或 账号+标题+时间 的哈希。"""
    biz = re.search(r'var biz = "([^"]*)"', html) or re.search(r'[?&]__biz=([^&"\']+)', html)
    mid = re.search(r'var mid = "(\d+)"', html) or re.search(r'[?&]mid=(\d+)', html)
    idx = re.search(r'var idx = "(\d+)"', html) or re.search(r'[?&]idx=(\d+)', html)
    if biz and mid and idx and biz.group(1):
        key = "|".join((biz.group(1), mid.group(1), idx.group(1)))
        return "wx:" + hashlib.md5(key.encode()).hexdigest()[:16]

    title = re.search(r'var msg_title = [\'"](.*?)[\'"]', html, re.S)
    nick = re.search(r'var nickname = [\'"](.*?)[\'"]', html)
    ct = re.search(r'var ct = [\'"](\d+)[\'"]', html)
    if title:
        key = "|".join((nick.group(1) if nick else "", title.group(1), ct.group(1) if ct else ""))
        return "wx:" + hashlib.md5(key.encode()).hexdigest()[:16]
    return fallback or "wx:" + hashlib.md5(html[:2000].encode()).hexdigest()[:16]


def _text(html: str, pattern: str, flags: int = re.S) -> str:
    m = re.search(pattern, html, flags)
    return unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""


def _clean_body(fragment: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", fragment, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p>|</section>|</div>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", html)
    text = unescape(text).replace("\u00a0", " ").replace("\u200b", "")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not re.fullmatch(r"[\s​]*", ln)]
    # 去掉公众号常见的引导语尾巴
    out: list[str] = []
    for ln in lines:
        if re.search(r"^(点击|长按|扫码|关注|在看|点赞|分享|星标)", ln) and len(ln) < 40:
            continue
        out.append(ln)
    return "\n".join(out)


def fetch_article(url: str) -> dict:
    if "mp.weixin.qq.com" not in url:
        raise WeChatError("不是公众号文章链接")
    client = httpx.Client(headers={"User-Agent": UA}, timeout=40, follow_redirects=True)
    r = client.get(url)
    if r.status_code != 200:
        raise WeChatError(f"抓取失败：HTTP {r.status_code}")
    h = r.text
    if 'id="js_content"' not in h:
        raise WeChatError("没有正文容器（可能是被删文章或需要验证）")

    title = _text(h, r'<h1[^>]*id="activity-name"[^>]*>(.*?)</h1>') or _text(h, r'var msg_title = [\'"](.*?)[\'"]')
    account = _text(h, r'var nickname = [\'"](.*?)[\'"]') or _text(h, r'id="js_name"[^>]*>(.*?)<')
    author = _text(h, r'var author = [\'"](.*?)[\'"]')
    ct = _text(h, r'var ct = [\'"](\d+)[\'"]')

    m = re.search(r'<div[^>]*id="js_content"[^>]*>(.*?)\n\s*</div>\s*<script', h, re.S) or \
        re.search(r'<div[^>]*id="js_content"[^>]*>(.*?)</div>', h, re.S)
    body = _clean_body(m.group(1)) if m else ""
    if len(body) < 200:
        raise WeChatError(f"正文太短（{len(body)} 字），可能被折叠或需要验证")

    cover = ""
    for pat in (r'var msg_cdn_url = [\'"](.*?)[\'"]', r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"'):
        cover = _text(h, pat)
        if cover:
            break

    return {
        "id": canonical_id(h, article_id(url)),
        "url": url,
        "title": title,
        "account": account,
        "author": author,
        "published": int(ct) if ct.isdigit() else int(time.time()),
        "text": body,
        "cover": cover,
        "html": h,
    }


def download_cover(url: str, dest) -> bool:
    if not url:
        return False
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=40, follow_redirects=True)
        if r.status_code == 200 and r.content:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


# ---------- 按公众号名发现最新文章 ----------

def _resolve_sogou_link(client: httpx.Client, href: str) -> str:
    """搜狗的 /link?url=... 是个 JS 拼地址的跳转页，这里把地址拼回来。"""
    page = client.get("https://weixin.sogou.com" + href.replace("&amp;", "&"))
    pieces = re.findall(r"url \+= '([^']*)'", page.text)
    return "".join(pieces).replace("@", "")


def search_account(account: str, limit: int = 5) -> list[dict]:
    """搜公众号下的最新文章。失败一律返回空列表，由调用方决定降级。"""
    client = httpx.Client(headers={"User-Agent": UA, "Referer": "https://weixin.sogou.com/"},
                          timeout=30, follow_redirects=True)
    try:
        r = client.get(SOGOU, params={"type": 2, "query": account})
        if r.status_code != 200:
            return []
        hrefs = list(dict.fromkeys(re.findall(r'href="(/link\?url=[^"]+)"', r.text)))
    except Exception:
        return []

    out: list[dict] = []
    for href in hrefs[: max(limit * 2, 6)]:
        try:
            url = _resolve_sogou_link(client, href)
            if not url.startswith("https://mp.weixin.qq.com"):
                continue
            art = fetch_article(url)
            if art["account"] and account not in art["account"] and art["account"] not in account:
                continue
            out.append(art)
            if len(out) >= limit:
                break
        except Exception:
            continue
        time.sleep(0.6)
    out.sort(key=lambda a: a.get("published") or 0, reverse=True)
    return out
