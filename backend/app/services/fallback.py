"""Optional HTTP fallback downloader for Douyin (`DOUYIN_FALLBACK_URL`)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.services.urls import validate_url

_CHUNK_SIZE = 64 * 1024
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


class FallbackError(RuntimeError):
    """Raised when the configured fallback downloader cannot fetch a video."""


def build_fallback_url(base_url: str, video_url: str) -> str:
    """Append `url=<video_url>` to the configured fallback endpoint."""
    try:
        base = validate_url(base_url)
        video = validate_url(video_url)
    except ValueError as exc:
        raise FallbackError(f"URL fallback không hợp lệ: {exc}") from exc

    parts = urlsplit(base)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "url"
    ]
    query.append(("url", video))
    return urlunsplit(parts._replace(query=urlencode(query)))


def download_via_fallback(
    base_url: str,
    video_url: str,
    target_path: Path,
    timeout_sec: float = 300.0,
    deadline_check: Callable[[], None] | None = None,
) -> Path:
    """Stream the fallback response into `target_path` without overwriting it."""
    request_url = build_fallback_url(base_url, video_url)
    target_path = Path(target_path)
    if target_path.exists() and target_path.stat().st_size > 0:
        raise FallbackError(f"{target_path.name} đã tồn tại — không ghi đè")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = target_path.with_name(target_path.name + ".part")
    part_path.unlink(missing_ok=True)

    request = Request(request_url, headers={"User-Agent": _USER_AGENT})
    started = time.monotonic()
    total = 0
    try:
        with urlopen(request, timeout=min(30.0, timeout_sec)) as response:
            final_url = str(response.geturl())
            if urlparse(final_url).scheme.lower() not in {"http", "https"}:
                raise FallbackError(
                    f"Fallback chuyển hướng tới URL không hợp lệ: {final_url}"
                )
            with part_path.open("wb") as handle:
                while True:
                    if deadline_check is not None:
                        deadline_check()
                    if time.monotonic() - started > timeout_sec:
                        raise FallbackError(
                            f"Fallback quá thời gian ({timeout_sec:.0f}s)"
                        )
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    total += len(chunk)

        if total == 0:
            raise FallbackError("Fallback trả về file rỗng")
        if target_path.exists() and target_path.stat().st_size > 0:
            raise FallbackError(f"{target_path.name} đã tồn tại — không ghi đè")
        os.replace(part_path, target_path)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise FallbackError(f"Fallback request lỗi: {exc}") from exc
    finally:
        part_path.unlink(missing_ok=True)

    return target_path
