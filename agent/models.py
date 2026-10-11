"""Typed data structures shared across the pipeline."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    niche: str
    title: str
    url: str
    source: str
    summary: str = ""
    published: Optional[datetime] = None
    score: float = 0.0


class WordTiming(BaseModel):
    text: str
    start: float
    end: float


class Script(BaseModel):
    niche: str
    source_title: str
    source_url: str
    hook: str
    body: str
    cta: str = "Follow for your daily tech intel."
    title: str = ""

    @property
    def full_text(self) -> str:
        parts = [self.hook.strip(), self.body.strip(), self.cta.strip()]
        return " ".join(p for p in parts if p)

    @property
    def word_count(self) -> int:
        return len(self.full_text.split())


class ClipAsset(BaseModel):
    path: str
    kind: str  # "video" | "image"
    source: str


class Metadata(BaseModel):
    title: str
    description: str
    tags: List[str] = Field(default_factory=list)
    hashtags: List[str] = Field(default_factory=list)


class RenderedVideo(BaseModel):
    job_id: str
    niche: str
    script: Script
    metadata: Metadata
    audio_path: str
    video_path: str
    duration_seconds: float
    publish_at: Optional[str] = None
    youtube_video_id: Optional[str] = None
    uploaded: bool = False
