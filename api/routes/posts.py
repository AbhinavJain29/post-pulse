"""
Posts routes: list all posts and fetch a single post by URL.
"""
import aiosqlite
from fastapi import APIRouter, HTTPException

from core.config import load
from core.database import get_all_posts, get_post

router = APIRouter()


@router.get("/api/posts")
async def list_posts():
    settings = load()
    async with aiosqlite.connect(settings.db_path) as db:
        posts = await get_all_posts(db)
    return posts


@router.get("/api/posts/{url:path}")
async def fetch_post(url: str):
    settings = load()
    async with aiosqlite.connect(settings.db_path) as db:
        post = await get_post(db, url)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    return post
