"""Build the single ffmpeg command that renders logo, subtitles and voice-over."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.services.cover import CoverRegion

LOGO_POSITIONS = ("tl", "tr", "bl", "br")
AUDIO_MODES = ("mute", "duck", "keep")
DUCK_VOLUME = 0.2
SUBTITLE_FILE = re.compile(r"\A[A-Za-z0-9_.-]+\.ass\Z")


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
    subtitle_file: str | None = None
    voice_path: Path | None = None
    cover_region: CoverRegion | None = None
    audio_mode: str = "keep"
    has_original_audio: bool = True
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


def _logo_filter(
    video_width: int,
    video_height: int,
    logo: LogoOptions,
    *,
    input_label: str = "0:v",
    output_label: str = "vout",
) -> str:
    if video_height <= 0:
        raise ValueError("video height must be known before overlaying a logo")
    if not 0 <= logo.opacity <= 1:
        raise ValueError("logo opacity must be between 0 and 1")
    width = _scaled_width(video_width, logo.scale_pct)
    opacity = f"{logo.opacity:g}"
    position = _overlay_xy(logo)
    return (
        f"[1:v]scale={width}:-2,format=rgba,colorchannelmixer=aa={opacity}[logo];"
        f"[{input_label}][logo]overlay={position}[{output_label}]"
    )


def _subtitle_filter(name: str | None) -> str | None:
    if name is None:
        return None
    if not SUBTITLE_FILE.fullmatch(name):
        raise ValueError("subtitle file name must be a plain .ass file name")
    return f"ass={name}"


def _cover_filter(
    region: CoverRegion,
    video_width: int,
    video_height: int,
    *,
    output_label: str,
) -> str:
    x, y, width, height = region.pixel_box(video_width, video_height)
    return (
        f"[0:v]drawbox=x={x}:y={y}:w={width}:h={height}"
        f":color=black@1.0:t=fill[{output_label}]"
    )


def _video_filter(options: RenderOptions) -> str:
    has_cover = options.cover_region is not None
    has_logo = options.logo is not None
    subtitle_filter = _subtitle_filter(options.subtitle_file)

    if not has_cover and not has_logo and subtitle_filter is None:
        raise ValueError("no video filters configured")

    parts: list[str] = []
    current = "0:v"
    if options.cover_region is not None:
        output = "vcover" if (has_logo or subtitle_filter is not None) else "vout"
        parts.append(
            _cover_filter(
                options.cover_region,
                options.video_width,
                options.video_height,
                output_label=output,
            )
        )
        current = output
    if options.logo is not None:
        output = "vlogo" if subtitle_filter is not None else "vout"
        parts.append(
            _logo_filter(
                options.video_width,
                options.video_height,
                options.logo,
                input_label=current,
                output_label=output,
            )
        )
        current = output
    if subtitle_filter is not None:
        parts.append(f"[{current}]{subtitle_filter}[vout]")
    return ";".join(parts)


def _audio_filter(options: RenderOptions, voice_index: int) -> str:
    if not options.has_original_audio or options.audio_mode == "mute":
        return f"[{voice_index}:a]alimiter=limit=0.95[aout]"
    volume = f"{DUCK_VOLUME:g}" if options.audio_mode == "duck" else "1"
    return (
        f"[0:a]volume={volume}[orig];"
        f"[{voice_index}:a]anull[voice];"
        "[orig][voice]amix=inputs=2:duration=longest:normalize=0:"
        "dropout_transition=0,alimiter=limit=0.95[aout]"
    )


def build_ffmpeg_command(
    video_path: Path, output_path: Path, options: RenderOptions
) -> list[str]:
    """Build a list of argv entries (never shell text) for one-pass rendering.

    Output is written to a caller-owned temporary path and only moved into
    place by the worker after ffmpeg succeeds, so `original.mp4` is never
    overwritten. ASS subtitle paths are relative; the worker runs ffmpeg
    with the video folder as its working directory.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    if video_path.resolve() == output_path.resolve():
        raise ValueError("render output must not overwrite original video")
    if options.audio_mode not in AUDIO_MODES:
        raise ValueError(f"Unknown audio mode: {options.audio_mode}")

    command = ["ffmpeg", "-y", "-nostdin", "-i", str(video_path)]
    next_input = 1
    if options.logo is not None:
        command += ["-i", str(options.logo.path)]
        next_input += 1
    voice_index = next_input
    if options.voice_path is not None:
        command += ["-i", str(options.voice_path)]

    filters: list[str] = []
    has_video_filter = (
        options.logo is not None
        or options.subtitle_file is not None
        or options.cover_region is not None
    )
    if has_video_filter:
        filters.append(_video_filter(options))
    if options.voice_path is not None:
        filters.append(_audio_filter(options, voice_index))
    if filters:
        command += ["-filter_complex", ";".join(filters)]

    if has_video_filter:
        command += ["-map", "[vout]"]
    else:
        command += ["-map", "0:v:0"]
    if options.voice_path is not None:
        command += ["-map", "[aout]"]

    command += [
        "-c:v",
        "libx264",
        "-crf",
        str(options.crf),
        "-preset",
        options.preset,
        "-pix_fmt",
        "yuv420p",
    ]
    if options.voice_path is None:
        command += ["-map", "0:a?", "-c:a", "copy"]
    else:
        command += ["-c:a", "aac", "-b:a", "192k"]
    command += [
        "-movflags",
        "+faststart",
        "-nostats",
        "-progress",
        "pipe:1",
        str(output_path),
    ]
    return command
