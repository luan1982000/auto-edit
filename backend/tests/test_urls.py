import pytest

from app.services.urls import detect_platform, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.facebook.com/reel/1234567890",
        "https://youtube.com/shorts/abc123",
        "http://v.douyin.com/abcDEF/",
        "https://www.tiktok.com/@user/video/123",
    ],
)
def test_validate_url_accepts_http_and_https(url: str) -> None:
    assert validate_url(url) == url


def test_validate_url_strips_whitespace() -> None:
    assert validate_url("  https://example.com/video  ") == "https://example.com/video"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "ftp://example.com/video.mp4",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hello",
        "example.com/video",
        "https://",
        "http://",
    ],
)
def test_validate_url_rejects_non_http_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.facebook.com/reel/123", "facebook"),
        ("https://fb.watch/abcd/", "facebook"),
        ("https://m.facebook.com/watch/?v=1", "facebook"),
        ("https://www.youtube.com/shorts/abc", "youtube"),
        ("https://youtu.be/abc", "youtube"),
        ("https://m.youtube.com/watch?v=abc", "youtube"),
        ("https://v.douyin.com/abc/", "douyin"),
        ("https://www.douyin.com/video/7123456", "douyin"),
        ("https://www.iesdouyin.com/share/video/7123456", "douyin"),
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://vm.tiktok.com/abc/", "tiktok"),
        ("https://example.com/video.mp4", "other"),
    ],
)
def test_detect_platform(url: str, expected: str) -> None:
    assert detect_platform(validate_url(url)) == expected
