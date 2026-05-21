"""
FastAPI application for Post Pulse.
Serves the static UI and mounts API routers.
"""
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import load
from api.routes import pipeline, posts, reset, settings

app = FastAPI(title="Post Pulse")


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


app.add_middleware(NoCacheMiddleware)

app.include_router(pipeline.router)
app.include_router(posts.router)
app.include_router(settings.router)
app.include_router(reset.router)

_ui_dir = Path(__file__).parent.parent / "ui"
if _ui_dir.exists():
    app.mount("/static", StaticFiles(directory=_ui_dir / "static"), name="static")
    app.mount("/ui", StaticFiles(directory=_ui_dir), name="ui")


@app.get("/")
async def index():
    cfg = load()
    if not cfg.anthropic_api_key:
        return RedirectResponse(url="/settings.html")
    return RedirectResponse(url="/index.html")


_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


@app.get("/index.html")
async def dashboard():
    return FileResponse(_ui_dir / "index.html", headers=_NO_CACHE)


@app.get("/settings.html")
async def settings_page():
    return FileResponse(_ui_dir / "settings.html", headers=_NO_CACHE)


@app.get("/post.html")
async def post_page():
    return FileResponse(_ui_dir / "post.html", headers=_NO_CACHE)


@app.get("/landing.html")
async def landing_page():
    return FileResponse(_ui_dir / "landing.html", headers=_NO_CACHE)


@app.get("/go")
async def go_dashboard():
    """Smart redirect: dashboard if LinkedIn session is active, settings otherwise."""
    cfg = load()
    cookies = cfg.cookies_path
    if cookies.exists():
        age_days = (datetime.now() - datetime.fromtimestamp(cookies.stat().st_mtime)).days
        if age_days < 30:
            return RedirectResponse(url="/index.html")
    return RedirectResponse(url="/settings.html")
