"""Single background worker thread that executes jobs from the SQLite `jobs` table."""

from __future__ import annotations

import json
import logging
import shutil
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
    extract_audio,
    make_thumbnail,
    probe_audio_duration,
    probe_video,
    run_ffmpeg_with_progress,
)
from app.services.render import (
    AUDIO_MODES,
    LogoOptions,
    RenderOptions,
    build_ffmpeg_command,
)
from app.services.subtitles import (
    SubtitleData,
    SubtitleError,
    SubtitleSegment,
    load_subtitle_data,
    save_subtitle_data,
    write_ass,
    write_srt,
)
from app.services.transcribe import (
    FasterWhisperTranscriber,
    Transcriber,
    TranscriptionError,
)
from app.services.translate import TranslationError, translate_segments
from app.services.tts import (
    EdgeTTSEngine,
    TTSEngine,
    TTSError,
    VoiceClip,
    build_voice_timeline,
    validate_rate,
    validate_voice,
)
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


TranslateFn = Callable[..., list[SubtitleSegment]]


def _persist_subtitles(video_dir: Path, data: SubtitleData) -> None:
    save_subtitle_data(video_dir / "subtitle.json", data)
    write_srt(video_dir / "subtitle.srt", data.segments)


def _set_has_subtitle(session_factory: SessionFactory, video_id: str, value: bool) -> None:
    with session_factory() as session:
        video = session.get(Video, video_id)
        if video is None:
            return
        video.has_subtitle = value
        session.add(video)
        session.commit()


def _load_video_settings(
    session_factory: SessionFactory, video_id: str
) -> tuple[Video, str, str, float]:
    with session_factory() as session:
        video = session.get(Video, video_id)
        if video is None:
            raise TranscriptionError("Video không tồn tại trong database")
        settings = get_or_create_settings(session)
        model = str(settings.whisper_model)
        target_language = str(settings.target_language)
        return video, model, target_language, float(video.duration_sec)


def build_transcribe_handler(
    config: AppConfig,
    session_factory: SessionFactory,
    transcriber: Transcriber | None = None,
    translate_fn: TranslateFn | None = None,
) -> JobHandler:
    engine = transcriber or FasterWhisperTranscriber()
    translator = translate_fn or translate_segments

    def handle(ctx: JobContext) -> None:
        if not ctx.video_id:
            raise TranscriptionError("Job transcribe thiếu video_id")
        video_dir = (config.videos_dir / ctx.video_id).resolve()

        video, model, target_language, duration = _load_video_settings(
            session_factory, ctx.video_id
        )
        source = Path(video.file_path).resolve()
        if not source.is_relative_to(video_dir) or not source.is_file():
            raise TranscriptionError("Chưa có file video gốc để nhận dạng")

        model = str(ctx.params.get("model") or model)
        target_language = str(ctx.params.get("target_language") or target_language)
        audio_path = video_dir / "audio.wav"

        ctx.update(1, "Tách audio...")
        try:
            extract_audio(source, audio_path)
        except FFmpegError as exc:
            raise TranscriptionError(f"Không tách được audio từ video: {exc}") from exc

        try:
            ctx.update(5, "Đang nhận dạng giọng nói...")
            result = engine.transcribe(
                audio_path,
                model_name=model,
                duration_sec=duration,
                on_progress=ctx.update,
                deadline_check=ctx.check_deadline,
            )
        finally:
            audio_path.unlink(missing_ok=True)

        if not result.segments:
            raise TranscriptionError("Không nhận dạng được lời nói trong video")

        data = SubtitleData(
            language=result.language,
            target_language=result.language,
            translated=False,
            segments=result.segments,
            source_segments=list(result.segments),
        )
        _persist_subtitles(video_dir, data)
        _set_has_subtitle(session_factory, ctx.video_id, True)

        if bool(ctx.params.get("translate")):
            if not target_language or target_language == result.language:
                ctx.update(100, "Ngôn ngữ đã trùng — không cần dịch")
                return
            ctx.update(92, "Đang dịch phụ đề...")
            translated = translator(
                data.source_segments,
                target_language,
                api_key=config.deepseek_api_key,
                base_url=config.deepseek_base_url,
                model=config.deepseek_model,
            )
            ctx.check_deadline()
            data.segments = translated
            data.target_language = target_language
            data.translated = target_language != data.language
            _persist_subtitles(video_dir, data)

        ctx.update(100, "Hoàn tất")

    return handle


def build_translate_handler(
    config: AppConfig,
    session_factory: SessionFactory,
    translate_fn: TranslateFn | None = None,
) -> JobHandler:
    translator = translate_fn or translate_segments

    def handle(ctx: JobContext) -> None:
        if not ctx.video_id:
            raise TranslationError("Job translate thiếu video_id")
        video_dir = (config.videos_dir / ctx.video_id).resolve()

        with session_factory() as session:
            video = session.get(Video, ctx.video_id)
            if video is None:
                raise TranslationError("Video không tồn tại trong database")
            settings = get_or_create_settings(session)
            target_language = str(
                ctx.params.get("target_language") or settings.target_language
            )

        data = load_subtitle_data(video_dir / "subtitle.json")
        if data is None:
            raise TranslationError("Video chưa có phụ đề để dịch")
        source_segments = data.source_segments or data.segments
        if not source_segments:
            raise TranslationError("Video chưa có phụ đề để dịch")

        if not target_language or target_language == data.language:
            data.segments = list(source_segments)
            data.target_language = target_language or data.language
            data.translated = False
            _persist_subtitles(video_dir, data)
            _set_has_subtitle(session_factory, ctx.video_id, True)
            ctx.update(100, "Ngôn ngữ đã trùng — không cần dịch")
            return

        ctx.update(5, "Đang dịch phụ đề...")
        translated = translator(
            source_segments,
            target_language,
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
            model=config.deepseek_model,
        )
        ctx.check_deadline()
        data.segments = translated
        data.source_segments = list(source_segments)
        data.target_language = target_language
        data.translated = True
        _persist_subtitles(video_dir, data)
        _set_has_subtitle(session_factory, ctx.video_id, True)
        ctx.update(100, "Hoàn tất")

    return handle


def _set_has_voice(session_factory: SessionFactory, video_id: str, value: bool) -> None:
    with session_factory() as session:
        video = session.get(Video, video_id)
        if video is None:
            return
        video.has_voice = value
        session.add(video)
        session.commit()


def build_tts_handler(
    config: AppConfig,
    session_factory: SessionFactory,
    engine: TTSEngine | None = None,
) -> JobHandler:
    tts_engine = engine or EdgeTTSEngine()

    def handle(ctx: JobContext) -> None:
        if not ctx.video_id:
            raise TTSError("Job tts thiếu video_id")
        video_dir = (config.videos_dir / ctx.video_id).resolve()

        with session_factory() as session:
            video = session.get(Video, ctx.video_id)
            if video is None:
                raise TTSError("Video không tồn tại trong database")
            settings = get_or_create_settings(session)
            voice = validate_voice(
                str(ctx.params.get("voice") or settings.tts_voice)
            )
            rate = validate_rate(str(ctx.params.get("rate") or settings.tts_rate))
            duration = float(video.duration_sec)

        data = load_subtitle_data(video_dir / "subtitle.json")
        if data is None or not data.segments:
            raise TTSError("Video chưa có phụ đề để tạo giọng đọc")
        segments = [segment for segment in data.segments if segment.text.strip()]
        if not segments:
            raise TTSError("Phụ đề không có nội dung để tạo giọng đọc")
        if duration <= 0:
            duration = max(segment.end for segment in segments)
        if duration <= 0:
            raise TTSError("Không xác định được thời lượng video")

        segment_dir = video_dir / "tts"
        shutil.rmtree(segment_dir, ignore_errors=True)
        segment_dir.mkdir(parents=True, exist_ok=True)
        temporary = video_dir / "voice.tmp.mp3"
        clips: list[VoiceClip] = []

        try:
            total = len(segments)
            for index, segment in enumerate(segments):
                ctx.check_deadline()
                ctx.update(
                    5 + int(index / total * 75),
                    f"Đang tạo giọng đọc {index + 1}/{total}...",
                )
                clip_path = segment_dir / f"seg-{index:04d}.mp3"
                tts_engine.synthesize(
                    segment.text, voice, rate, clip_path
                )
                ctx.check_deadline()
                clips.append(
                    VoiceClip(
                        path=clip_path,
                        start=segment.start,
                        end=segment.end,
                        duration=probe_audio_duration(clip_path),
                    )
                )

            ctx.update(85, "Đang ghép voice.mp3...")
            build_voice_timeline(clips, temporary, total_duration=duration)
            temporary.replace(video_dir / "voice.mp3")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(segment_dir, ignore_errors=True)

        _set_has_voice(session_factory, ctx.video_id, True)
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
            subtitle_enabled = bool(ctx.params.get("subtitle", False))
            voice_enabled = bool(ctx.params.get("voice", False))
            audio_mode = str(ctx.params.get("keep_original_audio", "keep"))
            subtitle_font = settings.subtitle_font
            subtitle_size = settings.subtitle_size
            subtitle_position = settings.subtitle_position
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
        if audio_mode not in AUDIO_MODES:
            raise RenderError(f"Chế độ âm thanh không hợp lệ: {audio_mode}")

        voice_path: Path | None = None
        has_original_audio = True
        if voice_enabled:
            voice_path = video_dir / "voice.mp3"
            if not voice_path.is_file():
                raise RenderError(
                    "Video chưa có file giọng đọc — tạo giọng đọc trước khi render"
                )
            try:
                has_original_audio = bool(probe_video(source)["has_audio"])
            except FFmpegError as exc:
                raise RenderError(f"Không đọc được audio gốc: {exc}") from exc

        subtitle_file: str | None = None
        if subtitle_enabled:
            try:
                subtitle_data = load_subtitle_data(video_dir / "subtitle.json")
                if subtitle_data is None or not subtitle_data.segments:
                    raise RenderError("Video chưa có phụ đề để burn")
                write_ass(
                    video_dir / "subtitle.ass",
                    subtitle_data.segments,
                    video_width=width,
                    video_height=height,
                    font=subtitle_font,
                    size=subtitle_size,
                    position=subtitle_position,
                )
            except SubtitleError as exc:
                raise RenderError(f"Không tạo được phụ đề: {exc}") from exc
            except OSError as exc:
                raise RenderError(f"Không ghi được file phụ đề: {exc}") from exc
            subtitle_file = "subtitle.ass"

        output = video_dir / "output_final.mp4"
        temporary = video_dir / "output_final.tmp.mp4"
        command = build_ffmpeg_command(
            source,
            temporary,
            RenderOptions(
                video_width=width,
                video_height=height,
                logo=logo_options,
                subtitle_file=subtitle_file,
                voice_path=voice_path,
                audio_mode=audio_mode,
                has_original_audio=has_original_audio,
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
                cwd=video_dir,
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
    transcriber = FasterWhisperTranscriber()
    return {
        "download": build_download_handler(config, session_factory),
        "transcribe": build_transcribe_handler(
            config, session_factory, transcriber=transcriber
        ),
        "translate": build_translate_handler(config, session_factory),
        "tts": build_tts_handler(config, session_factory, engine=EdgeTTSEngine()),
        "render": build_render_handler(config, session_factory),
    }
