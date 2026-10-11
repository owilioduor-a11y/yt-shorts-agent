"""Step 2: convert scripts to voice-overs with word-level timing.

Default engine is `edge-tts` (Microsoft Edge neural voices, free, no key).
An ElevenLabs adapter is included: set TTS_ENGINE=elevenlabs + ELEVENLABS_API_KEY.

Word timings power the animated captions in the video editor.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import List, Optional

from .config import settings
from .logging_utils import get_logger
from .models import WordTiming

log = get_logger("tts")

MAX_WORDS = int(settings.max_seconds * 2.6)


class TTSOutput:
    def __init__(self, audio_path: str, words: List[WordTiming], duration: float):
        self.audio_path = audio_path
        self.words = words
        self.duration = duration

    def to_json(self) -> dict:
        return {
            "audio_path": self.audio_path,
            "words": [w.model_dump() for w in self.words],
            "duration": self.duration,
        }


def _clip_text(text: str) -> str:
    words = text.split()
    if len(words) <= MAX_WORDS:
        return text
    return " ".join(words[:MAX_WORDS])


# ------------------------------------------------------------------ edge-tts
def _edge_tts_impl(text: str, out_path: Path) -> Optional[TTSOutput]:
    import edge_tts

    async def _run():
        clipped = _clip_text(text)
        communicate = edge_tts.Communicate(
            clipped,
            voice=settings.edge_voice,
            rate=settings.tts_rate,
            pitch=settings.tts_pitch,
        )
        words: List[WordTiming] = []
        with out_path.open("wb") as fh:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    fh.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    offset_s = chunk["offset"] / 10_000_000
                    duration_s = chunk["duration"] / 10_000_000
                    words.append(
                        WordTiming(
                            text=re.sub(r"[^\w''’.!?-]", "", chunk["text"]),
                            start=round(offset_s, 3),
                            end=round(offset_s + duration_s, 3),
                        )
                    )
        return words

    words = asyncio.run(_run())
    if not out_path.exists() or out_path.stat().st_size == 0:
        return None
    return TTSOutput(str(out_path), words, duration=words[-1].end if words else 0.0)


# --------------------------------------------------------------- elevenlabs
def _elevenlabs(text: str, out_path: Path) -> TTSOutput:
    import requests

    text = _clip_text(text)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
        "Accept-Meta": "json",  # returns word timings alongside audio
    }
    payload = {
        "text": text,
        "model_id": settings.elevenlabs_model,
        "voice_settings": {"stability": 0.35, "similarity_boost": 0.85, "style": 0.3},
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        data = resp.json()
        audio_b64 = data.get("audio_base64", "")
        import base64

        out_path.write_bytes(base64.b64decode(audio_b64))
        aligns = data.get("alignment", {})
        chars = aligns.get("characters", [])
        char_starts = aligns.get("character_start_times_seconds", [])
        char_ends = aligns.get("character_end_times_seconds", [])
        words: List[WordTiming] = []
        i = 0
        while i < len(chars):
            ch = chars[i]
            if ch.isspace():
                i += 1
                continue
            j = i
            while j < len(chars) and not chars[j].isspace():
                j += 1
            if j < len(chars):
                words.append(
                    WordTiming(
                        text="".join(chars[i:j]).strip(" .,!?;:"),
                        start=float(char_starts[i]),
                        end=float(char_ends[j - 1]),
                    )
                )
            i = j + 1
    else:
        out_path.write_bytes(resp.content)
        words = _approximate_words(text)

    return TTSOutput(str(out_path), words, duration=words[-1].end if words else 0.0)


def _approximate_words(text: str) -> List[WordTiming]:
    """Estimate timing when the engine gives no boundaries (fallback)."""
    words = text.split()
    wps = WORD_TIME_HZ = 2.6
    per_word = 1.0 / wps
    out: List[WordTiming] = []
    t = 0.0
    for w in words:
        out.append(WordTiming(text=w, start=round(t, 3), end=round(t + per_word, 3)))
        t += per_word
    return out


# ------------------------------------------------------------------ sapi/windows
def _sapi_tts(text: str, out_path: Path) -> TTSOutput:
    """Local Windows System.Speech fallback (no internet, no keys).

    Produces a WAV via PowerShell, transcodes to MP3 with ffmpeg, and estimates
    word timings by even pacing (SAPI does not expose word boundaries).
    Prefers a male voice (settings.sapi_voice -> 'Microsoft David Desktop'),
    falling back to the first installed male voice if that one is missing.
    """
    import base64
    import shutil
    import subprocess

    text = _clip_text(text)
    wav = out_path.with_suffix(".wav")
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {settings.sapi_rate}; "
        f"$wanted = '{settings.sapi_voice}'; "
        "$names = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }; "
        "if ($names -contains $wanted) { $s.SelectVoice($wanted) } "
        "else { $male = $names | Where-Object { $_ -match 'David|Mark|Guy|James|George|Christopher|Brian' } | Select-Object -First 1; "
        "if ($male) { $s.SelectVoice($male) } }; "
        "Write-Output ('selected-voice=' + $s.Voice.Name); "
        "$txt = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("
        f"'{payload}')); "
        f"$s.SetOutputToWaveFile('{wav}'); "
        "$s.Speak($txt); $s.Dispose()"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not wav.exists():
        raise RuntimeError(f"sapi TTS failed: {(proc.stderr or '')[-500:]}")
    voice_line = next((l.strip() for l in (proc.stdout or "").splitlines() if "selected-voice=" in l), "")
    selected_voice = voice_line.split("=", 1)[1] if "=" in voice_line else "default"
    log.info("sapi voice selected: %s", selected_voice)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and out_path.suffix == ".mp3":
        conv = subprocess.run(
            [ffmpeg, "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-qscale:a", "4", str(out_path)],
            capture_output=True,
            text=True,
        )
        if conv.returncode != 0 or not out_path.exists():
            wav.unlink(missing_ok=True)
            raise RuntimeError(f"sapi transcode failed: {conv.stderr[-400:]}")
        wav.unlink(missing_ok=True)
    else:
        # no ffmpeg: keep the WAV and use it directly
        out_path = wav
    return TTSOutput(str(out_path), _approximate_words(text), duration=len(text.split()) / 2.6)


# ------------------------------------------------------------------- public
def generate_voiceover(script_text: str, out_path: Path) -> TTSOutput:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    engine = settings.tts_engine
    if engine == "elevenlabs":
        return _elevenlabs(script_text, out_path)
    try:
        result = _edge_tts_impl(script_text, out_path)
        if result is None:
            raise RuntimeError("edge-tts produced no audio")
        log.info("voice-over: %.1fs, %d words -> %s (edge-tts)", result.duration, len(result.words), out_path.name)
    except Exception as exc:
        if settings.tts_fallback == "sapi":
            log.warning("edge-tts failed (%s); using Windows SAPI fallback", exc)
            result = _sapi_tts(script_text, out_path)
            log.info("voice-over (sapi): %.1fs, %d words -> %s", result.duration, len(result.words), out_path.name)
        else:
            raise
    words = result.words if result.words else _approximate_words(script_text)
    result.words = words
    word_path = out_path.with_suffix(".words.json")
    word_path.write_text(json.dumps({
        "audio_path": result.audio_path,
        "words": [w.model_dump() for w in words],
        "duration": result.duration,
    }, indent=2))
    return result