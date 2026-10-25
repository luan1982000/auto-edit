import json
from pathlib import Path

import pytest

from app.services.cover import (
    CoverRegion,
    CoverRegionError,
    load_cover_region,
    save_cover_region,
)


def test_cover_region_round_trips_through_json(tmp_path: Path) -> None:
    region = CoverRegion(x=0.05, y=0.75, width=0.9, height=0.2)

    save_cover_region(tmp_path, region)

    assert load_cover_region(tmp_path) == region
    payload = json.loads((tmp_path / "cover_region.json").read_text(encoding="utf-8"))
    assert payload == {"x": 0.05, "y": 0.75, "width": 0.9, "height": 0.2}


def test_saving_none_removes_the_cover_region(tmp_path: Path) -> None:
    save_cover_region(tmp_path, CoverRegion(0.1, 0.7, 0.8, 0.2))

    save_cover_region(tmp_path, None)

    assert load_cover_region(tmp_path) is None
    assert not (tmp_path / "cover_region.json").exists()


def test_missing_cover_region_returns_none(tmp_path: Path) -> None:
    assert load_cover_region(tmp_path) is None


@pytest.mark.parametrize(
    "values",
    [
        (-0.1, 0.7, 0.8, 0.2),
        (0.1, -0.1, 0.8, 0.2),
        (0.1, 0.7, 0.0, 0.2),
        (0.1, 0.7, 0.8, 0.0),
        (0.5, 0.7, 0.6, 0.2),
        (0.1, 0.7, 0.8, 0.4),
        (float("nan"), 0.7, 0.8, 0.2),
    ],
)
def test_cover_region_rejects_invalid_rectangles(values: tuple[float, ...]) -> None:
    with pytest.raises(ValueError):
        CoverRegion(*values)


def test_pixel_box_uses_percentages_of_the_video_size() -> None:
    region = CoverRegion(0.05, 0.75, 0.9, 0.15)

    assert region.pixel_box(1080, 1920) == (54, 1440, 972, 288)


def test_pixel_box_requires_video_dimensions() -> None:
    region = CoverRegion(0.05, 0.75, 0.9, 0.15)

    with pytest.raises(ValueError):
        region.pixel_box(0, 1920)


def test_loading_corrupt_region_raises_a_clear_error(tmp_path: Path) -> None:
    (tmp_path / "cover_region.json").write_text("not json", encoding="utf-8")

    with pytest.raises(CoverRegionError, match="Vùng che"):
        load_cover_region(tmp_path)


def test_loading_an_out_of_bounds_region_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "cover_region.json").write_text(
        json.dumps({"x": 0.8, "y": 0.7, "width": 0.5, "height": 0.2}),
        encoding="utf-8",
    )

    with pytest.raises(CoverRegionError, match="Vùng che"):
        load_cover_region(tmp_path)
