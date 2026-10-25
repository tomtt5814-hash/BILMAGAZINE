"""把公众号原文做成「翻译页」：保留正文段落与图片，文字换成英文，中文原文可切换显示。

做法：抓原始 HTML → 取 #js_content → 把块级文字分批英译并就地替换（中文放进隐藏 span）
→ 用自带外壳渲染（不加载微信的 JS，避免它重写 DOM）。

已知限制：评论/点赞是微信页面加载后异步拉取的，离开原域名拿不到，所以这里只放回原文的链接。
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import re

from lxml import etree, html as lxml_html

from . import config, llm, vocab

SKIP_TAGS = {"script", "style", "svg", "iframe", "video", "audio"}

SHELL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
body{margin:0;background:#fff;color:#333;font:16px/1.85 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:680px;margin:0 auto;padding:28px 20px 90px}
h1.art-title{font-size:22px;line-height:1.4;margin:0 0 10px;font-weight:600}
.art-meta{font-size:13px;color:#8b8b8b;margin:0 0 24px}
.art-meta a{color:#576b95;text-decoration:none}
.content p,.content section{margin:0 0 18px}
.content img{max-width:100%%;height:auto;display:block;margin:14px auto;border-radius:4px}
.zh-orig{display:none}
body.show-zh .zh-orig{display:block;color:#8f8a80;font-size:14.5px;line-height:1.8;
 border-left:2px solid #e6e0d4;padding-left:10px;margin-top:6px}
.w{font-style:normal}
.w-basic{font-weight:500;color:inherit}
.w-adv{font-weight:400;color:inherit}
.w-cet6{color:#1f5fa8;cursor:pointer;border-bottom:1px dotted rgba(31,95,168,.45)}
.w-cet6:hover{border-bottom-color:#1f5fa8}
.w .zh{display:none;font-family:ui-sans-serif,sans-serif;font-size:12px;font-weight:400;
 color:#4a7aa8;padding-left:2px}
.w .zh:before{content:"（"}
.w .zh:after{content:"）"}
.w-adv .zh{color:#8a8072;font-size:11.5px}
.w-cet6.on .zh{display:inline}
body.show-cet6 .w-cet6 .zh{display:inline}
body.show-adv .w-adv .zh{display:inline}
.tctl{position:fixed;right:16px;bottom:16px;display:flex;gap:6px;padding:7px;background:rgba(255,255,255,.96);
 border:1px solid #e2ddd2;box-shadow:0 2px 10px rgba(0,0,0,.08)}
.tbtn{font:12px ui-sans-serif,sans-serif;padding:5px 10px;border:1px solid #ddd4c4;background:#fff;color:#6b6459;cursor:pointer}
.tbtn.on{background:#15140f;color:#f6f2ea;border-color:#15140f}
body.embed .tctl{display:none}
</style></head>
<body><div class="wrap">
<h1 class="art-title">%(title)s</h1>
<p class="art-meta">%(author)s · %(account)s · %(date)s · <a href="%(url)s" target="_blank" rel="noopener">微信原文（含评论）↗</a></p>
<div class="content">%(content)s</div>
</div>
<div class="tctl">
  <button class="tbtn" data-toggle="zh">显示中文原文</button>
  <button class="tbtn" data-toggle="cet6">CET-6 释义</button>
  <button class="tbtn" data-toggle="adv">超纲词释义</button>
</div>
<script>
(function(){
  var embedded = location.search.indexOf('embed=1') >= 0;
  if (embedded) document.body.classList.add('embed');

  document.querySelectorAll('.tbtn').forEach(function(btn){
    btn.addEventListener('click', function(){
      var key = this.getAttribute('data-toggle');
      var on = this.classList.toggle('on');
      document.body.classList.toggle('show-' + key, on);
      if (key === 'zh') this.textContent = on ? '隐藏中文原文' : '显示中文原文';
    });
  });

  // 被嵌进杂志时，由外层按钮统一驱动（同源直接改 DOM，跨源走 postMessage）
  window.addEventListener('message', function(e){
    var d = e.data || {};
    if (d.type !== 'toggle' || !d.key) return;
    document.body.classList.toggle('show-' + d.key, !!d.on);
  });
})();
</script>
</body></html>
"""


def _blocks(root) -> list:
    """挑出承载正文文字的块级节点（只取最内层，避免重复翻译）。"""
    out = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag.lower() in SKIP_TAGS:
            continue
        if el.tag.lower() not in ("p", "section", "span", "li", "h1", "h2", "h3", "blockquote"):
            continue
        if len("".join(el.itertext()).strip()) < 12:
            continue
        if any(isinstance(ch.tag, str) and ch.tag.lower() in ("p", "section", "li")
               and len("".join(ch.itertext()).strip()) >= 12 for ch in el):
            continue
        out.append(el)
    return out


def _cache_path():
    return config.DATA_DIR / "wechat" / "translate_cache.json"


def _load_cache() -> dict:
    p = _cache_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _translate(texts: list[str]) -> list[str]:
    """带磁盘缓存的批量翻译，块数严格对齐。"""
    cache = _load_cache()
    keys = [hashlib.md5(t.encode()).hexdigest() for t in texts]
    result = [cache.get(k, "") for k in keys]
    todo = [(i, t, k) for i, (t, k) in enumerate(zip(texts, keys)) if not result[i]]
    if not todo:
        return result

    batch: list[str] = []
    size = 0
    chunks: list[list[tuple[int, str, str]]] = []
    for item in todo:
        if size + len(item[1]) > 1800 and batch:
            chunks.append(batch)
            batch, size = [], 0
        batch.append(item)
        size += len(item[1])
    if batch:
        chunks.append(batch)

    for chunk in chunks:
        payload = "\n@@\n".join(t for _, t, _ in chunk)
        try:
            raw = llm._chat(  # noqa: SLF001
                "你是英中翻译。逐段把中文译成英文，段与段之间用单独一行 @@ 分隔，"
                "段数必须与输入完全一致；不要解释、不要编号、不要合并段落。",
                payload,
                max_tokens=max(800, len(payload) * 2),
            )
            parts = [p.strip() for p in re.split(r"\n\s*@@\s*\n", raw)]
        except Exception:
            parts = []
        if len(parts) != len(chunk):
            parts = []
            for _, t, _ in chunk:
                try:
                    parts.append(llm._chat("把这段中文译成英文，只输出译文。", t, max_tokens=600).strip())
                except Exception:
                    parts.append("")
        for (idx, zh, k), en in zip(chunk, parts):
            if en and en != zh:
                result[idx] = en
                cache[k] = en
        _save_cache(cache)

    return [r or t for r, t in zip(result, texts)]


def _strip_inline_font(el) -> None:
    """去掉微信带来的行内字号/行高，否则它会压过杂志的字号变量。"""
    style = el.get("style")
    if not style:
        return
    kept = []
    for decl in style.split(";"):
        name = decl.split(":", 1)[0].strip().lower()
        if name in ("font-size", "line-height"):
            continue
        if decl.strip():
            kept.append(decl.strip())
    if kept:
        el.set("style", "; ".join(kept) + ";")
    else:
        el.attrib.pop("style", None)


def build_content(article: dict, ctx: dict[str, str] | None = None) -> str:
    """只产出正文 HTML（内联进杂志用），不含外壳与标题。

    ctx：语境义覆盖表，交给词汇层优先使用。
    """
    raw = article.get("html") or ""
    if not raw:
        raise ValueError("缺少原始 HTML")
    doc = lxml_html.fromstring(raw)
    root = doc.get_element_by_id("js_content", None)
    if root is None:
        # RSS 里的正文结构是普通的 <p>/<div>，没有 js_content 容器
        root = doc.find(".//body") if doc.find(".//body") is not None else doc
    if root is None:
        raise ValueError("找不到正文")

    for s in list(root.iter("script", "style")):
        s.drop_tree()

    blocks = _blocks(root)
    texts = [" ".join("".join(b.itertext()).split()) for b in blocks]
    translated = _translate(texts)

    # 供语境义分析用的纯英文
    article.setdefault("plain_en", " ".join(t for t in translated if t))

    for el, zh, en in zip(blocks, texts, translated):
        if not en:
            continue
        keep = [ch for ch in el if isinstance(ch.tag, str) and ch.tag.lower() in ("img", "br")]
        for ch in list(el):
            if ch not in keep:
                el.remove(ch)
        # 英文正文套上三层词汇标注（保留节点间的空白 tail，否则单词会粘在一起）
        frag = lxml_html.fragment_fromstring(vocab.annotate(en, ctx), create_parent="div")
        el.text = frag.text
        for ch in list(frag):
            el.append(ch)
        span = etree.SubElement(el, "span")
        span.set("class", "zh-orig")
        span.text = zh

    for img in root.iter("img"):
        img.set("referrerpolicy", "no-referrer")
        if not img.get("src") and img.get("data-src"):
            img.set("src", img.get("data-src"))
        for attr in ("data-src", "data-original", "srcset"):
            img.attrib.pop(attr, None)

    for el in root.iter():
        if isinstance(el.tag, str):
            _strip_inline_font(el)

    return "".join(
        lxml_html.tostring(ch, encoding="unicode") for ch in root if isinstance(ch.tag, str)
    )


def build_clone(article: dict) -> str:
    content = build_content(article)
    published = article.get("published")
    date = ""
    if published:
        import datetime as dt

        date = dt.datetime.fromtimestamp(published).strftime("%Y年%m月%d日")
    return SHELL % {
        "title": html_mod.escape(article.get("title", "")),
        "author": html_mod.escape(article.get("author", "") or article.get("account", "")),
        "account": html_mod.escape(article.get("account", "")),
        "date": date,
        "url": html_mod.escape(article.get("url", "")),
        "content": content,
    }


def clone_path(key: str):
    return config.DATA_DIR / "wechat" / f"{key.replace(':', '_')}.html"


def save_clone(key: str, html: str) -> None:
    p = clone_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
