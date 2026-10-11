"""Thin unified LLM client.

Supports three providers behind one `.chat()` / `.json()` API:
  * groq   -- OpenAI-compatible endpoint (free tier, fast; default)
  * ollama -- local OpenAI-compatible endpoint (no key, fully offline)
  * gemini -- Google AI Studio REST endpoint (free tier)

All calls retry with exponential backoff and fall back to a secondary model.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

import requests

from .config import settings
from .logging_utils import get_logger

log = get_logger("llm")

_GROQ_URL = "https://api.groq.com/openai/v1"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self) -> None:
        self.provider = settings.llm_provider
        self.model = settings.llm_model
        self.fallback_model = settings.llm_fallback_model
        self._client = None
        if self.provider in {"groq", "ollama"}:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise LLMError("openai package required: pip install openai") from exc
            if self.provider == "groq":
                if not settings.groq_api_key:
                    raise LLMError("GROQ_API_KEY is not set")
                self._client = OpenAI(api_key=settings.groq_api_key, base_url=_GROQ_URL)
            else:
                self._client = OpenAI(api_key="ollama", base_url=settings.ollama_base_url)

    # ---------------------------------------------------------------- public
    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)
        last_error: Optional[Exception] = None
        for model in models:
            for attempt in range(3):
                try:
                    return self._dispatch(system, user, model, temperature, max_tokens, json_mode)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    wait = 2 ** attempt
                    log.warning("LLM %s/%s failed (%s); retry in %ss", self.provider, model, exc, wait)
                    time.sleep(wait)
        raise LLMError(f"all LLM attempts failed: {last_error}")

    def json(self, system: str, user: str, *, temperature: float = 0.6, max_tokens: int = 1500) -> Any:
        raw = self.chat(system, user, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        return _extract_json(raw)

    # --------------------------------------------------------------- private
    def _dispatch(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        if self.provider == "gemini":
            return self._gemini(system, user, model, temperature, max_tokens, json_mode)
        return self._openai_compatible(system, user, model, temperature, max_tokens, json_mode)

    def _openai_compatible(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _gemini(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        url = _GEMINI_URL.format(model=model) + f"?key={settings.gemini_api_key}"
        body: Dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        resp = requests.post(url, json=body, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected gemini response: {data}") from exc


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to grabbing the outermost JSON object/array.
    match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(1))
    raise LLMError(f"could not parse JSON from LLM output: {text[:300]}")


_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
