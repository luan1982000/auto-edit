import base64
import subprocess
from pathlib import Path

import pytest

from app.config import AppConfig
from app.db import get_session_factory, init_db
from app.ids import new_id
from app.models import Job, Video
from app.services.cover import CoverRegion, save_cover_region
from app.services.ffmpeg_utils import probe_video
from app.services.subtitles import SubtitleData, SubtitleSegment, save_subtitle_data
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


def _make_video(
    config: AppConfig,
    session_factory,
    *,
    with_logo: bool,
    subtitle: bool = False,
    voice: bool = False,
    audio_mode: str = "keep",
    source_audio: bool = True,
) -> tuple[Video, Job]:
    video_id = new_id()
    video_dir = config.videos_dir / video_id
    video_dir.mkdir()
    original = video_dir / "original.mp4"
    source_args = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=10",
    ]
    if source_audio:
        source_args += ["-f", "lavfi", "-i", "sine=frequency=440"]
    source_args += [
        "-t",
        "1",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
    ]
    if source_audio:
        source_args += ["-c:a", "aac"]
    source_args.append(str(original))
    subprocess.run(source_args, check=True, capture_output=True)

    if voice:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                "1",
                "-c:a",
                "libmp3lame",
                str(video_dir / "voice.mp3"),
            ],
            check=True,
            capture_output=True,
        )
    logo_path = config.assets_dir / "logo.png"
    logo_path.write_bytes(PNG_1PX)

    if subtitle:
        save_subtitle_data(
            video_dir / "subtitle.json",
            SubtitleData(
                language="en",
                target_language="vi",
                translated=True,
                segments=[SubtitleSegment(0.0, 0.8, "Xin chào")],
                source_segments=[SubtitleSegment(0.0, 0.8, "Hello")],
            ),
        )

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
        has_voice=voice,
    )
    job = Job(
        id=new_id(),
        video_id=video_id,
        type="render",
        params={
            "logo": with_logo,
            "subtitle": subtitle,
            "voice": voice,
            "keep_original_audio": audio_mode,
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


def test_render_handler_burns_ass_subtitles(render_env) -> None:
    config, session_factory = render_env
    video, job = _make_video(
        config, session_factory, with_logo=True, subtitle=True
    )
    original = Path(video.file_path)
    original_bytes = original.read_bytes()

    worker = Worker(session_factory, {"render": build_render_handler(config, session_factory)})
    worker.run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "done", stored_job.error
    assert _reload(session_factory, Video, video.id).has_output is True
    video_dir = Path(video.dir_path)
    assert (video_dir / "output_final.mp4").is_file()
    ass = (video_dir / "subtitle.ass").read_text(encoding="utf-8")
    assert "PlayResX: 320" in ass
    assert "PlayResY: 240" in ass
    assert "Xin chào" in ass
    assert original.read_bytes() == original_bytes
    assert not (video_dir / "output_final.tmp.mp4").exists()


def test_render_handler_covers_old_subtitles_before_burning_new_ones(
    render_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, session_factory = render_env
    video, job = _make_video(
        config, session_factory, with_logo=True, subtitle=True
    )
    region = CoverRegion(0.05, 0.75, 0.9, 0.2)
    save_cover_region(Path(video.dir_path), region)
    captured: dict = {}
    from app.services import render as render_module

    real_build = render_module.build_ffmpeg_command

    def spy(source, output, options):
        captured["options"] = options
        captured["command"] = real_build(source, output, options)
        return captured["command"]

    monkeypatch.setattr("app.worker.build_ffmpeg_command", spy)

    Worker(
        session_factory,
        {"render": build_render_handler(config, session_factory)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "done", stored_job.error
    assert captured["options"].cover_region == region
    assert "drawbox=" in " ".join(captured["command"])
    output = Path(video.dir_path) / "output_final.mp4"
    assert output.is_file()


def test_render_handler_ignores_saved_region_without_subtitle_rendering(
    render_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, session_factory = render_env
    video, job = _make_video(config, session_factory, with_logo=True)
    save_cover_region(Path(video.dir_path), CoverRegion(0.05, 0.75, 0.9, 0.2))
    captured: dict = {}
    from app.services import render as render_module

    real_build = render_module.build_ffmpeg_command

    def spy(source, output, options):
        captured["options"] = options
        return real_build(source, output, options)

    monkeypatch.setattr("app.worker.build_ffmpeg_command", spy)

    Worker(
        session_factory,
        {"render": build_render_handler(config, session_factory)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "done", stored_job.error
    assert captured["options"].cover_region is None


def test_render_handler_rejects_a_corrupt_cover_region(render_env) -> None:
    config, session_factory = render_env
    video, job = _make_video(
        config, session_factory, with_logo=False, subtitle=True
    )
    (Path(video.dir_path) / "cover_region.json").write_text(
        "not json", encoding="utf-8"
    )
    original = Path(video.file_path)
    original_bytes = original.read_bytes()

    Worker(
        session_factory,
        {"render": build_render_handler(config, session_factory)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "failed"
    assert "Vùng che" in (stored_job.error or "")
    assert not (Path(video.dir_path) / "output_final.mp4").exists()
    assert original.read_bytes() == original_bytes


def test_render_handler_requires_subtitle_data_when_requested(render_env) -> None:
    config, session_factory = render_env
    video, job = _make_video(config, session_factory, with_logo=False)
    with session_factory() as session:
        stored = session.get(Job, job.id)
        stored.params = {**stored.params, "subtitle": True}
        session.add(stored)
        session.commit()

    worker = Worker(session_factory, {"render": build_render_handler(config, session_factory)})
    worker.run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "failed"
    assert "phụ đề" in (stored_job.error or "")
    assert _reload(session_factory, Video, video.id).has_output is False
    assert not (Path(video.dir_path) / "output_final.tmp.mp4").exists()


@pytest.mark.parametrize("audio_mode", ["duck", "keep", "mute"])
def test_render_handler_mixes_voice_with_logo_and_subtitles(
    render_env, audio_mode: str
) -> None:
    config, session_factory = render_env
    video, job = _make_video(
        config,
        session_factory,
        with_logo=True,
        subtitle=True,
        voice=True,
        audio_mode=audio_mode,
    )
    original = Path(video.file_path)
    original_bytes = original.read_bytes()

    Worker(
        session_factory,
        {"render": build_render_handler(config, session_factory)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "done", stored_job.error
    output = Path(video.dir_path) / "output_final.mp4"
    assert output.is_file()
    assert probe_video(output)["has_audio"] is True
    assert original.read_bytes() == original_bytes
    assert not (Path(video.dir_path) / "output_final.tmp.mp4").exists()


def test_render_handler_mixes_voice_into_silent_source(render_env) -> None:
    config, session_factory = render_env
    video, job = _make_video(
        config,
        session_factory,
        with_logo=False,
        voice=True,
        audio_mode="duck",
        source_audio=False,
    )

    Worker(
        session_factory,
        {"render": build_render_handler(config, session_factory)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "done", stored_job.error
    assert probe_video(Path(video.dir_path) / "output_final.mp4")["has_audio"] is True


def test_render_handler_requires_voice_file_when_requested(render_env) -> None:
    config, session_factory = render_env
    video, job = _make_video(config, session_factory, with_logo=False)
    with session_factory() as session:
        stored = session.get(Video, video.id)
        stored.has_voice = True
        session.add(stored)
        job_row = session.get(Job, job.id)
        job_row.params = {**job_row.params, "voice": True}
        session.add(job_row)
        session.commit()

    Worker(
        session_factory,
        {"render": build_render_handler(config, session_factory)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "failed"
    assert "giọng" in (stored_job.error or "").lower()
    assert not (Path(video.dir_path) / "output_final.mp4").exists()
