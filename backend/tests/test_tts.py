import asyncio
import subprocess
from pathlib import Path

import pytest

from app.services.ffmpeg_utils import FFmpegError, probe_audio_duration
from app.services.tts import (
    EdgeTTSEngine,
    TTSError,
    VoiceClip,
    build_voice_timeline,
    build_voice_timeline_command,
    compute_atempo,
    validate_rate,
    validate_voice,
)


def _option(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


def _tone(path: Path, seconds: float) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:a",
            "libmp3lame",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@pytest.mark.parametrize(
    ("audio_duration", "available", "expected"),
    [
        (0.8, 1.0, 1.0),
        (1.0, 1.0, 1.0),
        (1.65, 1.5, 1.1),
        (2.0, 1.0, 1.4),
        (10.0, 1.0, 1.4),
    ],
)
def test_compute_atempo_fits_audio_into_segment(
    audio_duration: float, available: float, expected: float
) -> None:
    assert compute_atempo(audio_duration, available) == pytest.approx(expected)


def test_compute_atempo_rejects_zero_length_segment() -> None:
    with pytest.raises(ValueError):
        compute_atempo(1.0, 0.0)


def test_voice_timeline_command_delays_each_clip_and_mixes(tmp_path: Path) -> None:
    first = tmp_path / "a.mp3"
    second = tmp_path / "b.mp3"
    output = tmp_path / "voice.mp3"

    command = build_voice_timeline_command(
        [
            VoiceClip(path=second, start=2.5, end=3.0, duration=0.5),
            VoiceClip(path=first, start=0.0, end=1.0, duration=0.8),
        ],
        total_duration=4.0,
        out_path=output,
    )

    assert command[0] == "ffmpeg"
    assert command[:3] == ["ffmpeg", "-y", "-nostdin"]
    assert command.count("-i") == 2
    assert str(first) in command
    assert str(second) in command

    filters = _option(command, "-filter_complex")
    assert "[0:a]adelay=0|0[a0]" in filters
    assert "[1:a]adelay=2500|2500[a1]" in filters
    assert "amix=inputs=2:duration=longest:normalize=0" in filters
    assert "apad" in filters
    assert "alimiter=limit=0.95" in filters
    assert filters.endswith("[aout]")
    assert _option(command, "-map") == "[aout]"
    assert _option(command, "-t") == "4.000"
    assert _option(command, "-c:a") == "libmp3lame"
    assert command[-1] == str(output)


def test_voice_timeline_command_speeds_up_overlong_clip(tmp_path: Path) -> None:
    clip = tmp_path / "long.mp3"
    command = build_voice_timeline_command(
        [VoiceClip(path=clip, start=5.0, end=6.0, duration=2.0)],
        total_duration=8.0,
        out_path=tmp_path / "voice.mp3",
    )

    filters = _option(command, "-filter_complex")
    assert "[0:a]atempo=1.4,adelay=5000|5000[a0]" in filters
    assert "amix" not in filters
    assert "[a0]apad,alimiter=limit=0.95[aout]" in filters


def test_voice_timeline_command_rejects_empty_clip_list(tmp_path: Path) -> None:
    with pytest.raises(TTSError, match="giọng"):
        build_voice_timeline_command([], total_duration=2.0, out_path=tmp_path / "v.mp3")


def test_voice_timeline_command_rejects_invalid_timing(tmp_path: Path) -> None:
    clip = VoiceClip(path=tmp_path / "a.mp3", start=2.0, end=2.0, duration=1.0)
    with pytest.raises(TTSError):
        build_voice_timeline_command([clip], total_duration=3.0, out_path=tmp_path / "v.mp3")


def test_build_voice_timeline_writes_audio_matching_video_length(tmp_path: Path) -> None:
    first = _tone(tmp_path / "a.mp3", 0.4)
    second = _tone(tmp_path / "b.mp3", 0.5)
    output = tmp_path / "voice.mp3"

    build_voice_timeline(
        [
            VoiceClip(path=first, start=0.0, end=0.5, duration=0.4),
            VoiceClip(path=second, start=1.0, end=1.5, duration=0.5),
        ],
        output,
        total_duration=2.0,
    )

    assert output.is_file()
    assert output.stat().st_size > 0
    assert probe_audio_duration(output) == pytest.approx(2.0, abs=0.2)


def test_probe_audio_duration_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FFmpegError):
        probe_audio_duration(tmp_path / "missing.mp3")


class FakeCommunicate:
    def __init__(
        self,
        text: str,
        voice: str,
        rate: str,
        *,
        payload: bytes = b"ID3 fake audio",
        error: Exception | None = None,
    ) -> None:
        self.text = text
        self.voice = voice
        self.rate = rate
        self.payload = payload
        self.error = error

    async def save(self, path: str) -> None:
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        Path(path).write_bytes(self.payload)


def test_edge_engine_uses_voice_and_rate(tmp_path: Path) -> None:
    calls: list[dict[str, str]] = []

    def factory(text: str, voice: str, rate: str) -> FakeCommunicate:
        calls.append({"text": text, "voice": voice, "rate": rate})
        return FakeCommunicate(text, voice, rate)

    output = tmp_path / "segment.mp3"
    engine = EdgeTTSEngine(communicate_factory=factory)
    result = engine.synthesize(
        "Xin chào", "vi-VN-HoaiMyNeural", "+10%", output
    )

    assert result == output
    assert output.read_bytes() == b"ID3 fake audio"
    assert calls == [
        {
            "text": "Xin chào",
            "voice": "vi-VN-HoaiMyNeural",
            "rate": "+10%",
        }
    ]


def test_edge_engine_wraps_synthesis_errors(tmp_path: Path) -> None:
    def factory(text: str, voice: str, rate: str) -> FakeCommunicate:
        return FakeCommunicate(text, voice, rate, error=RuntimeError("network down"))

    engine = EdgeTTSEngine(communicate_factory=factory)
    with pytest.raises(TTSError, match="network down"):
        engine.synthesize("Xin chào", "vi-VN-HoaiMyNeural", "+0%", tmp_path / "a.mp3")


def test_edge_engine_rejects_empty_text(tmp_path: Path) -> None:
    engine = EdgeTTSEngine(communicate_factory=lambda *_: pytest.fail("must not call"))
    with pytest.raises(TTSError, match="trống"):
        engine.synthesize("  ", "vi-VN-HoaiMyNeural", "+0%", tmp_path / "a.mp3")


def test_edge_engine_validates_output(tmp_path: Path) -> None:
    engine = EdgeTTSEngine(
        communicate_factory=lambda text, voice, rate: FakeCommunicate(
            text, voice, rate, payload=b""
        )
    )
    with pytest.raises(TTSError, match="audio"):
        engine.synthesize("Xin chào", "vi-VN-HoaiMyNeural", "+0%", tmp_path / "a.mp3")


@pytest.mark.parametrize(
    ("voice", "valid"),
    [
        ("vi-VN-HoaiMyNeural", True),
        ("vi-VN-NamMinhNeural", True),
        ("en-US-AriaNeural", True),
        ("", False),
        ("../evil", False),
        ("vi-VN-HoaiMy", False),
    ],
)
def test_validate_voice(voice: str, valid: bool) -> None:
    if valid:
        assert validate_voice(voice) == voice
    else:
        with pytest.raises(TTSError):
            validate_voice(voice)


@pytest.mark.parametrize(
    ("rate", "valid"),
    [("+0%", True), ("+10%", True), ("-15%", True), ("10%", False), ("fast", False)],
)
def test_validate_rate(rate: str, valid: bool) -> None:
    if valid:
        assert validate_rate(rate) == rate
    else:
        with pytest.raises(TTSError):
            validate_rate(rate)
