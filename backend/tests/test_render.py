from itertools import product
from pathlib import Path

import pytest

from app.services.cover import CoverRegion
from app.services.render import LogoOptions, RenderOptions, build_ffmpeg_command


def _option(cmd: list[str], name: str) -> str:
    return cmd[cmd.index(name) + 1]


def test_build_command_without_logo_reencodes_video_and_copies_audio(tmp_path: Path) -> None:
    source = tmp_path / "original.mp4"
    output = tmp_path / "output_final.mp4"

    cmd = build_ffmpeg_command(source, output, RenderOptions(video_width=1920, video_height=1080))

    assert cmd[0] == "ffmpeg"
    assert "-filter_complex" not in cmd
    assert _option(cmd, "-map") == "0:v:0"
    assert "0:a?" in cmd
    assert _option(cmd, "-c:v") == "libx264"
    assert _option(cmd, "-crf") == "20"
    assert _option(cmd, "-preset") == "medium"
    assert _option(cmd, "-c:a") == "copy"
    assert _option(cmd, "-movflags") == "+faststart"
    assert cmd[-1] == str(output)


def test_build_command_scales_logo_by_video_width(tmp_path: Path) -> None:
    source = tmp_path / "original.mp4"
    logo = tmp_path / "logo with space.png"
    output = tmp_path / "output_final.mp4"

    cmd = build_ffmpeg_command(
        source,
        output,
        RenderOptions(
            video_width=1920,
            video_height=1080,
            logo=LogoOptions(path=logo, position="tr", scale_pct=15, opacity=1.0, margin_px=24),
        ),
    )

    filters = _option(cmd, "-filter_complex")
    assert f"-i {logo}" not in filters  # paths are separate argv entries, not shell text
    assert str(logo) in cmd
    assert "[1:v]scale=288:-2,format=rgba,colorchannelmixer=aa=1[logo]" in filters
    assert "[0:v][logo]overlay=main_w-overlay_w-24:24[vout]" in filters
    assert _option(cmd, "-map") == "[vout]"
    assert "-filter_complex" in cmd


@pytest.mark.parametrize(
    ("position", "expression"),
    [
        ("tl", "24:24"),
        ("tr", "main_w-overlay_w-24:24"),
        ("bl", "24:main_h-overlay_h-24"),
        ("br", "main_w-overlay_w-24:main_h-overlay_h-24"),
    ],
)
def test_logo_positions_map_to_overlay_expressions(
    tmp_path: Path, position: str, expression: str
) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            logo=LogoOptions(path=tmp_path / "logo.png", position=position),
        ),
    )
    assert f"overlay={expression}" in _option(cmd, "-filter_complex")


def test_logo_opacity_is_applied(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            logo=LogoOptions(path=tmp_path / "logo.png", position="bl", opacity=0.35),
        ),
    )
    assert "colorchannelmixer=aa=0.35" in _option(cmd, "-filter_complex")


def test_logo_width_is_even_for_vertical_and_odd_percentages(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=300,
            video_height=500,
            logo=LogoOptions(path=tmp_path / "logo.png", scale_pct=11),
        ),
    )
    # 300 * 11% = 33 -> rounded down to the nearest even value so yuv420p encoding works.
    assert "scale=32:-2" in _option(cmd, "-filter_complex")


def test_unknown_logo_position_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="position"):
        build_ffmpeg_command(
            tmp_path / "in.mp4",
            tmp_path / "out.mp4",
            RenderOptions(
                video_width=100,
                video_height=100,
                logo=LogoOptions(path=tmp_path / "logo.png", position="middle"),
            ),
        )


def test_builder_refuses_to_overwrite_the_input(tmp_path: Path) -> None:
    source = tmp_path / "original.mp4"
    with pytest.raises(ValueError, match="original"):
        build_ffmpeg_command(
            source,
            source,
            RenderOptions(video_width=100, video_height=100),
        )


def test_command_requests_machine_readable_progress(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(video_width=100, video_height=100),
    )
    assert _option(cmd, "-progress") == "pipe:1"
    assert "-nostats" in cmd


def test_subtitle_only_uses_ass_filter(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            subtitle_file="subtitle.ass",
        ),
    )
    assert _option(cmd, "-filter_complex") == "[0:v]ass=subtitle.ass[vout]"
    assert _option(cmd, "-map") == "[vout]"
    assert "-c:a" in cmd and _option(cmd, "-c:a") == "copy"


def test_subtitle_is_burned_after_the_logo_overlay(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            logo=LogoOptions(path=tmp_path / "logo.png"),
            subtitle_file="subtitle.ass",
        ),
    )
    filters = _option(cmd, "-filter_complex")
    assert "[0:v][logo]overlay=" in filters
    assert "[vlogo];[vlogo]ass=subtitle.ass[vout]" in filters
    assert _option(cmd, "-map") == "[vout]"


@pytest.mark.parametrize(
    "name",
    ["../subtitle.ass", "/tmp/subtitle.ass", "subtitle.srt", "sub title.ass", "a:b.ass"],
)
def test_invalid_subtitle_file_names_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="subtitle"):
        build_ffmpeg_command(
            tmp_path / "in.mp4",
            tmp_path / "out.mp4",
            RenderOptions(
                video_width=100,
                video_height=100,
                subtitle_file=name,
            ),
        )


def test_voice_mute_uses_only_the_voice_track(tmp_path: Path) -> None:
    voice = tmp_path / "voice.mp3"
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            voice_path=voice,
            audio_mode="mute",
        ),
    )

    assert str(voice) in cmd
    assert _option(cmd, "-filter_complex") == "[1:a]alimiter=limit=0.95[aout]"
    assert _option(cmd, "-map") == "0:v:0"
    assert "[aout]" in cmd
    assert "0:a?" not in cmd
    assert _option(cmd, "-c:a") == "aac"
    assert _option(cmd, "-b:a") == "192k"


def test_voice_duck_with_logo_and_subtitle_combines_both_filters(tmp_path: Path) -> None:
    voice = tmp_path / "voice.mp3"
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            logo=LogoOptions(path=tmp_path / "logo.png"),
            subtitle_file="subtitle.ass",
            voice_path=voice,
            audio_mode="duck",
        ),
    )

    command_text = " ".join(cmd)
    assert f"-i {tmp_path / 'logo.png'} -i {voice}" in command_text
    filters = _option(cmd, "-filter_complex")
    assert "[0:v][logo]overlay=" in filters
    assert "[vlogo];[vlogo]ass=subtitle.ass[vout]" in filters
    assert "[0:a]volume=0.2[orig]" in filters
    assert "[2:a]anull[voice]" in filters
    assert (
        "[orig][voice]amix=inputs=2:duration=longest:normalize=0:"
        "dropout_transition=0,alimiter=limit=0.95[aout]" in filters
    )
    assert _option(cmd, "-map") == "[vout]"
    assert "[aout]" in cmd
    assert _option(cmd, "-c:a") == "aac"


def test_voice_keep_uses_full_original_volume(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            voice_path=tmp_path / "voice.mp3",
            audio_mode="keep",
        ),
    )

    filters = _option(cmd, "-filter_complex")
    assert "[0:a]volume=1[orig]" in filters
    assert "amix=inputs=2:duration=longest:normalize=0" in filters
    assert _option(cmd, "-map") == "0:v:0"
    assert _option(cmd, "-c:a") == "aac"


def test_voice_works_when_the_source_has_no_audio(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            voice_path=tmp_path / "voice.mp3",
            audio_mode="duck",
            has_original_audio=False,
        ),
    )

    filters = _option(cmd, "-filter_complex")
    assert filters == "[1:a]alimiter=limit=0.95[aout]"
    assert "[0:a]" not in filters
    assert _option(cmd, "-c:a") == "aac"


def test_unknown_audio_mode_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="audio"):
        build_ffmpeg_command(
            tmp_path / "in.mp4",
            tmp_path / "out.mp4",
            RenderOptions(
                video_width=100,
                video_height=100,
                voice_path=tmp_path / "voice.mp3",
                audio_mode="loud",
            ),
        )


def test_cover_region_is_drawn_before_logo_and_subtitles(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            cover_region=CoverRegion(0.05, 0.75, 0.9, 0.15),
            logo=LogoOptions(path=tmp_path / "logo.png"),
            subtitle_file="subtitle.ass",
        ),
    )

    assert _option(cmd, "-filter_complex") == (
        "[0:v]drawbox=x=54:y=1440:w=972:h=288:color=black@1.0:t=fill[vcover];"
        "[1:v]scale=162:-2,format=rgba,colorchannelmixer=aa=1[logo];"
        "[vcover][logo]overlay=main_w-overlay_w-24:24[vlogo];"
        "[vlogo]ass=subtitle.ass[vout]"
    )
    assert _option(cmd, "-map") == "[vout]"


def test_cover_region_alone_maps_the_filtered_video(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=320,
            video_height=240,
            cover_region=CoverRegion(0.05, 0.75, 0.9, 0.2),
        ),
    )

    assert (
        _option(cmd, "-filter_complex")
        == "[0:v]drawbox=x=16:y=180:w=288:h=48:color=black@1.0:t=fill[vout]"
    )
    assert _option(cmd, "-map") == "[vout]"
    assert _option(cmd, "-c:a") == "copy"


def test_cover_region_with_subtitle_uses_cover_as_base(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=100,
            video_height=100,
            cover_region=CoverRegion(0.1, 0.7, 0.8, 0.2),
            subtitle_file="subtitle.ass",
        ),
    )

    assert _option(cmd, "-filter_complex") == (
        "[0:v]drawbox=x=10:y=70:w=80:h=20:color=black@1.0:t=fill[vcover];"
        "[vcover]ass=subtitle.ass[vout]"
    )


@pytest.mark.parametrize(
    ("logo", "subtitle", "voice", "cover"), list(product([False, True], repeat=4))
)
def test_every_checkbox_combination_builds_one_ffmpeg_command(
    tmp_path: Path, logo: bool, subtitle: bool, voice: bool, cover: bool
) -> None:
    logo_path = tmp_path / "logo.png"
    voice_path = tmp_path / "voice.mp3"
    cmd = build_ffmpeg_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        RenderOptions(
            video_width=1080,
            video_height=1920,
            logo=LogoOptions(path=logo_path) if logo else None,
            subtitle_file="subtitle.ass" if subtitle else None,
            voice_path=voice_path if voice else None,
            cover_region=CoverRegion(0.05, 0.75, 0.9, 0.15) if cover else None,
            audio_mode="duck",
        ),
    )

    assert cmd[0] == "ffmpeg"
    has_video_filter = logo or subtitle or cover
    assert cmd.count("-filter_complex") == (
        1 if (has_video_filter or voice) else 0
    )
    assert (str(logo_path) in cmd) is logo
    assert ("ass=subtitle.ass" in " ".join(cmd)) is subtitle
    assert (str(voice_path) in cmd) is voice
    assert ("drawbox=" in " ".join(cmd)) is cover
    assert _option(cmd, "-map") == ("[vout]" if has_video_filter else "0:v:0")
    assert ("[aout]" in cmd) is voice
    if voice:
        assert _option(cmd, "-c:a") == "aac"
        assert "0:a?" not in cmd
    else:
        assert _option(cmd, "-c:a") == "copy"
        assert "0:a?" in cmd
    assert _option(cmd, "-progress") == "pipe:1"
    assert cmd[-1] == str(tmp_path / "out.mp4")
