"""Text-to-speech engines and voice-over timeline assembly."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services.ffmpeg_utils import FFmpegError, run_ffmpeg

MAX_ATEMPO = 1.4
VOICE_PATTERN = re.compile(r"\A[A-Za-z]{2,3}-[A-Za-z]{2,4}-[A-Za-z0-9]+Neural\Z")
RATE_PATTERN = re.compile(r"\A[+-]\d{1,3}%\Z")


class TTSError(RuntimeError):
    """Raised when speech synthesis or voice timeline assembly fails."""


def validate_voice(voice: str) -> str:
    value = (voice or "").strip()
    if not VOICE_PATTERN.fullmatch(value):
        raise TTSError(f"Giọng đọc không hợp lệ: {voice!r}")
    return value


def validate_rate(rate: str) -> str:
    value = (rate or "").strip()
    if not RATE_PATTERN.fullmatch(value):
        raise TTSError(f"Tốc độ đọc không hợp lệ: {rate!r}")
    return value


class TTSEngine(Protocol):
    def synthesize(self, text: str, voice: str, rate: str, out_path: Path) -> Path:
        """Write synthesized speech for one sentence to `out_path`."""


def _default_communicate(
    text: str, voice: str, rate: str
) -> object:
    import edge_tts

    return edge_tts.Communicate(text, voice, rate=rate)


class EdgeTTSEngine:
    """edge-tts backed engine. The network call runs in a fresh event loop."""

    def __init__(
        self,
        communicate_factory: Callable[[str, str, str], object] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._factory = communicate_factory or _default_communicate
        self._timeout = timeout

    def synthesize(self, text: str, voice: str, rate: str, out_path: Path) -> Path:
        normalized = " ".join((text or "").split())
        if not normalized:
            raise TTSError("Nội dung đọc bị trống")
        validate_voice(voice)
        validate_rate(rate)

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.unlink(missing_ok=True)

        async def save() -> None:
            communicate = self._factory(normalized, voice, rate)
            await asyncio.wait_for(
                communicate.save(str(out_path)), timeout=self._timeout
            )

        try:
            asyncio.run(save())
        except TTSError:
            out_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            out_path.unlink(missing_ok=True)
            raise TTSError(f"edge-tts lỗi: {exc}") from exc

        if not out_path.is_file() or out_path.stat().st_size == 0:
            out_path.unlink(missing_ok=True)
            raise TTSError("edge-tts không tạo được file audio")
        return out_path


@dataclass(frozen=True)
class VoiceClip:
    path: Path
    start: float
    end: float
    duration: float


def compute_atempo(
    audio_duration: float,
    available_duration: float,
    max_speed: float = MAX_ATEMPO,
) -> float:
    """Return the smallest tempo >= 1 that fits, capped at `max_speed`."""
    if available_duration <= 0:
        raise ValueError("segment duration must be positive")
    if audio_duration <= available_duration:
        return 1.0
    return min(round(audio_duration / available_duration, 3), max_speed)


def _validate_clips(clips: list[VoiceClip]) -> list[VoiceClip]:
    if not clips:
        raise TTSError("Không có đoạn giọng đọc nào để ghép")
    for clip in clips:
        if clip.end <= clip.start or clip.duration <= 0 or clip.start < 0:
            raise TTSError("Mốc thời gian của đoạn giọng đọc không hợp lệ")
    return sorted(clips, key=lambda clip: clip.start)


def build_voice_timeline_command(
    clips: list[VoiceClip],
    total_duration: float,
    out_path: Path,
) -> list[str]:
    """Build one ffmpeg command that places each clip at its subtitle time."""
    ordered = _validate_clips(clips)
    if total_duration <= 0:
        raise TTSError("Thời lượng video không hợp lệ")

    command = ["ffmpeg", "-y", "-nostdin"]
    for clip in ordered:
        command += ["-i", str(clip.path)]

    filters: list[str] = []
    labels: list[str] = []
    for index, clip in enumerate(ordered):
        tempo = compute_atempo(clip.duration, clip.end - clip.start)
        delay = max(0, round(clip.start * 1000))
        chain = f"[{index}:a]"
        if tempo > 1:
            chain += f"atempo={tempo:g},"
        chain += f"adelay={delay}|{delay}[a{index}]"
        filters.append(chain)
        labels.append(f"[a{index}]")

    if len(labels) == 1:
        mix = labels[0]
    else:
        mix = "".join(labels) + (
            f"amix=inputs={len(labels)}:duration=longest:"
            "normalize=0:dropout_transition=0,"
        )
    filters.append(f"{mix}apad,alimiter=limit=0.95[aout]")

    command += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[aout]",
        "-t",
        f"{total_duration:.3f}",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        str(Path(out_path)),
    ]
    return command


def build_voice_timeline(
    clips: list[VoiceClip],
    out_path: Path,
    total_duration: float,
) -> Path:
    """Render all per-segment audio clips onto one timeline at `out_path`."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_voice_timeline_command(clips, total_duration, out_path)
    try:
        run_ffmpeg(command, timeout=max(120, int(total_duration * 4) + 60))
    except FFmpegError as exc:
        out_path.unlink(missing_ok=True)
        raise TTSError(f"Không ghép được voice.mp3: {exc}") from exc
    if not out_path.is_file() or out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise TTSError("ffmpeg không tạo được voice.mp3")
    return out_path
