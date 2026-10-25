from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


DATA_DIR = ROOT / _get("DATA_DIR", "data")
MEDIA_DIR = DATA_DIR / "media"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
MAGAZINE_DIR = DATA_DIR / "magazines"
RUN_DIR = DATA_DIR / "runs"
DEMO_DIR = DATA_DIR / "demo"

SUBS_FILE = DATA_DIR / "subscriptions.json"
PROCESSED_FILE = DATA_DIR / "processed.json"

LLM_PROVIDER = _get("LLM_PROVIDER", "mock").lower()
LLM_API_KEY = _get("LLM_API_KEY")
LLM_BASE_URL = _get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = _get("LLM_MODEL", "deepseek-chat")
LLM_TEMPERATURE = float(_get("LLM_TEMPERATURE", "0.8") or 0.8)

BILI_COOKIE = _get("BILI_COOKIE")

TRANSCRIBE_ENGINE = _get("TRANSCRIBE_ENGINE", "auto").lower()
WHISPER_DIR = ROOT / _get("WHISPER_DIR", "tools/whisper")
WHISPER_MODEL = _get("WHISPER_MODEL", "ggml-small.bin")
WHISPER_THREADS = int(_get("WHISPER_THREADS", "8") or 8)
FASTER_MODEL = _get("FASTER_MODEL", "small")

SCHEDULE_ENABLED = _get("SCHEDULE_ENABLED", "1") == "1"
SCHEDULE_TIME = _get("SCHEDULE_TIME", "22:30")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

for d in (DATA_DIR, MEDIA_DIR, TRANSCRIPT_DIR, MAGAZINE_DIR, RUN_DIR, DEMO_DIR):
    d.mkdir(parents=True, exist_ok=True)
