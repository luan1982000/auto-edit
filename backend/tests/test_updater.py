import subprocess
import sys

import pytest

from app.services import updater


def test_build_update_command_uses_current_interpreter_and_pip_module() -> None:
    command = updater.build_update_command()

    assert command[:3] == [sys.executable, "-m", "pip"]
    assert "yt-dlp" in command
    assert "--upgrade" in command


def test_run_update_reports_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, "installed yt-dlp", "a warning"
        ),
    )
    monkeypatch.setattr(updater, "installed_version", lambda: "2026.10.1")

    result = updater.run_update(timeout_sec=10)

    assert result.ok is True
    assert result.version == "2026.10.1"
    assert result.restart_required is True
    assert "installed yt-dlp" in result.output
    assert "a warning" in result.output


def test_run_update_reports_failure_and_keeps_output_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tail = "NETWORK ERROR AT THE END"
    stderr = "x" * (updater.MAX_OUTPUT + 1000) + tail
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", stderr),
    )
    monkeypatch.setattr(updater, "installed_version", lambda: "2026.10.1")

    result = updater.run_update(timeout_sec=10)

    assert result.ok is False
    assert result.output.endswith(tail)
    assert len(result.output) <= updater.MAX_OUTPUT + 2


def test_run_update_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="pip", timeout=10)

    monkeypatch.setattr(updater.subprocess, "run", raise_timeout)
    monkeypatch.setattr(updater, "installed_version", lambda: "2026.10.1")

    result = updater.run_update(timeout_sec=10)

    assert result.ok is False
    assert "quá thời gian" in result.output


def test_run_update_handles_missing_pip(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("pip")

    monkeypatch.setattr(updater.subprocess, "run", raise_missing)
    monkeypatch.setattr(updater, "installed_version", lambda: "2026.10.1")

    result = updater.run_update(timeout_sec=10)

    assert result.ok is False
    assert "pip" in result.output
