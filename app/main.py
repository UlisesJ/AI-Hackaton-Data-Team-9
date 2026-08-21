from __future__ import annotations

import shutil
import threading
import traceback
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import ROOT_DIR, settings
from app.models import CreateJobRequest, JobResponse, JobStatus
from app.pipeline.pipeline import run_pipeline

app = FastAPI(title="Monk.Clip", version="0.1.0")

static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"
static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

_jobs: Dict[str, JobResponse] = {}
_lock = threading.Lock()


def _set_job(job: JobResponse) -> None:
    with _lock:
        _jobs[job.id] = job


def _get_job(job_id: str) -> JobResponse:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.model_copy(deep=True)


def _update_progress(job_id: str, status: JobStatus, message: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = status
        job.progress = message
        _jobs[job_id] = job


def _run_job(
    job_id: str,
    url: Optional[str],
    local_video: Optional[str],
    max_clips: int,
    clip_duration_sec: float,
    burn_in_subtitles: Optional[bool],
) -> None:
    try:

        def on_progress(status: JobStatus, message: str) -> None:
            _update_progress(job_id, status, message)

        title, clips = run_pipeline(
            job_id=job_id,
            url=url,
            local_video=Path(local_video) if local_video else None,
            max_clips=max_clips,
            clip_duration_sec=clip_duration_sec,
            burn_in_subtitles=burn_in_subtitles,
            on_progress=on_progress,
        )
        with _lock:
            job = _jobs[job_id]
            job.status = JobStatus.completed
            job.progress = f"Done — {len(clips)} clips ready"
            job.video_title = title
            job.clips = clips
            job.error = None
            _jobs[job_id] = job
    except Exception as exc:
        with _lock:
            job = _jobs[job_id]
            job.status = JobStatus.failed
            job.progress = "Failed"
            job.error = str(exc)
            _jobs[job_id] = job
        traceback.print_exc()


def _require_api_key() -> None:
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=400,
            detail="GEMINI_API_KEY is not configured. Copy .env.example to .env and set your Google AI Studio key.",
        )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_max_clips": settings.default_max_clips,
            "default_clip_duration": int(settings.default_clip_duration_sec),
        },
    )


@app.post("/jobs", response_model=JobResponse)
async def create_job(
    payload: CreateJobRequest, background_tasks: BackgroundTasks
) -> JobResponse:
    _require_api_key()
    if not payload.url:
        raise HTTPException(status_code=400, detail="url is required (or use /jobs/upload)")

    job_id = uuid.uuid4().hex
    job = JobResponse(
        id=job_id,
        status=JobStatus.queued,
        url=str(payload.url),
        max_clips=payload.max_clips,
        clip_duration_sec=payload.clip_duration_sec,
        progress="Queued",
    )
    _set_job(job)
    background_tasks.add_task(
        _run_job,
        job_id,
        str(payload.url),
        None,
        payload.max_clips,
        payload.clip_duration_sec,
        payload.burn_in_subtitles,
    )
    return job


@app.post("/jobs/upload", response_model=JobResponse)
async def create_job_from_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    max_clips: int = Form(5),
    clip_duration_sec: float = Form(15.0),
) -> JobResponse:
    _require_api_key()
    suffix = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
        raise HTTPException(status_code=400, detail="Unsupported video type")

    job_id = uuid.uuid4().hex
    job_dir = Path(settings.output_dir) / job_id
    uploads = job_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / f"input{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job = JobResponse(
        id=job_id,
        status=JobStatus.queued,
        url=f"upload://{file.filename or dest.name}",
        max_clips=max_clips,
        clip_duration_sec=clip_duration_sec,
        progress="Queued",
    )
    _set_job(job)
    background_tasks.add_task(
        _run_job,
        job_id,
        None,
        str(dest),
        max_clips,
        clip_duration_sec,
        None,
    )
    return job


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    return _get_job(job_id)


@app.get("/jobs/{job_id}/clips/{clip_id}")
async def download_clip(job_id: str, clip_id: str) -> FileResponse:
    job = _get_job(job_id)
    clip = next((c for c in job.clips if c.id == clip_id), None)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    path = Path(clip.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Clip file missing on disk")
    filename = f"{clip_id}_{clip.title[:40].replace(' ', '_')}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=filename)


@app.get("/jobs/{job_id}/clips/{clip_id}/srt")
async def download_srt(job_id: str, clip_id: str) -> FileResponse:
    job = _get_job(job_id)
    clip = next((c for c in job.clips if c.id == clip_id), None)
    if clip is None or not clip.srt_path:
        raise HTTPException(status_code=404, detail="SRT not found")
    path = Path(clip.srt_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="SRT file missing on disk")
    return FileResponse(path, media_type="application/x-subrip", filename=f"{clip_id}.srt")


@app.get("/health")
async def health() -> dict:
    cookies = Path(settings.ytdlp_cookies_file)
    if not cookies.is_absolute():
        cookies = ROOT_DIR / cookies
    return {
        "ok": True,
        "output_dir": str(settings.output_dir),
        "whisper_model": settings.whisper_model,
        "gemini_model": settings.gemini_model,
        "cookies_file": str(cookies),
        "cookies_present": cookies.exists(),
        "root": str(ROOT_DIR),
    }
