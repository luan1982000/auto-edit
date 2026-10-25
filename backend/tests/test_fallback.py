import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import pytest

from app.services.fallback import FallbackError, build_fallback_url, download_via_fallback

VIDEO_URL = "https://v.douyin.com/iAbCdEf/?share=1"


class _FallbackHandler(BaseHTTPRequestHandler):
    status: ClassVar[int] = 200
    body: ClassVar[bytes] = b""
    captured: ClassVar[dict[str, object]] = {}

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        type(self).captured = {
            "path": parsed.path,
            "query": parse_qs(parsed.query),
        }
        self.send_response(type(self).status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture()
def fallback_server():
    _FallbackHandler.status = 200
    _FallbackHandler.body = b""
    _FallbackHandler.captured = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/download", _FallbackHandler
    server.shutdown()
    thread.join(timeout=5)


def test_build_fallback_url_preserves_query_and_encodes_video_url() -> None:
    base = "http://example.test/download?token=abc&url=stale"
    result = build_fallback_url(base, VIDEO_URL)
    parsed = urlparse(result)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "example.test"
    assert parsed.path == "/download"
    assert query["token"] == ["abc"]
    assert query["url"] == [VIDEO_URL]


def test_build_fallback_url_rejects_non_http_base() -> None:
    with pytest.raises(FallbackError):
        build_fallback_url("ftp://example.test/download", VIDEO_URL)


def test_download_via_fallback_writes_file_and_passes_url(
    fallback_server, tmp_path: Path
) -> None:
    base_url, handler = fallback_server
    handler.body = b"fake mp4 bytes"
    target = tmp_path / "original.mp4"

    result = download_via_fallback(base_url, VIDEO_URL, target)

    assert result == target
    assert target.read_bytes() == b"fake mp4 bytes"
    assert not target.with_suffix(".mp4.part").exists()
    assert handler.captured["path"] == "/download"
    query = handler.captured["query"]
    assert query["url"] == [VIDEO_URL]


def test_download_via_fallback_reports_http_error(
    fallback_server, tmp_path: Path
) -> None:
    base_url, handler = fallback_server
    handler.status = 500
    target = tmp_path / "original.mp4"

    with pytest.raises(FallbackError, match="500"):
        download_via_fallback(base_url, VIDEO_URL, target)

    assert not target.exists()
    assert not target.with_suffix(".mp4.part").exists()


def test_download_via_fallback_rejects_empty_body(
    fallback_server, tmp_path: Path
) -> None:
    base_url, handler = fallback_server
    handler.body = b""
    target = tmp_path / "original.mp4"

    with pytest.raises(FallbackError, match="rỗng"):
        download_via_fallback(base_url, VIDEO_URL, target)

    assert not target.exists()
    assert not target.with_suffix(".mp4.part").exists()


def test_download_via_fallback_never_overwrites_existing_target(
    fallback_server, tmp_path: Path
) -> None:
    base_url, _ = fallback_server
    target = tmp_path / "original.mp4"
    target.write_bytes(b"original")

    with pytest.raises(FallbackError, match="không ghi đè"):
        download_via_fallback(base_url, VIDEO_URL, target)

    assert target.read_bytes() == b"original"


def test_download_via_fallback_propagates_deadline_error(
    fallback_server, tmp_path: Path
) -> None:
    base_url, handler = fallback_server
    handler.body = b"x" * (256 * 1024)
    target = tmp_path / "original.mp4"

    class Deadline(RuntimeError):
        pass

    def check() -> None:
        raise Deadline("stop")

    with pytest.raises(Deadline):
        download_via_fallback(
            base_url, VIDEO_URL, target, deadline_check=check
        )

    assert not target.exists()
    assert not target.with_suffix(".mp4.part").exists()
