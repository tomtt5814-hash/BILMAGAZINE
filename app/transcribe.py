"""转写层：B 站字幕优先，其次 whisper.cpp（Vulkan/CPU），最后报告不可用。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import config, hidewin


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
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                          **hidewin.quiet_kwargs())
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


def sensevoice_dir() -> Path:
    return config.ROOT / "tools" / "sensevoice"


def sensevoice_available() -> bool:
    d = sensevoice_dir()
    return (d / "model.int8.onnx").exists() and (d / "tokens.txt").exists()


def _split_on_silence(audio, sr: int = 16000, max_len: float = 28.0, min_gap: float = 0.45):
    """按能量切段（SenseVoice 适合短句输入）。"""
    import numpy as np

    frame = 400  # 25ms
    n = len(audio) // frame
    rms = np.array([np.sqrt(np.mean(audio[i * frame:(i + 1) * frame] ** 2) + 1e-9) for i in range(n)])
    thr = max(0.006, float(np.percentile(rms, 25)) * 1.6)
    segs, start, silent_run = [], 0, 0
    max_frames = int(max_len * sr / frame)
    gap_frames = int(min_gap * sr / frame)
    for i, v in enumerate(rms):
        silent_run = silent_run + 1 if v < thr else 0
        if (silent_run >= gap_frames or i - start >= max_frames) and i > start:
            segs.append(audio[start * frame:i * frame])
            start = i
            silent_run = 0
    if start < n:
        segs.append(audio[start * frame:])
    return [s for s in segs if len(s) > sr * 0.3]


_JUNK_HEAD = re.compile(r"^(?:[A-Za-z]+[.。,，]\s*)+")
_EMO = re.compile(r"<\|[^|]*\|>")


def _clean_sensevoice(text: str) -> str:
    text = _EMO.sub("", text)
    text = _JUNK_HEAD.sub("", text)
    text = re.sub(r"[。.]{2,}", "。", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def transcribe_sensevoice(audio: Path) -> dict:
    """SenseVoice-Small（ONNX，CPU）。实测 40x 实时，中文 CER 明显优于 Whisper。"""
    import sherpa_onnx

    d = sensevoice_dir()
    t0 = time.time()
    rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(d / "model.int8.onnx"),
        tokens=str(d / "tokens.txt"),
        num_threads=config.WHISPER_THREADS,
        use_itn=True,
        debug=False,
    )
    audio_np = _load_audio_np(audio)
    parts = []
    for seg in _split_on_silence(audio_np):
        s = rec.create_stream()
        s.accept_waveform(16000, seg)
        rec.decode_stream(s)
        t = _clean_sensevoice(s.result.text or "")
        if t:
            parts.append(t)
    elapsed = time.time() - t0
    return {
        "text": "\n".join(parts),
        "engine": "sensevoice-small (onnx, cpu)",
        "elapsed_s": round(elapsed, 1),
    }


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
        capture_output=True, text=True, timeout=1800, **hidewin.quiet_kwargs(),
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
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, encoding="utf-8",
                          errors="replace", **hidewin.quiet_kwargs())
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
        if sensevoice_available():
            result = transcribe_sensevoice(audio)
        elif ok_cpp:
            to_wav(audio, wav)
            result = transcribe_whisper(wav)
        elif faster_available():
            result = transcribe_faster(audio)
        else:
            raise TranscribeUnavailable(
                "没有可用的转写引擎：SenseVoice 模型缺失、whisper.cpp 未安装、faster-whisper 也未安装"
            )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result

    raise TranscribeUnavailable("转写引擎未启用（TRANSCRIBE_ENGINE）")
