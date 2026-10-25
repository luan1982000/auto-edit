"""Single background worker thread that executes jobs from the SQLite `jobs` table."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from app.config import AppConfig
from app.models import Job, Video, utcnow
from app.services.assets import resolve_logo
from app.services.douyin import normalize_douyin_url, with_douyin_hint
from app.services.downloader import DownloadError, DownloadResult, download_video
from app.services.fallback import FallbackError, download_via_fallback
from app.services.ffmpeg_utils import (
    FFmpegError,
    make_thumbnail,
    probe_video,
    run_ffmpeg_with_progress,
)
from app.services.render import LogoOptions, RenderOptions, build_ffmpeg_command
from app.services.urls import detect_platform
from app.settings_store import get_or_create_settings

logger = logging.getLogger(__name__)

SessionFactory = sessionmaker[Session]


class JobTimeoutError(RuntimeError):
    """Raised by handlers when a job exceeds its wall-clock budget."""


@dataclass
class JobContext:
    job_id: str
    video_id: str | None
    params: dict
    deadline: float
    _update: Callable[[int, str], None]

    def update(self, progress: int, message: str = "") -> None:
        self._update(progress, message)

    def check_deadline(self) -> None:
        if time.monotonic() > self.deadline:
            raise JobTimeoutError("Job timeout — vượt quá thời gian cho phép")


JobHandler = Callable[[JobContext], None]


class Worker:
    def __init__(
        self,
        session_factory: SessionFactory,
        handlers: dict[str, JobHandler],
        poll_interval: float = 0.5,
        default_timeout_sec: int = 900,
    ) -> None:
        self._session_factory = session_factory
        self._handlers = handlers
        self._poll_interval = poll_interval
        self._default_timeout_sec = default_timeout_sec
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="job-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                processed = self.run_once()
            except Exception:  # noqa: BLE001 - never let the worker thread die
                logger.exception("Worker iteration crashed")
                processed = False
            if not processed:
                self._stop.wait(self._poll_interval)

    def run_once(self) -> bool:
        """Claim and run at most one pending job. Returns False when queue is empty."""
        job = self._claim_next()
        if job is None:
            return False

        ctx = JobContext(
            job_id=job.id,
            video_id=job.video_id,
            params=dict(job.params or {}),
            deadline=time.monotonic() + self._timeout_for(job),
            _update=self._make_updater(job.id),
        )
        try:
            handler = self._handlers.get(job.type)
            if handler is None:
                raise RuntimeError(f"Unknown job type: {job.type}")
            handler(ctx)
        except Exception as exc:  # noqa: BLE001 - every failure is a job failure
            logger.exception("Job %s (%s) failed", job.id, job.type)
            self._finish(job, failed=True, error=str(exc).strip() or exc.__class__.__name__)
        else:
            self._finish(job, failed=False)
        return True

    def _timeout_for(self, job: Job) -> int:
        try:
            return int(job.params.get("timeout_sec", self._default_timeout_sec))
        except (TypeError, ValueError):
            return self._default_timeout_sec

    def _claim_next(self) -> Job | None:
        with self._session_factory() as session:
            job = session.exec(
                select(Job).where(Job.status == "pending").order_by(Job.created_at)
            ).first()
            if job is None:
                return None
            job.status = "running"
            job.message = "Đang chạy"
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def _make_updater(self, job_id: str) -> Callable[[int, str], None]:
        def update(progress: int, message: str = "") -> None:
            with self._session_factory() as session:
                job = session.get(Job, job_id)
                if job is None:
                    return
                job.progress = max(0, min(100, int(progress)))
                if message:
                    job.message = message
                session.add(job)
                session.commit()

        return update

    def _finish(self, job: Job, failed: bool, error: str | None = None) -> None:
        with self._session_factory() as session:
            stored = session.get(Job, job.id)
            if stored is None:
                return
            stored.finished_at = utcnow()
            if failed:
                stored.status = "failed"
                stored.error = (error or "Unknown error")[:2000]
                stored.message = "Thất bại"
                # Only a failed download makes the video unusable. A failed
                # transcribe/translate/tts/render leaves the ready video intact.
                if job.video_id and job.type == "download":
                    video = session.get(Video, job.video_id)
                    if video is not None:
                        video.status = "failed"
                        video.error = stored.error
                        session.add(video)
            else:
                stored.status = "done"
                stored.progress = 100
                stored.message = "Hoàn tất"
                stored.error = None
            session.add(stored)
            session.commit()


def build_download_handler(config: AppConfig, session_factory: SessionFactory) -> JobHandler:
    def handle(ctx: JobContext) -> None:
        if not ctx.video_id:
            raise DownloadError("Job download thiếu video_id")
        url = str(ctx.params.get("url") or "")
        if not url:
            raise DownloadError("Job download thiếu URL")

        source_input = url
        with session_factory() as session:
            video = session.get(Video, ctx.video_id)
            if video is None:
                raise DownloadError("Video không tồn tại trong database")
            cookies_browser = get_or_create_settings(session).cookies_browser
            platform = (
                video.platform
                if video.platform != "other"
                else detect_platform(url)
            )
            effective_url = (
                normalize_douyin_url(url) if platform == "douyin" else url
            )
            if effective_url != video.source_url:
                video.source_url = effective_url
                session.add(video)
                session.commit()

        video_dir = config.videos_dir / ctx.video_id
        ctx.update(0, "Bắt đầu tải...")
        used_fallback = False
        try:
            result = download_video(
                url=effective_url,
                video_dir=video_dir,
                progress_cb=ctx.update,
                cookies_browser=cookies_browser,
                deadline_check=ctx.check_deadline,
            )
        except DownloadError as exc:
            if platform != "douyin":
                raise
            if not config.douyin_fallback_url:
                raise DownloadError(
                    with_douyin_hint(str(exc), fallback_enabled=False)
                ) from exc

            ctx.update(0, "yt-dlp lỗi — thử downloader fallback...")
            try:
                fallback_file = download_via_fallback(
                    base_url=config.douyin_fallback_url,
                    video_url=effective_url,
                    target_path=video_dir / "original.mp4",
                    deadline_check=ctx.check_deadline,
                )
            except FallbackError as fallback_exc:
                raise DownloadError(
                    with_douyin_hint(
                        f"{exc}\n\nFallback cũng thất bại: {fallback_exc}",
                        fallback_enabled=True,
                    )
                ) from fallback_exc

            result = DownloadResult(
                file_path=fallback_file,
                title="Douyin video",
                platform="douyin",
            )
            used_fallback = True

        try:
            probed = probe_video(result.file_path)
        except FFmpegError as exc:
            raise DownloadError(f"Không đọc được file video sau khi tải: {exc}") from exc

        duration = float(probed["duration_sec"] or result.duration_sec)
        thumb_path = video_dir / "thumb.jpg"
        has_thumb = True
        try:
            make_thumbnail(
                result.file_path, thumb_path, at_sec=min(1.0, max(duration / 2, 0.1))
            )
        except FFmpegError:
            logger.warning("Could not create thumbnail for %s", result.file_path, exc_info=True)
            has_thumb = False

        meta = {
            "url": effective_url,
            "source_input": source_input,
            "title": result.title,
            "duration_sec": duration,
            "width": int(probed["width"]),
            "height": int(probed["height"]),
            "platform": result.platform,
            "fallback": used_fallback,
            "downloaded_at": utcnow().isoformat(),
        }
        (video_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with session_factory() as session:
            video = session.get(Video, ctx.video_id)
            if video is None:
                raise DownloadError("Video bị xoá trong lúc tải")
            video.source_url = effective_url
            video.title = result.title or video.title or ctx.video_id
            video.duration_sec = duration
            video.width = int(probed["width"])
            video.height = int(probed["height"])
            video.file_path = str(result.file_path)
            video.thumb_path = str(thumb_path) if has_thumb else ""
            if result.platform != "other":
                video.platform = result.platform
            video.status = "ready"
            video.error = None
            session.add(video)
            session.commit()

        ctx.update(100, "Hoàn tất")

    return handle


class RenderError(RuntimeError):
    """Raised when a render cannot start or ffmpeg fails."""


def build_render_handler(config: AppConfig, session_factory: SessionFactory) -> JobHandler:
    def handle(ctx: JobContext) -> None:
        if not ctx.video_id:
            raise RenderError("Job render thiếu video_id")

        video_dir = (config.videos_dir / ctx.video_id).resolve()
        with session_factory() as session:
            video = session.get(Video, ctx.video_id)
            if video is None:
                raise RenderError("Video không tồn tại trong database")
            settings = get_or_create_settings(session)
            source = Path(video.file_path).resolve()
            if not source.is_relative_to(video_dir) or not source.is_file():
                raise RenderError("Chưa có file video gốc để render")
            width = video.width
            height = video.height
            duration = video.duration_sec
            logo_enabled = bool(ctx.params.get("logo", True))
            logo_path = resolve_logo(config, settings.logo_path) if logo_enabled else None
            logo_options = (
                LogoOptions(
                    path=logo_path,
                    position=settings.logo_position,
                    scale_pct=settings.logo_scale_pct,
                    opacity=settings.logo_opacity,
                    margin_px=settings.logo_margin_px,
                )
                if logo_path is not None
                else None
            )

        if logo_enabled and logo_options is None:
            raise RenderError("Chưa có logo hợp lệ — upload logo trong Cài đặt")
        if logo_enabled and (width <= 0 or height <= 0):
            raise RenderError("Chưa có kích thước video để đặt logo")

        output = video_dir / "output_final.mp4"
        temporary = video_dir / "output_final.tmp.mp4"
        command = build_ffmpeg_command(
            source,
            temporary,
            RenderOptions(
                video_width=width,
                video_height=height,
                logo=logo_options,
            ),
        )

        ctx.update(1, "Bắt đầu render...")
        try:
            run_ffmpeg_with_progress(
                command,
                duration_sec=duration,
                on_progress=lambda percent: ctx.update(
                    max(1, min(99, percent)), f"Đang render... {percent}%"
                ),
                timeout=max(300.0, duration * 10),
                deadline_check=ctx.check_deadline,
            )
            temporary.replace(output)
        except FFmpegError as exc:
            temporary.unlink(missing_ok=True)
            raise RenderError(f"Render thất bại: {exc}") from exc
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

        with session_factory() as session:
            stored = session.get(Video, ctx.video_id)
            if stored is None:
                raise RenderError("Video bị xoá trong lúc render")
            stored.has_output = True
            session.add(stored)
            session.commit()

        ctx.update(100, "Hoàn tất")

    return handle


def default_handlers(config: AppConfig, session_factory: SessionFactory) -> dict[str, JobHandler]:
    return {
        "download": build_download_handler(config, session_factory),
        "render": build_render_handler(config, session_factory),
    }
