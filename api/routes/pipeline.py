"""
Pipeline routes: start a run and stream its events via SSE.
Only one pipeline run is active at a time.
"""
import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.config import load
from core.pipeline import run as pipeline_run

router = APIRouter()

# module-level state — one active run at a time
_active: dict[str, asyncio.Queue] = {}


@router.post("/api/pipeline/start")
async def start_pipeline():
    if _active:
        raise HTTPException(status_code=409, detail="A pipeline run is already in progress.")

    run_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _active[run_id] = queue

    settings = load()

    async def _run_and_cleanup():
        try:
            await pipeline_run(settings, queue)
        finally:
            _active.pop(run_id, None)

    asyncio.create_task(_run_and_cleanup())
    return {"run_id": run_id}


@router.get("/api/pipeline/stream/{run_id}")
async def stream_pipeline(run_id: str):
    if run_id not in _active:
        raise HTTPException(status_code=404, detail="Unknown run_id.")

    queue = _active[run_id]

    async def event_generator():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("phase") in ("complete", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")
