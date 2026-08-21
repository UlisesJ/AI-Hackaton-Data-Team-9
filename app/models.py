from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class JobStatus(str, Enum):
    queued = "queued"
    downloading = "downloading"
    transcribing = "transcribing"
    scoring = "scoring"
    exporting = "exporting"
    completed = "completed"
    failed = "failed"


class CreateJobRequest(BaseModel):
    url: Optional[HttpUrl] = None
    max_clips: int = Field(default=5, ge=1, le=10)
    clip_duration_sec: float = Field(default=15.0, ge=15.0, le=90.0)
    burn_in_subtitles: Optional[bool] = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    language: Optional[str] = None
    duration: float = 0.0
    segments: List[TranscriptSegment] = Field(default_factory=list)
    full_text: str = ""


class HighlightCandidate(BaseModel):
    start_sec: float
    end_sec: float
    score: float = Field(ge=0, le=100)
    title: str
    reason: str
    caption: str
    hashtags: List[str] = Field(default_factory=list)


class ClipResult(BaseModel):
    id: str
    start_sec: float
    end_sec: float
    score: float
    title: str
    reason: str
    caption: str
    hashtags: List[str] = Field(default_factory=list)
    video_path: str
    srt_path: Optional[str] = None
    duration_sec: float


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    url: str
    max_clips: int
    clip_duration_sec: float
    progress: str = ""
    error: Optional[str] = None
    video_title: Optional[str] = None
    clips: List[ClipResult] = Field(default_factory=list)