"""Tests for core/database.py"""
import pytest
import pytest_asyncio
import aiosqlite

from core.database import (
    init_db,
    upsert_post,
    get_all_posts,
    get_post,
    get_post_urls,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest_asyncio.fixture
async def db(db_path):
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


SAMPLE_POST = {
    "url": "https://www.linkedin.com/posts/test_activity-123",
    "content": "Test post content",
    "date_iso": "2024-03-15T09:00:00",
    "impressions": 1000,
    "reactions": 50,
    "comments": 10,
    "reposts": 5,
    "profile_viewers": 20,
    "followers_gained": 3,
    "scraped_at": "2024-03-16T10:00:00",
}

# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_init_db_creates_tables(db_path):
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cur:
            tables = {row[0] for row in await cur.fetchall()}
    assert "posts" in tables
    assert "seen_urls" not in tables


@pytest.mark.asyncio
async def test_init_db_idempotent(db_path):
    await init_db(db_path)
    await init_db(db_path)  # should not raise


@pytest.mark.asyncio
async def test_init_db_creates_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "test.db"
    await init_db(nested)
    assert nested.exists()


# ---------------------------------------------------------------------------
# upsert_post + get_post
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_and_get_post(db):
    await upsert_post(db, SAMPLE_POST)
    result = await get_post(db, SAMPLE_POST["url"])
    assert result is not None
    assert result["url"] == SAMPLE_POST["url"]
    assert result["impressions"] == 1000
    assert result["content"] == "Test post content"


@pytest.mark.asyncio
async def test_upsert_updates_existing_post(db):
    await upsert_post(db, SAMPLE_POST)
    updated = {**SAMPLE_POST, "impressions": 2000, "reactions": 100}
    await upsert_post(db, updated)
    result = await get_post(db, SAMPLE_POST["url"])
    assert result["impressions"] == 2000
    assert result["reactions"] == 100


@pytest.mark.asyncio
async def test_upsert_preserves_existing_ai_feedback_when_new_is_none(db):
    feedback = {"overall_assessment": "Great post", "key_takeaway": "Be specific"}
    post_with_feedback = {**SAMPLE_POST, "ai_feedback": feedback}
    await upsert_post(db, post_with_feedback)

    # Upsert again without ai_feedback — existing value should be preserved
    post_without_feedback = {**SAMPLE_POST, "impressions": 3000}
    await upsert_post(db, post_without_feedback)

    result = await get_post(db, SAMPLE_POST["url"])
    assert result["ai_feedback"] is not None
    assert result["ai_feedback"]["overall_assessment"] == "Great post"


@pytest.mark.asyncio
async def test_upsert_stores_ai_feedback_as_parsed_dict(db):
    feedback = {"overall_assessment": "Good", "what_worked": "Hook"}
    await upsert_post(db, {**SAMPLE_POST, "ai_feedback": feedback})
    result = await get_post(db, SAMPLE_POST["url"])
    assert isinstance(result["ai_feedback"], dict)
    assert result["ai_feedback"]["what_worked"] == "Hook"


@pytest.mark.asyncio
async def test_get_post_returns_none_for_unknown_url(db):
    result = await get_post(db, "https://www.linkedin.com/posts/nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# get_all_posts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_all_posts_empty_db(db):
    result = await get_all_posts(db)
    assert result == []


@pytest.mark.asyncio
async def test_get_all_posts_returns_sorted_by_date_desc(db):
    post_a = {**SAMPLE_POST, "url": "https://linkedin.com/posts/a", "date_iso": "2024-01-01"}
    post_b = {**SAMPLE_POST, "url": "https://linkedin.com/posts/b", "date_iso": "2024-03-01"}
    post_c = {**SAMPLE_POST, "url": "https://linkedin.com/posts/c", "date_iso": "2024-02-01"}
    for p in [post_a, post_b, post_c]:
        await upsert_post(db, p)

    results = await get_all_posts(db)
    dates = [r["date_iso"] for r in results]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_get_all_posts_returns_multiple(db):
    for i in range(3):
        post = {**SAMPLE_POST, "url": f"https://linkedin.com/posts/{i}"}
        await upsert_post(db, post)
    results = await get_all_posts(db)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# get_post_urls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_post_urls_empty(db):
    result = await get_post_urls(db)
    assert result == set()


@pytest.mark.asyncio
async def test_get_post_urls_returns_all_inserted_urls(db):
    urls = [f"https://linkedin.com/posts/{i}" for i in range(3)]
    for url in urls:
        await upsert_post(db, {**SAMPLE_POST, "url": url})
    result = await get_post_urls(db)
    assert result == set(urls)


@pytest.mark.asyncio
async def test_get_post_urls_deduplicates_on_upsert(db):
    await upsert_post(db, SAMPLE_POST)
    await upsert_post(db, {**SAMPLE_POST, "impressions": 9999})
    result = await get_post_urls(db)
    assert len(result) == 1
    assert SAMPLE_POST["url"] in result
