"""Safe handling of uploaded assets (currently the logo)."""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig

MAX_LOGO_BYTES = 5 * 1024 * 1024
IMAGE_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """Return (extension, media type) from magic bytes, or None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def save_logo(config: AppConfig, data: bytes) -> Path:
    """Validate and atomically store a logo under DATA_DIR/assets."""
    sniffed = sniff_image(data)
    if sniffed is None:
        raise ValueError("File logo phải là PNG, JPEG hoặc WEBP")
    extension, _ = sniffed
    config.assets_dir.mkdir(parents=True, exist_ok=True)
    target = config.assets_dir / f"logo.{extension}"
    temporary = config.assets_dir / f".logo.{extension}.tmp"
    temporary.write_bytes(data)
    temporary.replace(target)
    for stale in config.assets_dir.glob("logo.*"):
        if stale != target:
            stale.unlink(missing_ok=True)
    return target


def resolve_logo(config: AppConfig, stored: str) -> Path | None:
    """Only trust a stored logo path that stays inside DATA_DIR/assets."""
    if not stored:
        return None
    try:
        resolved = Path(stored).resolve()
    except OSError:
        return None
    assets_dir = config.assets_dir.resolve()
    if not resolved.is_relative_to(assets_dir) or not resolved.is_file():
        return None
    try:
        if sniff_image(resolved.read_bytes()[:16]) is None:
            return None
    except OSError:
        return None
    return resolved


def delete_logo_files(config: AppConfig) -> None:
    for stale in config.assets_dir.glob("logo.*"):
        stale.unlink(missing_ok=True)
