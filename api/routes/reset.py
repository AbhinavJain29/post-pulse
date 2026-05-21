"""Reset route: wipe all posts and LinkedIn cookies."""
from fastapi import APIRouter
from core.config import load

router = APIRouter()


@router.delete("/api/reset")
async def reset_data():
    settings = load()

    # Truncate posts table
    import aiosqlite
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM posts")
        await db.commit()

    # Remove LinkedIn cookies so next sync triggers fresh login
    if settings.cookies_path.exists():
        settings.cookies_path.unlink()

    return {"ok": True}
