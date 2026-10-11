"""Fetch, normalise and rank news items from RSS feeds."""
from __future__ import annotations

import concurrent.futures
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import feedparser

from ..logging_utils import get_logger
from ..models import NewsItem
from .feeds import FEEDS, HOT_KEYWORDS

log = get_logger("sources.rss")

_LOOKBACK_HOURS = 48
_UA = "Mozilla/5.0 (compatible; yt-shorts-agent/1.0; +https://example.com)"


def _parse_date(entry) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, key, None)
        if value:
            try:
                return datetime.fromtimestamp(time.mktime(value), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
        raw = entry.get(key, "")
        if raw:
            try:
                return datetime(*time.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
    return None


def _score(title: str, summary: str, published: Optional[datetime], niche: str) -> float:
    text = f"{title} {summary}".lower()
    score = 0.0
    for kw in HOT_KEYWORDS.get(niche, []):
        if kw in text:
            score += 3.0
    # Recency boost: newer items rank above older ones.
    if published:
        age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600.0
        score += max(0.0, 24.0 - age_hours) / 4.0
    # Short punchy titles tend to make better shorts.
    words = len(title.split())
    if 5 <= words <= 16:
        score += 2.0
    return score


def _fetch_feed(name: str, url: str, niche: str) -> List[NewsItem]:
    items: List[NewsItem] = []
    try:
        parsed = feedparser.parse(url, agent=_UA)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_LOOKBACK_HOURS)
        for entry in parsed.entries[:25]:
            published = _parse_date(entry)
            if published and published < cutoff:
                continue
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            summary = summary[:600]
            items.append(
                NewsItem(
                    niche=niche,
                    title=title,
                    url=link,
                    source=name,
                    summary=summary,
                    published=published,
                    score=_score(title, summary, published, niche),
                )
            )
    except Exception as exc:  # network errors must never kill the pipeline
        log.warning("feed failed [%s] %s: %s", niche, name, exc)
    return items


def fetch_niche(niche: str, per_feed_limit: int = 25) -> List[NewsItem]:
    feeds = FEEDS.get(niche, [])
    results: List[NewsItem] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_fetch_feed, name, url, niche) for name, url in feeds]
        for fut in concurrent.futures.as_completed(futures):
            results.extend(fut.result())
    return _dedupe(results)


def fetch_all(limit_per_niche: int = 40) -> Dict[str, List[NewsItem]]:
    """Return the top-N ranked items for every niche."""
    out: Dict[str, List[NewsItem]] = {}
    for niche in FEEDS:
        items = fetch_niche(niche)
        items.sort(key=lambda i: i.score, reverse=True)
        # de-duplicate near-identical headlines across publishers
        unique: List[NewsItem] = []
        seen: set[str] = set()
        for item in items:
            fingerprint = " ".join(sorted(item.title.lower().split()[:6]))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            unique.append(item)
        out[niche] = unique[:limit_per_niche]
        log.info("sourced %d fresh items for %s", len(out[niche]), niche)
    return out


def _dedupe(items: List[NewsItem]) -> List[NewsItem]:
    seen: set[str] = set()
    result: List[NewsItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        result.append(item)
    return result
