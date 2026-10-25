from pathlib import Path

import pytest

from app.services.subtitles import (
    SubtitleData,
    SubtitleError,
    SubtitleSegment,
    build_ass,
    format_srt,
    load_subtitle_data,
    parse_srt,
    save_subtitle_data,
    wrap_lines,
)

SRT_SAMPLE = """1
00:00:01,000 --> 00:00:02,500
Hello
world

2
00:00:03,000 --> 00:00:04,000
Xin chào
"""


def test_parse_srt_reads_timings_and_multiline_text() -> None:
    segments = parse_srt(SRT_SAMPLE)
    assert segments == [
        SubtitleSegment(start=1.0, end=2.5, text="Hello world"),
        SubtitleSegment(start=3.0, end=4.0, text="Xin chào"),
    ]


def test_parse_srt_ignores_blocks_without_a_valid_timing_line() -> None:
    segments = parse_srt("1\nnot a timing\nignored\n\n" + SRT_SAMPLE)
    assert len(segments) == 2


def test_parse_srt_rejects_garbage() -> None:
    with pytest.raises(SubtitleError):
        parse_srt("completely unrelated text")


def test_format_srt_round_trips() -> None:
    segments = [
        SubtitleSegment(start=65.25, end=67.5, text="Dòng một dòng hai"),
        SubtitleSegment(start=0.0, end=1.004, text="Mở đầu"),
    ]
    text = format_srt(segments)
    assert "00:01:05,250 --> 00:01:07,500" in text
    assert "Dòng một dòng hai" in text
    assert parse_srt(text) == segments


@pytest.mark.parametrize(
    ("text", "max_chars", "expected"),
    [
        ("one two three four", 9, ["one two", "three", "four"]),
        ("  nhiều   khoảng trắng  ", 40, ["nhiều khoảng trắng"]),
        ("你好世界你好世界", 4, ["你好世界", "你好世界"]),
        ("abcdefghij", 4, ["abcd", "efgh", "ij"]),
        ("", 40, []),
    ],
)
def test_wrap_lines(text: str, max_chars: int, expected: list[str]) -> None:
    assert wrap_lines(text, max_chars) == expected


def test_build_ass_styles_bottom_subtitles_for_vertical_video() -> None:
    ass = build_ass(
        [SubtitleSegment(start=1.0, end=2.5, text="Xin chào {bạn}")],
        video_width=1080,
        video_height=1920,
        font="Arial",
        size=18,
        position="bottom",
    )
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Style: Default,Arial,64," in ass
    assert "Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,Xin chào \\{bạn\\}" in ass
    # bottom alignment = 2, margin V = 8% of height, side margins = 5% of width
    assert ",2,54,54,154,1" in ass


@pytest.mark.parametrize(("position", "alignment"), [("top", 8), ("center", 5), ("bottom", 2)])
def test_build_ass_maps_positions_to_alignment(position: str, alignment: int) -> None:
    ass = build_ass(
        [SubtitleSegment(start=0.0, end=1.0, text="Hi")],
        video_width=640,
        video_height=360,
        font="Arial",
        size=18,
        position=position,
    )
    assert f",{alignment}," in ass


def test_build_ass_wraps_vertical_text_at_40_chars() -> None:
    text = " ".join(["từ"] * 30)
    ass = build_ass(
        [SubtitleSegment(start=0.0, end=1.0, text=text)],
        video_width=1080,
        video_height=1920,
        font="Arial",
        size=18,
        position="bottom",
    )
    dialogue = [line for line in ass.splitlines() if line.startswith("Dialogue:")][0]
    assert "\\N" in dialogue


def test_build_ass_uses_default_vietnamese_safe_font_when_empty() -> None:
    ass = build_ass(
        [SubtitleSegment(start=0.0, end=1.0, text="Hi")],
        video_width=640,
        video_height=360,
        font="",
        size=18,
        position="bottom",
    )
    assert "Style: Default,Arial," in ass


def test_subtitle_data_round_trips_json(tmp_path: Path) -> None:
    path = tmp_path / "subtitle.json"
    data = SubtitleData(
        language="zh",
        target_language="vi",
        translated=True,
        segments=[SubtitleSegment(0.0, 1.0, "Xin chào")],
        source_segments=[SubtitleSegment(0.0, 1.0, "你好")],
    )
    save_subtitle_data(path, data)
    assert load_subtitle_data(path) == data
    assert not (tmp_path / "subtitle.json.tmp").exists()


def test_load_subtitle_data_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_subtitle_data(tmp_path / "missing.json") is None


def test_load_subtitle_data_rejects_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "subtitle.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SubtitleError):
        load_subtitle_data(path)
