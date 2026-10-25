"""Pipeline 编排：检查 -> 下载 -> 转写 -> 清洗 -> 摘要 -> 改写 -> 排版。"""

from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

from . import clean, config, fetch, llm, magazine, source, store, transcribe, vocab, wechat_source

RUNS: dict[str, dict] = {}
_lock = threading.Lock()

STEP_LABEL = {
    "queued": "排队",
    "check": "检查",
    "download": "下载音频",
    "transcribe": "转写",
    "clean": "清洗",
    "summarize": "摘要",
    "rewrite": "六级改写",
    "done": "完成",
    "skip": "已处理，跳过",
    "fail": "失败",
}

# 每个步骤在单条视频里的进度权重（百分比）
STEP_PROGRESS = {
    "queued": 0,
    "check": 6,
    "download": 18,
    "transcribe": 62,
    "clean": 70,
    "summarize": 82,
    "rewrite": 92,
    "done": 100,
    "skip": 100,
    "fail": 100,
}


def _recalc(run: dict) -> None:
    """按「已完成步骤 / 视频总数」折算整体进度。运行中最多显示 99%，收尾才置 100。"""
    total = int(run.get("total") or 0) or len(run.get("items") or []) or 1
    done = sum(STEP_PROGRESS.get(it.get("state", "queued"), 0) for it in run.get("items", []))
    pct = max(0, min(100, round(done / total)))
    run["progress"] = min(99, pct) if run.get("status") == "running" else pct


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def get_run(run_id: str) -> dict | None:
    run = RUNS.get(run_id)
    if run:
        return run
    return store.load_run(run_id)


def start_run(trigger: str = "manual", bvids: list[str] | None = None, demo: bool = False,
              wechat_urls: list[str] | None = None) -> dict:
    run = {
        "id": store.new_run_id(),
        "trigger": trigger,
        "demo": demo,
        "started_at": _now(),
        "finished_at": None,
        "status": "running",
        "items": [],
        "ok": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "progress": 0,
        "note": "",
        "magazine": None,
    }
    with _lock:
        RUNS[run["id"]] = run
    store.save_run(run)
    t = threading.Thread(target=_execute, args=(run, bvids, demo, wechat_urls), daemon=True)
    t.start()
    return run


def _item(run: dict, **kw) -> dict:
    item = {
        "bvid": kw.get("bvid", ""),
        "title": kw.get("title", ""),
        "author": kw.get("author", ""),
        "state": kw.get("state", "queued"),
        "detail": kw.get("detail", ""),
        "engine": kw.get("engine", ""),
        "seconds": kw.get("seconds"),
        "updated_at": _now(),
    }
    run["items"].append(item)
    _recalc(run)
    store.save_run(run)
    return item


def _set(item: dict, run: dict, **kw) -> None:
    item.update(kw)
    item["updated_at"] = _now()
    _recalc(run)
    store.save_run(run)


def _execute(run: dict, bvids: list[str] | None, demo: bool = False,
             wechat_urls: list[str] | None = None) -> None:
    try:
        targets = _collect_targets(run, bvids, demo, wechat_urls)
        run["total"] = len(targets)
        _recalc(run)
        if not targets:
            run["status"] = "done"
            run["note"] = "没有需要处理的视频（全部已处理或未配置订阅）"
            run["progress"] = 100
            run["finished_at"] = _now()
            store.save_run(run)
            return

        articles: list[dict] = []
        for target in targets:
            if target.get("skip"):
                run["items"].append(
                    {
                        "bvid": target.get("bvid", ""),
                        "title": target.get("title", ""),
                        "author": target.get("author", ""),
                        "state": "skip",
                        "detail": "该 BV 号已在 processed.json 中",
                        "updated_at": _now(),
                    }
                )
                run["skipped"] += 1
                _recalc(run)
                store.save_run(run)
                continue
            try:
                article = _process_one(run, target)
                if article:
                    articles.append(article)
                    run["ok"] += 1
                    if not run.get("demo"):
                        store.mark_processed(
                            article.get("key") or article["bvid"], title=article.get("title", ""),
                            author=article.get("author", ""), day=time.strftime("%Y-%m-%d"),
                        )
            except Exception as exc:
                run["failed"] += 1
                if run["items"]:
                    _set(run["items"][-1], run, state="fail", detail=str(exc)[:300])
                else:
                    _item(run, state="fail", detail=str(exc)[:300])

        if articles:
            _generate_magazine(run, articles)
            run["status"] = "done"
        else:
            run["status"] = "done"
            run["note"] = run["note"] or "本次没有成功产出的文章"
        run["progress"] = 100
        run["finished_at"] = _now()
        store.save_run(run)
    except Exception:
        run["status"] = "error"
        run["note"] = traceback.format_exc(limit=3)[-600:]
        run["finished_at"] = _now()
        store.save_run(run)


def _collect_targets(run: dict, bvids: list[str] | None, demo: bool = False,
                     wechat_urls: list[str] | None = None) -> list[dict]:
    processed = store.load_processed()
    targets: list[dict] = []
    client = source.BiliClient()

    if wechat_urls:
        for url in wechat_urls:
            key = wechat_source.article_id(url)
            targets.append({"kind": "wechat", "url": url, "bvid": "", "key": key,
                            "title": "", "author": "", "skip": key in processed})
        return targets

    if demo:
        seed_file = config.DEMO_DIR / "seed.json"
        if not seed_file.exists():
            raise RuntimeError("缺少演示数据，请先运行 python scripts/seed_demo.py")
        for s in json.loads(seed_file.read_text(encoding="utf-8")):
            targets.append(
                {
                    "bvid": s["bvid"],
                    "title": s.get("title", ""),
                    "author": s.get("author", ""),
                    "cover": s.get("cover", ""),
                    "demo_transcript": s.get("transcript", ""),
                    "skip": False,
                }
            )
        return targets

    if bvids:
        for bvid in bvids:
            try:
                info = client.video_info(bvid)
            except Exception as exc:
                _item(run, bvid=bvid, state="fail", detail=f"取视频信息失败：{exc}")
                run["failed"] += 1
                continue
            targets.append(_target_from_info(info, processed))
        return targets

    subs = [b for b in store.load_subs() if b.get("enabled", True)]
    if not subs:
        run["note"] = "订阅列表为空"
        return targets

    # 公众号订阅：搜狗发现最新文章（脆弱，失败就跳过该号）
    for sub in [b for b in subs if b.get("kind") == "wechat"]:
        want = int(sub.get("recent_n", 1) or 1)
        try:
            arts = wechat_source.search_account(sub["uid"], want)
        except Exception:
            arts = []
        if not arts:
            run["note"] = f"公众号「{sub.get('name') or sub['uid']}」没取到文章（搜狗可能限流）"
            continue
        for art in arts:
            targets.append({
                "kind": "wechat", "url": art["url"], "key": art["id"],
                "title": art["title"], "author": art["account"] or sub.get("name", ""),
                "skip": art["id"] in processed,
            })
    subs = [b for b in subs if b.get("kind", "bili") != "wechat"]
    if not subs:
        return targets

    # 有 Cookie 走接口；没有就借浏览器登录态读空间页（会自动开合一个 Agent Window）
    if config.BILI_COOKIE:
        for sub in subs:
            n = int(sub.get("recent_n", 1) or 1)
            try:
                vids = client.space_videos(sub["uid"], n)
            except source.SourceBlocked as exc:
                run["note"] = str(exc)
                _item(run, state="fail", detail=f"{sub.get('name','')}：{exc}")
                run["failed"] += 1
                continue
            for v in vids:
                bv = v.get("bvid")
                if not bv:
                    continue
                targets.append(
                    {
                        "bvid": bv,
                        "title": v.get("title", ""),
                        "author": sub.get("name") or v.get("author", ""),
                        "cover": v.get("cover", ""),
                        "pubdate": v.get("pubdate"),
                        "skip": bv in processed,
                    }
                )
        return targets

    from . import browser_source

    try:
        mapping = browser_source.latest_bvs(
            [{"uid": s["uid"], "name": s.get("name", ""), "recent_n": s.get("recent_n", 1)} for s in subs]
        )
    except browser_source.BrowserUnavailable as exc:
        run["note"] = f"浏览器不可用：{exc}。可以改用下方「手动处理视频」直接贴 BV 号。"
        _item(run, state="fail", detail=run["note"])
        run["failed"] += 1
        return targets

    for sub in subs:
        for bv in mapping.get(str(sub["uid"]), []):
            if bv in processed:
                targets.append({"bvid": bv, "title": "", "author": sub.get("name", ""), "skip": True})
                continue
            try:
                info = client.video_info(bv)
            except Exception as exc:
                _item(run, bvid=bv, state="fail", detail=f"取视频信息失败：{exc}")
                run["failed"] += 1
                continue
            t = _target_from_info(info, processed)
            t["author"] = t.get("author") or sub.get("name", "")
            targets.append(t)
    return targets


def _target_from_info(info: dict, processed: dict) -> dict:
    return {
        "bvid": info["bvid"],
        "title": info.get("title", ""),
        "author": info.get("author", ""),
        "cover": info.get("cover", ""),
        "pubdate": info.get("pubdate"),
        "info": info,
        "skip": info["bvid"] in processed,
    }


def _target_words(duration_s: int, transcript_chars: int, chars_per_word: int = 12) -> tuple[int, str, str]:
    """按视频时长 + 信息密度决定篇幅。返回 (目标词数, 密度说明, 时长说明)。

    chars_per_word：口播转写冗余多，约 12 个中文字符才撑 1 个英文词；
    书面文章（公众号）信息密度高，用 4 即可。
    """
    minutes = max(1.0, (duration_s or 0) / 60)
    density = transcript_chars / minutes if transcript_chars else 0

    if minutes <= 5:
        base = 300
    elif minutes <= 15:
        base = 420
    elif minutes <= 30:
        base = 520
    elif minutes <= 60:
        base = 620
    else:
        base = 720

    if density >= 300:
        adj, note = 120, "很高（信息密集）"
    elif density >= 200:
        adj, note = 60, "较高"
    elif density >= 120:
        adj, note = 0, "中等"
    else:
        adj, note = -60, "偏低（口播冗余多）"

    target = base + adj
    # 素材不足以支撑时不要硬凑
    cap = max(240, transcript_chars // chars_per_word)
    target = max(240, min(target, cap))
    return target, note, f"{int(minutes)} 分钟"


def _process_wechat(run: dict, target: dict) -> dict | None:
    """公众号文章：直接抓正文，没有下载与转写两步。"""
    key = target.get("key") or wechat_source.article_id(target["url"])
    item = _item(run, bvid=key, title="", author="", state="check", detail="抓取公众号文章")

    art = wechat_source.fetch_article(target["url"])
    text = art.get("text", "")
    if len(text) < 200:
        raise RuntimeError("公众号正文过短，可能需要在浏览器里打开一次")

    cover_path = config.MEDIA_DIR / ("wx_" + key.replace(":", "_")) / "cover.jpg"
    if not cover_path.exists():
        wechat_source.download_cover(art.get("cover", ""), cover_path)

    _set(item, run, state="clean", title=art["title"],
         detail=f"正文 {len(text)} 字", engine="wechat article")

    # 文章没有时长，按阅读速度折算（每 400 字约 1 分钟）
    pseudo_duration = int(len(text) / 400 * 60)
    target_words, density_note, duration_note = _target_words(pseudo_duration, len(text), chars_per_word=4)
    meta = {
        "title": art["title"],
        "author": art.get("account", ""),
        "pubdate": time.strftime("%Y-%m-%d", time.localtime(art.get("published") or time.time())),
        "target_words": target_words,
        "density_note": density_note,
        "duration_note": duration_note + "（按篇幅折算）",
    }
    _set(item, run, state="summarize", detail=f"生成中文摘要（目标 {target_words} 词）")
    summary = llm.summarize(key, text, meta)

    _set(item, run, state="rewrite", detail=f"改写成 {target_words} 词左右")
    rewritten = llm.rewrite(key, summary, meta)

    # 生成「翻译克隆页」：保留原文排版与图片，正文换成英文，中文藏在下面
    clone_url = ""
    clone_html = ""
    try:
        from . import wechat_clone

        _set(item, run, state="rewrite", detail="生成翻译页（保留原文排版）")
        clone_html = wechat_clone.build_content(art)
        wechat_clone.save_clone(key, wechat_clone.build_clone(art))
        clone_url = f"/wx/{key.replace(':', '_')}"
    except Exception:
        clone_url = ""
        clone_html = ""

    _set(item, run, state="done", detail="完成")
    return {
        "bvid": "",
        "key": key,
        "title": rewritten.get("title", ""),
        "title_zh": art["title"],
        "body": rewritten.get("body", ""),
        "summary": summary,
        "author": art.get("account", ""),
        "pubdate_human": meta["pubdate"],
        "cover_path": str(cover_path) if cover_path.exists() else "",
        "url": clone_url or art["url"],
        "orig_url": art["url"],
        "full_page": clone_url,
        "clone_html": clone_html,
        "caption": f"{art.get('account','')}《{art['title']}》",
        "demo": rewritten.get("note", ""),
    }


def _process_one(run: dict, target: dict) -> dict | None:
    if target.get("kind") == "wechat":
        return _process_wechat(run, target)
    bvid = target["bvid"]
    item = _item(run, bvid=bvid, title=target.get("title", ""), author=target.get("author", ""), state="check")

    client = source.BiliClient()
    demo_text = target.get("demo_transcript")
    if demo_text:
        info = {"title": target.get("title", ""), "author": target.get("author", ""),
                "pubdate": target.get("pubdate") or int(time.time())}
        cover_path = Path(target["cover"]) if target.get("cover") else None
        _set(item, run, state="check", title=info.get("title", ""), detail="演示数据，跳过下载与转写")
        _set(item, run, state="clean", engine="演示样本文本", detail=f"样例转写 {len(demo_text)} 字")
        transcript = clean.clean_transcript(demo_text)
    else:
        info = target.get("info") or client.video_info(bvid)
        _set(item, run, state="check", title=info.get("title", ""), detail="已确认视频信息")

        # 封面
        cover_path = config.MEDIA_DIR / bvid / "cover.jpg"
        if not cover_path.exists() and info.get("cover"):
            client.download_cover(info["cover"], cover_path)

        # 下载
        _set(item, run, state="download", detail="下载音频中")
        t0 = time.time()
        audio = fetch.download_audio(bvid)
        _set(item, run, state="download", detail=f"音频 {audio.stat().st_size/1e6:.1f} MB", seconds=round(time.time()-t0, 1))

        # 转写
        _set(item, run, state="transcribe", detail="转写中")
        t0 = time.time()
        result = transcribe.transcribe(bvid, client, info)
        transcript = clean.clean_transcript(result.get("text", ""))
        if not transcript.strip():
            raise RuntimeError("转写结果为空")
        _set(item, run, state="clean", engine=result.get("engine", ""),
             detail=f"转写 {len(transcript)} 字，用时 {round(time.time()-t0,1)}s", seconds=round(time.time()-t0, 1))

    # LLM 两层
    target_words, density_note, duration_note = _target_words(
        int(info.get("duration") or 0), len(transcript)
    )
    meta = {
        "title": info.get("title", ""),
        "author": info.get("author", ""),
        "pubdate": time.strftime("%Y-%m-%d", time.localtime(info.get("pubdate") or time.time())),
        "target_words": target_words,
        "density_note": density_note,
        "duration_note": duration_note,
    }
    _set(item, run, state="summarize", detail=f"生成中文摘要（目标 {target_words} 词）")
    summary = llm.summarize(bvid, transcript, meta)

    _set(item, run, state="rewrite", detail=f"改写成 {target_words} 词左右")
    rewritten = llm.rewrite(bvid, summary, meta)

    _set(item, run, state="done", detail="完成")
    return {
        "bvid": bvid,
        "title": rewritten.get("title", ""),
        "title_zh": info.get("title", ""),
        "body": rewritten.get("body", ""),
        "summary": summary,
        "author": info.get("author", ""),
        "pubdate_human": meta["pubdate"],
        "cover_path": str(cover_path) if cover_path and cover_path.exists() else "",
        "url": f"https://www.bilibili.com/video/{bvid}",
        "caption": f"{info.get('author','')}《{info.get('title','')}》封面",
        "demo": rewritten.get("note", ""),
    }


def _generate_magazine(run: dict, articles: list[dict]) -> None:
    # 演示运行写到独立文件，绝不覆盖当天真实的一期
    day = "demo" if run.get("demo") else time.strftime("%Y-%m-%d")

    # 先合并进当天已有的一期，再据此生成刊名/导语（手动单条不会把整期冲掉）
    prev = store.read_json(config.MAGAZINE_DIR / f"daily-magazine-{day}.json", {})
    if prev.get("articles"):
        merged: dict[str, dict] = {}
        for a in prev["articles"]:
            merged[a.get("key") or a.get("bvid") or a.get("url", "")] = a
        for a in articles:
            merged[a.get("key") or a.get("bvid") or a.get("url", "")] = a
        articles = list(merged.values())

    titles = [a["title"] for a in articles]
    try:
        headline = llm.make_headline(titles)
        lede = llm.make_lede(headline, titles)
    except Exception:
        headline = prev.get("headline") or "Today's Science Digest"
        lede = prev.get("lede") or "A daily briefing on what creators are explaining, in plain English."
    bloggers = sorted({a.get("author", "") for a in articles if a.get("author")})

    # 补超纲词释义：词表查不到的交由 LLM 按语境补，结果缓存到 data/vocab/glossary.json
    try:
        texts = [a.get("body", "") for a in articles]
        missing = vocab.missing_adv_words(texts)
        if missing:
            glosses = llm.gloss(missing, "\n".join(texts))
            if glosses:
                vocab.set_glosses(glosses)
    except Exception:
        pass

    # 逐段中文译文（双语对照用），只在缺的时候调用
    try:
        for a in articles:
            if not a.get("paragraphs_zh"):
                a["paragraphs_zh"] = llm.translate_paragraphs(
                    magazine.paragraphs_of(a.get("body", ""))
                )
    except Exception:
        pass

    prev = store.read_json(config.MAGAZINE_DIR / f"daily-magazine-{day}.json", {})
    issue = prev.get("issue") or (len(store.list_magazines()) + 1)
    headline_zh = ""
    try:
        headline_zh = llm.translate_title(headline)
    except Exception:
        pass
    html, meta = magazine.render_magazine(
        day=day,
        issue=issue,
        headline=headline,
        lede=lede,
        articles=articles,
        bloggers=bloggers,
        cold_fact="SenseVoice 是非自回归模型，一次前向出一整句，所以 40 分钟视频 68 秒就转完了。",
        headline_zh=headline_zh,
    )
    path = store.save_magazine(day, html, meta)
    # 存一张缩略图给首页卡片用（第一篇文章的封面）
    first_cover = next((a.get("cover_path") for a in articles if a.get("cover_path")), "")
    if first_cover and Path(first_cover).exists():
        try:
            dst = config.MAGAZINE_DIR / f"thumb-{day}.jpg"
            dst.write_bytes(Path(first_cover).read_bytes())
        except Exception:
            pass
    run["magazine"] = {"day": day, "file": path.name}
    store.save_run(run)
