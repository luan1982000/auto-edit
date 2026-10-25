import subprocess
from pathlib import Path

import pytest

from app.services.ffmpeg_utils import FFmpegError, extract_sample_frames


@pytest.fixture()
def sample_video(tmp_path: Path) -> Path:
    path = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10",
            "-t",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_extract_sample_frames_writes_three_jpegs(
    sample_video: Path, tmp_path: Path
) -> None:
    frames = extract_sample_frames(
        sample_video, tmp_path / "frames", duration_sec=2.0
    )

    assert [round(time, 2) for time, _ in frames] == [0.3, 1.0, 1.7]
    assert [path.name for _, path in frames] == [
        "sample-1.jpg",
        "sample-2.jpg",
        "sample-3.jpg",
    ]
    for _, path in frames:
        assert path.is_file()
        assert path.stat().st_size > 0
        assert path.read_bytes()[:2] == b"\xff\xd8"


def test_extract_sample_frames_removes_stale_frames(
    sample_video: Path, tmp_path: Path
) -> None:
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    stale = out_dir / "sample-9.jpg"
    stale.write_bytes(b"old")

    extract_sample_frames(sample_video, out_dir, duration_sec=2.0)

    assert not stale.exists()


def test_extract_sample_frames_rejects_unknown_duration(
    sample_video: Path, tmp_path: Path
) -> None:
    with pytest.raises(FFmpegError, match="duration"):
        extract_sample_frames(sample_video, tmp_path / "frames", duration_sec=0)
