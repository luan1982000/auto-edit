"""FastAPI application factory: DB, worker thread, routers, static frontend."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT_DIR, AppConfig
from app.db import get_session_factory, init_db
from app.routers import jobs, settings, system, videos
from app.worker import Worker, default_handlers

logger = logging.getLogger(__name__)

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app(config: AppConfig | None = None, start_worker: bool = True) -> FastAPI:
    app_config = config or AppConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_config.data_dir.mkdir(parents=True, exist_ok=True)
        app_config.videos_dir.mkdir(parents=True, exist_ok=True)
        app_config.assets_dir.mkdir(parents=True, exist_ok=True)

        init_db(app_config.db_path)
        session_factory = get_session_factory()
        app.state.session_factory = session_factory

        tool_status = system.tool_status()
        app.state.tool_status = tool_status
        missing = [name for name in ("ffmpeg", "ffprobe", "yt_dlp") if not tool_status[name]]
        if missing:
            logger.error(
                "Thiếu công cụ bắt buộc: %s. Cài đặt theo README trước khi tải/xử lý video.",
                ", ".join(missing),
            )

        worker: Worker | None = None
        if start_worker:
            worker = Worker(
                session_factory,
                default_handlers(app_config, session_factory),
                poll_interval=app_config.poll_interval_sec,
                default_timeout_sec=app_config.job_timeout_sec,
            )
            worker.start()
        app.state.worker = worker

        try:
            yield
        finally:
            if worker is not None:
                worker.stop()

    app = FastAPI(title="Video Tool", lifespan=lifespan)
    app.state.config = app_config
    app.state.tool_status = {}
    app.state.session_factory = None
    app.state.worker = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(videos.router)
    app.include_router(jobs.router)
    app.include_router(settings.router)
    app.include_router(system.router)

    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        index = FRONTEND_DIST / "index.html"
        if full_path.startswith("api/") or not index.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIST.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)

    return app


app = create_app()
