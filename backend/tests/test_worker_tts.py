import subprocess
from pathlib import Path

import pytest

from app.config import AppConfig
from app.db import get_session_factory, init_db
from app.ids import new_id
from app.models import Job, Video
from app.services.ffmpeg_utils import probe_audio_duration
from app.services.subtitles import (
    SubtitleData,
    SubtitleSegment,
    save_subtitle_data,
)
from app.services.tts import TTSError
from app.worker import Worker, build_tts_handler


@pytest.fixture()
def tts_env(tmp_path: Path):
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    config.videos_dir.mkdir(parents=True)
    init_db(config.db_path)
    return config, get_session_factory()


def _make_video(
    config: AppConfig,
    session_factory,
    job_params: dict,
    *,
    segments: list[SubtitleSegment] | None = None,
    duration: float = 3.0,
    has_voice: bool = False,
) -> tuple[Video, Job]:
    video_id = new_id()
    video_dir = config.videos_dir / video_id
    video_dir.mkdir(parents=True)
    original = video_dir / "original.mp4"
    original.write_bytes(b"fake video")
    if segments is not None:
        save_subtitle_data(
            video_dir / "subtitle.json",
            SubtitleData(
                language="en",
                target_language="vi",
                translated=True,
                segments=segments,
                source_segments=list(segments),
            ),
        )
    video = Video(
        id=video_id,
        source_url="https://www.youtube.com/shorts/x",
        platform="youtube",
        title="Clip",
        duration_sec=duration,
        width=1080,
        height=1920,
        dir_path=str(video_dir),
        file_path=str(original),
        status="ready",
        has_subtitle=segments is not None,
        has_voice=has_voice,
    )
    job = Job(id=new_id(), video_id=video_id, type="tts", params=job_params)
    with session_factory() as session:
        session.add(video)
        session.add(job)
        session.commit()
        session.refresh(job)
    return video, job


def _reload(session_factory, model, ident: str):
    with session_factory() as session:
        return session.get(model, ident)


class FakeTTSEngine:
    def __init__(
        self,
        durations: list[float] | None = None,
        error: str | None = None,
    ) -> None:
        self.durations = durations or [0.4]
        self.error = error
        self.calls: list[dict[str, str]] = []

    def synthesize(self, text: str, voice: str, rate: str, out_path: Path) -> Path:
        self.calls.append({"text": text, "voice": voice, "rate": rate})
        if self.error is not None:
            raise TTSError(self.error)
        duration = self.durations[min(len(self.calls) - 1, len(self.durations) - 1)]
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                f"{duration:.3f}",
                "-c:a",
                "libmp3lame",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )
        return out_path


def test_tts_handler_builds_voice_timeline_and_marks_video(tts_env) -> None:
    config, session_factory = tts_env
    segments = [
        SubtitleSegment(0.0, 1.0, "Xin chào"),
        SubtitleSegment(1.2, 1.4, "  "),
        SubtitleSegment(1.5, 2.5, "Tạm biệt"),
    ]
    video, job = _make_video(
        config,
        session_factory,
        {"voice": "vi-VN-NamMinhNeural", "rate": "-5%"},
        segments=segments,
    )
    engine = FakeTTSEngine(durations=[0.5, 2.0])

    worker = Worker(
        session_factory,
        {"tts": build_tts_handler(config, session_factory, engine=engine)},
    )
    assert worker.run_once() is True

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "done", stored_job.error
    assert stored_job.progress == 100
    assert stored_job.message == "Hoàn tất"
    assert _reload(session_factory, Video, video.id).has_voice is True

    assert [call["text"] for call in engine.calls] == ["Xin chào", "Tạm biệt"]
    assert all(call["voice"] == "vi-VN-NamMinhNeural" for call in engine.calls)
    assert all(call["rate"] == "-5%" for call in engine.calls)

    video_dir = Path(video.dir_path)
    voice = video_dir / "voice.mp3"
    assert voice.is_file()
    assert probe_audio_duration(voice) == pytest.approx(3.0, abs=0.25)
    assert not (video_dir / "voice.tmp.mp3").exists()
    assert not (video_dir / "tts").exists()


def test_tts_handler_uses_settings_when_job_has_no_overrides(tts_env) -> None:
    config, session_factory = tts_env
    video, job = _make_video(
        config,
        session_factory,
        {},
        segments=[SubtitleSegment(0.0, 1.0, "Xin chào")],
    )
    engine = FakeTTSEngine()

    Worker(
        session_factory,
        {"tts": build_tts_handler(config, session_factory, engine=engine)},
    ).run_once()

    assert _reload(session_factory, Job, job.id).status == "done"
    assert engine.calls[0]["voice"] == "vi-VN-HoaiMyNeural"
    assert engine.calls[0]["rate"] == "+0%"


def test_tts_handler_requires_subtitles(tts_env) -> None:
    config, session_factory = tts_env
    video, job = _make_video(config, session_factory, {}, segments=None)
    engine = FakeTTSEngine()

    Worker(
        session_factory,
        {"tts": build_tts_handler(config, session_factory, engine=engine)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "failed"
    assert "phụ đề" in (stored_job.error or "")
    assert engine.calls == []
    assert _reload(session_factory, Video, video.id).has_voice is False
    assert not (Path(video.dir_path) / "voice.mp3").exists()


def test_tts_handler_rejects_subtitles_without_text(tts_env) -> None:
    config, session_factory = tts_env
    video, job = _make_video(
        config,
        session_factory,
        {},
        segments=[SubtitleSegment(0.0, 1.0, "   ")],
    )
    engine = FakeTTSEngine()

    Worker(
        session_factory,
        {"tts": build_tts_handler(config, session_factory, engine=engine)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "failed"
    assert "nội dung" in (stored_job.error or "").lower()
    assert engine.calls == []


def test_failed_tts_keeps_the_previous_voice_file(tts_env) -> None:
    config, session_factory = tts_env
    video, job = _make_video(
        config,
        session_factory,
        {},
        segments=[SubtitleSegment(0.0, 1.0, "Xin chào")],
        has_voice=True,
    )
    video_dir = Path(video.dir_path)
    voice = video_dir / "voice.mp3"
    voice.write_bytes(b"previous voice")
    engine = FakeTTSEngine(error="edge-tts lỗi: network down")

    Worker(
        session_factory,
        {"tts": build_tts_handler(config, session_factory, engine=engine)},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "failed"
    assert "network down" in (stored_job.error or "")
    assert voice.read_bytes() == b"previous voice"
    assert not (video_dir / "voice.tmp.mp3").exists()
    assert not (video_dir / "tts").exists()
    assert _reload(session_factory, Video, video.id).has_voice is True


def test_tts_handler_requires_a_video_id(tts_env) -> None:
    config, session_factory = tts_env
    job = Job(id=new_id(), video_id=None, type="tts", params={})
    with session_factory() as session:
        session.add(job)
        session.commit()

    Worker(
        session_factory,
        {"tts": build_tts_handler(config, session_factory, engine=FakeTTSEngine())},
    ).run_once()

    stored_job = _reload(session_factory, Job, job.id)
    assert stored_job.status == "failed"
    assert "video_id" in (stored_job.error or "")
