from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from app.config import settings
from app.models import ClipResult, JobStatus
from app.pipeline.download import download_media, ingest_local_video
from app.pipeline.export import export_highlights
from app.pipeline.highlights import score_highlights
from app.pipeline.transcribe import transcribe_audio

ProgressCb = Callable[[JobStatus, str], None]


def run_pipeline(
    job_id: str,
    url: Optional[str] = None,
    local_video: Optional[Path] = None,
    max_clips: int = 5,
    clip_duration_sec: float = 15.0,
    burn_in_subtitles: Optional[bool] = None,
    on_progress: Optional[ProgressCb] = None,
) -> tuple[str, list[ClipResult]]:
    """Run full clip pipeline. Returns (video_title, clips)."""

    def progress(status: JobStatus, message: str) -> None:
        if on_progress:
            on_progress(status, message)

    if not url and not local_video:
        raise ValueError("Provide either a YouTube url or a local_video path")

    job_dir = Path(settings.output_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    burn = (
        settings.burn_in_subtitles if burn_in_subtitles is None else burn_in_subtitles
    )

    if local_video is not None:
        progress(JobStatus.downloading, "Ingesting local video…")
        downloaded = ingest_local_video(local_video, job_dir)
    else:
        progress(JobStatus.downloading, "Downloading video and audio from YouTube…")
        downloaded = download_media(str(url), job_dir)

    progress(JobStatus.transcribing, "Transcribing audio with Whisper…")
    transcript = transcribe_audio(downloaded.audio_path, job_dir)
    if transcript.duration <= 0 and downloaded.duration > 0:
        transcript.duration = downloaded.duration

    progress(JobStatus.scoring, "Scoring highlight moments with LLM…")
    highlights = score_highlights(
        transcript=transcript,
        max_clips=max_clips,
        target_duration=clip_duration_sec,
    )
    if not highlights:
        raise RuntimeError("No highlight candidates returned by the model")

    progress(JobStatus.exporting, f"Exporting {len(highlights)} vertical clips…")
    clips = export_highlights(
        video_path=downloaded.video_path,
        transcript=transcript,
        highlights=highlights,
        job_dir=job_dir,
        burn_in_subtitles=burn,
    )

    progress(JobStatus.completed, f"Done — {len(clips)} clips ready")
    return downloaded.title, clips