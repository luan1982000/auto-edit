import pytest

from app.services.languages import (
    SOURCE_LANGUAGES,
    TARGET_LANGUAGES,
    normalize_source_language,
    normalize_target_language,
)


def test_language_catalogs_offer_vietnamese_and_english() -> None:
    assert SOURCE_LANGUAGES["vi"] == "Tiếng Việt"
    assert TARGET_LANGUAGES["en"] == "Tiếng Anh"
    assert TARGET_LANGUAGES["zh-Hant"] == "Tiếng Trung (Phồn thể)"


@pytest.mark.parametrize("value", [None, "", "   ", "auto", "AUTO"])
def test_source_auto_or_blank_means_detect_the_language(value: str | None) -> None:
    assert normalize_source_language(value) is None


def test_source_language_is_trimmed_and_case_insensitive() -> None:
    assert normalize_source_language("  VI ") == "vi"
    assert normalize_source_language("zh") == "zh"


def test_source_language_rejects_unknown_codes() -> None:
    with pytest.raises(ValueError, match="(?i)ngôn ngữ nguồn"):
        normalize_source_language("xx")


def test_target_language_is_trimmed_and_case_insensitive() -> None:
    assert normalize_target_language(" EN ") == "en"
    assert normalize_target_language("zh-hant") == "zh-Hant"


@pytest.mark.parametrize("value", ["", "   "])
def test_target_language_rejects_blank_values(value: str) -> None:
    with pytest.raises(ValueError, match="(?i)ngôn ngữ đích"):
        normalize_target_language(value)


def test_target_language_rejects_unknown_codes() -> None:
    with pytest.raises(ValueError, match="(?i)ngôn ngữ đích"):
        normalize_target_language("auto")
