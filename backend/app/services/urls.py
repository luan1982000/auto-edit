"""URL validation and platform detection for supported video sources."""

from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}

PLATFORM_HOSTS: dict[str, tuple[str, ...]] = {
    "facebook": ("facebook.com", "fb.watch", "facebook.net"),
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "douyin": ("douyin.com", "iesdouyin.com"),
    "tiktok": ("tiktok.com",),
}


def validate_url(url: str) -> str:
    """Return the trimmed URL if it is a safe http(s) URL, else raise ValueError."""
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("URL is empty")
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme or '(none)'} — only http/https")
    if not parsed.hostname:
        raise ValueError("URL has no host")
    return cleaned


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith(f".{suffix}")


def detect_platform(url: str) -> str:
    """Return one of facebook/youtube/douyin/tiktok/other for a validated URL."""
    host = (urlparse(url).hostname or "").lower()
    for platform, suffixes in PLATFORM_HOSTS.items():
        if any(_host_matches(host, suffix) for suffix in suffixes):
            return platform
    return "other"
