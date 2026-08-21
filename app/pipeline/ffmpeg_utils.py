from __future__ import annotations

import shutil
from functools import lru_cache


@lru_cache(maxsize=1)
def get_ffmpeg_path() -> str:
    """Return system ffmpeg if available, else the imageio-ffmpeg binary."""
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "ffmpeg not found. Install it (brew install ffmpeg) "
            "or ensure imageio-ffmpeg is installed."
        ) from exc
