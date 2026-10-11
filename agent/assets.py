"""Step 3a: fetch royalty-free vertical background assets (Pexels / Pixabay).

Both providers offer free commercial-use media. We always download to local
disk so the whole pipeline can re-run offline and so + attribution history is
preserved in the job manifest.

Rate limits: Pexels free tier = 200 requests/hour;
Pixabay free tier = 100 requests/hour, 20,000 downloads/day.
Asset cache keys on (provider, term, orientation) to avoid burning quota.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

import requests

from .config import settings
from .logging_utils import get_logger
from .models import ClipAsset

log = get_logger("assets")

_PEXELS_SEARCH = "https://api.pexels.com/videos/search"
_PIXABAY_SEARCH = "https://pixabay.com/api/"

# words we remove so searches stay generic (stock-terms, not "news words")
_STOPWORDS = {"news", "today", "breaking", "update", "hot", "latest", "shorts"}


class AssetError(RuntimeError):
    pass


def _normalise_term(script_text: str, niche: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", script_text.lower())
    stop = _STOPWORDS | {niche, "cybersecurity", "programming", "crypto", "follow", "subscribe"}
    words = [w for w in words if len(w) > 3 and w not in stop]
    # bias toward top-5 words, throws away fillers like "this/that/with"
    priority = {
        "hacked": "cyber attack", "breach": "security breach", "bitcoin": "bitcoin",
        "crypto": "cryptocurrency", "code": "programming code", "ai": "artificial intelligence",
    }
    for key, mapped in priority.items():
        if key in words:
            return mapped
    defaults = {"cybersecurity": "cybersecurity", "programming": "computer code", "crypto": "bitcoin"}
    return words[0] if words else defaults.get(niche, "technology")


def _pexels_search(term: str) -> Optional[str]:
    if not settings.pexels_api_key:
        return None
    resp = requests.get(
        _PEXELS_SEARCH,
        params={"query": term, "orientation": "portrait", "per_page": 8, "size": "medium"},
        headers={"Authorization": settings.pexels_api_key},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    for video in data.get("videos", []):
        for f in video.get("video_files", []):
            if f.get("height", 0) >= 720 and f.get("height", 0) <= 1080:
                return f["link"]
    return None


def _pixabay_search(term: str, kind: str) -> Optional[str]:
    """kind='video' -> video url; kind='image' -> large image url."""
    if not settings.pixabay_api_key:
        return None
    resp = requests.get(
        _PIXABAY_SEARCH,
        params={"key": settings.pixabay_api_key, "q": term, "orientation": "vertical", "per_page": 10},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    for hit in data.get("hits", []):
        if kind == "video" and hit.get("videos", {}).get("large"):
            return hit["videos"]["large"]["url"]
        if kind == "image" and hit.get("largeImageURL"):
            return hit["largeImageURL"]
    return None


def fetch_backgrounds(script_text: str, niche: str, cache_dir: Path, count: int = 3) -> List[ClipAsset]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    term = _normalise_term(script_text, niche)
    assets: List[ClipAsset] = []
    done: set[int] = set()
    for provider, kind in (("pexels", "video"), ("pixabay", "video"), ("pixabay", "image")):
        url = None
        try:
            if provider == "pexels":
                url = _pexels_search(term)
            else:
                url = _pixabay_search(term, kind)
        except requests.RequestException as exc:
            log.warning("stock search failed [%s/%s]: %s", provider, kind, exc)
            continue
        if not url:
            continue
        cache_key = hash((provider, url)) & 0xFFFFFFFF
        if cache_key in done:
            continue
        done.add(cache_key)
        local = cache_dir / f"bg_{provider}_{len(assets)}"
        local = local.with_suffix(".mp4" if kind == "video" else ".jpg")
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            local.write_bytes(r.content)
        except requests.RequestException:
            time.sleep(1)
            continue
        assets.append(ClipAsset(path=local.name, kind=kind, source=f"{provider}:{term}"))
        if len(assets) >= count:
            break
    if not assets:
        log.warning("no stock assets found for term=%r; renderer will use gradient fallback", term)
    else:
        log.info("fetched %d backgrounds for term=%r", len(assets), term)
    return assets