"""Step 1: pick the day's best stories and write 50-second scripts."""
from __future__ import annotations

import json
from typing import Dict, List

from .config import settings
from .llm import get_llm
from .logging_utils import get_logger
from .models import NewsItem, Script
from .sources import fetch_all

log = get_logger("script")

WORDS_PER_SECOND = 2.6  # energetic narration ≈ 155-160 wpm

SCRIPT_SYSTEM = """You are a top short-form video scriptwriter for a faceless tech news channel.
You write punchy, factual, high-retention scripts for vertical YouTube Shorts.

Rules:
- Total spoken length must be 45-58 seconds (~120-150 words).
- Structure: HOOK (first 3 seconds, a shocking question or bold claim), BODY (2-4 rapid facts), CTA (subscribe).
- HOOK must create curiosity or stakes within 3 seconds. No "in this video".
- Sentences are short. One idea per sentence. Active voice.
- Only use facts present in the provided source. Never invent numbers or claims.
- Conversational and authoritative, slightly excited. No emojis, no markdown, no hashtags in the spoken script.
- The CTA varies but always ends with a subscribe request, e.g. "Follow for your daily tech intel."

Return ONLY valid JSON matching the requested schema."""

SCRIPT_SCHEMA_HINT = """Return a JSON object:
{
  "scripts": [
    {
      "niche": "<cybersecurity|programming|crypto>",
      "source_url": "<exact url from the candidate list>",
      "hook": "<1-2 sentences, <12 words>",
      "body": "<2-4 short sentences>",
      "cta": "<one sentence subscribe ask>",
      "title": "<working headline for internal use>"
    }
  ]
}"""


def _candidates_block(items: List[NewsItem]) -> str:
    lines = []
    for idx, item in enumerate(items):
        when = item.published.strftime("%Y-%m-%d %H:%M UTC") if item.published else "recent"
        lines.append(
            f"[{idx}] niche={item.niche} source={item.source} ({when})\n"
            f"title: {item.title}\n"
            f"url: {item.url}\n"
            f"summary: {item.summary[:400]}\n"
        )
    return "\n".join(lines)


def select_and_write(items_by_niche: Dict[str, List[NewsItem]]) -> List[Script]:
    """Ask the LLM to choose the most compelling items and script them."""
    flat: List[NewsItem] = []
    for niche in settings.niches:
        flat.extend(items_by_niche.get(niche, [])[:12])
    flat = flat[:30]
    if not flat:
        log.error("no candidate news items available")
        return []

    mix = ", ".join(settings.niche_mix)
    user = (
        f"Today you must produce exactly {settings.videos_per_day} scripts.\n"
        f"Niche mix (in order): {mix}.\n"
        f"Pick the single most compelling, breaking, high-engagement story for each niche slot.\n"
        f"Prefer stories that are new, concrete and surprising.\n\n"
        f"CANDIDATE STORIES:\n{_candidates_block(flat)}\n\n"
        f"{SCRIPT_SCHEMA_HINT}"
    )

    llm = get_llm()
    data = llm.json(SCRIPT_SYSTEM, user, temperature=0.75, max_tokens=2000)
    scripts: List[Script] = []
    by_url = {item.url: item for item in flat}
    for entry in data.get("scripts", []):
        url = entry.get("source_url", "")
        source = by_url.get(url)
        scripts.append(
            Script(
                niche=(entry.get("niche") or (source.niche if source else "programming")).lower(),
                source_title=(source.title if source else entry.get("title", "")),
                source_url=url,
                hook=entry.get("hook", "").strip(),
                body=entry.get("body", "").strip(),
                cta=entry.get("cta", "Follow for your daily tech intel.").strip(),
                title=entry.get("title", "").strip(),
            )
        )
    scripts = [s for s in scripts if s.hook and s.body]
    log.info("wrote %d scripts", len(scripts))
    return scripts[: settings.videos_per_day]


def build_daily_scripts() -> List[Script]:
    items = fetch_all()
    return select_and_write(items)
