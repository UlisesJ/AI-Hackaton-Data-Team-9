from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path
from typing import List

from app.models import ClipResult, HighlightCandidate, Transcript, TranscriptSegment
from app.pipeline.ffmpeg_utils import get_ffmpeg_path


def _format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _segments_for_range(
    segments: List[TranscriptSegment], start: float, end: float
) -> List[TranscriptSegment]:
    selected: List[TranscriptSegment] = []
    for seg in segments:
        if seg.end <= start or seg.start >= end:
            continue
        clipped_start = max(seg.start, start) - start
        clipped_end = min(seg.end, end) - start
        if clipped_end <= clipped_start:
            continue
        selected.append(
            TranscriptSegment(start=clipped_start, end=clipped_end, text=seg.text)
        )
    return selected


def write_srt(segments: List[TranscriptSegment], path: Path) -> None:
    lines: List[str] = []
    for idx, seg in enumerate(segments, start=1):
        lines.append(str(idx))
        lines.append(
            f"{_format_srt_timestamp(seg.start)} --> {_format_srt_timestamp(seg.end)}"
        )
        lines.append(seg.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _safe_slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip().lower()).strip("-")
    return (slug or "clip")[:max_len]


def export_clip(
    video_path: Path,
    transcript: Transcript,
    highlight: HighlightCandidate,
    clips_dir: Path,
    burn_in_subtitles: bool,
) -> ClipResult:
    ffmpeg = get_ffmpeg_path()
    clips_dir.mkdir(parents=True, exist_ok=True)

    clip_id = uuid.uuid4().hex[:10]
    slug = _safe_slug(highlight.title)
    base = clips_dir / f"{clip_id}_{slug}"
    out_video = Path(str(base) + ".mp4")
    out_srt = Path(str(base) + ".srt")
    out_meta = Path(str(base) + ".json")

    start = highlight.start_sec
    duration = max(0.1, highlight.end_sec - highlight.start_sec)

    range_segments = _segments_for_range(transcript.segments, start, highlight.end_sec)
    write_srt(range_segments, out_srt)

    # Center crop to 9:16 (1080x1920)
    base_vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"

    def _run_ffmpeg(vf: str) -> subprocess.CompletedProcess[str]:
        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(out_video),
        ]
        return subprocess.run(cmd, capture_output=True, text=True)

    proc: subprocess.CompletedProcess[str]
    if burn_in_subtitles:
        srt_escaped = (
            str(out_srt).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        )
        burn_vf = (
            f"{base_vf},subtitles='{srt_escaped}':force_style="
            "'Fontsize=22,PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,"
            "BorderStyle=3,Outline=2,Shadow=0,MarginV=80'"
        )
        proc = _run_ffmpeg(burn_vf)
        if proc.returncode != 0:
            # Bundled ffmpeg builds may lack libass; fall back to clean crop.
            proc = _run_ffmpeg(base_vf)
    else:
        proc = _run_ffmpeg(base_vf)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-2000:]}")

    result = ClipResult(
        id=clip_id,
        start_sec=highlight.start_sec,
        end_sec=highlight.end_sec,
        score=highlight.score,
        title=highlight.title,
        reason=highlight.reason,
        caption=highlight.caption,
        hashtags=highlight.hashtags,
        video_path=str(out_video),
        srt_path=str(out_srt),
        duration_sec=round(duration, 2),
    )
    out_meta.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def export_highlights(
    video_path: Path,
    transcript: Transcript,
    highlights: List[HighlightCandidate],
    job_dir: Path,
    burn_in_subtitles: bool,
) -> List[ClipResult]:
    clips_dir = job_dir / "clips"
    results: List[ClipResult] = []
    for h in highlights:
        results.append(
            export_clip(
                video_path=video_path,
                transcript=transcript,
                highlight=h,
                clips_dir=clips_dir,
                burn_in_subtitles=burn_in_subtitles,
            )
        )
    return results