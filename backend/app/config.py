from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class AppConfig(BaseSettings):
    """Runtime configuration. Values may come from the repo-root `.env` file."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    data_dir: Path = ROOT_DIR / "data"
    anthropic_api_key: str = ""
    douyin_fallback_url: str = ""

    job_timeout_sec: int = 900
    poll_interval_sec: float = 0.5

    bind_host: str = "127.0.0.1"
    bind_port: int = 8000

    def model_post_init(self, __context: object) -> None:
        if not self.data_dir.is_absolute():
            self.data_dir = (ROOT_DIR / self.data_dir).resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"
