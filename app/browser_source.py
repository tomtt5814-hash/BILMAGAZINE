"""通过本机已登录的浏览器（bsk CLI）读取 UP 主最新一期 BV 号。

为什么不直接调 B 站接口：空间投稿接口对未登录请求返回 412 / -799（风控），
而浏览器里已经有登录态，直接读页面里的视频链接最稳，也不需要用户提供 Cookie。

副作用：每次抓取会短暂打开一个 Agent Window（约 10–20 秒），结束后立即关闭。
"""

from __future__ import annotations

import json
import re
import subprocess
import time

from . import hidewin

BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
JS_LINKS = (
    'Array.from(document.querySelectorAll("a[href*=\\"/video/BV\\"]"))'
    '.map(function(a){return a.getAttribute("href")})'
    '.filter(Boolean)'
)


class BrowserUnavailable(Exception):
    pass


def _bsk(*args: str, timeout: int = 90) -> str:
    try:
        proc = subprocess.run(["bsk", *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              **hidewin.quiet_kwargs())
    except FileNotFoundError:
        raise BrowserUnavailable("找不到 bsk 命令，浏览器插件未安装或不在 PATH 里")
    except subprocess.TimeoutExpired:
        raise BrowserUnavailable("bsk 调用超时")
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        raise BrowserUnavailable(msg[:300] or "bsk 调用失败")
    return proc.stdout


def _json(text: str):
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0] or [-1])
    if start < 0:
        raise BrowserUnavailable(f"bsk 输出不是 JSON：{text[:160]}")
    return json.loads(text[start:])


def _eval_list(raw: str) -> list:
    data = _json(raw)
    value = data.get("value") if isinstance(data, dict) else data
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return []
    return value if isinstance(value, list) else []


def _wait_links(sid: str, attempts: int = 5) -> list:
    for _ in range(attempts):
        try:
            links = _eval_list(_bsk("evaluate", "--session", sid, "--json", JS_LINKS, timeout=60))
        except Exception:
            links = []
        if links:
            return links
        time.sleep(2.5)
    return []


def latest_bvs(items: list[dict], n: int = 1) -> dict[str, list[str]]:
    """items: [{uid, name, recent_n}] -> {uid: [bvid, ...]}"""
    if not items:
        return {}
    # 背景 + 小窗口：定时任务不该在桌面上弹一个大浏览器窗口抢焦点
    sid = _json(_bsk("session", "start", "--json", "--no-focus",
                     "--width", "420", "--height", "320"))["session_id"]
    result: dict[str, list[str]] = {}
    try:
        for it in items:
            uid = str(it["uid"])
            want = max(1, min(int(it.get("recent_n") or n), 5))
            try:
                _bsk("navigate", "--session", sid, f"https://space.bilibili.com/{uid}/video",
                     "--wait-until", "load", timeout=90)
                hrefs = _wait_links(sid)
                bvs: list[str] = []
                for href in hrefs:
                    m = BV_RE.search(str(href))
                    if m and m.group(1) not in bvs:
                        bvs.append(m.group(1))
                    if len(bvs) >= want:
                        break
                result[uid] = bvs
            except Exception:
                result[uid] = []
            time.sleep(0.8)
    finally:
        try:
            _bsk("session", "stop", sid, timeout=30)   # 位置参数，不是 --session
        except Exception:
            pass
    if items and not any(result.values()):
        raise BrowserUnavailable(
            "没取到任何 UP 主的最新一期：浏览器可能未登录，或空间页被风控（可先手动打开一次空间页）"
        )
    return result
