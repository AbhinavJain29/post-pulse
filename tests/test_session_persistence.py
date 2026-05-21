"""Tests for LinkedIn session persistence (cookie freshness + settings endpoint)."""
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import httpx

from scraper import _cookies_are_fresh
from api.server import app
from core.config import Settings


# ---------------------------------------------------------------------------
# _cookies_are_fresh
# ---------------------------------------------------------------------------

def test_fresh_cookies_file_returns_true(tmp_path):
    f = tmp_path / "cookies.json"
    f.write_text("[]")
    assert _cookies_are_fresh(f) is True


def test_missing_cookies_file_returns_false(tmp_path):
    assert _cookies_are_fresh(tmp_path / "no_cookies.json") is False


def test_stale_cookies_file_returns_false(tmp_path):
    f = tmp_path / "cookies.json"
    f.write_text("[]")
    old_ts = (datetime.now() - timedelta(days=31)).timestamp()
    os.utime(f, (old_ts, old_ts))
    assert _cookies_are_fresh(f) is False


def test_cookies_exactly_30_days_old_returns_false(tmp_path):
    f = tmp_path / "cookies.json"
    f.write_text("[]")
    old_ts = (datetime.now() - timedelta(days=30)).timestamp()
    os.utime(f, (old_ts, old_ts))
    assert _cookies_are_fresh(f) is False


def test_cookies_29_days_old_returns_true(tmp_path):
    f = tmp_path / "cookies.json"
    f.write_text("[]")
    old_ts = (datetime.now() - timedelta(days=29)).timestamp()
    os.utime(f, (old_ts, old_ts))
    assert _cookies_are_fresh(f) is True


def test_custom_max_age_respected(tmp_path):
    f = tmp_path / "cookies.json"
    f.write_text("[]")
    old_ts = (datetime.now() - timedelta(days=8)).timestamp()
    os.utime(f, (old_ts, old_ts))
    assert _cookies_are_fresh(f, max_age_days=7) is False
    assert _cookies_are_fresh(f, max_age_days=9) is True


# ---------------------------------------------------------------------------
# GET /api/settings — linkedin_session_expires field
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_session_expires_present_when_fresh(tmp_path):
    settings = Settings(data_dir=tmp_path)
    cookies = tmp_path / "linkedin_cookies.json"
    cookies.write_text("[]")  # mtime = now → fresh

    with patch("api.routes.settings.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/settings")

    assert resp.status_code == 200
    body = resp.json()
    assert body["linkedin_session_expires"] is not None
    expires = datetime.fromisoformat(body["linkedin_session_expires"])
    days_remaining = (expires - datetime.now()).days
    assert 28 <= days_remaining <= 30


@pytest.mark.asyncio
async def test_settings_session_expires_none_when_no_cookies(tmp_path):
    settings = Settings(data_dir=tmp_path)
    # No cookies file created

    with patch("api.routes.settings.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/settings")

    assert resp.status_code == 200
    assert resp.json()["linkedin_session_expires"] is None


@pytest.mark.asyncio
async def test_settings_session_expires_none_when_stale(tmp_path):
    settings = Settings(data_dir=tmp_path)
    cookies = tmp_path / "linkedin_cookies.json"
    cookies.write_text("[]")
    old_ts = (datetime.now() - timedelta(days=31)).timestamp()
    os.utime(cookies, (old_ts, old_ts))

    with patch("api.routes.settings.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/settings")

    assert resp.status_code == 200
    assert resp.json()["linkedin_session_expires"] is None
