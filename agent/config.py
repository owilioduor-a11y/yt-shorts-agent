"""Central configuration loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
CREDENTIALS_DIR = ROOT / "credentials"
VIDEO_DIR = ROOT / "video"
VIDEO_PUBLIC = VIDEO_DIR / "public"
STATE_FILE = DATA_DIR / "state.json"

load_dotenv(ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    return _env(key, str(default)).lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_list(key: str, default: str = "") -> List[str]:
    raw = _env(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    # LLM
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "groq").lower())
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "openai/gpt-oss-120b"))
    llm_fallback_model: str = field(
        default_factory=lambda: _env("LLM_FALLBACK_MODEL", "openai/gpt-oss-20b")
    )
    ollama_base_url: str = field(
        default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    )

    # Voice
    tts_engine: str = field(default_factory=lambda: _env("TTS_ENGINE", "edge").lower())
    tts_fallback: str = field(default_factory=lambda: _env("TTS_FALLBACK", "none").lower())
    edge_voice: str = field(default_factory=lambda: _env("EDGE_VOICE", "en-US-AriaNeural"))
    tts_rate: str = field(default_factory=lambda: _env("TTS_RATE", "+8%"))
    tts_pitch: str = field(default_factory=lambda: _env("TTS_PITCH", "+0Hz"))
    sapi_rate: int = field(default_factory=lambda: _env_int("SAPI_RATE", 1))
    sapi_voice: str = field(default_factory=lambda: _env("SAPI_VOICE", "Microsoft David Desktop"))
    elevenlabs_api_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str = field(
        default_factory=lambda: _env("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    )
    elevenlabs_model: str = field(
        default_factory=lambda: _env("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    )

    # Assets
    pexels_api_key: str = field(default_factory=lambda: _env("PEXELS_API_KEY"))
    pixabay_api_key: str = field(default_factory=lambda: _env("PIXABAY_API_KEY"))

    # YouTube
    yt_client_id: str = field(default_factory=lambda: _env("YT_CLIENT_ID"))
    yt_client_secret: str = field(default_factory=lambda: _env("YT_CLIENT_SECRET"))
    yt_refresh_token: str = field(default_factory=lambda: _env("YT_REFRESH_TOKEN"))
    yt_channel_id: str = field(default_factory=lambda: _env("YT_CHANNEL_ID"))
    yt_category_id: str = field(default_factory=lambda: _env("YT_CATEGORY_ID", "28"))

    # Behaviour
    target_seconds: int = field(default_factory=lambda: _env_int("TARGET_SECONDS", 50))
    max_seconds: int = field(default_factory=lambda: _env_int("MAX_SECONDS", 60))
    video_width: int = field(default_factory=lambda: _env_int("VIDEO_WIDTH", 1080))
    video_height: int = field(default_factory=lambda: _env_int("VIDEO_HEIGHT", 1920))
    fps: int = field(default_factory=lambda: _env_int("FPS", 30))
    videos_per_day: int = field(default_factory=lambda: _env_int("VIDEOS_PER_DAY", 4))
    peak_hours: List[str] = field(default_factory=lambda: _env_list("PEAK_HOURS", "07:00,12:30,17:00,21:00"))
    generate_time: str = field(default_factory=lambda: _env("GENERATE_TIME", "05:00"))
    auto_upload: bool = field(default_factory=lambda: _env_bool("AUTO_UPLOAD", False))
    timezone: str = field(default_factory=lambda: _env("TIMEZONE", "America/New_York"))

    # Niche mix (how many of the daily videos per niche)
    niche_mix: List[str] = field(
        default_factory=lambda: _env_list("NICHE_MIX", "cybersecurity,programming,crypto,cybersecurity")
    )

    @property
    def niches(self) -> List[str]:
        seen: List[str] = []
        for n in self.niche_mix:
            if n not in seen:
                seen.append(n)
        return seen


settings = Settings()


def ensure_dirs() -> None:
    for path in (DATA_DIR, JOBS_DIR, CREDENTIALS_DIR, VIDEO_PUBLIC):
        path.mkdir(parents=True, exist_ok=True)
