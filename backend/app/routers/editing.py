"""Post-download editing endpoints: render (and later transcribe/subtitle/TTS)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from app.config import AppConfig
from app.db import get_session
from app.ids import new_id
from app.models import Job
from app.routers.common import (
    ensure_no_active_job,
    get_config,
    get_video,
    safe_source,
)
from app.schemas import JobRead, RenderRequest
from app.services.assets import resolve_logo
from app.settings_store import get_or_create_settings

router = APIRouter(prefix="/api", tags=["editing"])


@router.post("/videos/{video_id}/render", response_model=JobRead, status_code=202)
def start_render(
    video_id: str,
    payload: RenderRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> Job:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    if video.status != "ready":
        raise HTTPException(status_code=409, detail="Video chưa sẵn sàng để render")

    video_dir = (config.videos_dir / video.id).resolve()
    safe_source(video_dir, video.file_path)

    settings = get_or_create_settings(session)
    if payload.logo and resolve_logo(config, settings.logo_path) is None:
        raise HTTPException(
            status_code=400,
            detail="Chưa upload logo — vào Cài đặt để thêm logo trước",
        )
    if payload.subtitle and not video.has_subtitle:
        raise HTTPException(status_code=400, detail="Video chưa có phụ đề")
    if payload.voice and not video.has_voice:
        raise HTTPException(status_code=400, detail="Video chưa có giọng đọc")

    ensure_no_active_job(session, video.id, "render")

    job = Job(
        id=new_id(),
        video_id=video.id,
        type="render",
        params=payload.model_dump(),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
