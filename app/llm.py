"""LLM 层：摘要 + 六级科普改写 + 标题 + 导语。

provider=deepseek 走真实 API；provider=mock 走 data/demo/llm_cache.json（演示用，
每条样例都在页面上标注为「预置样例」，不冒充真实模型输出）。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


class LLMUnavailable(Exception):
    pass


def _prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def _demo_cache() -> dict:
    p = config.DEMO_DIR / "llm_cache.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _chat(system: str, user: str, max_tokens: int = 1200) -> str:
    from openai import OpenAI

    if not config.LLM_API_KEY:
        raise LLMUnavailable("未配置 LLM_API_KEY（.env 里填 DeepSeek key）")
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL, timeout=180)
    resp = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=config.LLM_TEMPERATURE,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def _demo(bvid: str, kind: str) -> str:
    item = _demo_cache().get(bvid, {})
    if kind in item:
        return item[kind]
    raise LLMUnavailable(
        "演示模式缺这条样例，且未配置 LLM_API_KEY。请在 .env 里填 DeepSeek key 后重跑。"
    )


def summarize(bvid: str, transcript: str, meta: dict) -> str:
    if config.LLM_PROVIDER == "mock":
        return _demo(bvid, "summary")
    user = (
        f"视频标题：{meta.get('title', '')}\n"
        f"UP 主：{meta.get('author', '')}\n"
        f"发布时间：{meta.get('pubdate', '')}\n\n"
        f"转写原文：\n{transcript[:24000]}"
    )
    return _chat(_prompt("summarize"), user, max_tokens=900)


def rewrite(bvid: str, summary: str, meta: dict) -> dict:
    """返回 {title, body, lede?}"""
    if config.LLM_PROVIDER == "mock":
        return {
            "title": _demo(bvid, "title"),
            "body": _demo(bvid, "body"),
            "note": "预设样例（未调用真实模型）",
        }
    user = (
        f"中文摘要：\n{summary}\n\n"
        f"参考信息：UP 主 {meta.get('author', '')}，视频标题《{meta.get('title', '')}》"
    )
    raw = _chat(_prompt("rewrite"), user, max_tokens=1200)
    title, body = _split_title(raw)
    return {"title": title, "body": body, "note": ""}


def _split_title(raw: str) -> tuple[str, str]:
    lines = [l.strip() for l in raw.splitlines()]
    title = ""
    body_lines: list[str] = []
    for line in lines:
        if not title and line.upper().startswith("TITLE:"):
            title = line[6:].strip().strip('"')
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    if not title:
        first = next((l for l in body_lines if l), "")
        title = first[:80]
        body = "\n".join(body_lines[body_lines.index(first) + 1 :]).strip()
    return title, body


def make_lede(headline: str, titles: list[str]) -> str:
    if config.LLM_PROVIDER == "mock":
        return _demo("__issue__", "lede")
    user = (
        f"本期主题：{headline}\n"
        f"各篇标题：\n" + "\n".join(f"- {t}" for t in titles) + "\n\n只输出 15–25 个英文单词的导语，不要引号。"
    )
    return _chat(_prompt("lede"), user, max_tokens=120)


def make_headline(titles: list[str]) -> str:
    if config.LLM_PROVIDER == "mock":
        return _demo("__issue__", "headline")
    user = "以下是今天几篇英文科普短文的标题：\n" + "\n".join(f"- {t}" for t in titles) + "\n\n给这一期起一个 4–9 个英文单词的刊名，体现共同主题，不要引号。"
    return _chat(_prompt("headline"), user, max_tokens=80)


def translate_paragraphs(paragraphs: list[str]) -> list[str]:
    """逐段译成中文，用于双语对照。段数对不上时按原文段数补齐/截断。"""
    if not paragraphs:
        return []
    if config.LLM_PROVIDER == "mock":
        return ["" for _ in paragraphs]
    payload = "\n\n".join(paragraphs)
    try:
        raw = _chat(_prompt("translate"), payload, max_tokens=2000)
    except Exception:
        return ["" for _ in paragraphs]
    parts = [p.strip() for p in raw.replace("\r", "").split("\n\n") if p.strip()]
    if len(parts) != len(paragraphs):
        # 段数不一致时退化成按行对齐，宁可少也不要错位
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        parts = lines if len(lines) == len(paragraphs) else parts
    if len(parts) < len(paragraphs):
        parts += [""] * (len(paragraphs) - len(parts))
    return parts[: len(paragraphs)]


def translate_title(title: str) -> str:
    if not title or config.LLM_PROVIDER == "mock":
        return ""
    try:
        return _chat(_prompt("translate"), title, max_tokens=120).strip().replace("\n", " ")
    except Exception:
        return ""


def gloss(words: list[str], context: str = "") -> dict[str, str]:
    words = [w for w in words if w]
    if not words:
        return {}
    if config.LLM_PROVIDER == "mock":
        return {}
    user = "单词：\n" + "\n".join(words) + "\n\n语境片段：\n" + (context or "")[:1200]
    raw = _chat(_prompt("gloss"), user, max_tokens=800)
    out: dict[str, str] = {}
    wanted = {w.lower() for w in words}
    for line in raw.splitlines():
        if "|" not in line:
            continue
        w, _, zh = line.partition("|")
        w = w.strip().lower().strip("-•* ")
        zh = zh.strip()
        if w in wanted and zh and len(zh) <= 20:
            out[w] = zh
    return out
