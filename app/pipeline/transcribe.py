from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

from app.config import settings
from app.models import Transcript, TranscriptSegment

_model: Optional[WhisperModel] = None


def _resolve_device() -> tuple[str, str]:
    device = settings.whisper_device
    if device == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda", "float16"
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                # faster-whisper/ctranslate2 often prefers cpu on macOS
                return "cpu", "int8"
        except Exception:
            pass
        return "cpu", "int8"
    if device == "cuda":
        return "cuda", "float16"
    return "cpu", "int8"


def get_whisper_model() -> WhisperModel:
    global _model
    if _model is None:
        device, compute_type = _resolve_device()
        _model = WhisperModel(
            settings.whisper_model,
            device=device,
            compute_type=compute_type,
        )
    return _model


def transcribe_audio(audio_path: Path, job_dir: Path) -> Transcript:
    model = get_whisper_model()
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,
        word_timestamps=False,
    )

    segments: list[TranscriptSegment] = []
    texts: list[str] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(start=float(seg.start), end=float(seg.end), text=text)
        )
        texts.append(text)

    transcript = Transcript(
        language=getattr(info, "language", None),
        duration=float(getattr(info, "duration", 0.0) or 0.0),
        segments=segments,
        full_text=" ".join(texts),
    )

    out_path = job_dir / "transcript.json"
    out_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    return transcript