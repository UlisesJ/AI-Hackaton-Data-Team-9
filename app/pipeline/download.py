from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import ROOT_DIR, settings
from app.pipeline.ffmpeg_utils import get_ffmpeg_path


@dataclass
class DownloadResult:
    video_path: Path
    audio_path: Path
    title: str
    duration: float
    info: Dict[str, Any]


def _ytdlp_bin() -> str:
    configured = (settings.ytdlp_bin or "").strip()
    if configured:
        return configured
    local = ROOT_DIR / "bin" / "yt-dlp"
    if local.exists():
        return str(local)
    found = shutil.which("yt-dlp")
    if found:
        return found
    raise RuntimeError(
        "yt-dlp binary not found. Expected ./bin/yt-dlp "
        "(download from https://github.com/yt-dlp/yt-dlp/releases)."
    )


def _plugin_dirs() -> List[str]:
    plugin_root = ROOT_DIR / "bin" / "yt-dlp-plugins"
    if plugin_root.exists():
        return [str(plugin_root)]
    return []


def _ensure_pot_server() -> None:
    """Start bgutil POT HTTP server if configured and not already up."""
    base = settings.pot_base_url.rstrip("/")
    try:
        import urllib.request

        with urllib.request.urlopen(f"{base}/ping", timeout=2) as resp:
            if resp.status == 200:
                return
    except Exception:
        pass

    server_js = (
        ROOT_DIR
        / "vendor"
        / "bgutil-ytdlp-pot-provider"
        / "server"
        / "build"
        / "main.js"
    )
    if not server_js.exists():
        return

    log_path = ROOT_DIR / "output" / "pot-server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as log:
        subprocess.Popen(
            ["node", str(server_js), "--port", "4416"],
            cwd=str(server_js.parent),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    for _ in range(20):
        time.sleep(0.25)
        try:
            import urllib.request

            with urllib.request.urlopen(f"{base}/ping", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            continue


def _extract_wav(video_path: Path, audio_path: Path, ffmpeg_path: str) -> None:
    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not audio_path.exists():
        raise RuntimeError(f"Failed to extract WAV audio: {proc.stderr[-1500:]}")


def _run_ytdlp(args: List[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    deno = Path.home() / ".deno" / "bin"
    if deno.exists():
        env["PATH"] = f"{deno}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(args, capture_output=True, text=True, env=env)


def download_media(url: str, job_dir: Path) -> DownloadResult:
    """Download video via standalone yt-dlp (+ POT/cookies), then extract WAV."""
    job_dir.mkdir(parents=True, exist_ok=True)
    video_out = job_dir / "source.%(ext)s"
    audio_path = job_dir / "audio.wav"
    meta_json = job_dir / "ytdlp_info.json"
    ffmpeg_path = get_ffmpeg_path()
    ytdlp = _ytdlp_bin()

    _ensure_pot_server()

    cmd: List[str] = [ytdlp]
    for plugin_dir in _plugin_dirs():
        cmd.extend(["--plugin-dirs", plugin_dir])

    cmd.extend(
        [
            "--no-playlist",
            "--no-progress",
            "-f",
            "bv*[height<=1080]+ba/b[ext=mp4]/best",
            "--merge-output-format",
            "mp4",
            "--ffmpeg-location",
            ffmpeg_path,
            "--extractor-args",
            (
                "youtube:player_client=web,android_vr;"
                f"youtubepot-bgutilhttp:base_url={settings.pot_base_url}"
            ),
            "-o",
            str(video_out),
            "--write-info-json",
            "--print-json",
        ]
    )

    browser = (settings.ytdlp_cookies_from_browser or "").strip()
    cookies_file = (settings.ytdlp_cookies_file or "").strip()
    if cookies_file:
        cookie_path = Path(cookies_file)
        if not cookie_path.is_absolute():
            cookie_path = ROOT_DIR / cookie_path
        if cookie_path.exists():
            cmd.extend(["--cookies", str(cookie_path)])
        else:
            raise RuntimeError(
                f"Cookies file not found: {cookie_path}. "
                "Export with: ./bin/yt-dlp --cookies-from-browser chrome --cookies cookies.txt "
                "--skip-download 'https://www.youtube.com/watch?v=jNQXAC9IVRw'"
            )
    elif browser:
        cmd.extend(["--cookies-from-browser", browser])

    cmd.append(url)

    proc = _run_ytdlp(cmd)
    (job_dir / "ytdlp_stderr.log").write_text(proc.stderr or "", encoding="utf-8")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if "403" in err or "Forbidden" in err:
            raise RuntimeError(
                "YouTube blocked the download (HTTP 403). "
                "Refresh cookies.txt (Chrome logged into YouTube), "
                "confirm POT server on :4416, or upload a local MP4."
            )
        raise RuntimeError(f"yt-dlp failed: {err[-2000:]}")

    # Prefer info json written next to output
    info: Dict[str, Any] = {}
    info_candidates = list(job_dir.glob("*.info.json"))
    if info_candidates:
        info = json.loads(info_candidates[0].read_text(encoding="utf-8"))
    elif proc.stdout.strip():
        # --print-json may emit one JSON object
        try:
            info = json.loads(proc.stdout.strip().splitlines()[-1])
            meta_json.write_text(json.dumps(info, indent=2), encoding="utf-8")
        except json.JSONDecodeError:
            info = {}

    matches = [
        p
        for p in job_dir.glob("source.*")
        if p.suffix.lower() in {".mp4", ".mkv", ".webm"} and not p.name.endswith(".part")
    ]
    if not matches:
        raise FileNotFoundError(f"Downloaded video not found in {job_dir}")
    video_path = max(matches, key=lambda p: p.stat().st_mtime)

    _extract_wav(video_path, audio_path, ffmpeg_path)

    title = str(info.get("title") or video_path.stem)
    duration = float(info.get("duration") or 0.0)

    (job_dir / "source_meta.json").write_text(
        json.dumps(
            {
                "url": url,
                "title": title,
                "duration": duration,
                "video_path": str(video_path),
                "audio_path": str(audio_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return DownloadResult(
        video_path=video_path,
        audio_path=audio_path,
        title=title,
        duration=duration,
        info=info,
    )


def ingest_local_video(source: Path, job_dir: Path, title: Optional[str] = None) -> DownloadResult:
    """Copy a local video into the job dir and extract WAV (YouTube-free path)."""
    job_dir.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        raise FileNotFoundError(f"Local video not found: {source}")

    video_path = job_dir / f"source{source.suffix.lower() or '.mp4'}"
    shutil.copy2(source, video_path)
    audio_path = job_dir / "audio.wav"
    _extract_wav(video_path, audio_path, get_ffmpeg_path())

    resolved_title = title or source.stem
    (job_dir / "source_meta.json").write_text(
        json.dumps(
            {
                "url": f"file://{source.resolve()}",
                "title": resolved_title,
                "duration": 0.0,
                "video_path": str(video_path),
                "audio_path": str(audio_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return DownloadResult(
        video_path=video_path,
        audio_path=audio_path,
        title=resolved_title,
        duration=0.0,
        info={},
    )
