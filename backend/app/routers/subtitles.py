"""Subtitle endpoints: transcription, translation, reading and editing."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
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
from app.schemas import (
    JobRead,
    SubtitleRead,
    SubtitleSegmentIn,
    SubtitleUpdate,
    TranscribeRequest,
    TranslateRequest,
)
from app.services.subtitles import (
    SubtitleData,
    SubtitleError,
    SubtitleSegment,
    load_subtitle_data,
    save_subtitle_data,
    write_srt,
)
from app.settings_store import get_or_create_settings

router = APIRouter(prefix="/api", tags=["subtitles"])


def _subtitle_path(config: AppConfig, video: Video) -> Path:
    return config.videos_dir / video.id / "subtitle.json"


def _load_existing(config: AppConfig, video: Video) -> SubtitleData:
    try:
        data = load_subtitle_data(_subtitle_path(config, video))
    except SubtitleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Video chưa có phụ đề")
    return data


def _to_read(data: SubtitleData) -> SubtitleRead:
    return SubtitleRead(
        language=data.language,
        target_language=data.target_language,
        translated=data.translated,
        segments=[
            SubtitleSegmentIn(start=segment.start, end=segment.end, text=segment.text)
            for segment in data.segments
        ],
    )


def _ensure_ready(video: Video) -> None:
    if video.status != "ready":
        raise HTTPException(status_code=409, detail="Video chưa sẵn sàng để xử lý")


def _ensure_no_subtitle_job(session: Session, video_id: str) -> None:
    ensure_no_active_job(session, video_id, "transcribe")
    ensure_no_active_job(session, video_id, "translate")


@router.post(
    "/videos/{video_id}/transcribe", response_model=JobRead, status_code=202
)
def start_transcribe(
    video_id: str,
    request: Request,
    payload: TranscribeRequest | None = None,
    session: Session = Depends(get_session),
) -> Job:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    _ensure_ready(video)
    safe_source((config.videos_dir / video.id).resolve(), video.file_path)
    _ensure_no_subtitle_job(session, video.id)

    settings = get_or_create_settings(session)
    job = Job(
        id=new_id(),
        video_id=video.id,
        type="transcribe",
        params={
            "translate": bool(payload.translate) if payload else False,
            "model": settings.whisper_model,
            "target_language": settings.target_language,
        },
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@router.post("/videos/{video_id}/translate", response_model=JobRead, status_code=202)
def start_translate(
    video_id: str,
    request: Request,
    payload: TranslateRequest | None = None,
    session: Session = Depends(get_session),
) -> Job:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    _ensure_ready(video)
    _load_existing(config, video)
    _ensure_no_subtitle_job(session, video.id)

    settings = get_or_create_settings(session)
    target = (payload.target_language if payload else None) or settings.target_language
    job = Job(
        id=new_id(),
        video_id=video.id,
        type="translate",
        params={"target_language": target},
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@router.get("/videos/{video_id}/subtitle", response_model=SubtitleRead)
def get_subtitle(
    video_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> SubtitleRead:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    return _to_read(_load_existing(config, video))


@router.put("/videos/{video_id}/subtitle", response_model=SubtitleRead)
def update_subtitle(
    video_id: str,
    payload: SubtitleUpdate,
    request: Request,
    session: Session = Depends(get_session),
) -> SubtitleRead:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    existing = _load_existing(config, video)
    _ensure_no_subtitle_job(session, video.id)

    segments = [
        SubtitleSegment(start=item.start, end=item.end, text=item.text)
        for item in payload.segments
    ]
    source_segments = (
        existing.source_segments if existing.translated else list(segments)
    )
    data = SubtitleData(
        language=existing.language,
        target_language=existing.target_language,
        translated=existing.translated,
        segments=segments,
        source_segments=source_segments or segments,
    )
    video_dir = config.videos_dir / video.id
    try:
        save_subtitle_data(video_dir / "subtitle.json", data)
        write_srt(video_dir / "subtitle.srt", segments)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Không lưu được phụ đề: {exc}"
        ) from exc

    video.has_subtitle = bool(segments)
    session.add(video)
    session.commit()
    return _to_read(data)
