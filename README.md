# yt-shorts-agent

Autonomous faceless YouTube Shorts agent: sources breaking tech news, writes
scripts, generates AI voice-overs, renders captioned 1080×1920 videos and
publishes/schedules 4 Shorts a day across **Cybersecurity News**, **Programming
Updates** and **Crypto News**.

On a high level, the system is a **Python orchestrator** + a **Remotion (React)
video compositor**, wired to a small set of free/hosted APIs.

```
┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐
│ 1. SOURCING │→ │ 2. VOICEOVER │→ │ 3. RENDER    │→ │ 4. META    │→ │ 5. PUBLISH   │
│ RSS feeds   │  │ edge-tts /   │  │ Remotion +   │  │ LLM title, │  │ YouTube Data │
│ + LLM pick  │  │ ElevenLabs   │  │ stock video  │  │ desc, tags │  │ API v3, OAuth │
└─────────────┘  └──────────────┘  └──────────────┘  └────────────┘  └──────────────┘
```

## Architecture (step by step)

### Step 1 — Trend sourcing & scripting (`agent/sources/`, `agent/script.py`)
- **Sources**: curated RSS catalog in `agent/sources/feeds.py` — BleepingComputer,
  The Hacker News, Krebs, CISA, GitHub Blog, Hacker News (hnrss), Dev.to, InfoQ,
  TechCrunch, CoinDesk, Cointelegraph, Decrypt, The Block, Bitcoin Magazine.
- RSS is deliberately used over X/Twitter scraping: it is structured, needs no
  paid API, always links to the original article, and every feed is start-
  friendly with rate limits.
- Each item is scored on **recenty + topical hot keywords** (zero-day, exploit,
  etf, halving, release, rust, …) and deduplicated by URL + headline fingerprint.
- The LLM (Groq **gpt-oss-120b** or Gemini/Ollama) picks the 4 most compelling
  stories across the configured niche mix and writes a ~150-word script with a
  ≤3s hook, rapid-fire body and a subscribe CTA.

### Step 2 — Voice-over generation (`agent/tts.py`)
- **Default**: `edge-tts` (free Microsoft Edge neural voices, no API key) with
  word-boundary timings streamed straight from the engine.
- **Optional**: ElevenLabs (`TTS_ENGINE=elevenlabs`) — same interface; word
  timings come back in the response headers.
- Output: `voice.mp3` + `voice.words.json` (word → start/end seconds) that drive
  the animated captions.

### Step 3 — Visuals & editing (`agent/assets.py`, `agent/music.py`, `video/`)
- **Backgrounds**: Pexels (`/videos/search`, portait, ≥720p) and Pixabay
  (video/image) APIs. Keywords are extracted from the script (generic tech words,
  not the specific news headline) to stay reactive-free and evergreen.
- **Music**: local royalty-free/CC0 MP3s dropped in `data/music/` (rotated daily),
  or a CC0 Pixabay Music query. Never downloaded from YouTube/SoundCloud.
- **Editor**: [Remotion](https://www.remotion.dev) renders each Short programmatically
  (`video/src/Short.tsx`):
  - full-bleed crossfading video/image backgrounds + dark editorial gradient,
  - large centered captions, current word highlighted in **yellow**, rolling
    3-word window, progress bar,
  - headline + niche chip (CYBER ALERT / DEV NEWS / CRYPTO PULSE) that fades
    after ~9s,
  - voice-over track + background music ducked to ~16% volume.
- Renderer is a Node subprocess (`npx remotion render`), driven by a props JSON
  that Python stages into `video/public/jobs/<id>/`.

### Step 4 — Metadata generation (`agent/metadata.py`)
- LLM enforces: title < 60 chars with a curiosity hook, short description with
  source link + 3 trending hashtags, 8–12 low-competition tags.
- Deterministic fallback if the LLM call fails so the pipeline never halts.

### Step 5 — Autonomous publishing (`agent/publish.py`)
- YouTube **Data API v3** with OAuth2 refresh-token auth
  (`python -m agent.cli auth` → token saved to `.env`).
- `videos.insert` with `privacyStatus=private` + `publishAt` for true scheduling
  (unlisted/*private for the first 24h is the safest path).
- The 4 uploads are spread across `PEAK_HOURS` (default 07:00/12:30/17:00/21:00).
- `AUTO_UPLOAD=false` by default: run `python -m agent.cli run` manually until
  you trust the output, export `AUTO_UPLOAD=true` for full autonomy.

### Scheduling (`agent/scheduler.py`)
- APScheduler runs the pipeline once daily at `GENERATE_TIME`, then queues
  uploads; **one long-running process** on any box/VPS keeps your channel going.

## Quickstart

```bash
# 1. Python side
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt

# 2. Renderer (once)
cd video
npm install
cd ..

# 3. Config: copy .env.example to .env (already present) and fill in keys

# 4. Smoke test — build one sample video (no upload)
python -m agent.cli build --sample

# 5. Browse today's fresh stories
python -m agent.cli news

# 6. One-time YouTube auth (needs credentials/client_secret.json)
python -m agent.cli auth

# 7. Build today's 4 videos
python -m agent.cli build

# 8. Build + upload/schedule to YouTube
python -m agent.cli run

# 9. Fully autonomous daemon
python -m agent.cli serve
```

## Tool map

| Concern               | Tool                                              | Why                                                        |
|-----------------------|---------------------------------------------------|------------------------------------------------------------|
| News sourcing         | RSS (feedparser) + Groq/Gemini/Ollama LLM         | Free, structured, respects publishers                      |
| Scriptwriting         | Groq `gpt-oss-120b` (fallback `gpt-oss-20b`)      | ~free tier, sub-second latency, JSON mode                  |
| Voice-over            | edge-tts (default) / ElevenLabs (premium)         | Free neural voices + exact word timings                    |
| Visuals               | Pexels / Pixabay APIs                             | Free commercial-use footage & images                       |
| Video editing         | Remotion (React -> MP4)                           | Code-defined: captions, transitions, audio mixing          |
| Music                 | Local CC0 tracks / Pixabay Music                  | Copyright-clean provenance                                 |
| Scheduling            | APScheduler                                       | Cron semantics, misfire grace, headless                    |
| Publishing            | YouTube Data API v3 + google-api-python-client    | OAuth2, resumable uploads, `publishAt` scheduling          |
| Orchestration         | Pure Python (subprocess bridges to Node)          | Full control, easy to port to n8n/CrewAI later             |

### Where no-code/low-code fits
The same primitive functions map 1:1 onto **n8n** or **Make.com**:
n8n nodes for RSS-feed-poll → LLM (`n8n-nodes-langchain`) → TTS → HTTP
request to a Shotstack/CapCut-template renderer → and the YouTube `videos.insert`
node. Remotion is the better fit here because captions + timing need a rendering
engine; Shotstack/CapCut are good drop-in alternatives if you prefer a hosted
compositor (Remotion can also be hosted via `remotion render` on CI).

## Rate limits & quota (critical)

- **YouTube**: 10,000 quota units/day free. `videos.insert` = 1,600 units → 4 daily
  uploads burn 6,400, leaving headroom for retries and captions. Never run more
  than ~6 `insert`s/day, and keep resumable uploads (`resumable=True`) to avoid
  re-uploading on network drops.
- **Groq**: ~30 requests/min, free tier; our pipeline uses ~15 calls/day. Cache
  per-day artifacts (`data/jobs/…`) to avoid re-generating on re-runs.
- **Pexels**: 200 req/hour. **Pixabay**: 100 req/hour, 20k downloads/day. We
  cache downloads on disk and reuse already-fetched clips.
- **edge-tts**: unofficial but free; keep it to a handful of utterances/day.
  If it starts failing, switch `TTS_ENGINE=elevenlabs`.

## Copyright safety checklist

1. **Text**: every script links back to its source; only facts from the article
   are used (LLM is constrained to the provided summaries). No copyrighted
   article is pasted into the video.
2. **Video/imagery**: Pexels/Pixabay media is royalty-free / CC0 — never scrape
   images from news sites or Google Images.
3. **Music**: only CC0 tracks you own or licensed downloads (Pixabay Music, YouTube
   Audio Library). Keep provenance in `data/` so you can prove attribution.
4. **Captions/voice**: generated from the LLM script — no third-party audio.
5. **YouTube flags**: uploads are `selfDeclaredMadeForKids=false`; scheduling uses
   private→public transition which avoids copyright-scan waves on public uploads.
6. **Niche hygiene**: when in doubt, a 6s clip from a licensed stock site with a
   news overlay is *transformative and sourced*; a 6s exact copy of an article
   screen recorded from a paywall is not — always summarize.

## Project layout

```
agent/
  sources/     feeds.py (catalog), rss.py (fetch+rank)
  config.py    env settings            models.py   pydantic types
  llm.py       Groq/Gemini/Ollama      script.py   story pick + script
  tts.py       voice + word timings    assets.py   stock footage
  music.py     CC0 background tracks   video.py    Remotion bridge
  metadata.py  SEO copy                publish.py  YouTube upload
  orchestrator.py 5-step pipeline      scheduler.py daily cron
  cli.py       auth/news/build/run/serve
video/         Remotion project (React) — captions, transitions, audio
data/          daily jobs, manifests, cached assets (gitignored)
credentials/   client_secret.json (gitignored)
```

## Getting from 4/day to scale

- Run the daemon on a VPS (`serve`) so generation+uploads happen even while your
  machine sleeps.
- Add more niches/feeds via `FEEDS` in `feeds.py` and `NICHE_MIX` in `.env`.
- Swap in CrewAI for the "selection" step if you want multi-LLM debate on
  story scoring; the rest of the pipeline is untouched.