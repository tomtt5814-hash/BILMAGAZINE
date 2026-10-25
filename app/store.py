"""JSON 文件存储：原子写入 + 损坏自愈（对应需求书 7.14）。"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from . import config


def read_json(path: Path, default: Any) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        corrupt = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        try:
            path.replace(corrupt)
        except OSError:
            pass
        return default


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


# ---------- 订阅 ----------

def load_subs() -> list[dict]:
    data = read_json(config.SUBS_FILE, {"bloggers": []})
    return data.get("bloggers", [])


def save_subs(items: list[dict]) -> None:
    write_json(config.SUBS_FILE, {"bloggers": items})


def add_sub(uid: str, name: str = "", recent_n: int = 1) -> dict:
    items = load_subs()
    for b in items:
        if b["uid"] == uid:
            b["enabled"] = True
            save_subs(items)
            return b
    item = {
        "uid": uid,
        "name": name or f"UP主 {uid}",
        "enabled": True,
        "recent_n": max(1, min(int(recent_n), 5)),
        "added_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    items.append(item)
    save_subs(items)
    return item


def update_sub(uid: str, **changes) -> list[dict]:
    items = load_subs()
    for b in items:
        if b["uid"] == uid:
            b.update({k: v for k, v in changes.items() if v is not None})
    save_subs(items)
    return items


def remove_sub(uid: str) -> list[dict]:
    items = [b for b in load_subs() if b["uid"] != uid]
    save_subs(items)
    return items


# ---------- 已处理记录 ----------

def load_processed() -> dict:
    return read_json(config.PROCESSED_FILE, {})


def is_processed(bvid: str) -> bool:
    return bvid in load_processed()


def mark_processed(bvid: str, **info) -> None:
    data = load_processed()
    data[bvid] = {
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **info,
    }
    write_json(config.PROCESSED_FILE, data)


# ---------- 运行日志 ----------

def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def save_run(run: dict) -> None:
    write_json(config.RUN_DIR / f"{run['id']}.json", run)


def load_run(run_id: str) -> dict | None:
    return read_json(config.RUN_DIR / f"{run_id}.json", None)


def list_runs(limit: int = 20) -> list[dict]:
    files = sorted(config.RUN_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": r.get("id"),
                    "started_at": r.get("started_at"),
                    "finished_at": r.get("finished_at"),
                    "status": r.get("status"),
                    "ok": r.get("ok", 0),
                    "failed": r.get("failed", 0),
                    "skipped": r.get("skipped", 0),
                    "note": r.get("note", ""),
                }
            )
        except Exception:
            continue
    return out


# ---------- 杂志 ----------

def save_magazine(day: str, html: str, meta: dict) -> Path:
    path = config.MAGAZINE_DIR / f"daily-magazine-{day}.html"
    path.write_text(html, encoding="utf-8")
    write_json(config.MAGAZINE_DIR / f"daily-magazine-{day}.json", meta)
    return path


def list_magazines() -> list[dict]:
    out = []
    for f in sorted(config.MAGAZINE_DIR.glob("daily-magazine-*.html"), reverse=True):
        day = f.stem.replace("daily-magazine-", "")
        if day == "demo":
            continue
        meta = read_json(f.with_suffix(".json"), {})
        thumb = config.MAGAZINE_DIR / f"thumb-{day}.jpg"
        out.append(
            {
                "day": day,
                "file": f.name,
                "title": meta.get("headline", f"每日杂志 {day}"),
                "lede": meta.get("lede", ""),
                "issue": meta.get("issue", 0),
                "count": meta.get("count", 0),
                "bloggers": meta.get("bloggers", []),
                "size_kb": round(f.stat().st_size / 1024),
                "mtime": int(f.stat().st_mtime),
                "thumb": thumb.name if thumb.exists() else "",
            }
        )
    return out
