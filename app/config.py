from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    whisper_model: str = "base"
    whisper_device: str = "auto"
    output_dir: Path = ROOT_DIR / "output"
    burn_in_subtitles: bool = False
    min_clip_sec: float = 12.0
    max_clip_sec: float = 60.0
    default_max_clips: int = 5
    default_clip_duration_sec: float = 15.0
    # YouTube download hardening (403 / SABR / PO tokens)
    ytdlp_bin: str = ""
    ytdlp_cookies_from_browser: str = ""
    ytdlp_cookies_file: str = "./cookies.txt"
    pot_base_url: str = "http://127.0.0.1:4416"


settings = Settings()
settings.output_dir.mkdir(parents=True, exist_ok=True)