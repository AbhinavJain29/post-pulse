"""
Async SQLite helpers for Post Pulse using aiosqlite.
All functions accept an open aiosqlite.Connection; callers manage the connection lifecycle.
"""
import json
from pathlib import Path

import aiosqlite

CREATE_POSTS = """
CREATE TABLE IF NOT EXISTS posts (
    url              TEXT PRIMARY KEY,
    content          TEXT    NOT NULL DEFAULT '',
    date_iso         TEXT    NOT NULL DEFAULT '',
    impressions      INTEGER NOT NULL DEFAULT 0,
    reactions        INTEGER NOT NULL DEFAULT 0,
    comments         INTEGER NOT NULL DEFAULT 0,
    reposts          INTEGER NOT NULL DEFAULT 0,
    profile_viewers  INTEGER NOT NULL DEFAULT 0,
    followers_gained INTEGER NOT NULL DEFAULT 0,
    scraped_at       TEXT    NOT NULL DEFAULT '',
    ai_feedback      TEXT
)
"""


async def init_db(db_path: Path) -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(CREATE_POSTS)
        await db.commit()


async def upsert_post(db: aiosqlite.Connection, post: dict) -> None:
    """Insert or replace a post. ai_feedback dict is serialised to JSON."""
    ai_feedback = post.get("ai_feedback")
    ai_json = json.dumps(ai_feedback) if ai_feedback is not None else None

    await db.execute(
        """
        INSERT INTO posts
            (url, content, date_iso, impressions, reactions, comments,
             reposts, profile_viewers, followers_gained, scraped_at, ai_feedback)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            content          = excluded.content,
            date_iso         = excluded.date_iso,
            impressions      = excluded.impressions,
            reactions        = excluded.reactions,
            comments         = excluded.comments,
            reposts          = excluded.reposts,
            profile_viewers  = excluded.profile_viewers,
            followers_gained = excluded.followers_gained,
            scraped_at       = excluded.scraped_at,
            ai_feedback      = COALESCE(excluded.ai_feedback, posts.ai_feedback)
        """,
        (
            post.get("url", ""),
            post.get("content", ""),
            post.get("date_iso", ""),
            post.get("impressions", 0),
            post.get("reactions", 0),
            post.get("comments", 0),
            post.get("reposts", 0),
            post.get("profile_viewers", 0),
            post.get("followers_gained", 0),
            post.get("scraped_at", ""),
            ai_json,
        ),
    )
    await db.commit()


async def get_all_posts(db: aiosqlite.Connection) -> list[dict]:
    """Return all posts sorted by date_iso descending."""
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT * FROM posts ORDER BY date_iso DESC"
    ) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_dict(row) for row in rows]


async def get_post(db: aiosqlite.Connection, url: str) -> dict | None:
    """Return a single post by URL, or None if not found."""
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM posts WHERE url = ?", (url,)) as cursor:
        row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def get_post_urls(db: aiosqlite.Connection) -> set[str]:
    """Return the set of all post URLs already in the database."""
    async with db.execute("SELECT url FROM posts") as cursor:
        rows = await cursor.fetchall()
    return {row[0] for row in rows}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    if d.get("ai_feedback"):
        try:
            d["ai_feedback"] = json.loads(d["ai_feedback"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d
