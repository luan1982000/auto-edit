"""Validation and storage helpers for videos uploaded from the local machine."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from app.services.ffmpeg_utils import FFmpegError, run_ffmpeg

MAX_UPLOAD_BYTES = 2 * 1024**3
UPLOAD_CHUNK_BYTES = 1024 * 1024
ALLOWED_VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpeg", ".mpg", ".wmv", ".flv"}
)
SUPPORTED_EXTENSIONS_LABEL = "MP4, MOV, M4V, MKV, WEBM, AVI, MPEG, MPG, WMV, FLV"


class UploadError(ValueError):
    """Raised when an uploaded file is missing, unsupported, or too large."""


def upload_size_label(max_bytes: int) -> str:
    """Human-readable limit used in API errors and the UI."""
    for unit, factor in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if max_bytes >= factor:
            return f"{max_bytes / factor:g} {unit}"
    return f"{max_bytes} bytes"


def sanitize_upload_name(filename: str | None) -> str:
    """Take only the basename and reject unsafe or unsupported file types."""
    raw = (filename or "").replace("\x00", "").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1].strip()
    if not name:
        raise UploadError("File tải lên không có tên")

    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise UploadError(f"Chỉ hỗ trợ video {SUPPORTED_EXTENSIONS_LABEL}")

    stem = Path(name).stem.strip()[:200]
    return f"{stem or 'video'}{suffix}"


def upload_title(filename: str) -> str:
    """Derive a display title from a sanitized upload filename."""
    title = " ".join(Path(filename).stem.split())
    return title[:200] or "Video tải lên"


def save_upload(stream: BinaryIO, target: Path, max_bytes: int) -> int:
    """Stream an upload to disk while enforcing the byte limit."""
    total = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as output:
        while True:
            chunk = stream.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise UploadError(
                    f"Video quá lớn — tối đa {upload_size_label(max_bytes)}"
                )
            output.write(chunk)
    if total == 0:
        raise UploadError("File video rỗng")
    return total


def convert_to_mp4(source: Path, target: Path) -> Path:
    """Remux an upload to MP4, falling back to an H.264/AAC transcode."""
    if source.suffix.lower() == ".mp4":
        if source != target:
            source.replace(target)
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    base = ["ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a?"]
    try:
        run_ffmpeg(
            [
                *base,
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(target),
            ],
            timeout=1800,
        )
    except FFmpegError:
        target.unlink(missing_ok=True)
        try:
            run_ffmpeg(
                [
                    *base,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    str(target),
                ],
                timeout=1800,
            )
        except FFmpegError as exc:
            raise UploadError(f"Không chuyển được video sang MP4: {exc}") from exc

    if not target.is_file() or target.stat().st_size == 0:
        raise UploadError("Không chuyển được video sang MP4: file đầu ra rỗng")
    source.unlink(missing_ok=True)
    return target


def remove_upload_dir(videos_dir: Path, video_dir: Path) -> None:
    """Remove only a direct child of videos_dir; never touch user data elsewhere."""
    root = videos_dir.resolve()
    resolved = video_dir.resolve()
    if resolved != root and resolved.is_relative_to(root):
        shutil.rmtree(resolved, ignore_errors=True)
