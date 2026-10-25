"""Subtitle endpoints: transcription, translation, reading and editing."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
from app.schemas import (
    CoverRegionPayload,
    CoverRegionRead,
    JobRead,
    SampleFrameRead,
    SampleFramesRead,
    SubtitleRead,
    SubtitleSegmentIn,
    SubtitleUpdate,
    TranscribeRequest,
    TranslateRequest,
)
from app.services.cover import (
    CoverRegion,
    CoverRegionError,
    load_cover_region,
    save_cover_region,
)
from app.services.ffmpeg_utils import FFmpegError, extract_sample_frames, probe_video
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
SAMPLE_FRAME_NAME = re.compile(r"\Asample-[1-9][0-9]*\.jpg\Z")


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


def _video_dir(config: AppConfig, video: Video) -> Path:
    return (config.videos_dir / video.id).resolve()


def _cover_read(region: CoverRegion | None) -> CoverRegionRead | None:
    return CoverRegionRead.model_validate(region) if region is not None else None


@router.post(
    "/videos/{video_id}/sample-frames", response_model=SampleFramesRead
)
def create_sample_frames(
    video_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> SampleFramesRead:
    """Capture a few frames and return the saved cover-region selection."""
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    _ensure_ready(video)
    video_dir = _video_dir(config, video)
    source = safe_source(video_dir, video.file_path)

    duration = float(video.duration_sec)
    if duration <= 0:
        try:
            duration = float(probe_video(source)["duration_sec"])
        except FFmpegError as exc:
            raise HTTPException(
                status_code=500, detail=f"Không đọc được video: {exc}"
            ) from exc
    try:
        frames = extract_sample_frames(
            source, video_dir / "frames", duration_sec=duration
        )
    except FFmpegError as exc:
        raise HTTPException(
            status_code=500, detail=f"Không chụp được ảnh mẫu: {exc}"
        ) from exc
    try:
        region = load_cover_region(video_dir)
    except CoverRegionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SampleFramesRead(
        frames=[
            SampleFrameRead(
                time=round(at_sec, 3),
                url=f"/api/videos/{video.id}/frames/{path.name}",
            )
            for at_sec, path in frames
        ],
        region=_cover_read(region),
    )


@router.get("/videos/{video_id}/frames/{name}")
def get_sample_frame(
    video_id: str,
    name: str,
    request: Request,
    session: Session = Depends(get_session),
) -> FileResponse:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    if not SAMPLE_FRAME_NAME.fullmatch(name):
        raise HTTPException(status_code=404, detail="Ảnh mẫu không tồn tại")
    video_dir = _video_dir(config, video)
    path = (video_dir / "frames" / name).resolve()
    if not path.is_relative_to(video_dir) or not path.is_file():
        raise HTTPException(status_code=404, detail="Ảnh mẫu không tồn tại")
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "no-store"}
    )


@router.get(
    "/videos/{video_id}/cover-region", response_model=CoverRegionRead | None
)
def get_cover_region(
    video_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> CoverRegionRead | None:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    try:
        region = load_cover_region(_video_dir(config, video))
    except CoverRegionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _cover_read(region)


@router.put("/videos/{video_id}/cover-region", response_model=CoverRegionRead)
def update_cover_region(
    video_id: str,
    payload: CoverRegionPayload,
    request: Request,
    session: Session = Depends(get_session),
) -> CoverRegionRead:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    region = CoverRegion(
        x=payload.x,
        y=payload.y,
        width=payload.width,
        height=payload.height,
    )
    try:
        save_cover_region(_video_dir(config, video), region)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Không lưu được vùng che: {exc}"
        ) from exc
    return CoverRegionRead.model_validate(region)


@router.delete("/videos/{video_id}/cover-region", status_code=204)
def delete_cover_region(
    video_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    config: AppConfig = get_config(request)
    video = get_video(session, video_id)
    try:
        save_cover_region(_video_dir(config, video), None)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Không xoá được vùng che: {exc}"
        ) from exc
    return Response(status_code=204)


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
            "source_language": payload.source_language if payload else None,
            "target_language": (
                payload.target_language if payload and payload.target_language else None
            )
            or settings.target_language,
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
