"""Thin, testable wrappers around ffmpeg/ffprobe subprocess calls."""

import json
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe command fails or cannot be run."""


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise FFmpegError(f"{args[0]} not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"{args[0]} timed out after {timeout}s") from exc
    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").strip().splitlines()[-8:])[:1000]
        raise FFmpegError(f"{Path(args[0]).name} failed (exit {result.returncode}): {tail}")
    return result


def probe_video(path: Path) -> dict[str, float | int]:
    """Return duration_sec, width and height for the first video stream."""
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise FFmpegError("ffprobe returned invalid JSON") from exc

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError("ffprobe found no video stream")
    duration = data.get("format", {}).get("duration") or video.get("duration") or 0
    return {
        "duration_sec": float(duration),
        "width": int(video["width"]),
        "height": int(video["height"]),
    }


def ensure_mp4(source: Path, target: Path) -> Path:
    """Make sure the downloaded file is an .mp4 at `target` (remux only, no re-encode)."""
    if source.suffix.lower() != ".mp4":
        target.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(target),
            ],
            timeout=300,
        )
        if not target.exists():
            raise FFmpegError("ffmpeg remux produced no output")
        source.unlink(missing_ok=True)
        return target
    if source != target:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
    return target


def make_thumbnail(
    video_path: Path, out_path: Path, at_sec: float = 1.0, width: int = 640
) -> Path:
    """Grab a single frame as JPEG. The caller owns the destination directory."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{max(at_sec, 0.0):.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            "-q:v",
            "3",
            str(out_path),
        ],
        timeout=60,
    )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise FFmpegError("ffmpeg produced an empty thumbnail")
    return out_path
