"""Tests for client-side pagination — verifies backend always returns the full list."""
import pytest
import aiosqlite
import httpx
from pathlib import Path
from unittest.mock import patch, AsyncMock

from api.server import app
from core.config import Settings
from core.database import init_db, upsert_post


async def _seed_posts(db_path: Path, count: int) -> list[dict]:
    await init_db(db_path)
    posts = []
    async with aiosqlite.connect(db_path) as db:
        for i in range(count):
            post = {
                "url": f"https://www.linkedin.com/posts/user_post-{i}",
                "content": f"Post number {i}",
                "date_iso": f"2026-05-{i + 1:02d}T12:00:00+00:00",
                "impressions": i * 10,
                "reactions": i,
                "comments": 0,
                "reposts": 0,
                "profile_viewers": 0,
                "followers_gained": 0,
                "scraped_at": "2026-05-21T00:00:00",
            }
            await upsert_post(db, post)
            posts.append(post)
    return posts


# ---------------------------------------------------------------------------
# GET /api/posts returns full list regardless of page size setting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_posts_returns_all_posts_no_backend_pagination(tmp_path):
    """Pagination is client-side; the API must always return the full list."""
    db_path = tmp_path / "tracker.db"
    settings = Settings(data_dir=tmp_path, scrape_limit=5)
    await _seed_posts(db_path, count=25)

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/posts")

    assert resp.status_code == 200
    assert len(resp.json()) == 25


@pytest.mark.asyncio
async def test_get_posts_returns_empty_list_for_empty_db(tmp_path):
    db_path = tmp_path / "tracker.db"
    settings = Settings(data_dir=tmp_path)
    await init_db(db_path)

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/posts")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_posts_returns_sorted_by_date_desc(tmp_path):
    db_path = tmp_path / "tracker.db"
    settings = Settings(data_dir=tmp_path)
    await _seed_posts(db_path, count=5)

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/posts")

    posts = resp.json()
    dates = [p["date_iso"] for p in posts]
    assert dates == sorted(dates, reverse=True)
