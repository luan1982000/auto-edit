from pathlib import Path

import pytest
from sqlmodel import select

from app.db import get_session_factory, init_db
from app.ids import new_id
from app.models import Job, Video
from app.worker import JobContext, Worker


@pytest.fixture()
def session_factory(tmp_path: Path):
    init_db(tmp_path / "test.db")
    return get_session_factory()


def _make_download_job(session_factory, job_type: str = "download") -> tuple[Video, Job]:
    video = Video(
        id=new_id(),
        source_url="https://youtube.com/shorts/abc",
        platform="youtube",
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
