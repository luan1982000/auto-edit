from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.urls import validate_url

LogoPosition = Literal["tl", "tr", "bl", "br"]
SubtitlePosition = Literal["bottom", "top", "center"]


class DownloadRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=50)
    force: bool = False

    @field_validator("urls")
    @classmethod
    def _validate_urls(cls, urls: list[str]) -> list[str]:
        return [validate_url(url) for url in urls]


class DuplicateInfo(BaseModel):
    url: str
    video_id: str
    title: str
    status: str


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str | None
    type: str
    status: str
    progress: int
    message: str
    error: str | None
    params: dict
    created_at: datetime
    finished_at: datetime | None


class DownloadResponse(BaseModel):
    jobs: list[JobRead]
    duplicates: list[DuplicateInfo]


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_url: str
    platform: str
    title: str
    duration_sec: float
    width: int
    height: int
    status: str
    error: str | None
    has_subtitle: bool
    has_voice: bool
    has_output: bool
    created_at: datetime


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    logo_path: str
    logo_position: LogoPosition
    logo_scale_pct: int
    logo_opacity: float
    logo_margin_px: int
    tts_engine: str
    tts_voice: str
    tts_rate: str
    subtitle_font: str
    subtitle_size: int
    subtitle_position: SubtitlePosition
    target_language: str
    whisper_model: str
    cookies_browser: str


class SettingsUpdate(BaseModel):
    logo_path: str | None = None
    logo_position: LogoPosition | None = None
    logo_scale_pct: int | None = Field(default=None, ge=1, le=100)
    logo_opacity: float | None = Field(default=None, ge=0, le=1)
    logo_margin_px: int | None = Field(default=None, ge=0, le=500)
    tts_engine: str | None = None
    tts_voice: str | None = None
    tts_rate: str | None = None
    subtitle_font: str | None = None
    subtitle_size: int | None = Field(default=None, ge=8, le=200)
    subtitle_position: SubtitlePosition | None = None
    target_language: str | None = None
    whisper_model: str | None = None
    cookies_browser: str | None = None
