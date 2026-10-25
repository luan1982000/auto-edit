from pathlib import Path

import pytest

from app.services.downloader import DownloadError, DownloadResult, download_video, retry_call


def test_retry_call_returns_without_sleep_on_first_success() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    result = retry_call(
        lambda: calls.append(1) or "ok",
        retries=2,
        sleep=sleeps.append,
    )

    assert result == "ok"
    assert calls == [1]
    assert sleeps == []


def test_retry_call_retries_twice_with_exponential_backoff() -> None:
    calls = 0
    sleeps: list[float] = []

    def action() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise DownloadError(f"fail {calls}")
        return "ok"

    result = retry_call(action, retries=2, backoff_sec=1.0, sleep=sleeps.append)

    assert result == "ok"
    assert calls == 3
    assert sleeps == [1.0, 2.0]


def test_retry_call_raises_after_exhausting_retries() -> None:
    calls = 0
    sleeps: list[float] = []

    def action() -> str:
        nonlocal calls
        calls += 1
        raise DownloadError("always fails")

    with pytest.raises(DownloadError, match="always fails"):
        retry_call(action, retries=2, backoff_sec=0.5, sleep=sleeps.append)

    assert calls == 3
    assert sleeps == [0.5, 1.0]


def test_retry_call_does_not_retry_unexpected_errors() -> None:
    calls = 0
    sleeps: list[float] = []

    def action() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("bug")

    with pytest.raises(ValueError, match="bug"):
        retry_call(action, sleep=sleeps.append)

    assert calls == 1
    assert sleeps == []


def test_download_video_retries_with_progress_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0
    events: list[tuple[int, str]] = []
    sleeps: list[float] = []

    def fake_once(
        url: str,
        video_dir: Path,
        progress_cb,
        cookies_browser: str,
        deadline_check,
    ) -> DownloadResult:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise DownloadError(f"attempt {attempts} failed")
        target = video_dir / "original.mp4"
        target.write_bytes(b"x")
        return DownloadResult(file_path=target, title="clip", platform="douyin")

    monkeypatch.setattr("app.services.downloader._download_once", fake_once)

    result = download_video(
        "https://v.douyin.com/abc/",
        tmp_path,
        progress_cb=lambda pct, message: events.append((pct, message)),
        retries=2,
        retry_backoff_sec=1.0,
        sleep=sleeps.append,
    )

    assert attempts == 3
    assert sleeps == [1.0, 2.0]
    assert result.title == "clip"
    messages = [message for _, message in events]
    assert any("thử lại 1/2" in message for message in messages)
    assert any("thử lại 2/2" in message for message in messages)
