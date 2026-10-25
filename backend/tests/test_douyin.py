from urllib.parse import parse_qs, urlparse

import pytest

from app.services.douyin import (
    douyin_hints,
    normalize_douyin_url,
    with_douyin_hint,
)

VIDEO_ID = "7345678901234567890"
CANONICAL = f"https://www.douyin.com/video/{VIDEO_ID}"


def test_normalizes_video_path_and_drops_tracking_query() -> None:
    url = f"https://www.douyin.com/video/{VIDEO_ID}?previous_page=web"
    assert normalize_douyin_url(url) == CANONICAL


def test_normalizes_share_video_path() -> None:
    url = f"https://www.douyin.com/share/video/{VIDEO_ID}"
    assert normalize_douyin_url(url) == CANONICAL


def test_normalizes_iesdouyin_share_link() -> None:
    url = f"https://www.iesdouyin.com/share/video/{VIDEO_ID}/"
    assert normalize_douyin_url(url) == CANONICAL


def test_normalizes_modal_id_query() -> None:
    url = f"https://www.douyin.com/discover?modal_id={VIDEO_ID}"
    assert normalize_douyin_url(url) == CANONICAL


def test_leaves_non_douyin_url_unchanged() -> None:
    url = "https://www.youtube.com/shorts/abc"
    assert normalize_douyin_url(url) == url


def test_resolves_short_link_with_injected_resolver() -> None:
    short = "https://v.douyin.com/iAbCdEf/"
    seen: list[str] = []

    def resolver(url: str) -> str:
        seen.append(url)
        return f"https://www.douyin.com/video/{VIDEO_ID}?region=VN"

    assert normalize_douyin_url(short, resolver=resolver) == CANONICAL
    assert seen == [short]


def test_short_link_resolution_failure_falls_back_to_original() -> None:
    short = "https://v.douyin.com/iAbCdEf/"

    def resolver(url: str) -> str:
        raise RuntimeError("network down")

    assert normalize_douyin_url(short, resolver=resolver) == short


def test_short_link_resolving_outside_douyin_is_rejected() -> None:
    short = "https://v.douyin.com/iAbCdEf/"
    assert (
        normalize_douyin_url(
            short, resolver=lambda _: "https://evil.example/video/123456"
        )
        == short
    )


def test_normalize_rejects_non_http_url() -> None:
    with pytest.raises(ValueError):
        normalize_douyin_url("file:///etc/passwd")


def test_hints_for_login_errors_mention_cookies() -> None:
    hints = douyin_hints("ERROR: This video is private, login required")
    assert any("Cookies" in hint for hint in hints)


def test_hints_for_extractor_errors_mention_update() -> None:
    hints = douyin_hints("ERROR: Unsupported URL: https://v.douyin.com/x")
    assert any("Cập nhật yt-dlp" in hint for hint in hints)


def test_hints_default_mention_cookies_and_update() -> None:
    joined = " ".join(douyin_hints("something odd"))
    assert "Cookies" in joined
    assert "yt-dlp" in joined


def test_hints_suggest_enabling_fallback_when_disabled() -> None:
    assert any(
        "DOUYIN_FALLBACK_URL" in hint
        for hint in douyin_hints("boom", fallback_enabled=False)
    )


def test_hints_do_not_suggest_fallback_when_already_enabled() -> None:
    assert not any(
        "DOUYIN_FALLBACK_URL" in hint
        for hint in douyin_hints("boom", fallback_enabled=True)
    )


def test_with_hint_preserves_original_message() -> None:
    message = with_douyin_hint("ERROR: boom")
    assert message.startswith("ERROR: boom")
    assert "Gợi ý:" in message


def test_with_hint_is_idempotent() -> None:
    once = with_douyin_hint("ERROR: boom")
    assert with_douyin_hint(once) == once


def test_canonical_url_has_no_extra_query() -> None:
    normalized = normalize_douyin_url(CANONICAL + "?x=1")
    assert parse_qs(urlparse(normalized).query) == {}
