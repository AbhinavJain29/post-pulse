"""
LinkedIn Post Tracker — CLI entry point.

Usage:
    python tracker.py                   # scrape and generate AI feedback
    python tracker.py --limit 10        # scrape only 10 posts
    python tracker.py --no-ai           # skip AI feedback generation
    python tracker.py --reset           # clear pipeline crash-recovery state
"""
import argparse
import asyncio
from dataclasses import replace

from core.config import load
from core.pipeline import run


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Post Tracker")
    parser.add_argument("--limit", type=int, default=None,
                        help="Posts to scrape per run (default: from config)")
    parser.add_argument("--no-ai", action="store_true", help="Skip AI feedback generation")
    parser.add_argument("--reset", action="store_true",
                        help="Clear pipeline crash-recovery state")
    args = parser.parse_args()

    settings = load()

    if args.reset:
        settings.pipeline_state_path.unlink(missing_ok=True)
        print("Pipeline state cleared.")

    if args.limit is not None:
        settings = replace(settings, scrape_limit=args.limit)

    if args.no_ai:
        settings = replace(settings, anthropic_api_key="")

    asyncio.run(run(settings, asyncio.Queue()))


if __name__ == "__main__":
    main()
