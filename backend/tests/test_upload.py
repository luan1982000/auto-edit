import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.routers import videos


def _make_video(tmp_path: Path, suffix: str = ".mp4") -> bytes:
    path = tmp_path / f"clip{suffix}"
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
            "1",
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
    return path.read_bytes()


@pytest.fixture(scope="module")
def sample_mp4(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    return _make_video(tmp_path_factory.mktemp("upload-source"))


@pytest.fixture(scope="module")
def sample_mkv(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    return _make_video(tmp_path_factory.mktemp("upload-source"), ".mkv")


@pytest.fixture(scope="module")
def incompatible_mkv(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    path = tmp_path_factory.mktemp("upload-incompatible") / "clip.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "0.5",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


def _video_dirs(client: TestClient) -> list[Path]:
    videos_dir = client.app.state.config.videos_dir
    if not videos_dir.is_dir():
        return []
    return [path for path in videos_dir.iterdir() if path.is_dir()]


def test_upload_creates_ready_video_with_thumbnail_and_metadata(
    client: TestClient, sample_mp4: bytes
) -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("Holiday Clip.mp4", sample_mp4, "video/mp4")},
    )

    assert response.status_code == 201, response.text
    video = response.json()
    assert video["status"] == "ready"
    assert video["platform"] == "upload"
    assert video["title"] == "Holiday Clip"
    assert video["source_url"] == ""
    assert video["duration_sec"] == pytest.approx(1.0, abs=0.3)
    assert video["width"] == 320
    assert video["height"] == 240

    video_dir = client.app.state.config.videos_dir / video["id"]
    assert (video_dir / "original.mp4").is_file()
    assert (video_dir / "thumb.jpg").is_file()
    meta = json.loads((video_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["source"] == "upload"
    assert meta["original_name"] == "Holiday Clip.mp4"
    assert meta["title"] == "Holiday Clip"

    listed = client.get("/api/videos")
    assert listed.status_code == 200
    assert any(item["id"] == video["id"] for item in listed.json())


def test_upload_converts_other_container_to_mp4(
    client: TestClient, sample_mkv: bytes
) -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("clip.mkv", sample_mkv, "video/x-matroska")},
    )

    assert response.status_code == 201, response.text
    video = response.json()
    video_dir = client.app.state.config.videos_dir / video["id"]
    assert (video_dir / "original.mp4").is_file()
    assert not (video_dir / "upload.mkv").exists()
    assert video["duration_sec"] == pytest.approx(1.0, abs=0.3)


def test_upload_transcodes_when_remux_to_mp4_is_impossible(
    client: TestClient, incompatible_mkv: bytes
) -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("clip.mkv", incompatible_mkv, "video/x-matroska")},
    )

    assert response.status_code == 201, response.text
    video = response.json()
    video_dir = client.app.state.config.videos_dir / video["id"]
    assert (video_dir / "original.mp4").is_file()
    assert not (video_dir / "upload.mkv").exists()
    assert video["width"] == 160
    assert video["height"] == 120


def test_upload_rejects_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"not a video", "text/plain")},
    )

    assert response.status_code == 400
    assert "MP4" in response.json()["detail"]
    assert _video_dirs(client) == []
    assert client.get("/api/videos").json() == []


def test_upload_rejects_invalid_video_and_cleans_up(client: TestClient) -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("broken.mp4", b"not a video", "video/mp4")},
    )

    assert response.status_code == 400
    assert _video_dirs(client) == []
    assert client.get("/api/videos").json() == []


def test_upload_rejects_file_over_limit(
    client: TestClient, sample_mp4: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(videos, "MAX_UPLOAD_BYTES", 100)

    response = client.post(
        "/api/upload",
        files={"file": ("clip.mp4", sample_mp4, "video/mp4")},
    )

    assert response.status_code == 413
    assert "100" in response.json()["detail"]
    assert _video_dirs(client) == []


def test_upload_uses_basename_for_title_and_never_escapes_video_dir(
    client: TestClient, sample_mp4: bytes, tmp_path: Path
) -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("../../evil.mp4", sample_mp4, "video/mp4")},
    )

    assert response.status_code == 201, response.text
    video = response.json()
    assert video["title"] == "evil"
    video_dir = client.app.state.config.videos_dir / video["id"]
    assert (video_dir / "original.mp4").is_file()
    assert not (tmp_path / "data" / "evil.mp4").exists()
    meta = json.loads((video_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["original_name"] == "evil.mp4"


def test_uploading_the_same_file_twice_creates_two_videos(
    client: TestClient, sample_mp4: bytes
) -> None:
    first = client.post(
        "/api/upload", files={"file": ("clip.mp4", sample_mp4, "video/mp4")}
    )
    second = client.post(
        "/api/upload", files={"file": ("clip.mp4", sample_mp4, "video/mp4")}
    )

    assert first.status_code == second.status_code == 201
    first_video = first.json()
    second_video = second.json()
    assert first_video["id"] != second_video["id"]
    for video in (first_video, second_video):
        video_dir = client.app.state.config.videos_dir / video["id"]
        assert (video_dir / "original.mp4").is_file()
