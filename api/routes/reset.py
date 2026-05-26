"""Reset route: wipe all posts and LinkedIn cookies."""
import asyncio
import sqlite3
from fastapi import APIRouter
from core.config import load

router = APIRouter()


def _vacuum(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.isolation_level = None  # autocommit — required for VACUUM
    conn.execute("VACUUM")
    conn.close()


@router.delete("/api/reset")
async def reset_data():
    settings = load()

    import aiosqlite
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM posts")
        await db.commit()

    await asyncio.to_thread(_vacuum, str(settings.db_path))

    if settings.cookies_path.exists():
        settings.cookies_path.unlink()

    return {"ok": True}
