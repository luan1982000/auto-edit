import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.models import Video


def _write_real_video(
    client: TestClient, video: Video, *, duration: float = 2.0
) -> Path:
    path = Path(video.file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10",
            "-t",
            str(duration),
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


def test_sample_frames_returns_three_displayable_images(
    client: TestClient, create_video
) -> None:
    video = create_video(duration_sec=2.0, width=320, height=240)
    _write_real_video(client, video, duration=2.0)

    response = client.post(f"/api/videos/{video.id}/sample-frames")

    assert response.status_code == 200
    payload = response.json()
    assert payload["region"] is None
    assert [round(frame["time"], 2) for frame in payload["frames"]] == [0.3, 1.0, 1.7]
    assert [frame["url"] for frame in payload["frames"]] == [
        f"/api/videos/{video.id}/frames/sample-1.jpg",
        f"/api/videos/{video.id}/frames/sample-2.jpg",
        f"/api/videos/{video.id}/frames/sample-3.jpg",
    ]
    for frame in payload["frames"]:
        image = client.get(frame["url"])
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/jpeg"
        assert image.headers["cache-control"] == "no-store"
        assert image.content[:2] == b"\xff\xd8"

    frames_dir = client.app.state.config.videos_dir / video.id / "frames"
    assert sorted(path.name for path in frames_dir.iterdir()) == [
        "sample-1.jpg",
        "sample-2.jpg",
        "sample-3.jpg",
    ]


def test_sample_frames_includes_the_saved_cover_region(
    client: TestClient, create_video
) -> None:
    video = create_video(duration_sec=2.0, width=320, height=240)
    _write_real_video(client, video)
    region = {"x": 0.05, "y": 0.75, "width": 0.9, "height": 0.2}
    assert client.put(f"/api/videos/{video.id}/cover-region", json=region).status_code == 200

    response = client.post(f"/api/videos/{video.id}/sample-frames")

    assert response.status_code == 200
    assert response.json()["region"] == region


def test_sample_frames_requires_a_ready_video_with_source(
    client: TestClient, create_video
) -> None:
    downloading = create_video(status="downloading")
    assert client.post(f"/api/videos/{downloading.id}/sample-frames").status_code == 409

    missing_source = create_video()
    response = client.post(f"/api/videos/{missing_source.id}/sample-frames")
    assert response.status_code == 409
    assert "file video" in response.json()["detail"]


def test_sample_frames_reports_ffmpeg_failure(client: TestClient, create_video) -> None:
    video = create_video(duration_sec=2.0)
    Path(video.file_path).write_bytes(b"not a video")

    response = client.post(f"/api/videos/{video.id}/sample-frames")

    assert response.status_code == 500
    assert "ảnh mẫu" in response.json()["detail"]


def test_sample_frame_endpoint_only_serves_generated_names(
    client: TestClient, create_video
) -> None:
    video = create_video()
    _write_real_video(client, video)

    assert (
        client.get(f"/api/videos/{video.id}/frames/sample-1.jpg").status_code == 404
    )
    assert (
        client.get(f"/api/videos/{video.id}/frames/subtitle.json").status_code == 404
    )
    assert client.get(f"/api/videos/{video.id}/frames/..%2Fsubtitle.json").status_code == 404


def test_cover_region_crud(client: TestClient, create_video) -> None:
    video = create_video()
    url = f"/api/videos/{video.id}/cover-region"

    missing = client.get(url)
    assert missing.status_code == 200
    assert missing.json() is None

    region = {"x": 0.05, "y": 0.75, "width": 0.9, "height": 0.2}
    saved = client.put(url, json=region)
    assert saved.status_code == 200
    assert saved.json() == region
    assert client.get(url).json() == region

    deleted = client.delete(url)
    assert deleted.status_code == 204
    assert client.get(url).json() is None


def test_cover_region_validates_the_rectangle(client: TestClient, create_video) -> None:
    video = create_video()
    url = f"/api/videos/{video.id}/cover-region"

    for payload in (
        {"x": -0.1, "y": 0.7, "width": 0.8, "height": 0.2},
        {"x": 0.1, "y": 0.7, "width": 0.0, "height": 0.2},
        {"x": 0.8, "y": 0.7, "width": 0.5, "height": 0.2},
        {"x": 0.1, "y": 0.9, "width": 0.8, "height": 0.2},
    ):
        response = client.put(url, json=payload)
        assert response.status_code == 422, payload


def test_cover_region_corrupt_file_reports_an_error(
    client: TestClient, create_video
) -> None:
    video = create_video()
    (client.app.state.config.videos_dir / video.id / "cover_region.json").write_text(
        "not json", encoding="utf-8"
    )

    response = client.get(f"/api/videos/{video.id}/cover-region")

    assert response.status_code == 422
    assert "Vùng che" in response.json()["detail"]


def test_region_endpoints_404_for_unknown_video(client: TestClient) -> None:
    assert client.post("/api/videos/nope/sample-frames").status_code == 404
    assert client.get("/api/videos/nope/frames/sample-1.jpg").status_code == 404
    assert client.get("/api/videos/nope/cover-region").status_code == 404
    assert (
        client.put(
            "/api/videos/nope/cover-region",
            json={"x": 0.1, "y": 0.7, "width": 0.8, "height": 0.2},
        ).status_code
        == 404
    )
    assert client.delete("/api/videos/nope/cover-region").status_code == 404
