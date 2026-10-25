"""转写层：B 站字幕优先，其次 whisper.cpp（Vulkan/CPU），最后报告不可用。"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from . import config


class TranscribeUnavailable(Exception):
    pass


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if exe:
            return exe
        raise TranscribeUnavailable("缺少 ffmpeg（pip install imageio-ffmpeg 可自动提供）")


def to_wav(src: Path, dst: Path) -> Path:
    """转 16kHz 单声道 wav，whisper.cpp 要求。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(), "-y", "-i", str(src), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not dst.exists():
        raise TranscribeUnavailable(f"ffmpeg 转码失败：{proc.stderr[-300:]}")
    return dst


def _find_whisper_exe() -> Path | None:
    base = config.WHISPER_DIR
    if not base.exists():
        return None
    for name in ("whisper-cli.exe", "main.exe", "whisper-cli", "main"):
        for p in base.rglob(name):
            return p
    return None


def whisper_available() -> tuple[bool, str]:
    exe = _find_whisper_exe()
    model = config.WHISPER_DIR / config.WHISPER_MODEL
    if exe is None:
        return False, f"未找到 whisper.cpp 可执行文件（{config.WHISPER_DIR}）"
    if not model.exists():
        return False, f"未找到模型文件 {model}"
    return True, str(exe)


def faster_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def _load_audio_np(path: Path):
    """ffmpeg 解码成 16k 单声道 float32 数组，绕开 PyAV 版本不兼容。"""
    import tempfile
    import wave

    import numpy as np

    tmp = Path(tempfile.gettempdir()) / f"asr-{int(time.time() * 1000)}.wav"
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(path),
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(tmp)],
        capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0 or not tmp.exists():
        raise TranscribeUnavailable(f"ffmpeg 解码失败：{proc.stderr[-200:]}")
    with wave.open(str(tmp), "rb") as w:
        raw = w.readframes(w.getnframes())
    tmp.unlink(missing_ok=True)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_faster(audio: Path) -> dict:
    """faster-whisper（CPU int8）。A 卡在 Windows 上没有可用的 ROCm 路径，这里就是纯 CPU。"""
    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(config.FASTER_MODEL, device="cpu", compute_type="int8", cpu_threads=8)
    segments, info = model.transcribe(
        _load_audio_np(audio), language="zh", beam_size=1, vad_filter=False,
        condition_on_previous_text=False,
        initial_prompt="以下是普通话的句子，内容为知识类视频讲解。",
    )
    parts = [seg.text.strip() for seg in segments if seg.text.strip()]
    elapsed = time.time() - t0
    return {
        "text": "\n".join(parts),
        "engine": f"faster-whisper ({config.FASTER_MODEL}, cpu-int8)",
        "elapsed_s": round(elapsed, 1),
    }


def transcribe_whisper(wav: Path) -> dict:
    ok, info = whisper_available()
    if not ok:
        raise TranscribeUnavailable(info)
    exe = Path(info)
    model = config.WHISPER_DIR / config.WHISPER_MODEL
    out_prefix = wav.with_suffix("")
    cmd = [
        str(exe), "-m", str(model), "-f", str(wav),
        "-l", "zh", "-otxt", "-of", str(out_prefix),
        "-t", str(config.WHISPER_THREADS), "-np",
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0
    txt = out_prefix.with_suffix(".txt")
    if proc.returncode != 0 or not txt.exists():
        raise TranscribeUnavailable(f"whisper.cpp 运行失败：{(proc.stderr or proc.stdout)[-400:]}")
    text = txt.read_text(encoding="utf-8", errors="replace")
    return {"text": text, "engine": f"whisper.cpp ({exe.name})", "elapsed_s": round(elapsed, 1)}


def transcribe(bvid: str, client, info: dict | None = None) -> dict:
    """统一入口：字幕 -> whisper。返回 {text, engine, elapsed_s}。"""
    engine = config.TRANSCRIBE_ENGINE
    cache = config.TRANSCRIPT_DIR / f"{bvid}.json"
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if cached.get("text"):
                return cached
        except Exception:
            pass

    if engine in ("auto", "subtitles") and info:
        try:
            subs = client.subtitles(bvid, info["cid"])
            for s in subs:
                lan = (s.get("lan") or "").lower()
                if lan.startswith("zh") or lan.startswith("ai-zh"):
                    text = client.fetch_subtitle_text(s["subtitle_url"])
                    if text.strip():
                        result = {"text": text, "engine": f"bilibili subtitle ({lan})", "elapsed_s": 0}
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                        return result
        except Exception:
            pass

    if engine in ("auto", "whisper"):
        audio = config.MEDIA_DIR / bvid / "audio.m4a"
        wav = config.MEDIA_DIR / bvid / "audio.wav"
        if not audio.exists():
            raise TranscribeUnavailable("音频未下载")

        ok_cpp, _ = whisper_available()
        if ok_cpp:
            to_wav(audio, wav)
            result = transcribe_whisper(wav)
        elif faster_available():
            result = transcribe_faster(audio)
        else:
            raise TranscribeUnavailable(
                "没有可用的转写引擎：whisper.cpp 未安装，faster-whisper 也未安装"
            )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result

    raise TranscribeUnavailable("转写引擎未启用（TRANSCRIBE_ENGINE）")
