"""Step 4: generate CTR-optimised title, description and hashtags."""
from __future__ import annotations

from .config import settings
from .llm import get_llm
from .logging_utils import get_logger
from .models import Metadata, Script

log = get_logger("metadata")

META_SYSTEM = """You are an expert YouTube SEO and thumbnail-copy writer for a faceless
tech news Shorts channel.

Rules:
- Title: under 60 characters, front-load the curiosity hook, no ALL CAPS spam,
  no clickbait that the script cannot support, one strong keyword.
- Description: 1-2 sentences summarising the news + a source link + 3 trending
  hashtags for the niche (e.g. #cybersecurity #bitcoin #python). Max 180 chars total.
- tags: 8-12 relevant keyword phrases (multi-word ok, lowercase, no '#').
Return ONLY valid JSON."""

META_SCHEMA_HINT = """Return a JSON object:
{
  "title": "<under 60 chars>",
  "description": "<short summary + source url + 3 hashtags>",
  "tags": ["kw1", "kw2", ...],
  "hashtags": ["#a", "#b", "#c"]
}"""


def generate_metadata(script: Script, niche_default: str) -> Metadata:
    niche = script.niche or niche_default
    hashtags = {
        "cybersecurity": "#cybersecurity",
        "programming": "#programming",
        "crypto": "#crypto",
    }
    fallback = lambda reason: _fallback_meta(script, niche, hashtags[niche], reason)
    try:
        llm = get_llm()
    except Exception as exc:
        return fallback(f"no LLM configured ({exc})")

    user = (
        f"niche={niche}\n"
        f"spoken script:\n\"\"\"{script.full_text}\"\"\"\n\n"
        f"source article title: {script.source_title}\n"
        f"source url: {script.source_url}\n\n"
        f"{META_SCHEMA_HINT}"
    )
    try:
        data = llm.json(META_SYSTEM, user, temperature=0.55, max_tokens=2048)
    except Exception as exc:  # never block the pipeline on copywriting
        return fallback(str(exc))
    if not isinstance(data, dict):
        return fallback(f"LLM returned {type(data).__name__}, expected dict")
    title = str(data.get("title", "")).strip()[:60]
    tags = [str(t).strip().lower() for t in data.get("tags", []) if str(t).strip()]
    if not title:
        title = (script.title or script.hook)[:60]
    meta = Metadata(
        title=title,
        description=str(data.get("description", "")).strip()[:300],
        tags=tags[:12],
        hashtags=[h for h in data.get("hashtags", []) if str(h).startswith("#")][:3],
    )
    log.info("metadata -> %s", meta.title)
    return meta


def _fallback_meta(script: Script, niche: str, tag: str, reason: str) -> Metadata:
    log.warning("metadata LLM unavailable (%s); using deterministic fallback", reason)
    base = (script.title or script.hook)[:52]
    return Metadata(
        title=base,
        description=f"{script.source_title} | Source: {script.source_url} | {tag} {tag} {tag}",
        tags=[niche, "news", "tech news", "shorts"],
        hashtags=[tag],
    )