from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.languages import (
    normalize_source_language,
    normalize_target_language,
)
from app.services.urls import validate_url

LogoPosition = Literal["tl", "tr", "bl", "br"]
SubtitlePosition = Literal["bottom", "top", "center"]
RenderPreset = Literal["logo", "logo_subtitle", "full"]
TTS_VOICE_PATTERN = r"^[A-Za-z]{2,3}-[A-Za-z]{2,4}-[A-Za-z0-9]+Neural$"
TTS_RATE_PATTERN = r"^[+-]\d{1,3}%$"


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
    output_version: int
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
    render_preset: RenderPreset
    subtitle_font: str
    subtitle_size: int
    subtitle_position: SubtitlePosition
    target_language: str
    whisper_model: str
    cookies_browser: str


class SettingsUpdate(BaseModel):
    logo_position: LogoPosition | None = None
    logo_scale_pct: int | None = Field(default=None, ge=1, le=100)
    logo_opacity: float | None = Field(default=None, ge=0, le=1)
    logo_margin_px: int | None = Field(default=None, ge=0, le=500)
    tts_engine: str | None = None
    tts_voice: str | None = Field(
        default=None, pattern=TTS_VOICE_PATTERN, max_length=64
    )
    tts_rate: str | None = Field(default=None, pattern=TTS_RATE_PATTERN, max_length=8)
    render_preset: RenderPreset | None = None
    subtitle_font: str | None = None
    subtitle_size: int | None = Field(default=None, ge=8, le=200)
    subtitle_position: SubtitlePosition | None = None
    target_language: str | None = Field(default=None, max_length=20)
    whisper_model: str | None = None
    cookies_browser: str | None = None

    @field_validator("target_language")
    @classmethod
    def _validate_target_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_target_language(value)


class RenderRequest(BaseModel):
    logo: bool = True
    subtitle: bool = False
    voice: bool = False
    keep_original_audio: Literal["mute", "duck", "keep"] = "keep"


class SubtitleSegmentIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        stripped = " ".join(value.split())
        if not stripped:
            raise ValueError("Nội dung phụ đề không được để trống")
        return stripped

    @model_validator(mode="after")
    def _check_timing(self) -> "SubtitleSegmentIn":
        if self.end <= self.start:
            raise ValueError("Thời điểm kết thúc phải sau thời điểm bắt đầu")
        return self


class SubtitleRead(BaseModel):
    language: str
    target_language: str
    translated: bool
    segments: list[SubtitleSegmentIn]


class SubtitleUpdate(BaseModel):
    segments: list[SubtitleSegmentIn] = Field(max_length=2000)


class TranscribeRequest(BaseModel):
    translate: bool = False
    source_language: str | None = Field(default=None, max_length=20)
    target_language: str | None = Field(default=None, max_length=20)

    @field_validator("source_language")
    @classmethod
    def _validate_source_language(cls, value: str | None) -> str | None:
        return normalize_source_language(value)

    @field_validator("target_language")
    @classmethod
    def _validate_target_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_target_language(value)


class CoverRegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    x: float
    y: float
    width: float
    height: float


class CoverRegionPayload(BaseModel):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check_bounds(self) -> "CoverRegionPayload":
        if self.x + self.width > 1 + 1e-9:
            raise ValueError("Vùng che vượt quá chiều rộng video")
        if self.y + self.height > 1 + 1e-9:
            raise ValueError("Vùng che vượt quá chiều cao video")
        return self


class SampleFrameRead(BaseModel):
    time: float
    url: str


class SampleFramesRead(BaseModel):
    frames: list[SampleFrameRead]
    region: CoverRegionRead | None = None


class TtsRequest(BaseModel):
    voice: str | None = Field(
        default=None, pattern=TTS_VOICE_PATTERN, max_length=64
    )
    rate: str | None = Field(default=None, pattern=TTS_RATE_PATTERN, max_length=8)


class TtsPreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    voice: str = Field(pattern=TTS_VOICE_PATTERN, max_length=64)
    rate: str = Field(pattern=TTS_RATE_PATTERN, max_length=8)

    @field_validator("text")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Nội dung nghe thử không được để trống")
        return normalized


class TranslateRequest(BaseModel):
    target_language: str | None = Field(default=None, max_length=20)

    @field_validator("target_language")
    @classmethod
    def _validate_target_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_target_language(value)
