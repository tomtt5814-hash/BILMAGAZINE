"""V2 词汇层：三层判定（超纲 / CET-6 / 正常）+ 词条渲染。

判定规则（按需求书 7.15，先规则跑通）：
  1. 命中 CET-6 词表            -> cet6（蓝色，可点）
  2. 命中基础词表（初中/高中/四级） -> basic（正常词，粗体）
  3. 其余且词长 >= 6            -> adv（超纲，细体，释义来自考研/托福/SAT 补充表）
释义来源：CET-6 表自带中英对照；超纲词的释义取自考研/托福/SAT 三张表的交集补全。
"""

from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

from . import config

VOCAB_DIR = config.DATA_DIR / "vocab"

TIER_CET6 = "cet6"
TIER_BASIC = "basic"
TIER_ADV = "adv"

_WORD_RE = re.compile(r"([A-Za-z][A-Za-z'’\-]*[A-Za-z]|[A-Za-z])")
_SUFFIXES = ("'s", "’s", "ies", "es", "s", "ing", "ed", "ly", "er", "est")

# 词表里查不到的超纲词，由 LLM 补的释义（进程内 + 磁盘缓存）
_GLOSS_OVERLAY: dict[str, str] = {}
GLOSS_CACHE = VOCAB_DIR / "glossary.json"


def load_gloss_cache() -> None:
    import json

    if GLOSS_CACHE.exists():
        try:
            _GLOSS_OVERLAY.update(json.loads(GLOSS_CACHE.read_text(encoding="utf-8")))
        except Exception:
            pass


def set_glosses(mapping: dict[str, str]) -> None:
    import json

    _GLOSS_OVERLAY.update(mapping)
    try:
        if GLOSS_CACHE.parent.exists():
            merged = dict(_GLOSS_OVERLAY)
            GLOSS_CACHE.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _load_pairs(name: str) -> dict[str, str]:
    path = VOCAB_DIR / f"{name}.txt"
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        word = parts[0].strip().lower()
        meaning = parts[1].strip() if len(parts) > 1 else ""
        if word and " " not in word:
            out.setdefault(word, meaning)
    return out


class Vocabulary:
    def __init__(self) -> None:
        self.basic = {}
        for name in ("junior", "senior", "cet4"):
            self.basic.update(_load_pairs(name))
        self.cet6 = _load_pairs("cet6")
        self.extra = {}
        for name in ("kaoyan", "toefl", "sat"):
            self.extra.update(_load_pairs(name))
        self.loaded = bool(self.cet6)

    # ---- 判定 ----
    def _variants(self, word: str) -> list[str]:
        w = word.lower().strip("'’-")
        out = [w]
        if w.endswith("ies") and len(w) > 4:
            out.append(w[:-3] + "y")
        for suf in _SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                base = w[: -len(suf)]
                out.append(base)
                if suf in ("ies", "es", "s") and not base.endswith("e"):
                    out.append(base + "e")
                if suf == "ing":
                    out.append(base + "e")
                    if len(base) > 2 and base[-1] == base[-2]:
                        out.append(base[:-1])
                if suf == "ed":
                    out.append(base + "e")
        return out

    def classify(self, word: str) -> tuple[str, str]:
        # 缩写/所有格（you're, hadn't, tesla's）不参与分级
        if "'" in word or "’" in word:
            return TIER_BASIC, ""
        for v in self._variants(word):
            if v in self.cet6:
                return TIER_CET6, self.cet6[v]
        for v in self._variants(word):
            if v in self.basic:
                return TIER_BASIC, ""
        if len(word.strip("'’-")) >= 6:
            for v in self._variants(word):
                if v in self.extra:
                    return TIER_ADV, self.extra[v]
            if word.lower() in _GLOSS_OVERLAY:
                return TIER_ADV, _GLOSS_OVERLAY[word.lower()]
            return TIER_ADV, ""
        return TIER_BASIC, ""


@lru_cache(maxsize=1)
def get_vocab() -> Vocabulary:
    return Vocabulary()


def missing_adv_words(texts: list[str], limit: int = 40) -> list[str]:
    """找出既不在词表、也没有缓存释义的超纲词。"""
    vocab = get_vocab()
    seen: list[str] = []
    for text in texts:
        for m in _WORD_RE.finditer(text):
            w = m.group(0)
            if len(w.strip("'’-")) < 6 or "'" in w or "’" in w:
                continue
            if w[:1].isupper() and not _at_sentence_start(text, m.start()):
                continue
            tier, meaning = vocab.classify(w)
            if tier == TIER_ADV and not meaning:
                lw = w.lower()
                if lw not in seen:
                    seen.append(lw)
            if len(seen) >= limit:
                return seen
    return seen


def _span(word: str, tier: str, meaning: str) -> str:
    text = html.escape(word)
    if tier == TIER_BASIC:
        return f'<span class="w w-basic">{text}</span>'
    full = (meaning or "").strip()
    short = full.split("；")[0].split(";")[0].strip()
    short = re.sub(r"^[a-z]+\.\s*", "", short)[:14]
    zh = html.escape(short) if short else ""
    cls = "w-cet6" if tier == TIER_CET6 else "w-adv"
    attrs = f' data-zh="{html.escape(short, quote=True)}"' if short else ""
    if full:
        attrs += f' title="{html.escape(full[:80], quote=True)}"'
    inner = f'<i class="zh">{zh}</i>' if zh else ""
    return f'<span class="w {cls}"{attrs}>{text}{inner}</span>'


def annotate(text: str, ctx: dict[str, str] | None = None) -> str:
    """把一段英文转成带三层标注的 HTML（保留原有空白与标点）。

    ctx：语境义覆盖表 {小写词: 中文}，优先于词表里的词典义。
    """
    vocab = get_vocab()
    if not vocab.loaded:
        return html.escape(text)
    ctx = ctx or {}
    out: list[str] = []
    pos = 0
    for m in _WORD_RE.finditer(text):
        if m.start() > pos:
            out.append(html.escape(text[pos : m.start()]))
        word = m.group(0)
        tier, meaning = vocab.classify(word)
        # 专有名词：首字母大写、且不在句首、且小写不在词典里 -> 当作普通词，不标注
        if tier == TIER_ADV and word[:1].isupper() and not _at_sentence_start(text, m.start()):
            tier, meaning = TIER_BASIC, ""
        if tier in (TIER_CET6, TIER_ADV) and word.lower() in ctx:
            meaning = ctx[word.lower()]
        out.append(_span(word, tier, meaning))
        pos = m.end()
    if pos < len(text):
        out.append(html.escape(text[pos:]))
    return "".join(out)


def _at_sentence_start(text: str, idx: int) -> bool:
    i = idx - 1
    while i >= 0 and text[i] in " \t\n\r\"'“‘([":
        i -= 1
    if i < 0:
        return True
    return text[i] in ".!?。！？:"


def ctx_targets(texts: list[str], limit: int = 120) -> list[str]:
    """需要语境义的词：CET-6 与超纲词里出现过的（按出现次数排序）。"""
    vocab = get_vocab()
    counts: dict[str, int] = {}
    for text in texts:
        for m in _WORD_RE.finditer(text):
            w = m.group(0)
            tier, _ = vocab.classify(w)
            if tier in (TIER_CET6, TIER_ADV):
                lw = w.lower()
                counts[lw] = counts.get(lw, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def stats(text: str) -> dict:
    vocab = get_vocab()
    counts = {TIER_CET6: 0, TIER_ADV: 0, TIER_BASIC: 0}
    for m in _WORD_RE.finditer(text):
        tier, _ = vocab.classify(m.group(0))
        counts[tier] = counts.get(tier, 0) + 1
    total = max(sum(counts.values()), 1)
    return {
        "cet6": counts[TIER_CET6],
        "adv": counts[TIER_ADV],
        "basic": counts[TIER_BASIC],
        "total": total,
        "cet6_pct": round(counts[TIER_CET6] * 100 / total, 1),
        "adv_pct": round(counts[TIER_ADV] * 100 / total, 1),
    }
