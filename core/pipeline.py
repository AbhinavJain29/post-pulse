"""
Main pipeline coroutine. Orchestrates scraping + AI feedback, writes to SQLite,
and emits progress events to a queue for the web UI or CLI to consume.
"""
import asyncio

import aiosqlite

from scraper import LinkedInScraper
from ai_feedback import PostFeedbackGenerator
from core.config import Settings
from core.database import init_db, upsert_post, get_post_urls


async def run(settings: Settings, progress_queue: asyncio.Queue) -> None:
    async def emit(phase: str, status: str, message: str = "", count: int = 0,
                   total: int = 0, post: dict | None = None):
        event = {
            "phase": phase,
            "status": status,
            "message": message,
            "count": count,
            "total": total,
        }
        if post is not None:
            event["post"] = post
        await progress_queue.put(event)

    await init_db(settings.db_path)

    # --- Phase 1: Scrape ---
    await emit("login", "waiting", "Please log in to LinkedIn in the browser window.")

    scraper = LinkedInScraper(cookies_path=settings.cookies_path)
    new_posts = []

    try:
        await scraper.start()
        await scraper.login()
        await emit("login", "complete", "Login successful.")

        async with aiosqlite.connect(settings.db_path) as db:
            skip_urls = await get_post_urls(db)

        await emit("scrape", "progress", f"Scraping posts (limit={settings.scrape_limit})...")

        async def on_post_scraped(post: dict, i: int, total: int) -> None:
            async with aiosqlite.connect(settings.db_path) as db:
                await upsert_post(db, post)
            await emit("scrape", "post_ready", f"Scraped post {i}/{total}",
                       count=i, total=total, post=post)

        new_posts = await scraper.get_my_posts(
            limit=settings.scrape_limit,
            skip_urls=skip_urls,
            on_post_ready=on_post_scraped,
        )

        await emit("scrape", "complete", f"Scraped {len(new_posts)} new post(s).",
                   count=len(new_posts), total=len(new_posts))

    except Exception as e:
        await emit("error", "error", str(e))
        return
    finally:
        await scraper.stop()

    if not new_posts:
        await emit("complete", "complete", "No new posts found.")
        settings.pipeline_state_path.unlink(missing_ok=True)
        return

    # --- Phase 2: AI Feedback ---
    if not settings.anthropic_api_key or not settings.ai_feedback_enabled:
        reason = "no API key" if not settings.anthropic_api_key else "AI feedback disabled"
        await emit("complete", "complete",
                   f"{len(new_posts)} post(s) saved. AI feedback skipped ({reason}).")
        settings.pipeline_state_path.unlink(missing_ok=True)
        return

    generator = PostFeedbackGenerator(api_key=settings.anthropic_api_key)
    total = len(new_posts)

    await emit("ai", "progress", f"Generating AI feedback for {total} post(s)...", total=total)

    async with aiosqlite.connect(settings.db_path) as db:
        for i, post in enumerate(new_posts, 1):
            try:
                feedback = await asyncio.to_thread(generator.generate_feedback, post)
                post["ai_feedback"] = feedback
            except Exception as e:
                post["ai_feedback"] = {
                    "overall_assessment": f"_Feedback generation failed: {e}_",
                    "what_worked": "",
                    "what_to_improve": "",
                    "rewrite_suggestion": "",
                    "key_takeaway": "",
                }
            await upsert_post(db, post)
            await emit("ai", "post_ready", f"AI feedback ({i}/{total})",
                       count=i, total=total, post=post)

    await emit("complete", "complete", f"{len(new_posts)} post(s) saved with AI feedback.")
    settings.pipeline_state_path.unlink(missing_ok=True)
