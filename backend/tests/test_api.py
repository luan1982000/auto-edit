from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import select

from app.ids import new_id
from app.models import Job
from app.routers import system
from app.services.updater import UpdateResult

URL_A = "https://www.youtube.com/shorts/aaaaaaaaaaa"
URL_B = "https://www.facebook.com/reel/1234567890"


def test_list_videos_starts_empty(client: TestClient) -> None:
    response = client.get("/api/videos")
    assert response.status_code == 200
    assert response.json() == []


def test_download_rejects_non_http_url(client: TestClient) -> None:
    response = client.post("/api/download", json={"urls": ["file:///etc/passwd"]})
    assert response.status_code == 422


def test_download_rejects_empty_list(client: TestClient) -> None:
    response = client.post("/api/download", json={"urls": []})
    assert response.status_code == 422


def test_download_creates_video_and_pending_job(client: TestClient) -> None:
    response = client.post("/api/download", json={"urls": [URL_A]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["duplicates"] == []
    assert len(payload["jobs"]) == 1

    job = payload["jobs"][0]
    assert job["type"] == "download"
    assert job["status"] == "pending"
    assert job["progress"] == 0
    assert job["params"] == {"url": URL_A}

    video = client.get(f"/api/videos/{job['video_id']}").json()
    assert video["status"] == "downloading"
    assert video["platform"] == "youtube"
    assert video["source_url"] == URL_A


def test_download_warns_on_duplicate_without_force(client: TestClient, create_video) -> None:
    video = create_video(source_url=URL_A, title="Old download")

    response = client.post("/api/download", json={"urls": [URL_A]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs"] == []
    assert payload["duplicates"] == [
        {"url": URL_A, "video_id": video.id, "title": "Old download", "status": "ready"}
    ]


def test_download_force_allows_duplicate(client: TestClient, create_video) -> None:
    old = create_video(source_url=URL_A)
    response = client.post("/api/download", json={"urls": [URL_A], "force": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["duplicates"] == []
    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["video_id"] != old.id


def test_get_video_returns_404_for_unknown_id(client: TestClient) -> None:
    assert client.get("/api/videos/does-not-exist").status_code == 404


def test_videos_are_listed_newest_first(client: TestClient, create_video) -> None:
    first = create_video(title="First", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    second = create_video(title="Second", created_at=datetime(2026, 2, 1, tzinfo=UTC))
    videos = client.get("/api/videos").json()
    assert [v["id"] for v in videos] == [second.id, first.id]


def test_delete_video_removes_record_folder_and_jobs(
    client: TestClient, create_video
) -> None:
    video = create_video()
    video_dir = Path(video.dir_path)
    (video_dir / "original.mp4").write_bytes(b"data")
    with client.app.state.session_factory() as session:
        session.add(Job(id=new_id(), video_id=video.id, type="render"))
        session.commit()

    response = client.delete(f"/api/videos/{video.id}")
    assert response.status_code == 204
    assert not video_dir.exists()
    assert client.get(f"/api/videos/{video.id}").status_code == 404
    with client.app.state.session_factory() as session:
        assert session.exec(select(Job).where(Job.video_id == video.id)).all() == []


def test_delete_video_rejects_path_traversal_id(client: TestClient) -> None:
    # The router (or Starlette's path normalization) must reject it; never delete outside data/.
    assert client.delete("/api/videos/..%2F..%2Fetc").status_code in (404, 405)


def test_stream_original_supports_range_requests(client: TestClient, create_video) -> None:
    video = create_video()
    Path(video.file_path).write_bytes(b"0123456789")

    response = client.get(
        f"/api/videos/{video.id}/file?variant=original",
        headers={"Range": "bytes=2-5"},
    )
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"


def test_stream_output_returns_404_when_missing(client: TestClient, create_video) -> None:
    video = create_video()
    response = client.get(f"/api/videos/{video.id}/file?variant=output")
    assert response.status_code == 404


def test_stream_rejects_unknown_variant(client: TestClient, create_video) -> None:
    video = create_video()
    assert client.get(f"/api/videos/{video.id}/file?variant=../../etc").status_code == 422


def test_thumbnail_returns_404_when_missing(client: TestClient, create_video) -> None:
    video = create_video()
    assert client.get(f"/api/videos/{video.id}/thumb").status_code == 404


def test_thumbnail_served_when_present(client: TestClient, create_video) -> None:
    video = create_video()
    Path(video.thumb_path).write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    response = client.get(f"/api/videos/{video.id}/thumb")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


def test_jobs_filter_by_status(client: TestClient) -> None:
    payload = client.post("/api/download", json={"urls": [URL_A, URL_B]}).json()
    failed_id = payload["jobs"][0]["id"]
    with client.app.state.session_factory() as session:
        job = session.get(Job, failed_id)
        job.status = "failed"
        session.add(job)
        session.commit()

    failed = client.get("/api/jobs?status=failed").json()
    assert [j["id"] for j in failed] == [failed_id]
    pending = client.get("/api/jobs?status=pending").json()
    assert [j["id"] for j in pending] == [payload["jobs"][1]["id"]]


def test_job_detail_returns_404_for_unknown_id(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").status_code == 404


def test_settings_defaults_and_update(client: TestClient) -> None:
    defaults = client.get("/api/settings").json()
    assert defaults["tts_voice"] == "vi-VN-HoaiMyNeural"
    assert defaults["whisper_model"] == "small"
    assert defaults["cookies_browser"] == ""

    response = client.put(
        "/api/settings", json={"cookies_browser": "chrome", "target_language": "en"}
    )
    assert response.status_code == 200
    assert response.json()["cookies_browser"] == "chrome"

    updated = client.get("/api/settings").json()
    assert updated["cookies_browser"] == "chrome"
    assert updated["target_language"] == "en"
    assert updated["tts_voice"] == "vi-VN-HoaiMyNeural"


def test_settings_rejects_invalid_values(client: TestClient) -> None:
    assert client.put("/api/settings", json={"logo_position": "middle"}).status_code == 422
    assert client.put("/api/settings", json={"logo_opacity": 1.5}).status_code == 422


def test_health_reports_tool_status(client: TestClient) -> None:
    payload = client.get("/api/health").json()
    assert payload["ok"] is True
    assert payload["ffmpeg"] is True
    assert payload["yt_dlp"] is True


def test_update_ytdlp_endpoint_returns_result(
    client: TestClient, monkeypatch
) -> None:
    fake = UpdateResult(
        ok=True,
        output="Successfully installed yt-dlp",
        version="2026.10.1",
        restart_required=True,
    )
    monkeypatch.setattr(system, "run_update", lambda: fake)

    response = client.post("/api/system/update-ytdlp")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "output": "Successfully installed yt-dlp",
        "version": "2026.10.1",
        "restart_required": True,
    }
    # The GET hits the SPA/API fallback, so 404 is expected; 405 is also acceptable.
    assert client.get("/api/system/update-ytdlp").status_code in (404, 405)
