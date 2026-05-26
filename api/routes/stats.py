"""Stats route: aggregate totals across all scraped posts."""
import aiosqlite
from fastapi import APIRouter
from core.config import load

router = APIRouter()


@router.get("/api/stats")
async def get_stats():
    settings = load()
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute("""
            SELECT COUNT(*),
                   COALESCE(SUM(impressions), 0),
                   COALESCE(SUM(reactions), 0),
                   COALESCE(SUM(comments), 0)
            FROM posts
        """) as cursor:
            row = await cursor.fetchone()
    return {
        "total_posts":       row[0],
        "total_impressions": row[1],
        "total_reactions":   row[2],
        "total_comments":    row[3],
    }
