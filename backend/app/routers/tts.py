"""Voice-over endpoints: preview one sentence and start a TTS job."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.config import AppConfig
from app.db import get_session
from app.ids import new_id
from app.models import Job, Video
from app.routers.common import (
    ensure_no_active_job,
    get_config,
    get_video,
    safe_source,
)
from app.schemas import JobRead, TtsPreviewRequest, TtsRequest
from app.services.subtitles import SubtitleError, load_subtitle_data
from app.services.tts import (
    EdgeTTSEngine,
    TTSError,
    validate_rate,
    validate_voice,
)
from app.settings_store import get_or_create_settings

router = APIRouter(prefix="/api", tags=["tts"])


def _require_subtitles(config: AppConfig, video: Video) -> None:
    try:
        data = load_subtitle_data(config.videos_dir / video.id / "subtitle.json")
    except SubtitleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if data is None or not any(segment.text.strip() for segment in data.segments):
        raise HTTPException(
            status_code=400, detail="Video chưa có phụ đề để tạo giọng đọc"
        )


@router.post("/videos/{video_id}/tts", response_model=JobRead, status_code=202)
def start_tts(
    video_id: str,
    request: Request,
    payload: TtsRequest | None = None,
    session: Session = Depends(get_session),
) -> Job:
    config = get_config(request)
    video = get_video(session, video_id)
    if video.status != "ready":
        raise HTTPException(status_code=409, detail="Video chưa sẵn sàng để xử lý")
    video_dir = (config.videos_dir / video.id).resolve()
    safe_source(video_dir, video.file_path)
    _require_subtitles(config, video)
    ensure_no_active_job(session, video.id, "tts")

    settings = get_or_create_settings(session)
    try:
        voice = validate_voice(
            (payload.voice if payload else None) or settings.tts_voice
        )
        rate = validate_rate((payload.rate if payload else None) or settings.tts_rate)
    except TTSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = Job(
        id=new_id(),
        video_id=video.id,
        type="tts",
        params={"voice": voice, "rate": rate},
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@router.post("/tts/preview")
def preview_tts(payload: TtsPreviewRequest, request: Request) -> FileResponse:
    config = get_config(request)
    output = config.assets_dir / "tts_preview.mp3"
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        EdgeTTSEngine().synthesize(payload.text, payload.voice, payload.rate, output)
    except TTSError as exc:
        output.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return FileResponse(
        output,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )
