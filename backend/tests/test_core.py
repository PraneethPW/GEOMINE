import numpy as np
import pytest
from fastapi import HTTPException

from app.catalog import select_observations, select_radar_pair
from app.geo import normalize_geojson
from app.main import JobInput
from app.processing import grid_for, physical_scores

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [[-1.94, 6.04], [-1.92, 6.04], [-1.92, 6.06], [-1.94, 6.06], [-1.94, 6.04]]
    ],
}


def test_geometry_validates_area_and_grid():
    geometry, km2 = normalize_geojson(GEOMETRY, 100)
    assert 4 < km2 < 6
    crs, affine, width, height, projected = grid_for(geometry)
    assert crs == "EPSG:32630"
    assert width * height < 60000
    assert affine.a == 10 and affine.e == -10


def test_invalid_and_oversize_geometries_rejected():
    with pytest.raises(HTTPException):
        normalize_geojson({"type": "Point", "coordinates": [0, 0]})
    with pytest.raises(HTTPException):
        normalize_geojson(GEOMETRY, 0.1)


def test_job_windows_must_not_overlap():
    with pytest.raises(ValueError):
        JobInput(
            area_id="6a6ebf33-5408-45ec-bb02-dcddc53d0000",
            before_start="2025-01-01",
            before_end="2025-02-01",
            after_start="2025-01-15",
            after_end="2025-02-28",
        )


def test_physical_change_rejects_stable_radar_and_clouds():
    # Numerical unit inputs are never used as application data.
    first = np.zeros((4, 20, 20), dtype="float32")
    second = first.copy()
    first[0] = 0.1
    first[3] = 0.6
    second[0] = 0.25
    second[3] = 0.3
    radar = np.ones((2, 20, 20), dtype="float32") * 0.04
    clear = np.ones((20, 20), dtype=bool)
    score, _ = physical_scores(first, second, radar, radar, clear, clear)
    assert not score.any()
    score, _ = physical_scores(first, second, radar, radar * 3, clear, clear)
    assert score.mean() > 0.3
    score, _ = physical_scores(
        first, second, radar, radar * 3, np.zeros_like(clear), clear
    )
    assert not score.any()


def test_radar_pairs_require_same_orbit():
    def scene(orbit, dt):
        return {
            "geometry": GEOMETRY,
            "assets": {"vv": {}, "vh": {}},
            "properties": {
                "sat:relative_orbit": orbit,
                "sat:orbit_state": "ascending",
                "datetime": dt,
            },
        }

    before = scene(1, "2025-01-01T00:00:00Z")
    after = scene(2, "2025-02-01T00:00:00Z")
    with pytest.raises(ValueError):
        select_radar_pair([before], [after], GEOMETRY, before, after)


def test_joint_selection_keeps_a_valid_optical_alternative_in_the_requested_windows():
    def optical(when, cloud):
        return {
            "geometry": GEOMETRY,
            "assets": {k: {} for k in ("B02", "B03", "B04", "B08", "SCL")},
            "properties": {"datetime": when + "T00:00:00Z", "eo:cloud_cover": cloud},
        }

    def radar(when):
        return {
            "geometry": GEOMETRY,
            "assets": {"vv": {}, "vh": {}},
            "properties": {
                "datetime": when + "T00:00:00Z",
                "sat:relative_orbit": 1,
                "sat:orbit_state": "ascending",
            },
        }

    clearest = optical("2025-01-31", 0)
    compatible = optical("2025-01-05", 10)
    after = optical("2025-02-05", 5)
    chosen = select_observations(
        [clearest, compatible],
        [after],
        [radar("2025-01-02")],
        [radar("2025-02-02")],
        GEOMETRY,
    )
    assert chosen[0] is compatible and chosen[1] is after
    with pytest.raises(ValueError, match="12-day"):
        select_observations(
            [clearest], [after], [radar("2025-01-02")], [radar("2025-02-02")], GEOMETRY
        )


def test_geodesic_area_subtracts_holes_regardless_of_winding():
    outer = GEOMETRY["coordinates"][0]
    hole = [
        [-1.935, 6.045],
        [-1.925, 6.045],
        [-1.925, 6.055],
        [-1.935, 6.055],
        [-1.935, 6.045],
    ]
    _, full = normalize_geojson(GEOMETRY)
    _, with_hole = normalize_geojson({"type": "Polygon", "coordinates": [outer, hole]})
    _, reversed_hole = normalize_geojson(
        {"type": "Polygon", "coordinates": [outer, list(reversed(hole))]}
    )
    assert 0.74 < with_hole / full < 0.76
    assert abs(with_hole - reversed_hole) < 1e-8


def test_public_rtc_uses_coarser_analysis_grid():
    _, fine, width10, height10, _ = grid_for(GEOMETRY, 10)
    _, coarse, width30, height30, _ = grid_for(GEOMETRY, 30)
    assert fine.a == 10 and coarse.a == 30 and coarse.e == -30
    assert width30 * height30 < width10 * height10 / 8


def test_neural_mode_rejects_mismatched_public_radar_resolution_before_reading():
    from app.processing import analyze

    radar = {"properties": {"geomine:analysis_grid_m": 30}}
    with pytest.raises(ValueError, match="expects 10m"):
        analyze(GEOMETRY, None, None, radar, radar, [], "geomine", lambda *args: None)


def test_radar_pair_selection_keeps_valid_alternative_within_both_time_limits():
    def scene(orbit, when):
        return {
            "geometry": GEOMETRY,
            "assets": {"vv": {}, "vh": {}},
            "properties": {
                "sat:relative_orbit": orbit,
                "sat:orbit_state": "ascending",
                "datetime": when + "T00:00:00Z",
            },
        }

    before = [scene(1, "2025-01-01"), scene(2, "2025-01-08")]
    after = [scene(1, "2025-02-14"), scene(2, "2025-02-08")]
    selected = select_radar_pair(
        before, after, GEOMETRY, scene(0, "2025-01-01"), scene(0, "2025-02-01")
    )
    assert selected[0]["properties"]["sat:relative_orbit"] == 2
