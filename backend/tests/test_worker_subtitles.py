from pathlib import Path

import pytest

from app.config import AppConfig
from app.db import get_session_factory, init_db
from app.ids import new_id
from app.models import Job, Video
from app.services.subtitles import (
    SubtitleData,
    SubtitleSegment,
    load_subtitle_data,
    save_subtitle_data,
)
from app.services.transcribe import TranscriptionResult
from app.worker import (
    Worker,
    build_transcribe_handler,
    build_translate_handler,
)


@pytest.fixture()
def session_factory(tmp_path: Path):
    init_db(tmp_path / "test.db")
    return get_session_factory()


def _setup_video(
    session_factory, config: AppConfig, job_type: str, params: dict
) -> tuple[Video, Job]:
    video_id = new_id()
    video_dir = config.videos_dir / video_id
    video_dir.mkdir(parents=True)
    (video_dir / "original.mp4").write_bytes(b"fake video")
    video = Video(
        id=video_id,
        source_url="https://www.youtube.com/shorts/x",
        platform="youtube",
        title="Clip",
        status="ready",
        width=1080,
        height=1920,
        duration_sec=10.0,
        dir_path=str(video_dir),
        file_path=str(video_dir / "original.mp4"),
    )
    job = Job(id=new_id(), video_id=video_id, type=job_type, params=params)
    with session_factory() as session:
        session.add(video)
        session.add(job)
        session.commit()
        session.refresh(video)
        session.refresh(job)
    return video, job


def _fake_extract(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Path]]:
    calls: list[tuple[Path, Path]] = []

    def extract(source: Path, out: Path, **kwargs) -> Path:
        calls.append((source, out))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"RIFF fake")
        return out

    monkeypatch.setattr("app.worker.extract_audio", extract)
    return calls


class FakeTranscriber:
    def __init__(self, result: TranscriptionResult) -> None:
        self.result = result
        self.calls: list[dict] = []

    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        duration_sec: float,
        on_progress,
        deadline_check=None,
        language=None,
    ) -> TranscriptionResult:
        self.calls.append(
            {
                "audio": audio_path,
                "model": model_name,
                "duration": duration_sec,
                "language": language,
            }
        )
        on_progress(50, "Đang nhận dạng...")
        return self.result


ZH_SEGMENTS = [
    SubtitleSegment(0.0, 1.0, "你好"),
    SubtitleSegment(1.0, 2.0, "世界"),
]


def _reload(session_factory, job_id: str) -> Job:
    with session_factory() as session:
        return session.get(Job, job_id)


def _reload_video(session_factory, video_id: str) -> Video:
    with session_factory() as session:
        return session.get(Video, video_id)


def test_transcribe_handler_saves_json_and_srt(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory,
        config,
        "transcribe",
        {"model": "small", "target_language": "vi", "translate": False},
    )
    extract_calls = _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("zh", ZH_SEGMENTS))

    worker = Worker(
        session_factory,
        {"transcribe": build_transcribe_handler(config, session_factory, transcriber)},
    )
    worker.run_once()

    assert _reload(session_factory, job.id).status == "done"
    assert _reload_video(session_factory, video.id).has_subtitle is True
    assert transcriber.calls == [
        {
            "audio": config.videos_dir / video.id / "audio.wav",
            "model": "small",
            "duration": 10.0,
            "language": None,
        }
    ]
    assert extract_calls == [
        (config.videos_dir / video.id / "original.mp4", config.videos_dir / video.id / "audio.wav")
    ]
    assert not (config.videos_dir / video.id / "audio.wav").exists()

    data = load_subtitle_data(config.videos_dir / video.id / "subtitle.json")
    assert data == SubtitleData(
        language="zh",
        target_language="zh",
        translated=False,
        segments=ZH_SEGMENTS,
        source_segments=ZH_SEGMENTS,
    )
    srt = (config.videos_dir / video.id / "subtitle.srt").read_text(encoding="utf-8")
    assert "你好" in srt
    assert "世界" in srt


def test_transcribe_handler_uses_the_selected_source_language(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory,
        config,
        "transcribe",
        {"model": "small", "source_language": " VI ", "translate": False},
    )
    _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("vi", ZH_SEGMENTS))

    worker = Worker(
        session_factory,
        {"transcribe": build_transcribe_handler(config, session_factory, transcriber)},
    )
    worker.run_once()

    assert _reload(session_factory, job.id).status == "done"
    assert transcriber.calls[0]["language"] == "vi"


def test_transcribe_handler_auto_source_language_is_none(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory,
        config,
        "transcribe",
        {"model": "small", "source_language": "auto", "translate": False},
    )
    _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("zh", ZH_SEGMENTS))

    worker = Worker(
        session_factory,
        {"transcribe": build_transcribe_handler(config, session_factory, transcriber)},
    )
    worker.run_once()

    assert _reload(session_factory, job.id).status == "done"
    assert transcriber.calls[0]["language"] is None


def test_transcribe_handler_rejects_unsupported_source_language(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory,
        config,
        "transcribe",
        {"source_language": "xx"},
    )
    extract_calls = _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("zh", ZH_SEGMENTS))

    worker = Worker(
        session_factory,
        {"transcribe": build_transcribe_handler(config, session_factory, transcriber)},
    )
    worker.run_once()

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "ngôn ngữ nguồn" in (stored.error or "").lower()
    assert extract_calls == []
    assert transcriber.calls == []


def test_transcribe_handler_rejects_unsupported_target_language(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory,
        config,
        "transcribe",
        {"translate": True, "target_language": "xx"},
    )
    extract_calls = _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("zh", ZH_SEGMENTS))

    worker = Worker(
        session_factory,
        {"transcribe": build_transcribe_handler(config, session_factory, transcriber)},
    )
    worker.run_once()

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "ngôn ngữ đích" in (stored.error or "").lower()
    assert extract_calls == []
    assert transcriber.calls == []


def test_transcribe_handler_can_translate_in_the_same_job(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory,
        config,
        "transcribe",
        {"model": "small", "target_language": "vi", "translate": True},
    )
    _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("zh", ZH_SEGMENTS))
    translated_calls: list[tuple] = []

    def fake_translate(segments, target, **kwargs):
        translated_calls.append((segments, target, kwargs))
        return [SubtitleSegment(s.start, s.end, f"vi:{s.text}") for s in segments]

    worker = Worker(
        session_factory,
        {
            "transcribe": build_transcribe_handler(
                config, session_factory, transcriber, translate_fn=fake_translate
            )
        },
    )
    worker.run_once()

    assert _reload(session_factory, job.id).status == "done"
    assert translated_calls[0][0] == ZH_SEGMENTS
    assert translated_calls[0][1] == "vi"
    data = load_subtitle_data(config.videos_dir / video.id / "subtitle.json")
    assert data.target_language == "vi"
    assert data.translated is True
    assert data.language == "zh"
    assert [s.text for s in data.segments] == ["vi:你好", "vi:世界"]
    assert data.source_segments == ZH_SEGMENTS
    srt = (config.videos_dir / video.id / "subtitle.srt").read_text(encoding="utf-8")
    assert "vi:你好" in srt


def test_transcribe_saves_source_before_translation_failure(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", deepseek_api_key="", _env_file=None)
    video, job = _setup_video(
        session_factory,
        config,
        "transcribe",
        {"model": "small", "target_language": "vi", "translate": True},
    )
    _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("zh", ZH_SEGMENTS))

    worker = Worker(
        session_factory,
        {"transcribe": build_transcribe_handler(config, session_factory, transcriber)},
    )
    worker.run_once()

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "DEEPSEEK_API_KEY" in (stored.error or "")
    assert _reload_video(session_factory, video.id).has_subtitle is True
    data = load_subtitle_data(config.videos_dir / video.id / "subtitle.json")
    assert data.language == "zh"
    assert data.translated is False
    assert data.segments == ZH_SEGMENTS


def test_transcribe_handler_rejects_video_without_speech(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(session_factory, config, "transcribe", {})
    _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("", []))

    worker = Worker(
        session_factory,
        {"transcribe": build_transcribe_handler(config, session_factory, transcriber)},
    )
    worker.run_once()

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "lời nói" in (stored.error or "")
    assert _reload_video(session_factory, video.id).has_subtitle is False
    assert not (config.videos_dir / video.id / "subtitle.json").exists()
    assert not (config.videos_dir / video.id / "audio.wav").exists()


def test_transcribe_handler_requires_the_original_file(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(session_factory, config, "transcribe", {})
    (config.videos_dir / video.id / "original.mp4").unlink()
    extract_calls = _fake_extract(monkeypatch)
    transcriber = FakeTranscriber(TranscriptionResult("zh", ZH_SEGMENTS))

    worker = Worker(
        session_factory,
        {"transcribe": build_transcribe_handler(config, session_factory, transcriber)},
    )
    worker.run_once()

    assert _reload(session_factory, job.id).status == "failed"
    assert extract_calls == []
    assert transcriber.calls == []


def _write_subtitle(
    config: AppConfig,
    video: Video,
    *,
    translated: bool = False,
    segments: list[SubtitleSegment] | None = None,
) -> None:
    current = segments or ZH_SEGMENTS
    save_subtitle_data(
        config.videos_dir / video.id / "subtitle.json",
        SubtitleData(
            language="zh",
            target_language="vi" if translated else "zh",
            translated=translated,
            segments=current,
            source_segments=ZH_SEGMENTS,
        ),
    )


def test_translate_handler_translates_source_segments(
    session_factory, tmp_path: Path
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory, config, "translate", {"target_language": "vi"}
    )
    _write_subtitle(config, video, translated=True, segments=ZH_SEGMENTS)
    calls: list[tuple] = []

    def fake_translate(segments, target, **kwargs):
        calls.append((segments, target))
        return [SubtitleSegment(s.start, s.end, f"vi:{s.text}") for s in segments]

    worker = Worker(
        session_factory,
        {"translate": build_translate_handler(config, session_factory, fake_translate)},
    )
    worker.run_once()

    assert _reload(session_factory, job.id).status == "done"
    assert calls == [(ZH_SEGMENTS, "vi")]
    data = load_subtitle_data(config.videos_dir / video.id / "subtitle.json")
    assert data.translated is True
    assert data.language == "zh"
    assert data.target_language == "vi"
    assert [s.text for s in data.segments] == ["vi:你好", "vi:世界"]
    assert data.source_segments == ZH_SEGMENTS
    assert "vi:世界" in (
        config.videos_dir / video.id / "subtitle.srt"
    ).read_text(encoding="utf-8")
    assert _reload_video(session_factory, video.id).has_subtitle is True


def test_translate_handler_restores_source_for_same_language(
    session_factory, tmp_path: Path
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory, config, "translate", {"target_language": "zh"}
    )
    _write_subtitle(
        config,
        video,
        translated=True,
        segments=[SubtitleSegment(0.0, 1.0, "Xin chào")],
    )

    def fail_translate(*args, **kwargs):  # pragma: no cover
        raise AssertionError("must not call the translator for the source language")

    worker = Worker(
        session_factory,
        {"translate": build_translate_handler(config, session_factory, fail_translate)},
    )
    worker.run_once()

    assert _reload(session_factory, job.id).status == "done"
    data = load_subtitle_data(config.videos_dir / video.id / "subtitle.json")
    assert data.segments == ZH_SEGMENTS
    assert data.translated is False
    assert data.target_language == "zh"


def test_translate_handler_rejects_unsupported_target_language(
    session_factory, tmp_path: Path
) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory, config, "translate", {"target_language": "xx"}
    )
    _write_subtitle(config, video)

    worker = Worker(
        session_factory,
        {
            "translate": build_translate_handler(
                config, session_factory, lambda *a, **k: []
            )
        },
    )
    worker.run_once()

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "ngôn ngữ đích" in (stored.error or "").lower()
    data = load_subtitle_data(config.videos_dir / video.id / "subtitle.json")
    assert data.segments == ZH_SEGMENTS


def test_translate_handler_requires_subtitles(session_factory, tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory, config, "translate", {"target_language": "vi"}
    )

    worker = Worker(
        session_factory,
        {"translate": build_translate_handler(config, session_factory, lambda *a, **k: [])},
    )
    worker.run_once()

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "phụ đề" in (stored.error or "")
    assert _reload_video(session_factory, video.id).status == "ready"


def test_translate_handler_reports_failure_without_losing_subtitles(
    session_factory, tmp_path: Path
) -> None:
    from app.services.translate import TranslationError

    config = AppConfig(data_dir=tmp_path / "data", _env_file=None)
    video, job = _setup_video(
        session_factory, config, "translate", {"target_language": "vi"}
    )
    _write_subtitle(config, video)

    def broken(*args, **kwargs):
        raise TranslationError("DeepSeek API lỗi 500: boom")

    worker = Worker(
        session_factory,
        {"translate": build_translate_handler(config, session_factory, broken)},
    )
    worker.run_once()

    stored = _reload(session_factory, job.id)
    assert stored.status == "failed"
    assert "boom" in (stored.error or "")
    data = load_subtitle_data(config.videos_dir / video.id / "subtitle.json")
    assert data.segments == ZH_SEGMENTS
    assert data.translated is False
