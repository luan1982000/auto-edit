import subprocess
from pathlib import Path

import pytest

from app.services.ffmpeg_utils import (
    FFmpegError,
    ensure_mp4,
    make_thumbnail,
    probe_video,
)


@pytest.fixture()
def sample_video(tmp_path: Path) -> Path:
    path = tmp_path / "clip with space.mp4"
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
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_probe_video_returns_metadata(sample_video: Path) -> None:
    info = probe_video(sample_video)
    assert info["width"] == 320
    assert info["height"] == 240
    assert info["duration_sec"] == pytest.approx(2.0, abs=0.2)


def test_make_thumbnail_writes_jpeg(sample_video: Path, tmp_path: Path) -> None:
    out = tmp_path / "thumb.jpg"
    make_thumbnail(sample_video, out, at_sec=1.0)
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.read_bytes()[:2] == b"\xff\xd8"


def test_probe_video_raises_clear_error_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FFmpegError) as excinfo:
        probe_video(tmp_path / "missing.mp4")
    assert "ffprobe" in str(excinfo.value).lower()


def test_probe_video_raises_clear_error_for_garbage_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(FFmpegError):
        probe_video(bad)


def test_ensure_mp4_remuxes_other_container(sample_video: Path, tmp_path: Path) -> None:
    mkv = tmp_path / "original.mkv"
    mkv.write_bytes(sample_video.read_bytes())
    target = tmp_path / "original.mp4"
    result = ensure_mp4(mkv, target)
    assert result == target
    assert target.exists()
    assert probe_video(target)["width"] == 320
    assert not mkv.exists()


def test_ensure_mp4_returns_input_when_already_mp4(sample_video: Path) -> None:
    assert ensure_mp4(sample_video, sample_video) == sample_video


def test_parse_progress_seconds_handles_ffmpeg_keys() -> None:
    from app.services.ffmpeg_utils import parse_progress_seconds

    assert parse_progress_seconds("out_time_us=1500000") == pytest.approx(1.5)
    assert parse_progress_seconds("out_time_ms=1500000") == pytest.approx(1.5)
    assert parse_progress_seconds("out_time=00:00:02.250000") == pytest.approx(2.25)
    assert parse_progress_seconds("progress=continue") is None
    assert parse_progress_seconds("garbage") is None


def test_run_ffmpeg_with_progress_reports_percentages(tmp_path: Path) -> None:
    import sys

    from app.services.ffmpeg_utils import run_ffmpeg_with_progress

    script = (
        "import sys\n"
        "for line in ('out_time_us=500000', 'progress=continue', "
        "'out_time_us=2000000', 'progress=end'):\n"
        "    print(line, flush=True)\n"
    )
    seen: list[int] = []
    run_ffmpeg_with_progress(
        [sys.executable, "-u", "-c", script],
        duration_sec=2.0,
        on_progress=seen.append,
    )
    assert seen[0] == 25
    assert seen[-1] == 100
    assert seen == sorted(seen)


def test_run_ffmpeg_with_progress_includes_stderr_on_failure() -> None:
    import sys

    from app.services.ffmpeg_utils import run_ffmpeg_with_progress

    with pytest.raises(FFmpegError, match="boom"):
        run_ffmpeg_with_progress(
            [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(3)"],
            duration_sec=1.0,
            on_progress=lambda _pct: None,
        )


def test_run_ffmpeg_with_progress_reports_missing_binary() -> None:
    from app.services.ffmpeg_utils import run_ffmpeg_with_progress

    with pytest.raises(FFmpegError, match="not found"):
        run_ffmpeg_with_progress(
            ["definitely-not-ffmpeg"],
            duration_sec=1.0,
            on_progress=lambda _pct: None,
        )


def test_run_ffmpeg_with_progress_enforces_timeout() -> None:
    import sys

    from app.services.ffmpeg_utils import run_ffmpeg_with_progress

    with pytest.raises(FFmpegError, match="timed out"):
        run_ffmpeg_with_progress(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            duration_sec=1.0,
            on_progress=lambda _pct: None,
            timeout=0.5,
        )


def test_extract_audio_writes_16k_mono_wav(sample_video: Path, tmp_path: Path) -> None:
    import json

    from app.services.ffmpeg_utils import extract_audio

    out = tmp_path / "audio.wav"
    assert extract_audio(sample_video, out) == out
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,codec_name",
            "-of",
            "json",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream == {"sample_rate": "16000", "channels": 1, "codec_name": "pcm_s16le"}


def test_run_ffmpeg_with_progress_runs_in_the_given_cwd(tmp_path: Path) -> None:
    import sys

    from app.services.ffmpeg_utils import run_ffmpeg_with_progress

    (tmp_path / "marker.txt").write_text("ok", encoding="utf-8")
    script = (
        "import pathlib\n"
        "assert pathlib.Path('marker.txt').read_text() == 'ok'\n"
        "print('progress=end')\n"
    )
    run_ffmpeg_with_progress(
        [sys.executable, "-u", "-c", script],
        duration_sec=1.0,
        on_progress=lambda percent: None,
        cwd=tmp_path,
    )
