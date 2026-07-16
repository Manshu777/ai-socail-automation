"""
Web UI for AI Social Media Automation (Render / cloud friendly).

CustomTkinter needs a desktop display. Render has none — use this FastAPI app instead.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from config import INDUSTRIES, LANGUAGES, PLATFORMS, TONES, config
from database import db
from generator import GenerationRequest, generator
from image_generator import image_generator
from scheduler import post_scheduler
from utils import (
    export_json,
    export_markdown,
    export_txt,
    get_logger,
    quality_report,
    safe_json_dumps,
)

logger = get_logger("web")

ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AI Social Media Automation", version="1.0.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _read_asset(name: str) -> str:
    path = STATIC_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Missing static asset: %s", path)
    return ""


@app.get("/assets/style.css")
async def asset_css() -> FileResponse:
    path = STATIC_DIR / "style.css"
    if not path.exists():
        raise HTTPException(status_code=404, detail="style.css missing")
    return FileResponse(path, media_type="text/css")


@app.get("/assets/app.js")
async def asset_js() -> FileResponse:
    path = STATIC_DIR / "app.js"
    if not path.exists():
        raise HTTPException(status_code=404, detail="app.js missing")
    return FileResponse(path, media_type="application/javascript")


# In-memory last generation for the session-less demo UI
_last_payload: dict[str, Any] | None = None
_last_quality: dict[str, Any] | None = None
_last_post_id: int | None = None


@app.on_event("startup")
def _startup() -> None:
    post_scheduler.start()
    logger.info(
        "Web app started | static=%s exists=%s files=%s",
        STATIC_DIR,
        STATIC_DIR.exists(),
        list(STATIC_DIR.glob("*")) if STATIC_DIR.exists() else [],
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    stats = db.stats()
    # Embed CSS/JS so Render works even if /static mount 404s
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "stats": stats,
            "industries": INDUSTRIES,
            "tones": TONES,
            "languages": LANGUAGES,
            "platforms": PLATFORMS,
            "has_openai": bool(config.openai_api_key),
            "payload": _last_payload,
            "quality": _last_quality,
            "post_id": _last_post_id,
            "payload_json": safe_json_dumps(_last_payload) if _last_payload else "",
            "css": _read_asset("style.css"),
            "js": _read_asset("app.js"),
        },
    )


def _as_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@app.post("/api/generate")
async def api_generate(
    topic: str = Form(...),
    industry: str = Form("Technology"),
    tone: str = Form("Professional"),
    language: str = Form("English"),
    word_count: int = Form(180),
    tone_mode: str = Form("Professional"),
    emoji_enabled: str = Form("false"),
    auto_image: str = Form("true"),
    platforms: list[str] = Form(default=PLATFORMS),
) -> JSONResponse:
    global _last_payload, _last_quality, _last_post_id

    topic = (topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required.")

    if isinstance(platforms, str):
        platforms = [platforms]
    if not platforms:
        platforms = list(PLATFORMS)

    emoji_on = _as_bool(emoji_enabled, False)
    image_on = _as_bool(auto_image, True)

    request = GenerationRequest(
        topic=topic,
        industry=industry,
        tone=tone,
        language=language,
        platforms=platforms,
        word_count=word_count,
        emoji_enabled=emoji_on,
        tone_mode=tone_mode,
    )

    try:
        result = generator.generate(request)
        payload = result.payload

        if image_on:
            img = image_generator.generate(
                payload.get("image_prompt", ""),
                topic=payload.get("topic", topic),
            )
            payload["image_path"] = str(img.path)
            payload["image_provider"] = img.provider
            payload["image_url"] = f"/api/image/{img.path.name}"

        post_id = db.save_post(
            payload,
            industry=industry,
            tone=tone,
            language=language,
            platforms=platforms,
        )
        _last_payload = payload
        _last_quality = result.quality
        _last_post_id = post_id

        return JSONResponse(
            {
                "ok": True,
                "provider": result.provider,
                "post_id": post_id,
                "payload": payload,
                "quality": result.quality,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Generate failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/image")
async def api_image() -> JSONResponse:
    global _last_payload
    if not _last_payload:
        raise HTTPException(status_code=400, detail="Generate a post first.")
    try:
        img = image_generator.generate(
            _last_payload.get("image_prompt", ""),
            topic=_last_payload.get("topic", ""),
        )
        _last_payload["image_path"] = str(img.path)
        _last_payload["image_provider"] = img.provider
        _last_payload["image_url"] = f"/api/image/{img.path.name}"
        if _last_post_id:
            db.save_post(_last_payload, post_id=_last_post_id)
        return JSONResponse(
            {
                "ok": True,
                "provider": img.provider,
                "image_url": _last_payload["image_url"],
                "path": str(img.path),
            }
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/image/{filename}")
async def serve_image(filename: str) -> FileResponse:
    path = ROOT / "posts" / "images" / filename
    if not path.exists() or ".." in filename:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


@app.get("/api/history")
async def api_history(q: str = Query("")) -> JSONResponse:
    posts = db.list_posts(query=q, limit=50)
    return JSONResponse(
        {
            "ok": True,
            "posts": [
                {
                    "id": p.id,
                    "topic": p.topic,
                    "title": p.title,
                    "created_at": p.created_at,
                    "summary": p.summary,
                }
                for p in posts
            ],
        }
    )


@app.get("/api/history/{post_id}")
async def api_history_one(post_id: int) -> JSONResponse:
    global _last_payload, _last_quality, _last_post_id
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    payload = post.payload
    if payload.get("image_path"):
        name = Path(str(payload["image_path"])).name
        payload["image_url"] = f"/api/image/{name}"
    _last_payload = payload
    _last_quality = quality_report(payload)
    _last_post_id = post.id
    return JSONResponse(
        {"ok": True, "post_id": post.id, "payload": payload, "quality": _last_quality}
    )


@app.delete("/api/history/{post_id}")
async def api_delete(post_id: int) -> JSONResponse:
    db.delete_post(post_id)
    return JSONResponse({"ok": True})


@app.post("/api/schedule")
async def api_schedule(
    post_id: int = Form(...),
    platform: str = Form("LinkedIn"),
    date: str = Form(...),
    time: str = Form(...),
    notes: str = Form(""),
) -> JSONResponse:
    try:
        when = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        sid = post_scheduler.schedule_post(post_id, platform, when, notes=notes)
        return JSONResponse({"ok": True, "schedule_id": sid})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/schedules")
async def api_schedules() -> JSONResponse:
    rows = db.list_schedules()
    return JSONResponse(
        {
            "ok": True,
            "schedules": [
                {
                    "id": r.id,
                    "post_id": r.post_id,
                    "platform": r.platform,
                    "scheduled_at": r.scheduled_at,
                    "status": r.status,
                    "notes": r.notes,
                }
                for r in rows
            ],
        }
    )


@app.get("/api/export/{fmt}")
async def api_export(fmt: str) -> FileResponse:
    if not _last_payload:
        raise HTTPException(status_code=400, detail="Nothing to export")
    if fmt == "json":
        path = export_json(_last_payload)
    elif fmt == "md":
        path = export_markdown(_last_payload)
    elif fmt == "txt":
        path = export_txt(_last_payload)
    else:
        raise HTTPException(status_code=400, detail="Use json, md, or txt")
    return FileResponse(path, filename=path.name)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "openai": bool(config.openai_api_key),
        "mode": "web",
        "stats": db.stats(),
    }


def run_web(host: str = "0.0.0.0", port: int | None = None) -> None:
    """Start uvicorn server (used by app.py on Render / cloud)."""
    import uvicorn

    port = port or int(os.getenv("PORT", "8000"))
    logger.info("Starting web server on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
