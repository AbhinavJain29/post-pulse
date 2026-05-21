"""Tests for api/routes/pipeline.py"""
import asyncio
import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from api.server import app
import api.routes.pipeline as pipeline_module


def _make_event(phase="complete", status="complete", message="done"):
    return {"phase": phase, "status": status, "message": message, "count": 0, "total": 0}


async def _fake_run_instant(settings, queue: asyncio.Queue):
    await queue.put(_make_event("complete", "complete", "done"))


async def _fake_run_slow(settings, queue: asyncio.Queue):
    await queue.put(_make_event("scrape", "progress", "scraping..."))
    await asyncio.sleep(0.05)
    await queue.put(_make_event("complete", "complete", "done"))


@pytest.fixture(autouse=True)
def clear_active():
    """Ensure no leftover active runs between tests."""
    pipeline_module._active.clear()
    yield
    pipeline_module._active.clear()


# ---------------------------------------------------------------------------
# POST /api/pipeline/start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_returns_run_id():
    with patch("api.routes.pipeline.pipeline_run", new=_fake_run_instant), \
         patch("api.routes.pipeline.load"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/pipeline/start")

    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    assert len(body["run_id"]) > 0


@pytest.mark.asyncio
async def test_start_returns_409_when_already_running():
    # Pre-seed an active run to simulate one in progress
    pipeline_module._active["existing-run"] = asyncio.Queue()

    with patch("api.routes.pipeline.pipeline_run", new=_fake_run_instant), \
         patch("api.routes.pipeline.load"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/pipeline/start")

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/pipeline/stream/{run_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_returns_404_for_unknown_run_id():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/pipeline/stream/nonexistent-id")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stream_delivers_events():
    queue: asyncio.Queue = asyncio.Queue()
    run_id = "test-run-123"
    pipeline_module._active[run_id] = queue

    # Pre-load events into the queue
    await queue.put(_make_event("scrape", "progress", "scraping..."))
    await queue.put(_make_event("complete", "complete", "done"))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with client.stream("GET", f"/api/pipeline/stream/{run_id}") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            lines = []
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    lines.append(json.loads(line[6:]))

    phases = [e["phase"] for e in lines]
    assert "scrape" in phases
    assert "complete" in phases


@pytest.mark.asyncio
async def test_stream_terminates_on_complete():
    queue: asyncio.Queue = asyncio.Queue()
    run_id = "test-run-complete"
    pipeline_module._active[run_id] = queue

    await queue.put(_make_event("complete", "complete", "done"))

    received = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with client.stream("GET", f"/api/pipeline/stream/{run_id}") as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    received.append(json.loads(line[6:]))

    assert len(received) == 1
    assert received[0]["phase"] == "complete"


@pytest.mark.asyncio
async def test_stream_terminates_on_error():
    queue: asyncio.Queue = asyncio.Queue()
    run_id = "test-run-error"
    pipeline_module._active[run_id] = queue

    await queue.put(_make_event("error", "error", "something went wrong"))

    received = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with client.stream("GET", f"/api/pipeline/stream/{run_id}") as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    received.append(json.loads(line[6:]))

    assert len(received) == 1
    assert received[0]["phase"] == "error"


@pytest.mark.asyncio
async def test_start_then_stream_full_flow():
    """Integration: start creates a run, stream consumes its events."""
    with patch("api.routes.pipeline.pipeline_run", new=_fake_run_slow), \
         patch("api.routes.pipeline.load"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            start_resp = await client.post("/api/pipeline/start")
            assert start_resp.status_code == 200
            run_id = start_resp.json()["run_id"]

            # Small delay so the background task can register in _active
            await asyncio.sleep(0.01)

            received = []
            async with client.stream("GET", f"/api/pipeline/stream/{run_id}") as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        received.append(json.loads(line[6:]))

    phases = [e["phase"] for e in received]
    assert "complete" in phases
