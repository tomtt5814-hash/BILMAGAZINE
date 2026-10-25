"""ASR 对比：SenseVoice(SenseVoiceSmall, ONNX) vs faster-whisper small(CPU)。

用法：python scripts/asr_compare.py data/media/xxx/slice300.wav
输出：两种引擎的耗时、倍率、前若干字文本，便于人工比对。
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == 16000, w.getframerate()
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def split_on_silence(audio: np.ndarray, sr: int = 16000,
                     max_len: float = 28.0, min_gap: float = 0.45) -> list[np.ndarray]:
    """按能量找静音切段，避免单段过长（SenseVoice 适合短句）。"""
    frame = 400  # 25ms
    n = len(audio) // frame
    rms = np.array([np.sqrt(np.mean(audio[i * frame:(i + 1) * frame] ** 2) + 1e-9) for i in range(n)])
    thr = max(0.006, float(np.percentile(rms, 25)) * 1.6)

    segs, start = [], 0
    silent_run = 0
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


def run_sensevoice(audio: np.ndarray) -> tuple[str, float]:
    import sherpa_onnx

    base = Path("tools/sensevoice")
    rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(base / "model.int8.onnx"),
        tokens=str(base / "tokens.txt"),
        num_threads=8,
        use_itn=True,
        debug=False,
    )
    segs = split_on_silence(audio)
    t0 = time.time()
    texts = []
    for seg in segs:
        s = rec.create_stream()
        s.accept_waveform(16000, seg)
        rec.decode_stream(s)
        t = s.result.text.strip()
        if t:
            texts.append(t)
    return "".join(texts), time.time() - t0


def run_whisper(path: Path) -> tuple[str, float]:
    from faster_whisper import WhisperModel

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.transcribe import _load_audio_np

    audio = _load_audio_np(path)
    t0 = time.time()
    model = WhisperModel("tools/fw-small", device="cpu", compute_type="int8", cpu_threads=8)
    segments, _ = model.transcribe(audio, language="zh", beam_size=1, vad_filter=False,
                                   condition_on_previous_text=False,
                                   initial_prompt="以下是普通话的句子，内容为知识类视频讲解。")
    text = "".join(s.text.strip() for s in segments)
    return text, time.time() - t0


def main() -> None:
    wav = Path(sys.argv[1] if len(sys.argv) > 1 else "data/media/BV1tcHK6pEZo/slice300.wav")
    audio = read_wav(wav)
    dur = len(audio) / 16000
    print(f"音频 {dur:.0f}s\n")

    sv_text, sv_t = run_sensevoice(audio)
    print(f"[SenseVoice] {sv_t:.1f}s  {dur/sv_t:.1f}x  {len(sv_text)} 字")
    print(sv_text[:600].replace("\n", " "))
    print()
    Path("data/asr_compare_sensevoice.txt").write_text(sv_text, encoding="utf-8")

    wh_text, wh_t = run_whisper(wav)
    print(f"[Whisper-small] {wh_t:.1f}s  {dur/wh_t:.1f}x  {len(wh_text)} 字")
    print(wh_text[:600].replace("\n", " "))
    print()

    Path("data/asr_compare_sensevoice.txt").write_text(sv_text, encoding="utf-8")
    Path("data/asr_compare_whisper.txt").write_text(wh_text, encoding="utf-8")
    print(f"倍率对比：SenseVoice 是 Whisper 的 {wh_t/sv_t:.2f} 倍速")


if __name__ == "__main__":
    main()
