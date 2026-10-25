from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.subtitles import SubtitleSegment
from app.services.transcribe import (
    FasterWhisperTranscriber,
    TranscriptionError,
    TranscriptionResult,
)


class FakeModel:
    def __init__(self, segments, language: str = "zh") -> None:
        self._segments = segments
        self._language = language
        self.kwargs: dict = {}

    def transcribe(self, audio: str, **kwargs):
        self.kwargs = kwargs
        info = SimpleNamespace(language=self._language)
        return iter(self._segments), info


@pytest.fixture()
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"RIFF fake")
    return path


def _segment(start: float, end: float, text: str):
    return SimpleNamespace(start=start, end=end, text=text)


def test_transcribe_maps_segments_language_and_progress(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeModel(
        [
            _segment(0.0, 1.0, " 你好 "),
            _segment(1.0, 2.0, ""),
            _segment(2.0, 10.0, "世界"),
        ]
    )
    transcriber = FasterWhisperTranscriber()
    monkeypatch.setattr(transcriber, "_build_model", lambda name: model)
    progress: list[tuple[int, str]] = []

    result = transcriber.transcribe(
        audio_file,
        model_name="small",
        duration_sec=10.0,
        on_progress=lambda percent, message: progress.append((percent, message)),
    )

    assert result == TranscriptionResult(
        language="zh",
        segments=[
            SubtitleSegment(0.0, 1.0, "你好"),
            SubtitleSegment(2.0, 10.0, "世界"),
        ],
    )
    assert [percent for percent, _ in progress] == [18, 27, 95]
    assert all("nhận dạng" in message for _, message in progress)
    assert model.kwargs["vad_filter"] is True
    assert model.kwargs["beam_size"] == 5


def test_transcribe_caches_models(audio_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []

    def build(name: str) -> FakeModel:
        built.append(name)
        return FakeModel([_segment(0.0, 1.0, "x")])

    transcriber = FasterWhisperTranscriber()
    monkeypatch.setattr(transcriber, "_build_model", build)

    for name in ("small", "small", "medium"):
        transcriber.transcribe(
            audio_file,
            model_name=name,
            duration_sec=1.0,
            on_progress=lambda percent, message: None,
        )

    assert built == ["small", "medium"]


def test_transcribe_checks_the_deadline_for_every_segment(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeModel([_segment(float(i), float(i + 1), str(i)) for i in range(3)])
    transcriber = FasterWhisperTranscriber()
    monkeypatch.setattr(transcriber, "_build_model", lambda name: model)
    checks = 0

    def deadline() -> None:
        nonlocal checks
        checks += 1

    transcriber.transcribe(
        audio_file,
        model_name="small",
        duration_sec=3.0,
        on_progress=lambda percent, message: None,
        deadline_check=deadline,
    )
    assert checks == 3


def test_transcribe_requires_an_existing_audio_file(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionError, match="audio"):
        FasterWhisperTranscriber().transcribe(
            tmp_path / "missing.wav",
            model_name="small",
            duration_sec=1.0,
            on_progress=lambda percent, message: None,
        )


def test_transcribe_wraps_model_errors(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenModel:
        def transcribe(self, audio: str, **kwargs):
            raise RuntimeError("model exploded")

    transcriber = FasterWhisperTranscriber()
    monkeypatch.setattr(transcriber, "_build_model", lambda name: BrokenModel())

    with pytest.raises(TranscriptionError, match="model exploded"):
        transcriber.transcribe(
            audio_file,
            model_name="small",
            duration_sec=1.0,
            on_progress=lambda percent, message: None,
        )


def test_transcribe_forces_the_selected_source_language(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeModel([_segment(0.0, 1.0, "xin chào")])
    transcriber = FasterWhisperTranscriber()
    monkeypatch.setattr(transcriber, "_build_model", lambda name: model)

    transcriber.transcribe(
        audio_file,
        model_name="small",
        duration_sec=1.0,
        on_progress=lambda percent, message: None,
        language="vi",
    )

    assert model.kwargs["language"] == "vi"


def test_transcribe_omits_language_when_auto_detection_is_selected(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeModel([_segment(0.0, 1.0, "hello")])
    transcriber = FasterWhisperTranscriber()
    monkeypatch.setattr(transcriber, "_build_model", lambda name: model)

    transcriber.transcribe(
        audio_file,
        model_name="small",
        duration_sec=1.0,
        on_progress=lambda percent, message: None,
        language=None,
    )

    assert "language" not in model.kwargs


def test_transcribe_tolerates_missing_language_info(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class NoLanguageModel:
        def transcribe(self, audio: str, **kwargs):
            return iter([_segment(0.0, 1.0, "hello")]), object()

    transcriber = FasterWhisperTranscriber()
    monkeypatch.setattr(transcriber, "_build_model", lambda name: NoLanguageModel())

    result = transcriber.transcribe(
        audio_file,
        model_name="small",
        duration_sec=1.0,
        on_progress=lambda percent, message: None,
    )
    assert result.language == ""
    assert result.segments == [SubtitleSegment(0.0, 1.0, "hello")]
