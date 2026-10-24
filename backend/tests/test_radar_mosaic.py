"""Regression coverage for AOIs straddling real provider tile boundaries."""

from copy import deepcopy

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping, shape

from app.catalog import radar_acquisitions, radar_members, select_radar_pair
from app.processing import read_radar

AOI = mapping(box(-1.61, 6.96, -1.57, 7.01))


def tiles(when, absolute_orbit):
    return [
        {
            "id": f"{absolute_orbit}-{part}",
            "collection": "s1_rtc",
            "geometry": mapping(footprint),
            "assets": {"vv": {}, "vh": {}, "mask": {}},
            "properties": {
                "datetime": when + "T18:17:25Z",
                "platform": "sentinel-1c",
                "sat:relative_orbit": 147,
                "sat:absolute_orbit": absolute_orbit,
                "sat:orbit_state": "ascending",
                "geomine:analysis_grid_m": 30,
            },
        }
        for part, footprint in enumerate((box(-2, 6, -1, 7), box(-2, 7, -1, 8)))
    ]


def test_same_pass_tiles_cover_cross_boundary_area_and_pair_across_dates():
    before, after = tiles("2026-08-02", 8820), tiles("2026-10-01", 9695)
    assert not any(shape(i["geometry"]).covers(shape(AOI)) for i in before)
    selected = select_radar_pair(before, after, AOI, before[0], after[0])
    for acquisition, original in zip(selected, (before, after)):
        assert shape(acquisition["geometry"]).covers(shape(AOI))
        assert {i["id"] for i in radar_members(acquisition)} == {
            i["id"] for i in original
        }
    assert "geomine:members" not in before[0]  # Input records remain original.


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sat:absolute_orbit", 8821),
        ("platform", "sentinel-1d"),
        ("sat:orbit_state", "descending"),
        ("sat:relative_orbit", 139),
        ("sat:absolute_orbit", None),
    ],
)
def test_mosaic_does_not_fill_coverage_with_a_different_or_unknown_pass(field, value):
    items = tiles("2026-08-02", 8820)
    items[1]["properties"][field] = value
    assert radar_acquisitions(items, AOI) == []


def test_mosaic_rejects_a_spatial_gap_and_missing_polarization():
    items = tiles("2026-08-02", 8820)
    items[1]["geometry"] = mapping(box(-2, 7.001, -1, 8))
    assert radar_acquisitions(items, AOI) == []
    items = tiles("2026-08-02", 8820)
    del items[1]["assets"]["vh"]
    assert radar_acquisitions(items, AOI) == []


def test_single_covering_scene_is_preserved_and_duplicate_tiles_are_deduplicated():
    items = tiles("2026-08-02", 8820)
    assert radar_acquisitions(items, mapping(box(-1.61, 6.96, -1.57, 6.99))) == [
        items[0]
    ]
    combined = radar_acquisitions([*items, deepcopy(items[0])], AOI)
    assert len(radar_members(combined[0])) == 2


def test_every_mosaic_member_must_be_within_optical_time_limit():
    before, after = tiles("2026-08-13", 8820), tiles("2026-10-01", 9695)
    before[1]["properties"]["datetime"] = "2026-08-14T00:00:01Z"
    optical = {"properties": {"datetime": "2026-08-01T12:00:00Z"}}
    with pytest.raises(ValueError, match="12 days"):
        select_radar_pair(before, after, AOI, optical, after[0])


def test_radar_mosaic_reads_real_rasters_and_preserves_per_tile_masks(tmp_path):
    members = []
    for n, (left, vv) in enumerate(((0, 0.2), (1, 0.8))):
        assets = {}
        for band, value in (("vv", vv), ("vh", vv / 5), ("mask", 1)):
            path = tmp_path / f"tile-{n}-{band}.tif"
            data = np.full((4, 3), value, dtype="float32")
            if n == 0 and band == "mask":
                data[:, 2] = 0
                data[3, 0] = 0
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=3,
                height=4,
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=from_origin(left, 4, 1, 1),
                nodata=0,
            ) as dst:
                dst.write(data, 1)
            assets[band] = {"href": str(path)}
        members.append({"collection": "s1_rtc", "assets": assets})
    grid = ("EPSG:4326", from_origin(0, 4, 1, 1), 4, 4, None)
    bands, valid = read_radar({"geomine:members": members}, grid)
    assert np.allclose(bands[0, :3, :2], 0.2)
    assert np.allclose(bands[1, :3, :2], 0.04)
    assert np.allclose(bands[0, :, 2:], 0.8)
    assert np.allclose(bands[1, :, 2:], 0.16)
    assert not valid[3, 0] and np.isnan(bands[:, 3, 0]).all()
    assert valid.sum() == 15
