"""Tests for api/routes/settings.py"""
import pytest
import httpx
from unittest.mock import patch, MagicMock
from pathlib import Path

import anthropic

from api.server import app
from core.config import Settings


def make_settings(tmp_path: Path, api_key: str = "") -> Settings:
    return Settings(anthropic_api_key=api_key, scrape_limit=20, data_dir=tmp_path)


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_settings_returns_masked_key(tmp_path):
    settings = make_settings(tmp_path, api_key="sk-ant-my-secret-key-abcd")

    with patch("api.routes.settings.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/settings")

    assert resp.status_code == 200
    body = resp.json()
    assert body["anthropic_api_key"] == "...abcd"
    assert body["scrape_limit"] == 20
    assert body["ai_feedback_enabled"] is False


@pytest.mark.asyncio
async def test_get_settings_empty_key_returns_empty_string(tmp_path):
    settings = make_settings(tmp_path, api_key="")

    with patch("api.routes.settings.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/settings")

    assert resp.status_code == 200
    assert resp.json()["anthropic_api_key"] == ""


@pytest.mark.asyncio
async def test_get_settings_short_key_masked(tmp_path):
    settings = make_settings(tmp_path, api_key="ab")

    with patch("api.routes.settings.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/settings")

    assert resp.status_code == 200
    assert resp.json()["anthropic_api_key"] == "***"


# ---------------------------------------------------------------------------
# POST /api/settings — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_settings_saves_valid_key(tmp_path):
    settings = make_settings(tmp_path)
    mock_client = MagicMock()
    mock_client.models.list.return_value = []

    with patch("api.routes.settings.load", return_value=settings), \
         patch("api.routes.settings.save") as mock_save, \
         patch("api.routes.settings.anthropic.Anthropic", return_value=mock_client):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/settings",
                json={"anthropic_api_key": "sk-ant-valid-key-1234"},
            )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_post_settings_updates_scrape_limit(tmp_path):
    settings = make_settings(tmp_path, api_key="existing-key")

    with patch("api.routes.settings.load", return_value=settings), \
         patch("api.routes.settings.save") as mock_save:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/settings", json={"scrape_limit": 50})

    assert resp.status_code == 200
    saved_settings = mock_save.call_args[0][0]
    assert saved_settings.scrape_limit == 50


@pytest.mark.asyncio
async def test_post_settings_toggles_ai_feedback(tmp_path):
    settings = make_settings(tmp_path, api_key="sk-key")

    with patch("api.routes.settings.load", return_value=settings), \
         patch("api.routes.settings.save") as mock_save:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/settings", json={"ai_feedback_enabled": False})

    assert resp.status_code == 200
    saved_settings = mock_save.call_args[0][0]
    assert saved_settings.ai_feedback_enabled is False


@pytest.mark.asyncio
async def test_post_settings_clears_api_key(tmp_path):
    settings = make_settings(tmp_path, api_key="old-key")

    with patch("api.routes.settings.load", return_value=settings), \
         patch("api.routes.settings.save") as mock_save:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/settings", json={"anthropic_api_key": ""})

    assert resp.status_code == 200
    saved_settings = mock_save.call_args[0][0]
    assert saved_settings.anthropic_api_key == ""


# ---------------------------------------------------------------------------
# POST /api/settings — invalid API key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_settings_returns_400_for_invalid_key(tmp_path):
    settings = make_settings(tmp_path)
    mock_client = MagicMock()
    mock_client.models.list.side_effect = anthropic.AuthenticationError(
        message="Invalid key", response=MagicMock(status_code=401), body={}
    )

    with patch("api.routes.settings.load", return_value=settings), \
         patch("api.routes.settings.anthropic.Anthropic", return_value=mock_client):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/settings",
                json={"anthropic_api_key": "sk-ant-bad-key"},
            )

    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_post_settings_returns_400_for_scrape_limit_zero(tmp_path):
    settings = make_settings(tmp_path)

    with patch("api.routes.settings.load", return_value=settings), \
         patch("api.routes.settings.save"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/settings", json={"scrape_limit": 0})

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/settings — malformed body
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_settings_returns_422_for_malformed_body(tmp_path):
    settings = make_settings(tmp_path)

    with patch("api.routes.settings.load", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/settings",
                content="not-json",
                headers={"Content-Type": "application/json"},
            )

    assert resp.status_code == 422
