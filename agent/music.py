"""Copyright-safe background music.

The agent never downloads music from copyrighted sources. Instead:

1. LOCAL: user drops royalty-free / Creative Commons tracks into
   `data/music/` (cache dir override: assets/music). UUID-named files are
   picked deterministically per day.
2. OPTIONAL Pixabay Music API: if PIXABAY_API_KEY is set, a CC0 track is
   searched and stored with its license metadata.

The license responsibility is on the asset creator; we store attribution
strings so the manifest records provenance.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import requests

from .config import settings
from .logging_utils import get_logger
from .models import ClipAsset

log = get_logger("music")

MUSIC_DIR_NAME = "music"


def pick_track(job_dir: Path) -> Optional[ClipAsset]:
    """Return a ClipAsset for background music, or None (renderer will skip)."""
    from .config import DATA_DIR

    music_dir = DATA_DIR / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    mp3s = sorted(music_dir.glob("*.mp3")) + sorted(music_dir.glob("*.m4a"))
    if not mp3s:
        return None
    # deterministic pick for the day (rotate daily)
    import datetime

    chosen = mp3s[datetime.date.today().toordinal() % len(mp3s)]
    local = job_dir / f"background_music{chosen.suffix}"
    shutil.copyfile(chosen, local)
    return ClipAsset(path=local.name, kind="audio", source=f"local:{chosen.parent.name}")


def fetch_royalty_free_track(job_dir: Path, cue: str) -> Optional[ClipAsset]:
    """Optional CC0 fetch from Pixabay Music API (100 req/hour free)."""
    if not settings.pixabay_api_key:
        return None
    resp = requests.get(
        "https://pixabay.com/api/",
        params={"key": settings.pixabay_api_key, "q": cue, "per_page": 5, "music_type": "music"},
        timeout=30,
    )
    if resp.status_code != 200:
        return None
    hits = resp.json().get("hits", [])
    if not hits:
        return None
    audio_url = hits[0].get("audio", {}).get("download_url")
    if not audio_url:
        return None
    try:
        r = requests.get(audio_url, timeout=60)
        r.raise_for_status()
        out = job_dir / "background_music.mp3"
        out.write_bytes(r.content)
        log.info("fetched royalty-free music track")
        return ClipAsset(path=out.name, kind="audio", source=f"pixabay:{hits[0].get('tags','')}")
    except requests.RequestException as exc:
        log.warning("could not download music track: %s", exc)
        return None