"""Pipeline 编排：检查 -> 下载 -> 转写 -> 清洗 -> 摘要 -> 改写 -> 排版。"""

from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

from . import clean, config, fetch, llm, magazine, source, store, transcribe, vocab

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


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def get_run(run_id: str) -> dict | None:
    run = RUNS.get(run_id)
    if run:
        return run
    return store.load_run(run_id)


def start_run(trigger: str = "manual", bvids: list[str] | None = None, demo: bool = False) -> dict:
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
        "note": "",
        "magazine": None,
    }
    with _lock:
        RUNS[run["id"]] = run
    store.save_run(run)
    t = threading.Thread(target=_execute, args=(run, bvids, demo), daemon=True)
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
    store.save_run(run)
    return item


def _set(item: dict, run: dict, **kw) -> None:
    item.update(kw)
    item["updated_at"] = _now()
    store.save_run(run)


def _execute(run: dict, bvids: list[str] | None, demo: bool = False) -> None:
    try:
        targets = _collect_targets(run, bvids, demo)
        if not targets:
            run["status"] = "done"
            run["note"] = "没有需要处理的视频（全部已处理或未配置订阅）"
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
                store.save_run(run)
                continue
            try:
                article = _process_one(run, target)
                if article:
                    articles.append(article)
                    run["ok"] += 1
                    store.mark_processed(
                        article["bvid"], title=article.get("title", ""),
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
        run["finished_at"] = _now()
        store.save_run(run)
    except Exception:
        run["status"] = "error"
        run["note"] = traceback.format_exc(limit=3)[-600:]
        run["finished_at"] = _now()
        store.save_run(run)


def _collect_targets(run: dict, bvids: list[str] | None, demo: bool = False) -> list[dict]:
    processed = store.load_processed()
    targets: list[dict] = []
    client = source.BiliClient()

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


def _process_one(run: dict, target: dict) -> dict | None:
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
    meta = {
        "title": info.get("title", ""),
        "author": info.get("author", ""),
        "pubdate": time.strftime("%Y-%m-%d", time.localtime(info.get("pubdate") or time.time())),
    }
    _set(item, run, state="summarize", detail="生成中文摘要")
    summary = llm.summarize(bvid, transcript, meta)

    _set(item, run, state="rewrite", detail="改写成六级科普短文")
    rewritten = llm.rewrite(bvid, summary, meta)

    _set(item, run, state="done", detail="完成")
    return {
        "bvid": bvid,
        "title": rewritten.get("title", ""),
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
    day = time.strftime("%Y-%m-%d")
    titles = [a["title"] for a in articles]
    try:
        headline = llm.make_headline(titles)
        lede = llm.make_lede(headline, titles)
    except Exception:
        headline = "Today's Science Digest"
        lede = "A daily briefing on what creators are explaining, in plain English."
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

    prev = store.read_json(config.MAGAZINE_DIR / f"daily-magazine-{day}.json", {})
    issue = prev.get("issue") or (len(store.list_magazines()) + 1)
    html, meta = magazine.render_magazine(
        day=day,
        issue=issue,
        headline=headline,
        lede=lede,
        articles=articles,
        bloggers=bloggers,
        cold_fact="whisper.cpp 的 Vulkan 后端让 AMD 显卡也能跑本地转写——这条管线每天只在你睡觉时启动一次。",
    )
    path = store.save_magazine(day, html, meta)
    run["magazine"] = {"day": day, "file": path.name}
    store.save_run(run)
