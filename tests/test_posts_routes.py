"""Tests for api/routes/posts.py"""
import pytest
import httpx
import aiosqlite
from pathlib import Path
from unittest.mock import patch

from api.server import app
from core.database import init_db, upsert_post
from core.config import Settings


def make_settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path)


def make_post(n: int = 1) -> dict:
    return {
        "url": f"https://linkedin.com/posts/test-{n}",
        "content": f"Content {n}",
        "date_iso": f"2024-0{n}-01T09:00:00",
        "impressions": 100 * n,
        "reactions": 10,
        "comments": 5,
        "reposts": 2,
        "profile_viewers": 3,
        "followers_gained": 1,
        "scraped_at": "2024-03-16T10:00:00",
    }


# ---------------------------------------------------------------------------
# GET /api/posts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_posts_returns_all(tmp_path):
    settings = make_settings(tmp_path)
    await init_db(settings.db_path)
    async with aiosqlite.connect(settings.db_path) as db:
        await upsert_post(db, make_post(1))
        await upsert_post(db, make_post(2))

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/posts")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    urls = {p["url"] for p in body}
    assert urls == {make_post(1)["url"], make_post(2)["url"]}


@pytest.mark.asyncio
async def test_list_posts_empty_db_returns_empty_array(tmp_path):
    settings = make_settings(tmp_path)
    await init_db(settings.db_path)

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/posts")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_posts_sorted_by_date_desc(tmp_path):
    settings = make_settings(tmp_path)
    await init_db(settings.db_path)
    async with aiosqlite.connect(settings.db_path) as db:
        await upsert_post(db, make_post(1))  # date 2024-01-01
        await upsert_post(db, make_post(3))  # date 2024-03-01
        await upsert_post(db, make_post(2))  # date 2024-02-01

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/posts")

    dates = [p["date_iso"] for p in resp.json()]
    assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# GET /api/posts/{url:path}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_post_returns_post(tmp_path):
    settings = make_settings(tmp_path)
    post = make_post(1)
    await init_db(settings.db_path)
    async with aiosqlite.connect(settings.db_path) as db:
        await upsert_post(db, post)

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/posts/{post['url']}")

    assert resp.status_code == 200
    assert resp.json()["url"] == post["url"]


@pytest.mark.asyncio
async def test_fetch_post_returns_404_for_missing_post(tmp_path):
    settings = make_settings(tmp_path)
    await init_db(settings.db_path)

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/posts/https://linkedin.com/posts/nonexistent")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fetch_post_includes_parsed_ai_feedback(tmp_path):
    settings = make_settings(tmp_path)
    post = make_post(1)
    post["ai_feedback"] = {
        "overall_assessment": "Great post",
        "what_worked": "Hook",
        "what_to_improve": "Length",
        "rewrite_suggestion": "Try shorter",
        "key_takeaway": "Be brief",
    }
    await init_db(settings.db_path)
    async with aiosqlite.connect(settings.db_path) as db:
        await upsert_post(db, post)

    with patch("api.routes.posts.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/posts/{post['url']}")

    assert resp.status_code == 200
    feedback = resp.json()["ai_feedback"]
    assert isinstance(feedback, dict)
    assert feedback["overall_assessment"] == "Great post"
