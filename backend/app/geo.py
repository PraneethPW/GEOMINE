import math

from fastapi import HTTPException
from pyproj import Geod
from shapely.geometry import mapping, shape
from shapely.geometry.polygon import orient
from shapely.validation import explain_validity

GEOD = Geod(ellps="WGS84")


def validate_geometry(value: dict, max_km2: float | None = None):
    try:
        geom = shape(value)
        if geom.geom_type not in ("Polygon", "MultiPolygon") or geom.is_empty:
            raise ValueError("Provide a Polygon or MultiPolygon.")
        if not geom.is_valid:
            raise ValueError(explain_validity(geom))
        coords = (
            list(geom.exterior.coords)
            if geom.geom_type == "Polygon"
            else [c for p in geom.geoms for c in p.exterior.coords]
        )
        if any(
            len(c) != 2
            or not all(math.isfinite(v) for v in c)
            or not (-180 <= c[0] <= 180 and -80 <= c[1] <= 80)
            for c in coords
        ):
            raise ValueError(
                "Coordinates must be WGS84 longitude/latitude within ±80° latitude."
            )
        x1, y1, x2, y2 = geom.bounds
        if x2 - x1 > 5 or y2 - y1 > 5:
            raise ValueError(
                "Split large or antimeridian-crossing geometries into smaller areas."
            )
        area = (
            sum(
                abs(GEOD.geometry_area_perimeter(orient(p, sign=1.0))[0])
                for p in (geom.geoms if geom.geom_type == "MultiPolygon" else [geom])
            )
            / 1e6
        )
        if area <= 0:
            raise ValueError("Geometry has zero area.")
        if max_km2 and area > max_km2:
            raise ValueError(
                f"Area is {area:.1f} km²; maximum per analysis is {max_km2:g} km²."
            )
        return mapping(geom), area
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


def normalize_geojson(value: dict, max_km2: float | None = None):
    if value.get("type") == "Feature":
        value = value.get("geometry", {})
    return validate_geometry(value, max_km2)
