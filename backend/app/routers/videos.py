"""Video download, listing, streaming and file-management endpoints."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.config import AppConfig
from app.db import get_session
from app.ids import new_id
from app.models import Job, Video, utcnow
from app.routers.common import get_config as _config
from app.routers.common import get_video as _get_video
from app.schemas import DownloadRequest, DownloadResponse, DuplicateInfo, VideoRead
from app.services.ffmpeg_utils import FFmpegError, make_thumbnail, probe_video
from app.services.uploads import (
    MAX_UPLOAD_BYTES,
    UploadError,
    convert_to_mp4,
    remove_upload_dir,
    sanitize_upload_name,
    save_upload,
    upload_size_label,
    upload_title,
)
from app.services.urls import detect_platform

router = APIRouter(prefix="/api", tags=["videos"])


def _safe_video_path(video: Video, config: AppConfig, path: Path) -> Path:
    """Reject any stored path that escapes DATA_DIR/videos/{id}."""
    video_dir = (config.videos_dir / video.id).resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(video_dir):
        raise HTTPException(status_code=400, detail="Đường dẫn file không hợp lệ")
    return resolved


@router.post("/upload", response_model=VideoRead, status_code=201)
def upload_video(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Video:
    """Store a local video, normalise it to MP4, and add it to the library."""
    config = _config(request)
    try:
        original_name = sanitize_upload_name(file.filename)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    declared_size = getattr(file, "size", None)
    if isinstance(declared_size, int) and declared_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Video quá lớn — tối đa {upload_size_label(MAX_UPLOAD_BYTES)}",
        )

    video_id = new_id()
    video_dir = config.videos_dir / video_id
    extension = Path(original_name).suffix.lower()
    upload_path = video_dir / f"upload{extension}"
    target = video_dir / "original.mp4"
    thumb_path = video_dir / "thumb.jpg"
    title = upload_title(original_name)

    try:
        video_dir.mkdir(parents=True, exist_ok=False)
        save_upload(file.file, upload_path, MAX_UPLOAD_BYTES)
        convert_to_mp4(upload_path, target)

        probed = probe_video(target)
        duration = float(probed["duration_sec"])
        if duration <= 0:
            raise UploadError("Video tải lên không có thời lượng hợp lệ")

        try:
            make_thumbnail(
                target, thumb_path, at_sec=min(1.0, max(duration / 2, 0.1))
            )
            stored_thumb: Path | None = thumb_path
        except FFmpegError:
            stored_thumb = None

        meta = {
            "source": "upload",
            "original_name": original_name,
            "title": title,
            "duration_sec": duration,
            "width": int(probed["width"]),
            "height": int(probed["height"]),
            "has_audio": bool(probed["has_audio"]),
            "uploaded_at": utcnow().isoformat(),
        }
        (video_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        video = Video(
            id=video_id,
            source_url="",
            platform="upload",
            title=title,
            duration_sec=round(duration, 3),
            width=int(probed["width"]),
            height=int(probed["height"]),
            dir_path=str(video_dir),
            file_path=str(target),
            thumb_path=str(stored_thumb) if stored_thumb else "",
            status="ready",
            error=None,
        )
        session.add(video)
        session.commit()
        session.refresh(video)
        return video
    except HTTPException:
        remove_upload_dir(config.videos_dir, video_dir)
        raise
    except UploadError as exc:
        remove_upload_dir(config.videos_dir, video_dir)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FFmpegError as exc:
        remove_upload_dir(config.videos_dir, video_dir)
        raise HTTPException(
            status_code=400, detail=f"Không xử lý được video tải lên: {exc}"
        ) from exc
    except OSError as exc:
        remove_upload_dir(config.videos_dir, video_dir)
        raise HTTPException(
            status_code=500, detail=f"Không lưu được video tải lên: {exc}"
        ) from exc
    except Exception:
        remove_upload_dir(config.videos_dir, video_dir)
        raise


@router.post("/download", response_model=DownloadResponse)
def create_download(
    payload: DownloadRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> DownloadResponse:
    config = _config(request)
    jobs: list[Job] = []
    duplicates: list[DuplicateInfo] = []

    for url in payload.urls:
        existing = session.exec(
            select(Video).where(Video.source_url == url).order_by(Video.created_at.desc())
        ).first()
        if existing is not None and not payload.force:
            duplicates.append(
                DuplicateInfo(
                    url=url,
                    video_id=existing.id,
                    title=existing.title,
                    status=existing.status,
                )
            )
            continue

        video_id = new_id()
        video_dir = config.videos_dir / video_id
        video = Video(
            id=video_id,
            source_url=url,
            platform=detect_platform(url),
            dir_path=str(video_dir),
            file_path=str(video_dir / "original.mp4"),
            thumb_path=str(video_dir / "thumb.jpg"),
            status="downloading",
        )
        job = Job(
            id=new_id(),
            video_id=video_id,
            type="download",
            params={"url": url},
        )
        session.add(video)
        session.add(job)
        session.commit()
        session.refresh(job)
        jobs.append(job)

    return DownloadResponse(jobs=jobs, duplicates=duplicates)


@router.get("/videos", response_model=list[VideoRead])
def list_videos(session: Session = Depends(get_session)) -> list[Video]:
    return list(session.exec(select(Video).order_by(Video.created_at.desc())).all())


@router.get("/videos/{video_id}", response_model=VideoRead)
def get_video(video_id: str, session: Session = Depends(get_session)) -> Video:
    return _get_video(session, video_id)


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(
    video_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    config = _config(request)
    video = _get_video(session, video_id)

    video_dir = (config.videos_dir / video.id).resolve()
    if not video_dir.is_relative_to(config.videos_dir.resolve()):
        raise HTTPException(status_code=400, detail="Đường dẫn thư mục không hợp lệ")
    shutil.rmtree(video_dir, ignore_errors=True)

    for job in session.exec(select(Job).where(Job.video_id == video.id)).all():
        session.delete(job)
    session.delete(video)
    session.commit()
    return Response(status_code=204)


@router.get("/videos/{video_id}/file")
def stream_video(
    video_id: str,
    request: Request,
    variant: Literal["original", "output"] = Query("original"),
    session: Session = Depends(get_session),
) -> FileResponse:
    config = _config(request)
    video = _get_video(session, video_id)
    if variant == "original":
        path = Path(video.file_path)
    else:
        path = Path(video.dir_path) / "output_final.mp4"

    path = _safe_video_path(video, config, path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Chưa có file {variant}")
    return FileResponse(path, media_type="video/mp4", content_disposition_type="inline")


@router.get("/videos/{video_id}/thumb")
def get_thumb(
    video_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> FileResponse:
    config = _config(request)
    video = _get_video(session, video_id)
    if not video.thumb_path:
        raise HTTPException(status_code=404, detail="Chưa có thumbnail")
    path = _safe_video_path(video, config, Path(video.thumb_path))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Chưa có thumbnail")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/videos/{video_id}/open-folder")
def open_folder(
    video_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, str | bool]:
    config = _config(request)
    video = _get_video(session, video_id)
    path = _safe_video_path(video, config, Path(video.dir_path))
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="Thư mục video không tồn tại")

    system = platform.system()
    if system == "Darwin":
        command = ["open", str(path)]
    elif system == "Windows":
        command = ["explorer", str(path)]
    else:
        command = ["xdg-open", str(path)]
    try:
        subprocess.run(command, check=False, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail="Không mở được thư mục") from exc
    return {"opened": True, "path": str(path)}
