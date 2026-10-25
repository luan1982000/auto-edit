from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp (SQLModel requires tz info for datetime fields)."""
    return datetime.now(UTC)


class Video(SQLModel, table=True):
    id: str = Field(primary_key=True)
    source_url: str = Field(index=True)
    platform: str = "other"
    title: str = ""
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    dir_path: str = ""
    file_path: str = ""
    thumb_path: str = ""
    status: str = "downloading"  # downloading | ready | failed
    error: str | None = None
    has_subtitle: bool = False
    has_voice: bool = False
    has_output: bool = False
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)
    video_id: str | None = Field(default=None, foreign_key="video.id", index=True)
    type: str = "download"  # download | transcribe | translate | tts | render
    status: str = "pending"  # pending | running | done | failed
    progress: int = 0
    message: str = ""
    error: str | None = None
    params: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: datetime | None = None


class AppSettings(SQLModel, table=True):
    __tablename__ = "settings"

    id: int = Field(default=1, primary_key=True)
    logo_path: str = ""
    logo_position: str = "tr"  # tl | tr | bl | br
    logo_scale_pct: int = 15
    logo_opacity: float = 1.0
    logo_margin_px: int = 24

    tts_engine: str = "edge"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    tts_rate: str = "+0%"

    subtitle_font: str = ""
    subtitle_size: int = 18
    subtitle_position: str = "bottom"
    target_language: str = "vi"

    whisper_model: str = "small"
    cookies_browser: str = ""
