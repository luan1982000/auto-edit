"""Small helpers shared by API routers."""

from pathlib import Path

from fastapi import HTTPException, Request
from sqlmodel import Session, select

from app.config import AppConfig
from app.models import Job, Video


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


def safe_source(video_dir: Path, file_path: str) -> Path:
    """Resolve the original video path and require it to live inside its folder."""
    try:
        source = Path(file_path).resolve()
    except OSError as exc:
        raise HTTPException(
            status_code=409, detail="Đường dẫn video gốc không hợp lệ"
        ) from exc
    if not source.is_relative_to(video_dir) or not source.is_file():
        raise HTTPException(status_code=409, detail="Chưa có file video gốc")
    return source


def get_video(session: Session, video_id: str) -> Video:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video không tồn tại")
    return video


def ensure_no_active_job(session: Session, video_id: str, job_type: str) -> None:
    active = session.exec(
        select(Job).where(
            Job.video_id == video_id,
            Job.type == job_type,
            Job.status.in_(["pending", "running"]),
        )
    ).first()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Đang có job {job_type} chưa xong cho video này",
        )
