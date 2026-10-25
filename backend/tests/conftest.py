from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.ids import new_id
from app.main import create_app
from app.models import Video
from app.services.urls import detect_platform


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(data_dir=tmp_path / "data", _env_file=None)


@pytest.fixture()
def client(app_config: AppConfig):
    app = create_app(app_config, start_worker=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def create_video(client: TestClient) -> Callable[..., Video]:
    def _create(
        source_url: str = "https://www.youtube.com/shorts/x",
        title: str = "Test video",
        **overrides,
    ) -> Video:
        video_id = overrides.pop("id", new_id())
        video_dir = client.app.state.config.videos_dir / video_id
        video_dir.mkdir(parents=True, exist_ok=True)
        video = Video(
            id=video_id,
            source_url=source_url,
            platform=detect_platform(source_url),
            title=title,
            dir_path=str(video_dir),
            file_path=str(video_dir / "original.mp4"),
            thumb_path=str(video_dir / "thumb.jpg"),
            status=overrides.pop("status", "ready"),
            **overrides,
        )
        with client.app.state.session_factory() as session:
            session.add(video)
            session.commit()
        return video

    return _create
