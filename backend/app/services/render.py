"""Build the single ffmpeg command that renders logo, subtitles and voice-over."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LOGO_POSITIONS = ("tl", "tr", "bl", "br")


@dataclass(frozen=True)
class LogoOptions:
    path: Path
    position: str = "tr"
    scale_pct: int = 15
    opacity: float = 1.0
    margin_px: int = 24


@dataclass(frozen=True)
class RenderOptions:
    video_width: int
    video_height: int
    logo: LogoOptions | None = None
    crf: int = 20
    preset: str = "medium"


def _scaled_width(video_width: int, scale_pct: int) -> int:
    if video_width <= 0:
        raise ValueError("video width must be known before overlaying a logo")
    if not 1 <= scale_pct <= 100:
        raise ValueError("logo scale_pct must be between 1 and 100")
    # yuv420p/libx264 needs even dimensions; -2 keeps the logo's own aspect ratio.
    width = int(round(video_width * scale_pct / 100))
    width -= width % 2
    return max(2, width)


def _overlay_xy(logo: LogoOptions) -> str:
    if logo.position not in LOGO_POSITIONS:
        raise ValueError(f"Unknown logo position: {logo.position}")
    margin = max(0, int(logo.margin_px))
    x = str(margin) if logo.position in {"tl", "bl"} else f"main_w-overlay_w-{margin}"
    y = str(margin) if logo.position in {"tl", "tr"} else f"main_h-overlay_h-{margin}"
    return f"{x}:{y}"


def _logo_filter(video_width: int, video_height: int, logo: LogoOptions) -> str:
    if video_height <= 0:
        raise ValueError("video height must be known before overlaying a logo")
    if not 0 <= logo.opacity <= 1:
        raise ValueError("logo opacity must be between 0 and 1")
    width = _scaled_width(video_width, logo.scale_pct)
    opacity = f"{logo.opacity:g}"
    position = _overlay_xy(logo)
    return (
        f"[1:v]scale={width}:-2,format=rgba,colorchannelmixer=aa={opacity}[logo];"
        f"[0:v][logo]overlay={position}[vout]"
    )


def build_ffmpeg_command(
    video_path: Path, output_path: Path, options: RenderOptions
) -> list[str]:
    """Build a list of argv entries (never shell text) for one-pass rendering.

    Output is written to a caller-owned temporary path and only moved into
    place by the worker after ffmpeg succeeds, so `original.mp4` is never
    overwritten.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    if video_path.resolve() == output_path.resolve():
        raise ValueError("render output must not overwrite original video")

    command = ["ffmpeg", "-y", "-nostdin", "-i", str(video_path)]
    filters = ""
    if options.logo is not None:
        command += ["-i", str(options.logo.path)]
        filters = _logo_filter(options.video_width, options.video_height, options.logo)

    if filters:
        command += ["-filter_complex", filters, "-map", "[vout]"]
    else:
        command += ["-map", "0:v:0"]

    command += [
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-crf",
        str(options.crf),
        "-preset",
        options.preset,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        "-nostats",
        "-progress",
        "pipe:1",
        str(output_path),
    ]
    return command
