"""Tests for core/pipeline.py"""
import asyncio
import pytest
import aiosqlite
from unittest.mock import AsyncMock, MagicMock, patch

from core.config import Settings
from core.database import get_all_posts
from core.pipeline import run


def make_settings(tmp_path, api_key="sk-test", ai_feedback_enabled=True):
    return Settings(anthropic_api_key=api_key, scrape_limit=5,
                    ai_feedback_enabled=ai_feedback_enabled, data_dir=tmp_path)


def make_posts(n=2):
    return [
        {
            "url": f"https://linkedin.com/posts/test-{i}",
            "content": f"Post content {i}",
            "date_iso": f"2024-0{i + 1}-01T09:00:00",
            "impressions": 100 * i,
            "reactions": 10,
            "comments": 5,
            "reposts": 2,
            "profile_viewers": 3,
            "followers_gained": 1,
            "scraped_at": "2024-03-16T10:00:00",
        }
        for i in range(1, n + 1)
    ]


def make_feedback():
    return {
        "overall_assessment": "Great post",
        "what_worked": "Good hook",
        "what_to_improve": "Add more specifics",
        "rewrite_suggestion": "Try starting with a story",
        "key_takeaway": "Be specific",
    }


def drain(queue: asyncio.Queue) -> list[dict]:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def mock_scraper(posts):
    m = AsyncMock()
    async def _get_my_posts(limit=200, skip_urls=None, on_post_ready=None):
        total = len(posts)
        for i, post in enumerate(posts, 1):
            if on_post_ready:
                await on_post_ready(post, i, total)
        return posts
    m.get_my_posts.side_effect = _get_my_posts
    return m


# ---------------------------------------------------------------------------
# Happy path — scrape + AI
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_emits_events_in_order(tmp_path):
    settings = make_settings(tmp_path)
    posts = make_posts(2)
    scraper = mock_scraper(posts)
    generator = MagicMock()
    generator.generate_feedback.return_value = make_feedback()
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper), \
         patch("core.pipeline.PostFeedbackGenerator", return_value=generator):
        await run(settings, queue)

    events = drain(queue)
    phase_status = [(e["phase"], e["status"]) for e in events]

    assert phase_status[0] == ("login", "waiting")
    assert ("login", "complete") in phase_status
    assert ("scrape", "progress") in phase_status
    assert ("scrape", "complete") in phase_status
    assert ("ai", "progress") in phase_status
    assert phase_status[-1] == ("complete", "complete")


@pytest.mark.asyncio
async def test_run_writes_posts_to_db(tmp_path):
    settings = make_settings(tmp_path)
    posts = make_posts(2)
    scraper = mock_scraper(posts)
    generator = MagicMock()
    generator.generate_feedback.return_value = make_feedback()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper), \
         patch("core.pipeline.PostFeedbackGenerator", return_value=generator):
        await run(settings, asyncio.Queue())

    async with aiosqlite.connect(settings.db_path) as db:
        saved = await get_all_posts(db)

    assert len(saved) == 2
    urls = {p["url"] for p in saved}
    assert urls == {p["url"] for p in posts}


@pytest.mark.asyncio
async def test_run_stores_ai_feedback_in_db(tmp_path):
    settings = make_settings(tmp_path)
    posts = make_posts(1)
    scraper = mock_scraper(posts)
    feedback = make_feedback()
    generator = MagicMock()
    generator.generate_feedback.return_value = feedback

    with patch("core.pipeline.LinkedInScraper", return_value=scraper), \
         patch("core.pipeline.PostFeedbackGenerator", return_value=generator):
        await run(settings, asyncio.Queue())

    async with aiosqlite.connect(settings.db_path) as db:
        saved = await get_all_posts(db)

    assert saved[0]["ai_feedback"]["overall_assessment"] == "Great post"


@pytest.mark.asyncio
async def test_run_emits_one_ai_post_ready_event_per_post(tmp_path):
    settings = make_settings(tmp_path)
    posts = make_posts(3)
    scraper = mock_scraper(posts)
    generator = MagicMock()
    generator.generate_feedback.return_value = make_feedback()
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper), \
         patch("core.pipeline.PostFeedbackGenerator", return_value=generator):
        await run(settings, queue)

    events = drain(queue)
    ai_ready = [e for e in events if e["phase"] == "ai" and e["status"] == "post_ready"]
    assert len(ai_ready) == 3


@pytest.mark.asyncio
async def test_run_emits_scrape_post_ready_events(tmp_path):
    settings = make_settings(tmp_path, api_key="")
    posts = make_posts(3)
    scraper = mock_scraper(posts)
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, queue)

    events = drain(queue)
    scrape_ready = [e for e in events if e["phase"] == "scrape" and e["status"] == "post_ready"]
    assert len(scrape_ready) == 3


@pytest.mark.asyncio
async def test_run_post_ready_events_include_post_data(tmp_path):
    settings = make_settings(tmp_path, api_key="")
    posts = make_posts(2)
    scraper = mock_scraper(posts)
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, queue)

    events = drain(queue)
    scrape_ready = [e for e in events if e["phase"] == "scrape" and e["status"] == "post_ready"]
    assert all("post" in e for e in scrape_ready)
    urls = {e["post"]["url"] for e in scrape_ready}
    assert urls == {p["url"] for p in posts}


# ---------------------------------------------------------------------------
# AI skipped when no API key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_skips_ai_when_no_api_key(tmp_path):
    settings = make_settings(tmp_path, api_key="")
    posts = make_posts(2)
    scraper = mock_scraper(posts)
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, queue)

    events = drain(queue)
    phases = [e["phase"] for e in events]

    assert "ai" not in phases
    assert "complete" in phases


@pytest.mark.asyncio
async def test_run_posts_saved_even_without_ai(tmp_path):
    settings = make_settings(tmp_path, api_key="")
    posts = make_posts(2)
    scraper = mock_scraper(posts)

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, asyncio.Queue())

    async with aiosqlite.connect(settings.db_path) as db:
        saved = await get_all_posts(db)

    assert len(saved) == 2
    assert all(p["ai_feedback"] is None for p in saved)


# ---------------------------------------------------------------------------
# AI skipped when flag disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_skips_ai_when_flag_disabled(tmp_path):
    settings = make_settings(tmp_path, ai_feedback_enabled=False)
    posts = make_posts(2)
    scraper = mock_scraper(posts)
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, queue)

    events = drain(queue)
    phases = [e["phase"] for e in events]

    assert "ai" not in phases
    assert "complete" in phases


@pytest.mark.asyncio
async def test_run_complete_message_says_disabled_when_flag_off(tmp_path):
    settings = make_settings(tmp_path, ai_feedback_enabled=False)
    scraper = mock_scraper(make_posts(1))
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, queue)

    events = drain(queue)
    complete = next(e for e in events if e["phase"] == "complete")
    assert "disabled" in complete["message"]


# ---------------------------------------------------------------------------
# No new posts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_no_new_posts_emits_complete(tmp_path):
    settings = make_settings(tmp_path)
    scraper = mock_scraper([])
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, queue)

    events = drain(queue)
    phases = [e["phase"] for e in events]

    assert "complete" in phases
    assert "ai" not in phases


@pytest.mark.asyncio
async def test_run_no_new_posts_db_stays_empty(tmp_path):
    settings = make_settings(tmp_path)
    scraper = mock_scraper([])

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, asyncio.Queue())

    async with aiosqlite.connect(settings.db_path) as db:
        saved = await get_all_posts(db)

    assert saved == []


# ---------------------------------------------------------------------------
# Scraper error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_scraper_error_emits_error_event(tmp_path):
    settings = make_settings(tmp_path)
    scraper = AsyncMock()
    scraper.get_my_posts.side_effect = Exception("LinkedIn is down")
    queue = asyncio.Queue()

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, queue)

    events = drain(queue)
    error_events = [e for e in events if e["phase"] == "error"]

    assert len(error_events) == 1
    assert "LinkedIn is down" in error_events[0]["message"]


@pytest.mark.asyncio
async def test_run_scraper_error_does_not_write_to_db(tmp_path):
    settings = make_settings(tmp_path)
    scraper = AsyncMock()
    scraper.get_my_posts.side_effect = Exception("scrape failed")

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, asyncio.Queue())

    async with aiosqlite.connect(settings.db_path) as db:
        saved = await get_all_posts(db)

    assert saved == []


@pytest.mark.asyncio
async def test_run_scraper_error_calls_stop(tmp_path):
    settings = make_settings(tmp_path)
    scraper = AsyncMock()
    scraper.get_my_posts.side_effect = Exception("scrape failed")

    with patch("core.pipeline.LinkedInScraper", return_value=scraper):
        await run(settings, asyncio.Queue())

    scraper.stop.assert_called_once()
