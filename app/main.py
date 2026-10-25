"""本地 Web 应用入口：订阅管理、手动/补跑、杂志预览、历史。"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, runner, source, store, transcribe, vocab

ROOT = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


SKIP_ONCE = config.DATA_DIR / "skip_once"


def _scheduled_run():
    """定时触发入口。若存在 skip_once 标记，只跳过这一次（用完即删）。"""
    if SKIP_ONCE.exists():
        try:
            SKIP_ONCE.unlink()
        except OSError:
            pass
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        run = {
            "id": store.new_run_id(),
            "trigger": "cron-skipped",
            "started_at": now,
            "finished_at": now,
            "status": "done",
            "items": [],
            "ok": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
            "progress": 100,
            "note": "本次定时按标记跳过（skip_once），不发请求、不调用模型",
            "magazine": None,
        }
        store.save_run(run)
        return
    runner.start_run(trigger="cron")


@asynccontextmanager
async def lifespan(app: FastAPI):
    vocab.load_gloss_cache()
    if config.SCHEDULE_ENABLED:
        hh, mm = (config.SCHEDULE_TIME.split(":") + ["0"])[:2]
        scheduler.add_job(
            _scheduled_run,
            CronTrigger(hour=int(hh), minute=int(mm)),
            id="daily",
            replace_existing=True,
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="博主日报杂志", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def _status() -> dict:
    import shutil

    cpp_ok, cpp_info = transcribe.whisper_available()
    faster_ok = transcribe.faster_available()
    if transcribe.sensevoice_available():
        asr_label, asr_ok = "sensevoice-small (ONNX)", True
    elif cpp_ok:
        asr_label, asr_ok = "whisper.cpp", True
    elif faster_ok:
        asr_label, asr_ok = f"faster-whisper ({Path(str(config.FASTER_MODEL)).name})", True
    else:
        asr_label, asr_ok = "不可用", False

    if config.BILI_COOKIE:
        src_label, src_ok = "接口 Cookie", True
        src_hint = "已配置 Cookie，走接口取最新一期"
    elif shutil.which("bsk"):
        src_label, src_ok = "浏览器登录态", True
        src_hint = "借本机浏览器登录态取最新一期（会短暂开窗）"
    else:
        src_label, src_ok = "未配置", False
        src_hint = "需要 bsk 浏览器插件，或配置 BILI_COOKIE"

    return {
        "llm_provider": config.LLM_PROVIDER,
        "llm_key": bool(config.LLM_API_KEY),
        "llm_model": config.LLM_MODEL,
        "asr_ok": asr_ok,
        "asr_label": asr_label,
        "src_ok": src_ok,
        "src_label": src_label,
        "src_hint": src_hint,
        "whisper_ok": asr_ok,
        "whisper_info": cpp_info,
        "cookie": bool(config.BILI_COOKIE),
        "schedule": f"{config.SCHEDULE_TIME} 每日" if config.SCHEDULE_ENABLED else "关闭（手动触发）",
        "next_run": _next_run(),
    }


def _next_run() -> str:
    if not config.SCHEDULE_ENABLED or not scheduler.running:
        return ""
    job = scheduler.get_job("daily")
    return job.next_run_time.strftime("%m-%d %H:%M") if job and job.next_run_time else ""


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    recent = store.list_runs(3)
    active = next((r for r in recent if r.get("status") == "running"), None)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "mags": store.list_magazines(), "active_run": active},
    )


@app.get("/manage", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "subs": store.load_subs(),
            "status": _status(),
            "runs": store.list_runs(8),
            "magazines": store.list_magazines(),
            "processed_count": len(store.load_processed()),
        },
    )


@app.get("/magazine-thumb/{day}")
def magazine_thumb(day: str):
    from fastapi.responses import FileResponse

    path = config.MAGAZINE_DIR / f"thumb-{day}.jpg"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="image/jpeg")


@app.post("/subscriptions")
def add_subscription(uid_input: str = Form(...), name: str = Form(""), recent_n: int = Form(1)):
    uid = source.parse_uid(uid_input)
    if not uid:
        return RedirectResponse("/?err=uid", status_code=303)
    store.add_sub(uid, name.strip(), recent_n)
    return RedirectResponse("/", status_code=303)


@app.post("/subscriptions/{uid}/toggle")
def toggle_subscription(uid: str):
    for b in store.load_subs():
        if b["uid"] == uid:
            store.update_sub(uid, enabled=not b.get("enabled", True))
    return RedirectResponse("/", status_code=303)


@app.post("/subscriptions/{uid}/n")
def set_recent_n(uid: str, recent_n: int = Form(...)):
    store.update_sub(uid, recent_n=max(1, min(int(recent_n), 5)))
    return RedirectResponse("/", status_code=303)


@app.post("/subscriptions/{uid}/delete")
def delete_subscription(uid: str):
    store.remove_sub(uid)
    return RedirectResponse("/", status_code=303)


@app.post("/run")
def trigger_run(bv_input: str = Form("")):
    raw = [x.strip() for x in bv_input.replace("，", ",").split(",") if x.strip()]
    wechat = [x for x in raw if "mp.weixin.qq.com" in x]
    bvs = [b for b in (source.parse_bvid(x) for x in raw) if b]
    run = runner.start_run(trigger="manual", bvids=bvs or None, wechat_urls=wechat or None)
    return RedirectResponse(f"/manage?run={run['id']}", status_code=303)


@app.post("/subscribe-wechat")
def subscribe_wechat(account: str = Form(...), recent_n: int = Form(1)):
    name = account.strip()
    if name:
        store.add_sub(name, name, recent_n, kind="wechat")
    return RedirectResponse("/manage", status_code=303)


@app.post("/run-demo")
def trigger_demo_run():
    run = runner.start_run(trigger="demo", demo=True)
    return RedirectResponse(f"/manage?run={run['id']}", status_code=303)


@app.get("/api/runs/{run_id}")
def api_run(run_id: str):
    run = runner.get_run(run_id)
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(run)


@app.get("/api/status")
def api_status():
    return JSONResponse(_status())


@app.get("/magazine/{day}", response_class=HTMLResponse)
def magazine_page(day: str):
    path = config.MAGAZINE_DIR / f"daily-magazine-{day}.html"
    if not path.exists():
        return HTMLResponse("<h1>404</h1><p>这一期还没有生成。</p>", status_code=404)
    return HTMLResponse(path.read_text(encoding="utf-8"))
