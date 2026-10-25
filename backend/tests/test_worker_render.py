import base64
import subprocess
from pathlib import Path

import pytest

from app.config import AppConfig
from app.db import get_session_factory, init_db
from app.ids import new_id
from app.models import Job, Video
from app.services.ffmpeg_utils import probe_video
from app.settings_store import get_or_create_settings
from app.worker import Worker, build_render_handler

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
)


@pytest.fixture()
def render_env(tmp_path: Path):
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    config.videos_dir.mkdir(parents=True)
    config.assets_dir.mkdir(parents=True)
    init_db(config.db_path)
    return config, get_session_factory()


def _make_video(config: AppConfig, session_factory, *, with_logo: bool) -> tuple[Video, Job]:
    video_id = new_id()
    video_dir = config.videos_dir / video_id
    video_dir.mkdir()
    original = video_dir / "original.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(original),
        ],
        check=True,
        capture_output=True,
    )
    logo_path = config.assets_dir / "logo.png"
    logo_path.write_bytes(PNG_1PX)

    video = Video(
        id=video_id,
        source_url="https://www.youtube.com/shorts/x",
        platform="youtube",
        title="Clip",
        duration_sec=1.0,
        width=320,
        height=240,
        dir_path=str(video_dir),
        file_path=str(original),
        status="ready",
    )
    job = Job(
        id=new_id(),
        video_id=video_id,
        type="render",
        params={
            "logo": with_logo,
            "subtitle": False,
            "voice": False,
            "keep_original_audio": "keep",
        },
    )
    with session_factory() as session:
        session.add(video)
        session.add(job)
        settings = get_or_create_settings(session)
        if with_logo:
            settings.logo_path = str(logo_path)
            session.add(settings)
        session.commit()
        session.refresh(job)
    return video, job


def _reload(session_factory, model, ident: str):
    with session_factory() as session:
        return session.get(model, ident)


def test_render_handler_writes_output_with_logo_and_keeps_original(render_env) -> None:
    config, session_factory = render_env
    video, job = _make_video(config, session_factory, with_logo=True)
    original = Path(video.file_path)
    original_bytes = original.read_bytes()

    worker = Worker(session_factory, {"render": build_render_handler(config, session_factory)})
    assert worker.run_once() is True

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "done", stored_job.error
    stored_video = _reload(session_factory, Video, video.id)
    assert stored_video.status == "ready"
    assert stored_video.has_output is True

    output = Path(video.dir_path) / "output_final.mp4"
    assert output.is_file()
    info = probe_video(output)
    assert info["width"] == 320
    assert info["height"] == 240
    assert original.read_bytes() == original_bytes
    assert not (Path(video.dir_path) / "output_final.tmp.mp4").exists()


def test_render_handler_without_logo_works_when_nothing_uploaded(render_env) -> None:
    config, session_factory = render_env
    video, job = _make_video(config, session_factory, with_logo=False)

    worker = Worker(session_factory, {"render": build_render_handler(config, session_factory)})
    worker.run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "done", stored_job.error
    assert (Path(video.dir_path) / "output_final.mp4").is_file()


def test_failed_render_keeps_video_ready_and_cleans_temp_file(render_env) -> None:
    config, session_factory = render_env
    video, job = _make_video(config, session_factory, with_logo=True)

    # Simulate the uploaded logo disappearing from disk after it was configured.
    with session_factory() as session:
        settings = get_or_create_settings(session)
        Path(settings.logo_path).unlink()
        session.add(settings)
        session.commit()

    worker = Worker(session_factory, {"render": build_render_handler(config, session_factory)})
    worker.run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "failed"
    assert "logo" in (stored_job.error or "").lower()
    stored_video = _reload(session_factory, Video, video.id)
    assert stored_video.status == "ready"
    assert stored_video.has_output is False
    assert not (Path(video.dir_path) / "output_final.tmp.mp4").exists()
    assert not (Path(video.dir_path) / "output_final.mp4").exists()
