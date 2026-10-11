"""Orchestrator: the full daily 5-step pipeline.

  1 source+script -> 2 voiceover -> 3 visuals+render -> 4 metadata -> 5 publish
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .assets import fetch_backgrounds
from .config import DATA_DIR, JOBS_DIR, ensure_dirs, settings
from .logging_utils import get_logger
from .metadata import generate_metadata
from .models import RenderedVideo, Script, WordTiming
from .music import fetch_royalty_free_track, pick_track
from .publish import save_manifest, schedule_four_videos, upload_video
from .script import build_daily_scripts
from .tts import generate_voiceover
from .video import render_short

log = get_logger("orchestrator")


def slugify(text: str, maxlen: int = 48) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:maxlen].strip("-") or "clip"


def _niche_accent(niche: str) -> str:
    return {"cybersecurity": "#FF3B30", "programming": "#0A84FF", "crypto": "#30D158"}.get(niche, "#FFD60A")


def build_one(script: Script, job_dir: Path, index: int, date_str: str) -> Optional[RenderedVideo]:
    """Produce a single finished video for one script. Returns None on failure."""
    assets_dir = job_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # ---- 2. voice-over
    try:
        voice = generate_voiceover(script.full_text, assets_dir / "voice.mp3")
    except Exception as exc:
        log.error("TTS failed for %s: %s", script.niche, exc)
        return None

    duration = voice.duration or float(voice.words[-1].end) if voice.words else 0.0
    if duration > settings.max_seconds:
        log.warning("voice is %.0fs (cap %ss); client re-truncates", duration, settings.max_seconds)
    duration = min(duration, float(settings.max_seconds)) or float(settings.target_seconds)

    words: List[WordTiming] = [w for w in voice.words if w.end <= duration + 0.05]

    # ---- 3a. visuals + music
    backgrounds = fetch_backgrounds(script.full_text, script.niche, count=3, cache_dir=assets_dir)
    music_cues = ["energetic tech", "trendy corporate", "upbeat news", "hip hop beat"]
    music = pick_track(assets_dir) or fetch_royalty_free_track(assets_dir, cue=music_cues[index % len(music_cues)])

    # ---- 4. metadata
    try:
        meta = generate_metadata(script, script.niche)
    except Exception as exc:
        log.error("metadata generation failed: %s", exc)
        return None

    # ---- 3b. render
    job_id = f"{date_str}-{index+1}-{script.niche}-{slugify(script.title or script.hook)}"
    try:
        rendered = render_short(
            job_id=job_id,
            title=meta.title,
            niche=script.niche,
            hook=script.hook,
            duration_seconds=duration,
            words=words,
            voice_mp3=assets_dir / "voice.mp3",
            backgrounds=backgrounds,
            music=music,
            assets_dir=assets_dir,
        )
    except Exception as exc:
        log.error("render failed for %s: %s", job_id, exc)
        return None

    final_dir = job_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_mp4 = final_dir / f"{job_id}.mp4"
    shutil.move(str(rendered), str(final_mp4))

    return RenderedVideo(
        job_id=job_id,
        niche=script.niche,
        script=script,
        metadata=meta,
        audio_path=str(assets_dir / "voice.mp3"),
        video_path=str(final_mp4),
        duration_seconds=round(duration, 2),
    )


def run_pipeline(*, upload: Optional[bool] = None, count: Optional[int] = None,
                 scripts: Optional[List[Script]] = None) -> List[RenderedVideo]:
    """Execute the whole pipeline and optionally auto-upload."""
    ensure_dirs()
    date_str = datetime.now().strftime("%Y%m%d")
    jobs_root = JOBS_DIR / date_str
    jobs_root.mkdir(parents=True, exist_ok=True)

    if scripts is None:
        scripts = build_daily_scripts()
    scripts = scripts[: settings.videos_per_day] if count is None else scripts[:count]
    log.info("pipeline: %d scripts today", len(scripts))

    videos: List[RenderedVideo] = []
    for i, script in enumerate(scripts):
        job_dir = jobs_root / f"{date_str}-{i+1}-{script.niche}-{slugify(script.title or script.hook)}"
        if job_dir.exists():
            # already built today; reuse the artifact if present
            finals = list(job_dir.rglob("*.mp4"))
            if finals:
                videos.append(_rehydrate(job_dir, finals[0], script, i, date_str))
                continue
        vid = build_one(script, job_dir, i, date_str)
        if vid:
            videos.append(vid)

    if not videos:
        log.warning("no videos produced today")
        return []

    videos = schedule_four_videos(videos, settings.peak_hours[: len(videos)])
    manifest = save_manifest(videos, date_str)

    upload = settings.auto_upload if upload is None else upload
    if upload:
        for vid in videos:
            if vid.youtube_video_id:
                continue
            for attempt in (1, 2):
                try:
                    vid.youtube_video_id = upload_video(
                        Path(vid.video_path),
                        vid.metadata,
                        publish_at=vid.publish_at,
                        notify_subscribers=False,
                    )
                    vid.uploaded = True
                    break
                except Exception as exc:
                    log.error("upload attempt %d failed: %s", attempt, exc)
        save_manifest(videos, date_str)
    else:
        log.warning("AUTO_UPLOAD=false or --no-upload: videos built but NOT published.")
        log.warning("manifest: %s", manifest)

    return videos


def _rehydrate(job_dir: Path, mp4: Path, script: Script, index: int, date_str: str) -> RenderedVideo:
    import json

    from .models import Metadata

    meta = Metadata(title=script.title or script.hook, description="", tags=[])
    duration = 0.0
    words_file = job_dir / "assets" / "voice.words.json"
    if words_file.exists():
        try:
            duration = float(json.loads(words_file.read_text()).get("duration", 0.0))
        except (ValueError, TypeError):
            duration = 0.0
    return RenderedVideo(
        job_id=mp4.stem,
        niche=script.niche,
        script=script,
        metadata=meta,
        audio_path=str(job_dir / "assets" / "voice.mp3"),
        video_path=str(mp4),
        duration_seconds=duration,
    )