import json
from pathlib import Path

import pytest
from sqlmodel import select

from app.config import AppConfig
from app.db import get_session_factory, init_db
from app.ids import new_id
from app.models import Job, Video
from app.services.downloader import DownloadError, DownloadResult
from app.services.fallback import FallbackError
from app.settings_store import get_or_create_settings
from app.worker import JobContext, Worker, build_download_handler


@pytest.fixture()
def session_factory(tmp_path: Path):
    init_db(tmp_path / "test.db")
    return get_session_factory()


def _make_download_job(
    session_factory,
    job_type: str = "download",
    source_url: str = "https://youtube.com/shorts/abc",
    platform: str = "youtube",
) -> tuple[Video, Job]:
    video = Video(
        id=new_id(),
        source_url=source_url,
        platform=platform,
        status="downloading",
    )
    job = Job(id=new_id(), video_id=video.id, type=job_type, params={"url": video.source_url})
    with session_factory() as session:
        session.add(video)
        session.add(job)
        session.commit()
        session.refresh(job)
        session.refresh(video)
    return video, job


def _reload(session_factory, job_id: str) -> Job:
    with session_factory() as session:
        return session.get(Job, job_id)


def _reload_video(session_factory, video_id: str) -> Video:
    with session_factory() as session:
        return session.get(Video, video_id)


def test_worker_completes_pending_job(session_factory) -> None:
    _, job = _make_download_job(session_factory)
    seen: list[JobContext] = []

    def handler(ctx: JobContext) -> None:
        seen.append(ctx)
        ctx.update(50, "Đang tải")
        ctx.update(100, "Xong")

    worker = Worker(session_factory, {"download": handler})
    assert worker.run_once() is True

    stored = _reload(session_factory, job.id)
    assert stored.status == "done"
    assert stored.progress == 100
    assert stored.finished_at is not None
    assert seen[0].params == {"url": "https://youtube.com/shorts/abc"}


def test_worker_marks_job_and_video_failed_on_error(session_factory) -> None:
    video, job = _make_download_job(session_factory)

    def handler(ctx: JobContext) -> None:
        raise RuntimeError("yt-dlp exploded")

    worker = Worker(session_factory, {"download": handler})
    worker.run_once()

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "yt-dlp exploded" in (stored.error or "")
    assert stored.finished_at is not None
    stored_video = _reload_video(session_factory, video.id)
    assert stored_video.status == "failed"
    assert "yt-dlp exploded" in (stored_video.error or "")


def test_worker_fails_unknown_job_type(session_factory) -> None:
    _, job = _make_download_job(session_factory, job_type="mystery")
    worker = Worker(session_factory, {})
    worker.run_once()
    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "mystery" in (stored.error or "")


def test_worker_enforces_deadline(session_factory) -> None:
    _, job = _make_download_job(session_factory)

    def handler(ctx: JobContext) -> None:
        ctx.check_deadline()

    worker = Worker(session_factory, {"download": handler}, default_timeout_sec=0)
    worker.run_once()
    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "timeout" in (stored.error or "").lower()


def test_worker_clamps_progress_updates(session_factory) -> None:
    _, job = _make_download_job(session_factory)

    def handler(ctx: JobContext) -> None:
        ctx.update(-10, "below")
        ctx.update(999, "above")
        raise RuntimeError("fail after update")

    worker = Worker(session_factory, {"download": handler})
    worker.run_once()
    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert stored.progress == 100


def test_run_once_returns_false_when_no_pending_jobs(session_factory) -> None:
    worker = Worker(session_factory, {"download": lambda ctx: None})
    assert worker.run_once() is False


def test_worker_claims_jobs_in_created_order(session_factory) -> None:
    _, first = _make_download_job(session_factory)
    _, second = _make_download_job(session_factory)
    processed: list[str] = []

    def handler(ctx: JobContext) -> None:
        processed.append(ctx.job_id)

    worker = Worker(session_factory, {"download": handler})
    worker.run_once()
    worker.run_once()
    assert processed == [first.id, second.id]


def test_completed_job_is_not_reprocessed(session_factory) -> None:
    _, job = _make_download_job(session_factory)
    calls = 0

    def handler(ctx: JobContext) -> None:
        nonlocal calls
        calls += 1

    worker = Worker(session_factory, {"download": handler})
    assert worker.run_once() is True
    assert worker.run_once() is False
    assert calls == 1

    with session_factory() as session:
        pending = session.exec(select(Job).where(Job.status == "pending")).all()
    assert pending == []
    assert _reload(session_factory, job.id).status == "done"


def test_download_handler_passes_cookies_from_settings(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, job = _make_download_job(session_factory)
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    with session_factory() as session:
        settings = get_or_create_settings(session)
        settings.cookies_browser = "firefox"
        session.add(settings)
        session.commit()

    captured: dict[str, object] = {}

    def fake_download(**kwargs) -> DownloadResult:
        captured.update(kwargs)
        target = config.videos_dir / video.id / "original.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return DownloadResult(file_path=target, title="Clip", platform="youtube")

    monkeypatch.setattr("app.worker.download_video", fake_download)
    monkeypatch.setattr(
        "app.worker.probe_video",
        lambda path: {"duration_sec": 1.0, "width": 100, "height": 200},
    )
    monkeypatch.setattr("app.worker.make_thumbnail", lambda *args, **kwargs: None)

    worker = Worker(
        session_factory,
        {"download": build_download_handler(config, session_factory)},
    )
    worker.run_once()

    assert captured["cookies_browser"] == "firefox"
    assert _reload(session_factory, job.id).status == "done"


def test_douyin_download_falls_back_and_stores_canonical_url(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_id = "7345678901234567890"
    canonical = f"https://www.douyin.com/video/{video_id}"
    video, job = _make_download_job(
        session_factory,
        source_url=f"https://www.iesdouyin.com/share/video/{video_id}/",
        platform="douyin",
    )
    config = AppConfig(
        data_dir=tmp_path / "data",
        douyin_fallback_url="http://fallback.test/download",
        _env_file=None,
    )
    calls: dict[str, object] = {}

    def fail_download(**kwargs) -> DownloadResult:
        calls["ytdlp_url"] = kwargs["url"]
        raise DownloadError("ERROR: login required")

    def fake_fallback(base_url, video_url, target_path, **kwargs):
        calls["base_url"] = base_url
        calls["video_url"] = video_url
        calls["target"] = target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"fake mp4")
        return target_path

    monkeypatch.setattr("app.worker.download_video", fail_download)
    monkeypatch.setattr("app.worker.download_via_fallback", fake_fallback)
    monkeypatch.setattr(
        "app.worker.probe_video",
        lambda path: {"duration_sec": 4.0, "width": 1080, "height": 1920},
    )
    monkeypatch.setattr("app.worker.make_thumbnail", lambda *args, **kwargs: None)

    worker = Worker(
        session_factory,
        {"download": build_download_handler(config, session_factory)},
    )
    worker.run_once()

    stored_job = _reload(session_factory, job.id)
    stored_video = _reload_video(session_factory, video.id)
    assert stored_job.status == "done"
    assert stored_video.status == "ready"
    assert stored_video.source_url == canonical
    assert stored_video.platform == "douyin"
    assert calls["ytdlp_url"] == canonical
    assert calls["video_url"] == canonical
    assert Path(calls["target"]).name == "original.mp4"

    meta = json.loads(
        (config.videos_dir / video.id / "meta.json").read_text(encoding="utf-8")
    )
    assert meta["url"] == canonical
    assert meta["fallback"] is True


def test_douyin_failure_without_fallback_includes_hints(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, job = _make_download_job(
        session_factory,
        source_url="https://www.douyin.com/video/7345678901234567890",
        platform="douyin",
    )
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)

    def fail_download(**kwargs) -> DownloadResult:
        raise DownloadError("ERROR: Unsupported URL")

    monkeypatch.setattr("app.worker.download_video", fail_download)

    worker = Worker(
        session_factory,
        {"download": build_download_handler(config, session_factory)},
    )
    worker.run_once()

    stored_job = _reload(session_factory, job.id)
    stored_video = _reload_video(session_factory, video.id)
    assert stored_job.status == "failed"
    assert stored_video.status == "failed"
    assert "Gợi ý" in (stored_job.error or "")
    assert "Cập nhật yt-dlp" in (stored_job.error or "")


def test_douyin_fallback_failure_reports_both_errors(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job = _make_download_job(
        session_factory,
        source_url="https://www.douyin.com/video/7345678901234567890",
        platform="douyin",
    )
    config = AppConfig(
        data_dir=tmp_path / "data",
        douyin_fallback_url="http://fallback.test/download",
        _env_file=None,
    )

    def fail_download(**kwargs) -> DownloadResult:
        raise DownloadError("ERROR: login required")

    def fail_fallback(*args, **kwargs):
        raise FallbackError("HTTP 503")

    monkeypatch.setattr("app.worker.download_video", fail_download)
    monkeypatch.setattr("app.worker.download_via_fallback", fail_fallback)

    worker = Worker(
        session_factory,
        {"download": build_download_handler(config, session_factory)},
    )
    worker.run_once()

    error = _reload(session_factory, job.id).error or ""
    assert "login required" in error
    assert "Fallback cũng thất bại" in error
    assert "HTTP 503" in error
    assert "DOUYIN_FALLBACK_URL" not in error


def test_non_douyin_failure_does_not_use_fallback(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job = _make_download_job(session_factory)
    config = AppConfig(
        data_dir=tmp_path / "data",
        douyin_fallback_url="http://fallback.test/download",
        _env_file=None,
    )
    fallback_calls: list[object] = []

    def fail_download(**kwargs) -> DownloadResult:
        raise DownloadError("ERROR: boom")

    def fake_fallback(*args, **kwargs):
        fallback_calls.append(args)
        raise AssertionError("fallback must not run for non-Douyin")

    monkeypatch.setattr("app.worker.download_video", fail_download)
    monkeypatch.setattr("app.worker.download_via_fallback", fake_fallback)

    worker = Worker(
        session_factory,
        {"download": build_download_handler(config, session_factory)},
    )
    worker.run_once()

    error = _reload(session_factory, job.id).error or ""
    assert fallback_calls == []
    assert "Gợi ý" not in error


def test_failure_of_post_download_job_keeps_video_ready(session_factory) -> None:
    video, job = _make_download_job(session_factory, job_type="render")
    with session_factory() as session:
        stored_video = session.get(Video, video.id)
        stored_video.status = "ready"
        session.add(stored_video)
        session.commit()

    def handler(ctx: JobContext) -> None:
        raise RuntimeError("ffmpeg exploded")

    worker = Worker(session_factory, {"render": handler})
    worker.run_once()

    assert _reload(session_factory, job.id).status == "failed"
    stored_video = _reload_video(session_factory, video.id)
    assert stored_video.status == "ready"
    assert stored_video.error is None


def _set_job_status(session_factory, job_id: str, status: str) -> None:
    with session_factory() as session:
        job = session.get(Job, job_id)
        job.status = status
        job.message = "Đang chạy"
        job.progress = 42
        session.add(job)
        session.commit()


def test_worker_recovers_an_interrupted_download(session_factory) -> None:
    video, job = _make_download_job(session_factory)
    _set_job_status(session_factory, job.id, "running")

    worker = Worker(session_factory, {})
    assert worker.recover_orphaned_jobs() == 1

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert stored.finished_at is not None
    assert "khởi động lại" in (stored.error or "")
    stored_video = _reload_video(session_factory, video.id)
    assert stored_video.status == "failed"
    assert stored_video.error == stored.error


def test_worker_recovery_keeps_a_ready_video_for_editing_jobs(session_factory) -> None:
    video, job = _make_download_job(session_factory, job_type="render")
    with session_factory() as session:
        stored_video = session.get(Video, video.id)
        stored_video.status = "ready"
        session.add(stored_video)
        session.commit()
    _set_job_status(session_factory, job.id, "running")

    worker = Worker(session_factory, {})
    assert worker.recover_orphaned_jobs() == 1

    assert _reload(session_factory, job.id).status == "failed"
    stored_video = _reload_video(session_factory, video.id)
    assert stored_video.status == "ready"
    assert stored_video.error is None


def test_worker_recovery_fails_videos_stuck_downloading_without_a_job(
    session_factory,
) -> None:
    video, _ = _make_download_job(session_factory)
    with session_factory() as session:
        for job in session.exec(select(Job).where(Job.video_id == video.id)).all():
            session.delete(job)
        session.commit()

    Worker(session_factory, {}).recover_orphaned_jobs()

    stored_video = _reload_video(session_factory, video.id)
    assert stored_video.status == "failed"
    assert "gián đoạn" in (stored_video.error or "")


def test_worker_recovery_leaves_pending_jobs_alone(session_factory) -> None:
    video, job = _make_download_job(session_factory)

    assert Worker(session_factory, {}).recover_orphaned_jobs() == 0

    assert _reload(session_factory, job.id).status == "pending"
    assert _reload_video(session_factory, video.id).status == "downloading"


def test_worker_start_recovers_orphans_before_polling(session_factory, monkeypatch) -> None:
    worker = Worker(session_factory, {})
    calls: list[str] = []
    monkeypatch.setattr(
        worker, "recover_orphaned_jobs", lambda: calls.append("recovered") or 0
    )

    worker.start()
    worker.stop()

    assert calls == ["recovered"]
