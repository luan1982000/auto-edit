from pathlib import Path

from fastapi.testclient import TestClient

from app.ids import new_id
from app.models import Job, Video
from app.services.subtitles import (
    SubtitleData,
    SubtitleSegment,
    save_subtitle_data,
)
from app.services.tts import TTSError


def _video_dir(client: TestClient, video: Video) -> Path:
    return client.app.state.config.videos_dir / video.id


def _write_source(client: TestClient, video: Video) -> Path:
    path = Path(video.file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake video")
    return path


def _write_subtitle(client: TestClient, video: Video) -> SubtitleData:
    data = SubtitleData(
        language="en",
        target_language="vi",
        translated=True,
        segments=[SubtitleSegment(0.0, 1.5, "Xin chào")],
        source_segments=[SubtitleSegment(0.0, 1.5, "Hello")],
    )
    save_subtitle_data(_video_dir(client, video) / "subtitle.json", data)
    return data


def test_tts_creates_a_job_with_snapshotted_voice_and_rate(
    client: TestClient, create_video
) -> None:
    video = create_video()
    _write_source(client, video)
    _write_subtitle(client, video)
    assert (
        client.put(
            "/api/settings",
            json={"tts_voice": "vi-VN-NamMinhNeural", "tts_rate": "+5%"},
        ).status_code
        == 200
    )

    response = client.post(f"/api/videos/{video.id}/tts", json={})
    assert response.status_code == 202
    body = response.json()
    assert body["type"] == "tts"
    assert body["status"] == "pending"
    assert body["params"] == {"voice": "vi-VN-NamMinhNeural", "rate": "+5%"}

    response = client.post(
        f"/api/videos/{video.id}/tts",
        json={"voice": "vi-VN-HoaiMyNeural", "rate": "-10%"},
    )
    assert response.status_code == 409  # the first job is still pending


def test_tts_payload_overrides_saved_settings(client: TestClient, create_video) -> None:
    video = create_video()
    _write_source(client, video)
    _write_subtitle(client, video)

    response = client.post(
        f"/api/videos/{video.id}/tts",
        json={"voice": "vi-VN-NamMinhNeural", "rate": "-10%"},
    )
    assert response.status_code == 202
    assert response.json()["params"] == {
        "voice": "vi-VN-NamMinhNeural",
        "rate": "-10%",
    }


def test_tts_requires_ready_source_and_subtitles(
    client: TestClient, create_video
) -> None:
    unready = create_video(status="downloading")
    _write_source(client, unready)
    assert client.post(f"/api/videos/{unready.id}/tts", json={}).status_code == 409

    no_source = create_video()
    response = client.post(f"/api/videos/{no_source.id}/tts", json={})
    assert response.status_code == 409
    assert "file video" in response.json()["detail"]

    no_subtitle = create_video()
    _write_source(client, no_subtitle)
    response = client.post(f"/api/videos/{no_subtitle.id}/tts", json={})
    assert response.status_code == 400
    assert "phụ đề" in response.json()["detail"]


def test_tts_conflicts_with_an_active_tts_job(client: TestClient, create_video) -> None:
    video = create_video()
    _write_source(client, video)
    _write_subtitle(client, video)
    with client.app.state.session_factory() as session:
        session.add(Job(id=new_id(), video_id=video.id, type="tts", status="running"))
        session.commit()

    response = client.post(f"/api/videos/{video.id}/tts", json={})
    assert response.status_code == 409


def test_tts_rejects_invalid_voice_override(client: TestClient, create_video) -> None:
    video = create_video()
    response = client.post(
        f"/api/videos/{video.id}/tts", json={"voice": "../evil", "rate": "10%"}
    )
    assert response.status_code == 422


class FakeEngine:
    calls: list[dict[str, str]] = []
    error: str | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    def synthesize(self, text: str, voice: str, rate: str, out_path: Path) -> Path:
        type(self).calls.append({"text": text, "voice": voice, "rate": rate})
        if type(self).error is not None:
            raise TTSError(type(self).error)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"ID3 preview")
        return out_path


def test_preview_returns_audio(
    client: TestClient, monkeypatch
) -> None:
    FakeEngine.calls = []
    FakeEngine.error = None
    monkeypatch.setattr("app.routers.tts.EdgeTTSEngine", FakeEngine)

    response = client.post(
        "/api/tts/preview",
        json={
            "text": "  Xin   chào  ",
            "voice": "vi-VN-HoaiMyNeural",
            "rate": "+5%",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"ID3 preview"
    assert FakeEngine.calls == [
        {
            "text": "Xin chào",
            "voice": "vi-VN-HoaiMyNeural",
            "rate": "+5%",
        }
    ]
    preview = client.app.state.config.assets_dir / "tts_preview.mp3"
    assert preview.read_bytes() == b"ID3 preview"


def test_preview_rejects_bad_input(client: TestClient) -> None:
    base = {
        "text": "Xin chào",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "+0%",
    }
    assert client.post("/api/tts/preview", json={**base, "text": "   "}).status_code == 422
    assert client.post("/api/tts/preview", json={**base, "text": "x" * 1001}).status_code == 422
    assert client.post("/api/tts/preview", json={**base, "voice": "../evil"}).status_code == 422
    assert client.post("/api/tts/preview", json={**base, "rate": "fast"}).status_code == 422


def test_preview_reports_tts_failure_as_bad_gateway(
    client: TestClient, monkeypatch
) -> None:
    FakeEngine.calls = []
    FakeEngine.error = "edge-tts lỗi: network down"
    monkeypatch.setattr("app.routers.tts.EdgeTTSEngine", FakeEngine)

    response = client.post(
        "/api/tts/preview",
        json={
            "text": "Xin chào",
            "voice": "vi-VN-HoaiMyNeural",
            "rate": "+0%",
        },
    )

    assert response.status_code == 502
    assert "network down" in response.json()["detail"]
    assert not (client.app.state.config.assets_dir / "tts_preview.mp3").exists()


def test_settings_validate_tts_voice_and_rate(client: TestClient) -> None:
    assert client.put("/api/settings", json={"tts_voice": "../evil"}).status_code == 422
    assert client.put("/api/settings", json={"tts_rate": "fast"}).status_code == 422
    response = client.put(
        "/api/settings",
        json={"tts_voice": "vi-VN-NamMinhNeural", "tts_rate": "-10%"},
    )
    assert response.status_code == 200
    assert response.json()["tts_voice"] == "vi-VN-NamMinhNeural"
    assert response.json()["tts_rate"] == "-10%"
