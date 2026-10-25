"""yt-dlp wrapper: download a URL into `<video_dir>/original.mp4`."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import yt_dlp

from app.services.ffmpeg_utils import ensure_mp4
from app.services.urls import detect_platform

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]
DeadlineCheck = Callable[[], None]

_PLATFORMS = ("youtube", "facebook", "douyin", "tiktok")


class DownloadError(RuntimeError):
    """Raised with a user-facing message when yt-dlp cannot download a URL."""


@dataclass
class DownloadResult:
    file_path: Path
    title: str
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    platform: str = "other"
    info: dict[str, Any] = field(default_factory=dict)


def human_size(num_bytes: float) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def parse_progress(data: dict[str, Any]) -> tuple[int, str] | None:
    """Translate a yt-dlp progress-hook dict into (percent, message)."""
    status = data.get("status")
    if status == "finished":
        return 100, "Đang xử lý video..."
    if status != "downloading":
        return None

    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    downloaded = data.get("downloaded_bytes") or 0
    percent = int(downloaded * 100 / total) if total else 0
    percent = max(0, min(percent, 99))

    parts = [f"{percent}%"]
    speed = data.get("speed")
    if speed:
        parts.append(f"{human_size(speed)}/s")
    eta = data.get("eta")
    if eta is not None:
        parts.append(f"còn ~{int(eta)}s")
    return percent, " • ".join(parts)


def build_ydl_opts(
    video_dir: Path,
    progress_cb: ProgressCallback | None = None,
    cookies_browser: str = "",
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(video_dir / "original.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "continuedl": True,
        "socket_timeout": 30,
        "retries": 2,
    }
    if progress_cb is not None:
        opts["progress_hooks"] = [lambda data: _on_progress(data, progress_cb)]
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    return opts


def _on_progress(data: dict[str, Any], callback: ProgressCallback) -> None:
    parsed = parse_progress(data)
    if parsed is not None:
        callback(*parsed)


def _platform_from_info(info: dict[str, Any]) -> str:
    raw = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    for platform in _PLATFORMS:
        if platform in raw:
            return platform
    webpage_url = info.get("webpage_url") or info.get("original_url")
    if isinstance(webpage_url, str) and webpage_url.startswith(("http://", "https://")):
        return detect_platform(webpage_url)
    return "other"


def _largest_original_file(video_dir: Path) -> Path | None:
    candidates = [
        path
        for path in video_dir.glob("original.*")
        if path.is_file() and path.suffix not in {".part", ".ytdl"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)


def result_from_info(info: dict[str, Any], video_dir: Path) -> DownloadResult:
    requested = info.get("requested_downloads") or []
    file_path: Path | None = None
    if requested and requested[0].get("filepath"):
        file_path = Path(requested[0]["filepath"])
    if file_path is None:
        file_path = _largest_original_file(video_dir)
    if file_path is None:
        file_path = video_dir / "original.mp4"

    return DownloadResult(
        file_path=file_path,
        title=str(info.get("title") or "").strip(),
        duration_sec=float(info.get("duration") or 0.0),
        width=int(info.get("width") or 0),
        height=int(info.get("height") or 0),
        platform=_platform_from_info(info),
        info=info,
    )


class _CollectingLogger:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        self.errors.append(str(msg))

    @property
    def last_error(self) -> str:
        return self.errors[-1] if self.errors else ""


T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    retries: int = 2,
    backoff_sec: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, DownloadError], None] | None = None,
) -> T:
    """Run `func`, retrying only DownloadError with exponential backoff."""
    attempts = max(0, int(retries)) + 1
    for attempt in range(attempts):
        try:
            return func()
        except DownloadError as exc:
            if attempt + 1 >= attempts:
                raise
            if on_retry is not None:
                on_retry(attempt + 1, exc)
            sleep(backoff_sec * (2**attempt))
    raise AssertionError("unreachable")


def _download_once(
    url: str,
    video_dir: Path,
    progress_cb: ProgressCallback | None,
    cookies_browser: str,
    deadline_check: DeadlineCheck | None,
) -> DownloadResult:
    if deadline_check is not None:
        deadline_check()
    collector = _CollectingLogger()

    def hook(data: dict[str, Any]) -> None:
        if deadline_check is not None:
            deadline_check()
        if progress_cb is not None:
            _on_progress(data, progress_cb)

    opts = build_ydl_opts(video_dir, progress_cb=None, cookies_browser=cookies_browser)
    opts["logger"] = collector
    opts["progress_hooks"] = [hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        message = collector.last_error or str(exc)
        raise DownloadError(message.strip()[:1500]) from exc
    except Exception as exc:  # noqa: BLE001 - surface any yt-dlp crash as a job error
        logger.exception("Unexpected yt-dlp failure for %s", url)
        raise DownloadError(str(exc).strip()[:1500]) from exc

    if not isinstance(info, dict):
        raise DownloadError("yt-dlp không trả về thông tin video")
    if isinstance(info.get("entries"), list):
        entries = [entry for entry in info["entries"] if isinstance(entry, dict)]
        if not entries:
            raise DownloadError("Không tìm thấy video trong link (playlist rỗng?)")
        info = entries[0]

    result = result_from_info(info, video_dir)
    result.file_path = ensure_mp4(result.file_path, video_dir / "original.mp4")
    return result


def download_video(
    url: str,
    video_dir: Path,
    progress_cb: ProgressCallback | None = None,
    cookies_browser: str = "",
    deadline_check: DeadlineCheck | None = None,
    retries: int = 2,
    retry_backoff_sec: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadResult:
    """Download `url` and return metadata. Raises DownloadError after retries."""
    video_dir.mkdir(parents=True, exist_ok=True)
    last_progress = 0

    def tracked_progress(percent: int, message: str) -> None:
        nonlocal last_progress
        last_progress = percent
        if progress_cb is not None:
            progress_cb(percent, message)

    def on_retry(attempt: int, exc: DownloadError) -> None:
        if deadline_check is not None:
            deadline_check()
        if progress_cb is not None:
            first_line = str(exc).splitlines()[0][:140] if str(exc) else "lỗi"
            progress_cb(
                last_progress,
                f"Lỗi: {first_line} — thử lại {attempt}/{max(0, int(retries))}...",
            )

    return retry_call(
        lambda: _download_once(
            url, video_dir, tracked_progress, cookies_browser, deadline_check
        ),
        retries=retries,
        backoff_sec=retry_backoff_sec,
        sleep=sleep,
        on_retry=on_retry,
    )
