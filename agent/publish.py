"""Step 5: publish / schedule videos to YouTube via the Data API v3.

OAuth2 refresh-token auth: run `python -m agent.cli auth` once, which writes
`YT_REFRESH_TOKEN` into `.env`.

Quota budget (free tier = 10,000 units/day):
  * videos.insert          = 1600 units each  -> 4 uploads = 6400/day
  * videos.update          = 1600 each        -> retries must be sparse
  * captions/insert        = ~50-400 each (optional auto-captions)
Daily generation targets 4 videos therefore fits comfortably; the publisher
raises before spending quota if a job is missing required fields.
"""
from __future__ import annotations

import json
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .config import CREDENTIALS_DIR, settings
from .logging_utils import get_logger
from .models import Metadata, RenderedVideo

log = get_logger("publish")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _credentials(path_for_file: Optional[str] = None):
    """Build an AuthorizedCredentials object from .env, or a saved client-secret json."""
    from google.oauth2.credentials import Credentials

    from google_auth_oauthlib.flow import InstalledAppFlow

    client_id = settings.yt_client_id
    client_secret = settings.yt_client_secret
    refresh_token = settings.yt_refresh_token
    if client_id and client_secret and refresh_token:
        return Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )

    secret_file = CREDENTIALS_DIR / "client_secret.json"
    if path_for_file:
        secret_file = Path(path_for_file)
    if not secret_file.exists():
        raise RuntimeError(
            "No YouTube credentials. Either set YT_CLIENT_ID/SECRET/REFRESH_TOKEN "
            "or place credentials/client_secret.json, then run `python -m agent.cli auth`."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    return creds


def build_uploader():
    """Return the authed YT API service + credentials."""
    from googleapiclient.discovery import build

    creds = _credentials()
    if not creds.valid and creds.refresh_token:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
    service = build("youtube", "v3", credentials=creds)
    return service


def upload_video(
    video_path: Path,
    metadata: Metadata,
    *,
    publish_at: Optional[str] = None,
    notify_subscribers: bool = False,
    made_for_kids: bool = False,
) -> str:
    """Upload a rendered MP4. Returns the YouTube video id on success."""
    from googleapiclient.http import MediaFileUpload

    service = build_uploader()
    body = {
        "snippet": {
            "title": metadata.title[:100],
            "description": metadata.description[:5000],
            "tags": metadata.tags[:500],
            "categoryId": settings.yt_category_id,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",  # scheduled videos must start private
            "selfDeclaredMadeForKids": made_for_kids,
            "notifySubscribers": notify_subscribers,
        },
    }
    if publish_at:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("upload progress %d%%", int(status.progress() * 100))
    video_id = response["id"]
    verb = "scheduled" if publish_at else "published"
    log.info("uploaded %s -> https://youtube.com/watch?v=%s (%s)", video_path.name, video_id, verb)
    return video_id


def schedule_four_videos(videos: list[RenderedVideo], peak_hours: list[str]) -> list[RenderedVideo]:
    """Assign publishAt timestamps to the daily 4 across peak hours (local tz)."""
    peak_hours = list(peak_hours) or ["07:00", "12:30", "17:00", "21:00"]
    today = datetime.now().date()
    for i, vid in enumerate(videos):
        hh, mm = peak_hours[i % len(peak_hours)].split(":")
        at = datetime(today.year, today.month, today.day, int(hh), int(mm))
        # if already past, push to tomorrow so uploads land in order
        publish_utc = at.astimezone(timezone.utc)
        if publish_utc < datetime.now(timezone.utc):
            at += timedelta(days=1)
        vid.publish_at = at.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    return videos


def auth_flow() -> None:
    """Interactive OAuth2 flow that persists YT_REFRESH_TOKEN into .env."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret_file = CREDENTIALS_DIR / "client_secret.json"
    if not secret_file.exists():
        raise RuntimeError(
            "Put credentials/client_secret.json (Google OAuth client, Desktop type) "
            "before running auth."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
    try:
        creds = flow.run_local_server(port=0, prompt="consent")
    except Exception:
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
        webbrowser.open(auth_url)
        code = input(f"Open the URL, allow access, then paste the code:\n{auth_url}\nCode: ").strip()
        flow.oauth2session.fetch_token(
            token_uri=flow.client_config["token_uri"],
            client_id=flow.client_config["client_id"],
            client_secret=flow.client_config["client_secret"],
            code=code,
        )
        creds = flow.credentials
    env_path = Path(__file__).resolve().parent.parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    key = "YT_REFRESH_TOKEN="
    value = key + creds.refresh_token
    if any(l.startswith(key) for l in lines):
        lines = [value if l.startswith(key) else l for l in lines]
    else:
        lines.append(value)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("refresh token written to .env")


def save_manifest(videos: list[RenderedVideo], date_str: str) -> Path:
    data = [v.model_dump(mode="json") for v in videos]
    manifest_path = Path(__file__).resolve().parent.parent / "data" / f"manifest-{date_str}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info("manifest written to %s", manifest_path)
    return manifest_path