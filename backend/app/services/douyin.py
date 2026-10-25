"""Douyin URL normalization and user-facing failure hints."""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, parse_qs, urlparse
from urllib.request import Request, urlopen

from app.services.urls import validate_url

logger = logging.getLogger(__name__)

DOUYIN_SUFFIXES = ("douyin.com", "iesdouyin.com")
SHORT_HOST = "v.douyin.com"
CANONICAL_PREFIX = "https://www.douyin.com/video/"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

COOKIE_HINT = (
    "video có thể cần đăng nhập — chọn Cookies trình duyệt trong Cài đặt rồi thử lại."
)
UPDATE_HINT = (
    "yt-dlp có thể đã cũ — bấm “Cập nhật yt-dlp” trong Cài đặt rồi thử lại."
)
FALLBACK_HINT = (
    "nếu vẫn lỗi, cấu hình DOUYIN_FALLBACK_URL trong .env (xem README)."
)

_COOKIE_KEYWORDS = (
    "login",
    "log in",
    "sign in",
    "cookie",
    "private",
    "403",
    "forbidden",
    "permission",
)
_UPDATE_KEYWORDS = (
    "unsupported",
    "unable to extract",
    "no video formats",
    "no formats",
    "extractor",
)


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith(f".{suffix}")


def _is_douyin_host(host: str) -> bool:
    return any(_host_matches(host, suffix) for suffix in DOUYIN_SUFFIXES)


def _video_id(parsed: ParseResult) -> str | None:
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) == 2 and segments[0] == "video" and segments[1].isdigit():
        return segments[1]
    if (
        len(segments) == 3
        and segments[0] == "share"
        and segments[1] == "video"
        and segments[2].isdigit()
    ):
        return segments[2]

    query = parse_qs(parsed.query)
    for key in ("modal_id", "vid", "video_id"):
        values = query.get(key) or []
        if values and values[0].isdigit():
            return values[0]
    return None


def resolve_short_link(url: str, timeout_sec: float = 10.0) -> str:
    """Follow redirects for a v.douyin.com short link and return the final URL."""
    cleaned = validate_url(url)
    headers = {"User-Agent": _USER_AGENT}
    try:
        request = Request(cleaned, headers=headers, method="HEAD")
        with urlopen(request, timeout=timeout_sec) as response:
            return str(response.geturl())
    except (HTTPError, URLError):
        # Douyin sometimes rejects HEAD; retry with a tiny ranged GET.
        request = Request(
            cleaned,
            headers={**headers, "Range": "bytes=0-1"},
        )
        with urlopen(request, timeout=timeout_sec) as response:
            return str(response.geturl())


def normalize_douyin_url(
    url: str,
    resolver: Callable[[str], str] | None = None,
) -> str:
    """Return a canonical Douyin video URL when the input is a known Douyin form.

    Short links are resolved through `resolver` (network by default). Resolution is
    best-effort: failures return the original URL so yt-dlp can still try it.
    """
    cleaned = validate_url(url)
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if not _is_douyin_host(host):
        return cleaned

    video_id = _video_id(parsed)
    if video_id:
        return f"{CANONICAL_PREFIX}{video_id}"

    if host == SHORT_HOST and parsed.path.strip("/"):
        resolve = resolver or resolve_short_link
        try:
            resolved = validate_url(resolve(cleaned))
        except Exception as exc:  # noqa: BLE001 - resolution is best-effort
            logger.warning("Could not resolve Douyin short link %s: %s", cleaned, exc)
            return cleaned

        resolved_parsed = urlparse(resolved)
        resolved_host = (resolved_parsed.hostname or "").lower()
        if not _is_douyin_host(resolved_host):
            logger.warning(
                "Douyin short link resolved outside Douyin (%s) — ignoring",
                resolved_host,
            )
            return cleaned
        resolved_id = _video_id(resolved_parsed)
        if resolved_id:
            return f"{CANONICAL_PREFIX}{resolved_id}"
        return resolved

    return cleaned


def douyin_hints(message: str, fallback_enabled: bool = False) -> list[str]:
    """Build actionable hints from a yt-dlp error message."""
    lower = message.lower()
    hints: list[str] = []
    if any(keyword in lower for keyword in _COOKIE_KEYWORDS):
        hints.append(COOKIE_HINT)
    if any(keyword in lower for keyword in _UPDATE_KEYWORDS):
        hints.append(UPDATE_HINT)
    if not hints:
        hints.extend([COOKIE_HINT, UPDATE_HINT])
    if not fallback_enabled:
        hints.append(FALLBACK_HINT)
    return hints


def with_douyin_hint(message: str, fallback_enabled: bool = False) -> str:
    """Append hints once; keep the original yt-dlp error untouched."""
    if "Gợi ý:" in message:
        return message
    hints = douyin_hints(message, fallback_enabled=fallback_enabled)
    return message.rstrip() + "\n\n" + "\n".join(f"Gợi ý: {hint}" for hint in hints)
