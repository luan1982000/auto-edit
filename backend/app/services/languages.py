"""Supported source/target languages and their normalized codes."""

from __future__ import annotations

SOURCE_LANGUAGES: dict[str, str] = {
    "vi": "Tiếng Việt",
    "en": "Tiếng Anh",
    "zh": "Tiếng Trung (Giản thể)",
    "ja": "Tiếng Nhật",
    "ko": "Tiếng Hàn",
    "th": "Tiếng Thái",
    "id": "Tiếng Indonesia",
    "ms": "Tiếng Mã Lai",
    "tl": "Tiếng Philippines",
    "fr": "Tiếng Pháp",
    "de": "Tiếng Đức",
    "es": "Tiếng Tây Ban Nha",
    "pt": "Tiếng Bồ Đào Nha",
    "it": "Tiếng Ý",
    "ru": "Tiếng Nga",
    "ar": "Tiếng Ả Rập",
    "hi": "Tiếng Hindi",
    "tr": "Tiếng Thổ Nhĩ Kỳ",
    "nl": "Tiếng Hà Lan",
    "pl": "Tiếng Ba Lan",
    "uk": "Tiếng Ukraine",
    "lo": "Tiếng Lào",
    "km": "Tiếng Khmer",
    "my": "Tiếng Myanmar",
}

# Translation can additionally target Traditional Chinese; Whisper has one
# Chinese model code, so the extra variant is target-only.
TARGET_LANGUAGES: dict[str, str] = {
    **SOURCE_LANGUAGES,
    "zh-Hant": "Tiếng Trung (Phồn thể)",
}


def _match_supported(value: str, supported: dict[str, str], label: str) -> str:
    code = value.strip()
    for candidate in supported:
        if candidate.lower() == code.lower():
            return candidate
    raise ValueError(f"{label} không được hỗ trợ: {value.strip()}")


def normalize_source_language(value: str | None) -> str | None:
    """Return a supported Whisper language code, or `None` to auto-detect."""
    if value is None:
        return None
    code = value.strip()
    if not code or code.lower() == "auto":
        return None
    return _match_supported(code, SOURCE_LANGUAGES, "Ngôn ngữ nguồn")


def normalize_target_language(value: str) -> str:
    """Return a supported translation target code."""
    if not value.strip():
        raise ValueError("Ngôn ngữ đích không được để trống")
    return _match_supported(value, TARGET_LANGUAGES, "Ngôn ngữ đích")
