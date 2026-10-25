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
