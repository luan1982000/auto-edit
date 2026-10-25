"""Thin, testable wrappers around ffmpeg/ffprobe subprocess calls."""

import json
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe command fails or cannot be run."""


def parse_progress_seconds(line: str) -> float | None:
    """Parse one `-progress pipe:1` line into elapsed output seconds.

    ffmpeg reports `out_time_ms` in microseconds (historical naming). Both
    `out_time_us` and `out_time_ms` are accepted.
    """
    key, separator, raw_value = line.strip().partition("=")
    if not separator:
        return None
    value = raw_value.strip()
    if key in {"out_time_us", "out_time_ms"}:
        try:
            return max(0.0, int(value) / 1_000_000)
        except ValueError:
            return None
    if key == "out_time":
        try:
            hours, minutes, seconds = value.split(":")
            return max(0.0, int(hours) * 3600 + int(minutes) * 60 + float(seconds))
        except ValueError:
            return None
    return None


def run_ffmpeg_with_progress(
    args: list[str],
    duration_sec: float,
    on_progress: Callable[[int], None],
    timeout: float = 900,
    deadline_check: Callable[[], None] | None = None,
    cwd: Path | None = None,
) -> None:
    """Run ffmpeg and translate `-progress pipe:1` output into percentages."""
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"{args[0]} not found in PATH") from exc

    timed_out = False

    def kill() -> None:
        nonlocal timed_out
        timed_out = True
        process.kill()

    timer = threading.Timer(timeout, kill)
    timer.daemon = True
    timer.start()

    stderr_chunks: list[str] = []

    def drain_stderr() -> None:
        if process.stderr is not None:
            stderr_chunks.append(process.stderr.read())

    drain = threading.Thread(target=drain_stderr, daemon=True)
    drain.start()

    try:
        assert process.stdout is not None
        for line in process.stdout:
            if deadline_check is not None:
                deadline_check()
            seconds = parse_progress_seconds(line)
            if seconds is not None and duration_sec > 0:
                percent = min(99, int(seconds / duration_sec * 100))
                on_progress(percent)
        process.wait()
        drain.join(timeout=5)
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        timer.cancel()

    if timed_out:
        raise FFmpegError(f"{Path(args[0]).name} timed out after {timeout:g}s")
    if process.returncode != 0:
        tail = "\n".join("".join(stderr_chunks).strip().splitlines()[-8:])[:1000]
        raise FFmpegError(f"{Path(args[0]).name} failed (exit {process.returncode}): {tail}")
    on_progress(100)


def run_ffmpeg(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
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


def probe_video(path: Path) -> dict[str, float | int | bool]:
    """Return duration, dimensions, and whether the file has audio."""
    result = run_ffmpeg(
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
        "has_audio": any(
            stream.get("codec_type") == "audio" for stream in data.get("streams", [])
        ),
    }


def probe_audio_duration(path: Path) -> float:
    """Return the duration in seconds of an audio file."""
    path = Path(path)
    if not path.is_file():
        raise FFmpegError(f"audio file not found: {path}")
    result = run_ffmpeg(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ]
    )
    try:
        data = json.loads(result.stdout or "{}")
        duration = float(data.get("format", {}).get("duration") or 0)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise FFmpegError("ffprobe returned invalid audio metadata") from exc
    if duration <= 0:
        raise FFmpegError("ffprobe found no audio duration")
    return duration


def ensure_mp4(source: Path, target: Path) -> Path:
    """Make sure the downloaded file is an .mp4 at `target` (remux only, no re-encode)."""
    if source.suffix.lower() != ".mp4":
        target.parent.mkdir(parents=True, exist_ok=True)
        run_ffmpeg(
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


def extract_audio(video_path: Path, out_path: Path, sample_rate: int = 16000) -> Path:
    """Extract the first audio stream as mono PCM WAV for speech recognition."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ],
        timeout=600,
    )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise FFmpegError("ffmpeg produced an empty audio file")
    return out_path


def make_thumbnail(
    video_path: Path, out_path: Path, at_sec: float = 1.0, width: int = 640
) -> Path:
    """Grab a single frame as JPEG. The caller owns the destination directory."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
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


def extract_sample_frames(
    video_path: Path,
    out_dir: Path,
    *,
    duration_sec: float,
    fractions: tuple[float, ...] = (0.15, 0.5, 0.85),
    width: int = 720,
) -> list[tuple[float, Path]]:
    """Capture evenly spaced JPEG frames used to locate burned-in subtitles.

    Frames are named `sample-1.jpg`, `sample-2.jpg`, ... and stale samples from
    a previous request are removed first. Returns `(seconds, path)` pairs.
    """
    if duration_sec <= 0:
        raise FFmpegError("video duration must be positive to sample frames")
    if not fractions:
        raise FFmpegError("at least one frame position is required")
    video_path = Path(video_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("sample-*.jpg"):
        stale.unlink(missing_ok=True)

    frames: list[tuple[float, Path]] = []
    for index, fraction in enumerate(fractions, start=1):
        position = min(max(fraction, 0.0), 0.99)
        at_sec = duration_sec * position
        out_path = out_dir / f"sample-{index}.jpg"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{at_sec:.3f}",
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
            raise FFmpegError("ffmpeg produced an empty sample frame")
        frames.append((at_sec, out_path))
    return frames
