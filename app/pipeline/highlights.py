from __future__ import annotations

import json
import re
import time
from typing import List

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from app.config import settings
from app.models import HighlightCandidate, Transcript


SYSTEM_PROMPT = """You are an expert social media editor. Given a timestamped transcript of a long video,
select the most viral / relevant highlight moments for short-form platforms (TikTok, Reels, Shorts).

Rules:
- Return ONLY valid JSON (no markdown fences).
- Prefer self-contained moments with a clear hook in the first 3 seconds.
- Prefer surprising claims, strong opinions, emotional peaks, punchlines, or concrete takeaways.
- Each clip duration MUST be between min_duration and max_duration seconds.
- Avoid heavy overlap between clips (overlap < 5 seconds).
- Anchor start_sec/end_sec to natural sentence boundaries from the transcript when possible.
- Titles should be short hooks (<= 80 chars). Captions should be post-ready.
- hashtags: 3-6 relevant tags; prefer with #.
"""


def _build_user_prompt(
    transcript: Transcript,
    max_clips: int,
    target_duration: float,
    min_duration: float,
    max_duration: float,
) -> str:
    lines = []
    for seg in transcript.segments:
        lines.append(f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text}")
    transcript_block = "\n".join(lines)
    if len(transcript_block) > 100_000:
        transcript_block = transcript_block[:100_000] + "\n...[truncated]..."

    return f"""Video duration: {transcript.duration:.1f}s
Language: {transcript.language or "unknown"}
Target clip duration: ~{target_duration:.0f}s (hard min {min_duration:.0f}s, hard max {max_duration:.0f}s)
Select top {max_clips} highlights.

Transcript:
{transcript_block}

Respond with JSON of the form:
{{
  "highlights": [
    {{
      "start_sec": 12.5,
      "end_sec": 48.0,
      "score": 91,
      "title": "Hook title",
      "reason": "Why this works for social",
      "caption": "Post caption text",
      "hashtags": ["#example", "#clip"]
    }}
  ]
}}
"""


def _clamp_and_dedupe(
    highlights: List[HighlightCandidate],
    max_clips: int,
    min_duration: float,
    max_duration: float,
    video_duration: float,
) -> List[HighlightCandidate]:
    cleaned: List[HighlightCandidate] = []
    for h in sorted(highlights, key=lambda x: x.score, reverse=True):
        start = max(0.0, float(h.start_sec))
        end = float(h.end_sec)
        if video_duration > 0:
            end = min(end, video_duration)
        if end <= start:
            continue
        duration = end - start
        if duration < min_duration:
            end = min(
                start + min_duration,
                video_duration if video_duration > 0 else start + min_duration,
            )
            duration = end - start
        if duration > max_duration:
            end = start + max_duration
            duration = end - start
        if duration < min_duration * 0.8:
            continue

        overlaps = False
        for kept in cleaned:
            overlap = min(end, kept.end_sec) - max(start, kept.start_sec)
            if overlap > 5.0:
                overlaps = True
                break
        if overlaps:
            continue

        cleaned.append(
            HighlightCandidate(
                start_sec=round(start, 2),
                end_sec=round(end, 2),
                score=float(h.score),
                title=h.title.strip() or "Highlight",
                reason=h.reason.strip() or "Relevant moment",
                caption=h.caption.strip() or h.title,
                hashtags=h.hashtags or [],
            )
        )
        if len(cleaned) >= max_clips:
            break
    return cleaned


def _parse_json_content(content: str) -> dict:
    text = (content or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def score_highlights(
    transcript: Transcript,
    max_clips: int,
    target_duration: float,
) -> List[HighlightCandidate]:
    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get one at https://aistudio.google.com/apikey"
        )

    if not transcript.segments:
        raise RuntimeError("Transcript is empty; cannot score highlights")

    client = genai.Client(api_key=settings.gemini_api_key)
    user_prompt = _build_user_prompt(
        transcript=transcript,
        max_clips=max_clips,
        target_duration=target_duration,
        min_duration=settings.min_clip_sec,
        max_duration=min(settings.max_clip_sec, target_duration + 15),
    )

    last_error: Exception | None = None
    response = None
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.4,
                    response_mime_type="application/json",
                ),
            )
            break
        except ClientError as exc:
            last_error = exc
            message = str(exc)
            if "429" not in message and "RESOURCE_EXHAUSTED" not in message:
                raise
            # Free-tier Pro models often have limit 0; tell the user clearly.
            if "limit: 0" in message and "pro" in settings.gemini_model.lower():
                raise RuntimeError(
                    f"Gemini quota is 0 for model '{settings.gemini_model}' on free tier. "
                    "Set GEMINI_MODEL=gemini-3.6-flash in .env (or enable billing for Pro)."
                ) from exc
            wait_s = 30 * (attempt + 1)
            time.sleep(wait_s)
    else:
        raise RuntimeError(
            f"Gemini rate limit exceeded after retries ({settings.gemini_model}). "
            "Try GEMINI_MODEL=gemini-3.6-flash or wait and retry."
        ) from last_error

    content = getattr(response, "text", None) or "{}"
    data = _parse_json_content(content)
    raw = data.get("highlights") or data.get("clips") or []
    candidates = [HighlightCandidate.model_validate(item) for item in raw]

    return _clamp_and_dedupe(
        candidates,
        max_clips=max_clips,
        min_duration=settings.min_clip_sec,
        max_duration=settings.max_clip_sec,
        video_duration=transcript.duration,
    )
