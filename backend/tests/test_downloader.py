from pathlib import Path

from app.services.downloader import build_ydl_opts, parse_progress, result_from_info

VIDEO_DIR = Path("/tmp/video")


def test_parse_progress_uses_total_bytes() -> None:
    pct, message = parse_progress(
        {
            "status": "downloading",
            "downloaded_bytes": 500,
            "total_bytes": 1000,
            "speed": 2048,
            "eta": 3,
        }
    )
    assert pct == 50
    assert "2.0 KB/s" in message


def test_parse_progress_falls_back_to_estimate() -> None:
    pct, _ = parse_progress(
        {"status": "downloading", "downloaded_bytes": 250, "total_bytes_estimate": 1000}
    )
    assert pct == 25


def test_parse_progress_caps_at_99_while_downloading() -> None:
    pct, _ = parse_progress(
        {"status": "downloading", "downloaded_bytes": 1000, "total_bytes": 1000}
    )
    assert pct == 99


def test_parse_progress_finished_returns_100() -> None:
    pct, message = parse_progress({"status": "finished"})
    assert pct == 100
    assert "xử lý" in message.lower()


def test_parse_progress_ignores_unknown_status() -> None:
    assert parse_progress({"status": "error"}) is None


def test_build_ydl_opts_merges_to_original_mp4() -> None:
    opts = build_ydl_opts(VIDEO_DIR)
    assert opts["merge_output_format"] == "mp4"
    assert opts["outtmpl"] == str(VIDEO_DIR / "original.%(ext)s")
    assert opts["noplaylist"] is True
    assert "cookiesfrombrowser" not in opts


def test_build_ydl_opts_passes_cookies_browser() -> None:
    opts = build_ydl_opts(VIDEO_DIR, cookies_browser="chrome")
    assert opts["cookiesfrombrowser"] == ("chrome",)


def test_result_from_info_maps_metadata() -> None:
    info = {
        "title": "My clip",
        "duration": 12.5,
        "width": 1080,
        "height": 1920,
        "extractor_key": "Youtube",
        "id": "abc",
    }
    result = result_from_info(info, VIDEO_DIR)
    assert result.title == "My clip"
    assert result.duration_sec == 12.5
    assert result.width == 1080
    assert result.height == 1920
    assert result.platform == "youtube"


def test_result_from_info_uses_requested_downloads_filepath() -> None:
    info = {
        "title": "clip",
        "requested_downloads": [{"filepath": str(VIDEO_DIR / "original.mp4")}],
    }
    result = result_from_info(info, VIDEO_DIR)
    assert result.file_path == VIDEO_DIR / "original.mp4"


def test_result_from_info_picks_largest_original_file(tmp_path: Path) -> None:
    small = tmp_path / "original.webm"
    large = tmp_path / "original.mkv"
    small.write_bytes(b"x")
    large.write_bytes(b"x" * 100)
    result = result_from_info({"title": "clip"}, tmp_path)
    assert result.file_path == large


def test_download_reports_a_missing_ytdlp_dependency(
    tmp_path: Path, monkeypatch
) -> None:
    import sys

    import pytest

    from app.services.downloader import DownloadError, _download_once

    monkeypatch.setitem(sys.modules, "yt_dlp", None)

    with pytest.raises(DownloadError, match="yt-dlp"):
        _download_once(
            "https://www.youtube.com/shorts/abc",
            tmp_path,
            progress_cb=None,
            cookies_browser="",
            deadline_check=None,
        )
