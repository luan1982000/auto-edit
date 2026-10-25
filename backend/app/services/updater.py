"""Update the installed yt-dlp package through the current Python environment."""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from dataclasses import dataclass

MAX_OUTPUT = 4000


@dataclass(frozen=True)
class UpdateResult:
    ok: bool
    output: str
    version: str | None
    restart_required: bool = True


def build_update_command() -> list[str]:
    """Fixed argument list: no shell, no user input."""
    return [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]


def installed_version() -> str | None:
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return None


def _tail(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) <= MAX_OUTPUT:
        return cleaned
    return "…\n" + cleaned[-MAX_OUTPUT:]


def run_update(timeout_sec: float = 180.0) -> UpdateResult:
    version = installed_version()
    try:
        result = subprocess.run(
            build_update_command(),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except FileNotFoundError as exc:
        return UpdateResult(False, f"Không chạy được pip: {exc}", version, False)
    except subprocess.TimeoutExpired:
        return UpdateResult(
            False,
            f"pip install --upgrade yt-dlp quá thời gian ({timeout_sec:.0f}s)",
            version,
            False,
        )

    combined = "\n".join(
        part for part in (result.stdout, result.stderr) if part.strip()
    )
    ok = result.returncode == 0
    output = _tail(combined) or (
        "Đã cập nhật yt-dlp" if ok else f"pip exit {result.returncode}"
    )
    return UpdateResult(ok, output, installed_version(), ok)
