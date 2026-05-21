"""
Settings routes: read and update user configuration.
API key is masked on reads; validated against Anthropic on writes.
"""
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import anthropic

from core.config import load, save

router = APIRouter()


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = None
    scrape_limit: int | None = None
    ai_feedback_enabled: bool | None = None


@router.get("/api/settings")
async def get_settings():
    settings = load()
    key = settings.anthropic_api_key
    masked_key = f"...{key[-4:]}" if len(key) >= 4 else ("***" if key else "")
    return {
        "anthropic_api_key": masked_key,
        "scrape_limit": settings.scrape_limit,
        "ai_feedback_enabled": settings.ai_feedback_enabled,
        "linkedin_session_expires": _session_expires_at(settings.cookies_path),
    }


def _session_expires_at(cookies_path: Path) -> str | None:
    """Return ISO expiry timestamp (mtime + 30 days) or None if cookies are missing/stale."""
    if not cookies_path.exists():
        return None
    mtime = datetime.fromtimestamp(cookies_path.stat().st_mtime)
    if (datetime.now() - mtime).days >= 30:
        return None
    return (mtime + timedelta(days=30)).isoformat()


@router.post("/api/settings")
async def update_settings(body: SettingsUpdate):
    settings = load()

    if body.anthropic_api_key is not None:
        if body.anthropic_api_key:
            # validate key with a lightweight Anthropic API call
            try:
                client = anthropic.Anthropic(api_key=body.anthropic_api_key)
                client.models.list()
            except anthropic.AuthenticationError:
                raise HTTPException(status_code=400, detail="Invalid Anthropic API key.")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Could not verify API key: {e}")
        settings = replace(settings, anthropic_api_key=body.anthropic_api_key)

    if body.scrape_limit is not None:
        if body.scrape_limit < 1:
            raise HTTPException(status_code=400, detail="scrape_limit must be at least 1.")
        settings = replace(settings, scrape_limit=body.scrape_limit)

    if body.ai_feedback_enabled is not None:
        settings = replace(settings, ai_feedback_enabled=body.ai_feedback_enabled)

    save(settings)
    return {"ok": True}
