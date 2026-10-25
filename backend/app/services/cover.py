"""Persist the normalized rectangle that covers burned-in source subtitles."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

COVER_FILE = "cover_region.json"


class CoverRegionError(RuntimeError):
    """Raised when the saved cover region cannot be read or is invalid."""


@dataclass(frozen=True)
class CoverRegion:
    """A rectangle in normalized 0..1 video coordinates."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("cover region values must be finite numbers")
        if self.x < 0 or self.y < 0:
            raise ValueError("cover region must start inside the video")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("cover region must have a positive size")
        if self.x + self.width > 1 + 1e-9 or self.y + self.height > 1 + 1e-9:
            raise ValueError("cover region must not extend past the video")

    def pixel_box(self, video_width: int, video_height: int) -> tuple[int, int, int, int]:
        """Return `(x, y, width, height)` pixels, clamped to the video frame."""
        if video_width <= 0 or video_height <= 0:
            raise ValueError("video dimensions must be positive")
        x = min(round(self.x * video_width), video_width - 1)
        y = min(round(self.y * video_height), video_height - 1)
        width = max(1, min(round(self.width * video_width), video_width - x))
        height = max(1, min(round(self.height * video_height), video_height - y))
        return x, y, width, height


def load_cover_region(video_dir: Path) -> CoverRegion | None:
    """Load the saved region, returning `None` when the user has not set one."""
    path = Path(video_dir) / COVER_FILE
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("expected an object")
        return CoverRegion(
            x=float(raw["x"]),
            y=float(raw["y"]),
            width=float(raw["width"]),
            height=float(raw["height"]),
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise CoverRegionError(f"Vùng che phụ đề cũ không hợp lệ: {exc}") from exc


def save_cover_region(video_dir: Path, region: CoverRegion | None) -> None:
    """Save a region atomically, or delete it when `region` is `None`."""
    path = Path(video_dir) / COVER_FILE
    if region is None:
        path.unlink(missing_ok=True)
        return
    payload = {
        "x": region.x,
        "y": region.y,
        "width": region.width,
        "height": region.height,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)
