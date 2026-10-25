"""把音频转成文字（faster-whisper，本地模型目录，不依赖 HF 下载）。

用法：python scripts/transcribe_file.py <audio 路径> [--model-dir tools/fw-base]
输出：同目录下 <audio>.txt，并打印耗时与实时倍率。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path


def load_audio_16k(path: Path) -> "object":
    """用 ffmpeg 解成 16k 单声道 wav，再读成 float32 数组（绕开 PyAV 版本问题）。"""
    import numpy as np

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg = "ffmpeg"

    tmp = Path(tempfile.gettempdir()) / f"asr-{int(time.time()*1000)}.wav"
    proc = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(path),
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(tmp)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not tmp.exists():
        sys.exit(f"ffmpeg 转码失败：{proc.stderr[-300:]}")
    with wave.open(str(tmp), "rb") as w:
        raw = w.readframes(w.getnframes())
    tmp.unlink(missing_ok=True)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--model-dir", default="tools/fw-base")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    audio = Path(args.audio)
    model_dir = Path(args.model_dir)
    if not audio.exists():
        sys.exit(f"找不到音频：{audio}")
    if not (model_dir / "model.bin").exists():
        sys.exit(f"模型目录不完整：{model_dir}")

    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=8)
    audio_np = load_audio_16k(audio)
    segments, info = model.transcribe(
        audio_np, language=args.lang, beam_size=1, vad_filter=False,
        condition_on_previous_text=False,
        initial_prompt="以下是普通话的句子，内容为知识类视频讲解。",
    )
    parts = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            parts.append(text)
            if len(parts) % 40 == 0:
                print(f"  ...{len(parts)} 段 / {seg.end:.0f}s", flush=True)
    elapsed = time.time() - t0
    text = "\n".join(parts)
    out = Path(args.out) if args.out else audio.with_suffix(".txt")
    out.write_text(text, encoding="utf-8")
    dur = info.duration or 0
    speed = (dur / elapsed) if elapsed else 0
    print(f"完成：{len(text)} 字，用时 {elapsed:.0f}s，音频 {dur:.0f}s，约 {speed:.1f}x 实时")
    print(f"输出：{out}")

if __name__ == "__main__":
    main()
