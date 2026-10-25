"""转写文本清洗：去时间戳、去口播填充词、去重复句、规整换行。"""

from __future__ import annotations

import re

_TS = re.compile(r"\[?\d{1,2}:\d{2}(:\d{2})?\]?")
_FILLERS = [
    "大家好", "那么", "就是说", "然后呢", "这个呢", "对吧", "是吧", "嗯", "额", "呃",
    "好的", "我们来看一下", "我们看一下", "可以看到", "接下来",
]


def clean_transcript(text: str) -> str:
    if not text:
        return ""
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        line = _TS.sub("", raw).strip()
        if not line:
            continue
        # 去掉纯语气词行
        stripped = line
        for f in _FILLERS:
            stripped = stripped.replace(f, "")
        stripped = re.sub(r"[\s，,。、]+", "", stripped)
        if len(stripped) < 2:
            continue
        lines.append(line)

    # 合并成以句号断开的段落，去掉相邻重复句
    joined = " ".join(lines)
    sentences = re.split(r"(?<=[。！？!?])", joined)
    out: list[str] = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if out and _similar(s, out[-1]):
            continue
        out.append(s)

    # 每 4~6 句分一段
    paras, cur = [], []
    for s in out:
        cur.append(s)
        if len(cur) >= 5:
            paras.append("".join(cur))
            cur = []
    if cur:
        paras.append("".join(cur))
    return "\n\n".join(p.strip() for p in paras if p.strip())


def _similar(a: str, b: str) -> bool:
    a2 = re.sub(r"\s", "", a)
    b2 = re.sub(r"\s", "", b)
    if not a2 or not b2:
        return False
    if a2 == b2:
        return True
    short, long_ = (a2, b2) if len(a2) <= len(b2) else (b2, a2)
    return len(short) > 6 and short in long_
