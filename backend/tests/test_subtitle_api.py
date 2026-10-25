from pathlib import Path

from fastapi.testclient import TestClient

from app.ids import new_id
from app.models import Job, Video
from app.services.subtitles import SubtitleData, SubtitleSegment, save_subtitle_data


def _video_dir(client: TestClient, video: Video) -> Path:
    return client.app.state.config.videos_dir / video.id


def _write_source(client: TestClient, video: Video) -> Path:
    path = Path(video.file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake video")
    return path


def _write_subtitle(client: TestClient, video: Video) -> SubtitleData:
    data = SubtitleData(
        language="zh",
        target_language="zh",
        translated=False,
        segments=[SubtitleSegment(0.0, 1.5, "你好")],
        source_segments=[SubtitleSegment(0.0, 1.5, "你好")],
    )
    save_subtitle_data(_video_dir(client, video) / "subtitle.json", data)
    return data


def test_transcribe_creates_a_job_with_snapshotted_settings(
    client: TestClient, create_video
) -> None:
    video = create_video()
    _write_source(client, video)
    response = client.put(
        "/api/settings",
        json={"target_language": "en", "whisper_model": "medium"},
    )
    assert response.status_code == 200

    response = client.post(
        f"/api/videos/{video.id}/transcribe", json={"translate": True}
    )
    assert response.status_code == 202
    body = response.json()
    assert body["type"] == "transcribe"
    assert body["status"] == "pending"
    assert body["params"] == {
        "translate": True,
        "model": "medium",
        "target_language": "en",
    }

    jobs = client.get("/api/jobs", params={"video_id": video.id}).json()
    assert [job["id"] for job in jobs] == [body["id"]]


def test_transcribe_rejects_unready_or_missing_source(
    client: TestClient, create_video
) -> None:
    video = create_video(status="downloading")
    _write_source(client, video)
    response = client.post(f"/api/videos/{video.id}/transcribe", json={})
    assert response.status_code == 409

    ready = create_video()
    response = client.post(f"/api/videos/{ready.id}/transcribe", json={})
    assert response.status_code == 409
    assert "file video" in response.json()["detail"]


def test_transcribe_conflicts_with_an_active_subtitle_job(
    client: TestClient, create_video
) -> None:
    video = create_video()
    _write_source(client, video)
    with client.app.state.session_factory() as session:
        session.add(
            Job(id=new_id(), video_id=video.id, type="translate", status="running")
        )
        session.commit()
    response = client.post(f"/api/videos/{video.id}/transcribe", json={})
    assert response.status_code == 409


def test_translate_requires_an_existing_subtitle(
    client: TestClient, create_video
) -> None:
    video = create_video()
    response = client.post(f"/api/videos/{video.id}/translate", json={})
    assert response.status_code == 404

    _write_subtitle(client, video)
    response = client.post(
        f"/api/videos/{video.id}/translate", json={"target_language": "en"}
    )
    assert response.status_code == 202
    assert response.json()["params"] == {"target_language": "en"}


def test_get_subtitle_returns_saved_data(client: TestClient, create_video) -> None:
    video = create_video()
    _write_subtitle(client, video)
    response = client.get(f"/api/videos/{video.id}/subtitle")
    assert response.status_code == 200
    assert response.json() == {
        "language": "zh",
        "target_language": "zh",
        "translated": False,
        "segments": [{"start": 0.0, "end": 1.5, "text": "你好"}],
    }

    missing = create_video()
    response = client.get(f"/api/videos/{missing.id}/subtitle")
    assert response.status_code == 404


def test_put_subtitle_saves_edits_and_updates_srt(
    client: TestClient, create_video
) -> None:
    video = create_video()
    _write_subtitle(client, video)
    payload = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "  Xin chào  "},
            {"start": 1.0, "end": 2.5, "text": "Thế giới"},
        ]
    }
    response = client.put(f"/api/videos/{video.id}/subtitle", json=payload)
    assert response.status_code == 200
    assert response.json()["segments"] == [
        {"start": 0.0, "end": 1.0, "text": "Xin chào"},
        {"start": 1.0, "end": 2.5, "text": "Thế giới"},
    ]
    video_dir = _video_dir(client, video)
    assert "Xin chào" in (video_dir / "subtitle.srt").read_text(encoding="utf-8")
    with client.app.state.session_factory() as session:
        assert session.get(Video, video.id).has_subtitle is True

    response = client.get(f"/api/videos/{video.id}/subtitle")
    assert response.json()["segments"][0]["text"] == "Xin chào"


def test_put_empty_subtitle_clears_the_flag(client: TestClient, create_video) -> None:
    video = create_video(has_subtitle=True)
    _write_subtitle(client, video)
    response = client.put(f"/api/videos/{video.id}/subtitle", json={"segments": []})
    assert response.status_code == 200
    with client.app.state.session_factory() as session:
        assert session.get(Video, video.id).has_subtitle is False


def test_put_subtitle_validates_timing_and_text(client: TestClient, create_video) -> None:
    video = create_video()
    _write_subtitle(client, video)
    bad = [
        {"segments": [{"start": 2.0, "end": 0.5, "text": "x"}]},
        {"segments": [{"start": -1.0, "end": 1.0, "text": "x"}]},
        {"segments": [{"start": 0.0, "end": 1.0, "text": "   "}]},
    ]
    for payload in bad:
        response = client.put(f"/api/videos/{video.id}/subtitle", json=payload)
        assert response.status_code == 422, payload


def test_put_subtitle_requires_existing_data(client: TestClient, create_video) -> None:
    video = create_video()
    response = client.put(
        f"/api/videos/{video.id}/subtitle",
        json={"segments": [{"start": 0.0, "end": 1.0, "text": "x"}]},
    )
    assert response.status_code == 404


def test_subtitle_endpoints_404_for_unknown_video(client: TestClient) -> None:
    assert client.get("/api/videos/nope/subtitle").status_code == 404
    assert (
        client.post("/api/videos/nope/transcribe", json={}).status_code == 404
    )
    assert client.post("/api/videos/nope/translate", json={}).status_code == 404
    assert (
        client.put(
            "/api/videos/nope/subtitle",
            json={"segments": [{"start": 0.0, "end": 1.0, "text": "x"}]},
        ).status_code
        == 404
    )


