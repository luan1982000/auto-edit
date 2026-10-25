import base64
from pathlib import Path

from fastapi.testclient import TestClient

from app.ids import new_id
from app.models import Job

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
)
MAX_LOGO_BYTES = 5 * 1024 * 1024


def _upload_logo(client: TestClient, data: bytes = PNG_1PX, name: str = "logo.png"):
    return client.post(
        "/api/settings/logo",
        files={"file": (name, data, "image/png")},
    )


def test_upload_logo_saves_file_and_updates_settings(client: TestClient) -> None:
    response = _upload_logo(client)
    assert response.status_code == 200
    logo_path = response.json()["logo_path"]
    assert logo_path
    path = Path(logo_path)
    assert path.is_file()
    assert path.resolve().is_relative_to(client.app.state.config.assets_dir.resolve())
    assert path.read_bytes() == PNG_1PX

    preview = client.get("/api/settings/logo")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content == PNG_1PX


def test_upload_logo_rejects_non_image_payload(client: TestClient) -> None:
    response = _upload_logo(client, b"<svg onload=alert(1)>")
    assert response.status_code == 400
    assert "logo" in response.json()["detail"].lower()


def test_upload_logo_rejects_oversized_file(client: TestClient) -> None:
    response = _upload_logo(client, PNG_1PX + b"\x00" * MAX_LOGO_BYTES)
    assert response.status_code == 413


def test_delete_logo_removes_file_and_clears_setting(client: TestClient) -> None:
    logo_path = Path(_upload_logo(client).json()["logo_path"])
    response = client.delete("/api/settings/logo")
    assert response.status_code == 200
    assert response.json()["logo_path"] == ""
    assert not logo_path.exists()
    assert client.get("/api/settings/logo").status_code == 404


def test_get_logo_returns_404_when_not_configured(client: TestClient) -> None:
    assert client.get("/api/settings/logo").status_code == 404


def test_settings_update_cannot_set_arbitrary_logo_path(client: TestClient) -> None:
    response = client.put("/api/settings", json={"logo_path": "/etc/passwd"})
    assert response.status_code == 200
    assert response.json()["logo_path"] == ""


def test_render_creates_pending_job(client: TestClient, create_video) -> None:
    video = create_video(width=1920, height=1080, duration_sec=2.5)
    Path(video.file_path).write_bytes(b"not-a-real-video")

    response = client.post(
        f"/api/videos/{video.id}/render",
        json={"logo": False, "subtitle": False, "voice": False, "keep_original_audio": "keep"},
    )
    assert response.status_code == 202
    job = response.json()
    assert job["type"] == "render"
    assert job["status"] == "pending"
    assert job["video_id"] == video.id
    assert job["params"] == {
        "logo": False,
        "subtitle": False,
        "voice": False,
        "keep_original_audio": "keep",
    }


def test_render_rejects_video_that_is_not_ready(client: TestClient, create_video) -> None:
    video = create_video(status="downloading")
    response = client.post(
        f"/api/videos/{video.id}/render",
        json={"logo": False, "subtitle": False, "voice": False, "keep_original_audio": "keep"},
    )
    assert response.status_code == 409


def test_render_requires_uploaded_logo_when_logo_enabled(
    client: TestClient, create_video
) -> None:
    video = create_video(width=1920, height=1080)
    Path(video.file_path).write_bytes(b"x")
    response = client.post(
        f"/api/videos/{video.id}/render",
        json={"logo": True, "subtitle": False, "voice": False, "keep_original_audio": "keep"},
    )
    assert response.status_code == 400
    assert "logo" in response.json()["detail"].lower()


def test_render_is_rejected_while_another_render_is_running(
    client: TestClient, create_video
) -> None:
    video = create_video()
    Path(video.file_path).write_bytes(b"x")
    with client.app.state.session_factory() as session:
        session.add(Job(id=new_id(), video_id=video.id, type="render", status="running"))
        session.commit()

    response = client.post(
        f"/api/videos/{video.id}/render",
        json={"logo": False, "subtitle": False, "voice": False, "keep_original_audio": "keep"},
    )
    assert response.status_code == 409


def test_render_requires_subtitles_when_requested(client: TestClient, create_video) -> None:
    video = create_video()
    Path(video.file_path).write_bytes(b"x")
    response = client.post(
        f"/api/videos/{video.id}/render",
        json={
            "logo": False,
            "subtitle": True,
            "voice": False,
            "keep_original_audio": "keep",
        },
    )
    assert response.status_code == 400
    assert "phụ đề" in response.json()["detail"].lower()
