"""Step 3-bridge: render each Short with Remotion (Node subprocess).

The Python orchestrator stages all media (voice, backgrounds, music) into
`video/public/jobs/<job_id>/`, writes a props JSON, then shells out to
`npx remotion render` (Remotion 4 headless Chrome compositor).

Output lands in `video/out/<job_id>.mp4`.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from .config import settings, VIDEO_DIR
from .logging_utils import get_logger
from .models import ClipAsset, WordTiming

log = get_logger("video")

PUBLIC_DIR = VIDEO_DIR / "public"
OUT_DIR = VIDEO_DIR / "out"
PROPS_DIR = VIDEO_DIR / "props"


class RenderError(RuntimeError):
    pass


def _stage_public(job_id: str, voice_mp3: Path, backgrounds: List[ClipAsset],
                  music: Optional[ClipAsset], assets_dir: Path) -> Path:
    """Copy job media into Remotion's public folder; return the staging dir."""
    stage = PUBLIC_DIR / "jobs" / job_id
    stage.mkdir(parents=True, exist_ok=True)
    for old in stage.iterdir():
        old.unlink()
    shutil.copy2(voice_mp3, stage / "voice.mp3")
    for asset in backgrounds:
        src = assets_dir / asset.path
        if src.exists():
            shutil.copy2(src, stage / asset.path)
    if music is not None and (assets_dir / music.path).exists():
        shutil.copy2(assets_dir / music.path, stage / music.path)
    return stage


def render_short(
    job_id: str,
    title: str,
    niche: str,
    hook: str,
    duration_seconds: float,
    words: List[WordTiming],
    voice_mp3: Path,
    backgrounds: List[ClipAsset],
    music: Optional[ClipAsset],
    assets_dir: Path,
) -> Path:
    """Render a 1080x1920 Short. Returns the absolute path to the MP4."""
    fps = settings.fps
    _stage_public(job_id, voice_mp3, backgrounds, music, assets_dir)

    props = {
        "title": title,
        "niche": niche,
        "hook": hook,
        "durationInSeconds": round(duration_seconds, 3),
        "fps": fps,
        "words": [{"text": w.text, "start": w.start, "end": w.end} for w in words],
        "backgrounds": [
            {"path": f"jobs/{job_id}/{b.path}", "kind": b.kind} for b in backgrounds
        ],
        "voiceSrc": f"jobs/{job_id}/voice.mp3",
        "musicSrc": f"jobs/{job_id}/{music.path}" if music else None,
    }
    PROPS_DIR.mkdir(parents=True, exist_ok=True)
    props_file = PROPS_DIR / f"{job_id}.json"
    props_file.write_text(json.dumps(props, indent=2))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_mp4 = OUT_DIR / f"{job_id}.mp4"
    if out_mp4.exists():
        out_mp4.unlink()

    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise RenderError("npx not found — install Node.js and run `npm install` in video/")
    cmd = [
        npx,
        "remotion",
        "render",
        "Short",
        str(out_mp4),
        f"--props={props_file}",
        "--log=error",
    ]
    log.info("rendering short: %s (%ss)", job_id, round(duration_seconds, 1))
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=VIDEO_DIR, capture_output=True, text=True)
    if proc.returncode != 0 or not out_mp4.exists():
        raise RenderError(
            f"remotion render failed (exit={proc.returncode}):\n{proc.stdout[-1200:]}\n{proc.stderr[-1200:]}"
        )
    log.info("rendered %s in %.1fs (%.1f MB)", out_mp4.name, time.time() - t0, out_mp4.stat().st_size / 1e6)
    return out_mp4