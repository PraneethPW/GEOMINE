from datetime import date

import httpx
from fastapi import HTTPException
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from .config import settings

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
DEA_STAC = "https://explorer.digitalearth.africa/stac"
COLLECTIONS = {"optical": "sentinel-2-l2a", "radar": "sentinel-1-rtc"}


class TemporalAlignmentError(ValueError):
    """Coverage/orbits exist but their acquisition dates are incompatible."""


def radar_provider():
    return (
        "planetary-computer"
        if settings().pc_subscription_key
        else "digital-earth-africa"
    )


def catalog_url(item):
    base = DEA_STAC if item["collection"] == "s1_rtc" else STAC
    return f"{base}/collections/{item['collection']}/items/{item['id']}"


async def search_scenes(
    geometry: dict, start: date, end: date, sensor: str, limit: int = 30
):
    public_radar = sensor == "radar" and radar_provider() == "digital-earth-africa"
    endpoint = DEA_STAC if public_radar else STAC
    payload = {
        "collections": ["s1_rtc" if public_radar else COLLECTIONS[sensor]],
        "intersects": geometry,
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": min(limit, 100),
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f"{endpoint}/search", json=payload)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            502, "Satellite catalog is unavailable. Retry shortly."
        ) from exc
    items = data.get("features", [])
    for item in items:
        item["properties"]["geomine:provider"] = (
            "digital-earth-africa" if public_radar else "planetary-computer"
        )
        item["properties"]["geomine:analysis_grid_m"] = 30 if public_radar else 10
    return items


def public_scene(item):
    props = item["properties"]
    # Do not send signed raster URLs or provider tokens to the browser.
    return {
        "id": item["id"],
        "collection": item["collection"],
        "datetime": props.get("datetime"),
        "cloud_cover": props.get("eo:cloud_cover"),
        "platform": props.get("platform"),
        "orbit": props.get("sat:relative_orbit"),
        "geometry": item["geometry"],
        "sensor": "optical"
        if item["collection"] == COLLECTIONS["optical"]
        else "radar",
        "catalog_url": catalog_url(item),
        "provider": props.get("geomine:provider", "planetary-computer"),
        "analysis_grid_m": props.get("geomine:analysis_grid_m", 10),
    }


def select_optical(items, geometry):
    area = shape(geometry)
    candidates = [
        i
        for i in items
        if shape(i["geometry"]).covers(area)
        and all(k in i["assets"] for k in ("B02", "B03", "B04", "B08", "SCL"))
    ]
    if not candidates:
        raise ValueError(
            "No Sentinel-2 scene covers the full area in this date range. Try a smaller area or wider date range."
        )
    return min(candidates, key=lambda i: i["properties"].get("eo:cloud_cover", 100))


def select_observations(
    optical_before, optical_after, radar_before, radar_after, geometry
):
    """Choose the clearest compatible set, rather than pinning incompatible optical dates."""
    area = shape(geometry)

    def optical(items):
        return [
            i
            for i in items
            if shape(i["geometry"]).covers(area)
            and all(k in i["assets"] for k in ("B02", "B03", "B04", "B08", "SCL"))
        ]

    before, after = optical(optical_before), optical(optical_after)
    if not before:
        select_optical(
            optical_before, geometry
        )  # Preserve the actionable coverage error.
    if not after:
        select_optical(optical_after, geometry)
    radar_b, radar_a = (
        radar_acquisitions(radar_before, geometry),
        radar_acquisitions(radar_after, geometry),
    )
    combinations = sorted(
        ((b, a) for b in before for a in after),
        key=lambda pair: (
            sum(float(i["properties"].get("eo:cloud_cover", 100)) for i in pair),
            max(float(i["properties"].get("eo:cloud_cover", 100)) for i in pair),
        ),
    )
    for ob, oa in combinations:
        try:
            rb, ra = select_radar_pair(radar_b, radar_a, geometry, ob, oa)
            return ob, oa, rb, ra
        except TemporalAlignmentError:
            continue
    raise ValueError(
        "No optical/radar observation set satisfies the 12-day time limit in both windows. Widen the windows to include more compatible acquisitions."
    )


def radar_members(item):
    """Original STAC records, including each tile of a same-pass mosaic."""
    return item.get("geomine:members", [item])


def radar_acquisitions(items, geometry):
    """Join DEA's spatial tiles only within an identified satellite pass.

    Relative orbit alone repeats over time and cannot identify a mosaic. Keep
    platform, absolute orbit, direction and collection identical. Providers or
    records without this identity retain the single-scene coverage contract.
    """
    area = shape(geometry)
    acquisitions, groups = [], {}
    for item in items:
        if not all(k in item["assets"] for k in ("vv", "vh")):
            continue
        footprint = shape(item["geometry"])
        if footprint.covers(area):
            acquisitions.append(item)
            continue
        if not footprint.intersects(area):
            continue
        props = item["properties"]
        identity = tuple(
            props.get(key)
            for key in (
                "platform",
                "sat:absolute_orbit",
                "sat:relative_orbit",
                "sat:orbit_state",
            )
        )
        if item.get("collection") != "s1_rtc" or not all(
            value is not None for value in identity
        ):
            continue
        key = (item["collection"], *identity)
        # STAC pagination can repeat a tile. Read and cite each record once.
        groups.setdefault(key, {})[item["id"]] = item
    for group in groups.values():
        members = sorted(
            group.values(), key=lambda i: (i["properties"]["datetime"], i["id"])
        )
        coverage = unary_union([shape(i["geometry"]) for i in members])
        if len(members) > 1 and coverage.covers(area):
            acquisitions.append(
                {
                    **members[0],
                    "geometry": mapping(coverage),
                    "geomine:members": members,
                }
            )
    return acquisitions


def select_radar_pair(before, after, geometry, opt_before, opt_after):

    pairs = [
        (b, a)
        for b in radar_acquisitions(before, geometry)
        for a in radar_acquisitions(after, geometry)
        if b["properties"].get("sat:relative_orbit") is not None
        and b["properties"].get("sat:orbit_state") in ("ascending", "descending")
        and b["properties"].get("sat:relative_orbit")
        == a["properties"].get("sat:relative_orbit")
        and b["properties"].get("sat:orbit_state")
        == a["properties"].get("sat:orbit_state")
    ]
    if not pairs:
        raise ValueError(
            "No matching-orbit VV/VH radar acquisitions fully cover this area, including adjacent same-pass tiles. Try wider windows or a smaller area within radar coverage."
        )
    target_b = date.fromisoformat(opt_before["properties"]["datetime"][:10])
    target_a = date.fromisoformat(opt_after["properties"]["datetime"][:10])

    def offset(acquisition, target):
        return max(
            abs((date.fromisoformat(i["properties"]["datetime"][:10]) - target).days)
            for i in radar_members(acquisition)
        )

    def distance(pair):
        return offset(pair[0], target_b) + offset(pair[1], target_a)

    eligible = [
        pair
        for pair in pairs
        if max(
            offset(pair[0], target_b),
            offset(pair[1], target_a),
        )
        <= 12
    ]
    if not eligible:
        raise TemporalAlignmentError(
            "Radar and optical acquisitions are more than 12 days apart. Choose closer windows."
        )
    return min(eligible, key=distance)
