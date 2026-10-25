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


def _scheduled_run():
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
    ok, info = transcribe.whisper_available()
    return {
        "llm_provider": config.LLM_PROVIDER,
        "llm_key": bool(config.LLM_API_KEY),
        "llm_model": config.LLM_MODEL,
        "whisper_ok": ok,
        "whisper_info": info,
        "cookie": bool(config.BILI_COOKIE),
        "schedule": f"{config.SCHEDULE_TIME} 每日" if config.SCHEDULE_ENABLED else "未启用",
        "next_run": _next_run(),
    }


def _next_run() -> str:
    if not config.SCHEDULE_ENABLED or not scheduler.running:
        return ""
    job = scheduler.get_job("daily")
    return job.next_run_time.strftime("%m-%d %H:%M") if job and job.next_run_time else ""


@app.get("/", response_class=HTMLResponse)
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
    bvs = [b for b in (source.parse_bvid(x) for x in bv_input.replace("，", ",").split(",")) if b]
    run = runner.start_run(trigger="manual", bvids=bvs or None)
    return RedirectResponse(f"/?run={run['id']}", status_code=303)


@app.post("/run-demo")
def trigger_demo_run():
    run = runner.start_run(trigger="demo", demo=True)
    return RedirectResponse(f"/?run={run['id']}", status_code=303)


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
