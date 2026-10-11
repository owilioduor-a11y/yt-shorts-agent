"""Command-line interface for the agent.

  python -m agent.cli auth       # one-time YouTube OAuth (writes refresh token)
  python -m agent.cli news       # browse today's fresh stories per niche
  python -m agent.cli build      # build today's 4 videos, do NOT upload
  python -m agent.cli run        # build AND upload/schedule (respects AUTO_UPLOAD)
  python -m agent.cli serve      # run the daily scheduler (long-running)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from .config import ensure_dirs, settings
from .logging_utils import get_logger

log = get_logger("cli")


def cmd_auth(_args) -> int:
    from .publish import auth_flow

    auth_flow()
    return 0


def cmd_news(_args) -> int:
    from .sources import fetch_all

    ensure_dirs()
    items = fetch_all()
    for niche, list_items in items.items():
        print(f"\n=== {niche.upper()} ({len(list_items)} fresh) ===")
        for it in list_items[:10]:
            when = it.published.strftime("%m-%d %H:%M") if it.published else "?"
            print(f"  [{it.score:5.1f}] {when}  {it.title}")
            print(f"          {it.source}  {it.url}")
    return 0


def cmd_build(args) -> int:
    if getattr(args, "sample", False):
        return cmd_sample(args)
    from .orchestrator import run_pipeline

    videos = run_pipeline(upload=False, count=args.count)
    if not videos:
        log.error("pipeline produced nothing")
        return 1
    for v in videos:
        print(f"  built: {v.niche:14s} {v.duration_seconds:5.1f}s -> {v.video_path}")
    print(f"\nmanifest/artifacts under data/jobs/{datetime.now():%Y%m%d}/")
    return 0


def cmd_run(args) -> int:
    from .orchestrator import run_pipeline

    videos = run_pipeline(upload=not args.no_upload, count=args.count)
    if not videos:
        log.error("pipeline produced nothing")
        return 1
    for v in videos:
        status = f"scheduled {v.publish_at}" if v.publish_at else "uploaded"
        print(f"  {v.niche:14s} {v.metadata.title[:50]:50s} {status}")
    return 0


def cmd_serve(_args) -> int:
    from .scheduler import serve

    serve()
    return 0


def cmd_sample(args) -> int:
    """Build a single sample video from a hardcoded script (sanity check)."""
    from .models import Script
    from .orchestrator import run_pipeline

    scripts = [
        Script(
            niche="programming",
            source_title="Sample: The AI code assistant race heats up",
            source_url="https://example.com/sample",
            hook="Just in: a new open-source AI can write 90 percent of your code.",
            body="It hits release today, and devs are already calling it a game changer. It reviews pull requests in seconds. And it runs fully on your own machine.",
            cta="Follow for your daily dev intel.",
        )
    ]
    videos = run_pipeline(upload=False, scripts=scripts, count=1)
    return 0 if videos else 1


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(prog="yt-shorts-agent", description="Autonomous faceless YouTube Shorts agent")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="one-time YouTube OAuth (writes refresh token to .env)")
    sub.add_parser("news", help="list today's fresh stories per niche")

    parser_build = sub.add_parser("build", help="build today's 4 videos, no upload")
    parser_build.add_argument("--count", type=int, default=None, help="limit number of videos (default: all)")
    parser_build.add_argument("--sample", action="store_true", help="build one sample video for a smoke test")

    parser_run = sub.add_parser("run", help="build AND upload/schedule to YouTube")
    parser_run.add_argument("--count", type=int, default=None)
    parser_run.add_argument("--no-upload", action="store_true", help="build only (overrides AUTO_UPLOAD)")

    sub.add_parser("serve", help="run the daily scheduler (long-running)")

    args = parser.parse_args()
    handler = {"auth": cmd_auth, "news": cmd_news, "build": cmd_build, "run": cmd_run, "serve": cmd_serve}.get(args.command)
    if not handler:
        parser.print_help()
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())