"""Subtitle data model plus SRT/ASS serialization.

Subtitle text is stored as a single line; line breaks are added by the ASS
renderer according to the video orientation.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

SRT_TIMING = re.compile(
    r"(?P<sh>\d{1,3}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{1,3})"
    r"\s*-->\s*"
    r"(?P<eh>\d{1,3}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{1,3})"
)

ASS_POSITIONS = {"top": 8, "center": 5, "bottom": 2}


class SubtitleError(RuntimeError):
    """Raised when subtitle input cannot be parsed or generated."""


@dataclass(frozen=True)
class SubtitleSegment:
    start: float
    end: float
    text: str


@dataclass
class SubtitleData:
    language: str = ""
    target_language: str = ""
    translated: bool = False
    segments: list[SubtitleSegment] = field(default_factory=list)
    source_segments: list[SubtitleSegment] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _srt_seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis.ljust(3, "0")) / 1000
    )


def parse_srt(text: str) -> list[SubtitleSegment]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    if not normalized.strip():
        return []

    segments: list[SubtitleSegment] = []
    for block in re.split(r"\n\s*\n", normalized.strip()):
        lines = [line.strip() for line in block.splitlines()]
        timing_index = next(
            (index for index, line in enumerate(lines) if SRT_TIMING.search(line)),
            None,
        )
        if timing_index is None:
            continue
        timing = SRT_TIMING.search(lines[timing_index])
        assert timing is not None  # guarded by the generator above
        body = _normalize_text(" ".join(lines[timing_index + 1 :]))
        if not body:
            continue
        segments.append(
            SubtitleSegment(
                start=_srt_seconds(
                    timing["sh"], timing["sm"], timing["ss"], timing["sms"]
                ),
                end=_srt_seconds(
                    timing["eh"], timing["em"], timing["es"], timing["ems"]
                ),
                text=body,
            )
        )

    if not segments:
        raise SubtitleError("Không tìm thấy dòng phụ đề hợp lệ trong file SRT")
    return segments


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    whole_seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{millis:03d}"


def format_srt(segments: list[SubtitleSegment]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        text = _normalize_text(segment.text)
        blocks.append(
            f"{index}\n"
            f"{format_srt_timestamp(segment.start)} --> "
            f"{format_srt_timestamp(segment.end)}\n"
            f"{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def wrap_lines(text: str, max_chars: int) -> list[str]:
    """Word-wrap to at most max_chars per line; hard-split words without spaces."""
    normalized = _normalize_text(text)
    if not normalized:
        return []
    max_chars = max(1, max_chars)

    lines: list[str] = []
    current = ""
    for word in normalized.split(" "):
        chunks = (
            [word[index : index + max_chars] for index in range(0, len(word), max_chars)]
            if len(word) > max_chars
            else [word]
        )
        for chunk in chunks:
            if not current:
                current = chunk
            elif len(current) + 1 + len(chunk) <= max_chars:
                current = f"{current} {chunk}"
            else:
                lines.append(current)
                current = chunk
    if current:
        lines.append(current)
    return lines


def _escape_ass_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )


def _ass_timestamp(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    hours, rest = divmod(total_cs, 360_000)
    minutes, rest = divmod(rest, 6000)
    whole_seconds, centis = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centis:02d}"


def _font_size(video_height: int, setting_size: int) -> int:
    scaled = round(video_height * max(1, setting_size) / 540)
    return max(12, min(200, scaled))


def build_ass(
    segments: list[SubtitleSegment],
    *,
    video_width: int,
    video_height: int,
    font: str,
    size: int,
    position: str,
) -> str:
    """Build an ASS file scaled to the video's resolution."""
    if video_width <= 0 or video_height <= 0:
        raise SubtitleError("Kích thước video không hợp lệ để tạo phụ đề")
    if position not in ASS_POSITIONS:
        raise SubtitleError(f"Vị trí phụ đề không hợp lệ: {position}")

    safe_font = (font or "Arial").replace(",", " ").replace("\n", " ").strip() or "Arial"
    font_size = _font_size(video_height, size)
    alignment = ASS_POSITIONS[position]
    margin_v = round(video_height * 0.08)
    margin_lr = round(video_width * 0.05)
    max_chars = 40 if video_height > video_width else 60

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {video_width}\n"
        f"PlayResY: {video_height}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{safe_font},{font_size},&H00FFFFFF,&H000000FF,"
        f"&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,"
        f"{alignment},{margin_lr},{margin_lr},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )

    events = []
    for segment in segments:
        lines = wrap_lines(segment.text, max_chars)
        if not lines:
            continue
        text = "\\N".join(_escape_ass_text(line) for line in lines)
        events.append(
            "Dialogue: 0,"
            f"{_ass_timestamp(segment.start)},{_ass_timestamp(segment.end)},"
            f"Default,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + ("\n" if events else "")


def _segment_to_dict(segment: SubtitleSegment) -> dict:
    return asdict(segment)


def _segments_to_dicts(segments: list[SubtitleSegment]) -> list[dict]:
    return [_segment_to_dict(segment) for segment in segments]


def _parse_segments(raw: object) -> list[SubtitleSegment]:
    if not isinstance(raw, list):
        raise SubtitleError("Dữ liệu phụ đề không hợp lệ")
    segments = []
    for item in raw:
        if not isinstance(item, dict):
            raise SubtitleError("Dữ liệu phụ đề không hợp lệ")
        try:
            start = float(item["start"])
            end = float(item["end"])
            text = str(item["text"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SubtitleError("Dữ liệu phụ đề không hợp lệ") from exc
        if start < 0 or end <= start:
            raise SubtitleError("Mốc thời gian phụ đề không hợp lệ")
        segments.append(SubtitleSegment(start=start, end=end, text=text))
    return segments


def load_subtitle_data(path: Path) -> SubtitleData | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SubtitleError(f"Không đọc được file phụ đề: {exc}") from exc
    if not isinstance(raw, dict):
        raise SubtitleError("File phụ đề không hợp lệ")
    segments = _parse_segments(raw.get("segments", []))
    source_segments = _parse_segments(raw.get("source_segments") or segments)
    return SubtitleData(
        language=str(raw.get("language") or ""),
        target_language=str(raw.get("target_language") or ""),
        translated=bool(raw.get("translated", False)),
        segments=segments,
        source_segments=source_segments,
    )


def save_subtitle_data(path: Path, data: SubtitleData) -> None:
    payload = {
        "version": 1,
        "language": data.language,
        "target_language": data.target_language,
        "translated": data.translated,
        "segments": _segments_to_dicts(data.segments),
        "source_segments": _segments_to_dicts(data.source_segments),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def write_srt(path: Path, segments: list[SubtitleSegment]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(format_srt(segments), encoding="utf-8")
    temporary.replace(path)


def write_ass(
    path: Path,
    segments: list[SubtitleSegment],
    *,
    video_width: int,
    video_height: int,
    font: str,
    size: int,
    position: str,
) -> None:
    content = build_ass(
        segments,
        video_width=video_width,
        video_height=video_height,
        font=font,
        size=size,
        position=position,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
