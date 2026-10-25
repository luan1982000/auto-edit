"""Speech recognition with faster-whisper, cached per model name."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services.subtitles import SubtitleSegment

ProgressCallback = Callable[[int, str], None]


class TranscriptionError(RuntimeError):
    """Raised when audio cannot be transcribed."""


@dataclass
class TranscriptionResult:
    language: str
    segments: list[SubtitleSegment]


class Transcriber(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        duration_sec: float,
        on_progress: ProgressCallback,
        deadline_check: Callable[[], None] | None = None,
    ) -> TranscriptionResult: ...


class FasterWhisperTranscriber:
    """Lazy wrapper so importing the app does not load whisper models."""

    def __init__(self) -> None:
        self._models: dict[str, object] = {}

    def _build_model(self, model_name: str) -> object:
        from faster_whisper import WhisperModel

        return WhisperModel(model_name, device="auto", compute_type="int8")

    def _get_model(self, model_name: str) -> object:
        model = self._models.get(model_name)
        if model is None:
            try:
                model = self._build_model(model_name)
            except Exception as exc:  # noqa: BLE001 - network/cache/model errors
                raise TranscriptionError(
                    f"Không tải được model whisper '{model_name}': {exc}"
                ) from exc
            self._models[model_name] = model
        return model

    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        duration_sec: float,
        on_progress: ProgressCallback,
        deadline_check: Callable[[], None] | None = None,
    ) -> TranscriptionResult:
        if not audio_path.is_file():
            raise TranscriptionError(f"File audio không tồn tại: {audio_path}")

        model = self._get_model(model_name)
        segments: list[SubtitleSegment] = []
        language = ""
        try:
            raw_segments, info = model.transcribe(  # type: ignore[attr-defined]
                str(audio_path),
                vad_filter=True,
                beam_size=5,
            )
            language = str(getattr(info, "language", "") or "")
            for raw in raw_segments:
                if deadline_check is not None:
                    deadline_check()
                end = max(0.0, float(raw.end))
                start = max(0.0, min(float(raw.start), end))
                text = " ".join(str(raw.text).split())
                if text:
                    segments.append(SubtitleSegment(start=start, end=end, text=text))
                percent = (
                    10 + int(min(end / duration_sec, 1.0) * 85)
                    if duration_sec > 0
                    else 50
                )
                on_progress(min(95, percent), f"Đang nhận dạng... {end:.0f}s")
        except TranscriptionError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface model failures as job errors
            raise TranscriptionError(f"Nhận dạng giọng nói thất bại: {exc}") from exc

        return TranscriptionResult(language=language, segments=segments)
