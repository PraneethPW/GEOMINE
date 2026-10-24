"""Bounded, co-registered analysis of actual Sentinel COG pixels. No synthetic fallback."""

import hashlib
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
import numpy as np
import planetary_computer as pc
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from scipy.ndimage import label, median_filter
from shapely.geometry import mapping, shape
from shapely.ops import transform as transform_geom

from .catalog import catalog_url, radar_members
from .config import settings

RESOLUTION = 10


def grid_for(geometry, resolution=RESOLUTION):
    if resolution not in (10, 30):
        raise ValueError("Unsupported analysis resolution.")
    geom = shape(geometry)
    lon, lat = geom.centroid.x, geom.centroid.y
    crs = f"EPSG:{32600 + int((lon + 180) // 6) + 1 if lat >= 0 else 32700 + int((lon + 180) // 6) + 1}"
    forward = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    projected = transform_geom(forward.transform, geom)
    left, bottom, right, top = projected.bounds
    width, height = (
        math.ceil((right - left) / resolution),
        math.ceil((top - bottom) / resolution),
    )
    if width * height > 2_000_000:
        raise ValueError(
            "Area bounding box is too large. Use a compact area below 100 km²."
        )
    return crs, from_origin(left, top, resolution, resolution), width, height, projected


def read_asset(item, asset, crs, transform, width, height, categorical=False):
    if settings().pc_subscription_key:
        pc.settings.set_subscription_key(settings().pc_subscription_key)
    try:
        href = item["assets"][asset]["href"]
        if href.startswith("s3://deafrica-sentinel-1/"):
            href = (
                "https://deafrica-sentinel-1.s3.af-south-1.amazonaws.com/"
                + href.removeprefix("s3://deafrica-sentinel-1/")
            )
        else:
            href = pc.sign(href)
        with rasterio.Env(
            GDAL_HTTP_TIMEOUT="60",
            GDAL_HTTP_MAX_RETRY="2",
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
        ):
            with rasterio.open(href) as src:
                with WarpedVRT(
                    src,
                    crs=crs,
                    transform=transform,
                    width=width,
                    height=height,
                    resampling=Resampling.nearest
                    if categorical
                    else Resampling.bilinear,
                    nodata=np.nan,
                    dtype="float32",
                ) as vrt:
                    return vrt.read(1).astype("float32")
    except Exception:
        # Signed URLs and tokens must never be included in persisted errors.
        raise ValueError(
            f"Unable to read {item['collection']} {asset}. Check provider availability and access, then retry."
        ) from None


def optical_scaling(item):
    bands = ("B04", "B03", "B02", "B08")
    metadata = {b: item["assets"][b].get("raster:bands", [{}])[0] for b in bands}
    if all("scale" in metadata[b] for b in bands):
        return {b: (metadata[b]["scale"], metadata[b].get("offset", 0)) for b in bands}
    asset = item["assets"].get("product-metadata", {})
    if not asset.get("href"):
        raise ValueError("Sentinel-2 radiometric product metadata is unavailable.")
    try:
        href = pc.sign(asset["href"])
        with httpx.Client(timeout=45) as client:
            with client.stream("GET", href) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError("Metadata exceeds the supported size.")
        if b"<!DOCTYPE" in body or b"<!ENTITY" in body:
            raise ValueError("Unsupported XML declarations.")
        elements = list(ET.fromstring(body).iter())
        quant = next(
            float(e.text)
            for e in elements
            if e.tag.split("}")[-1] == "BOA_QUANTIFICATION_VALUE"
        )
        if quant <= 0:
            raise ValueError("Invalid reflectance quantification.")
        offsets = {
            e.attrib["band_id"]: float(e.text)
            for e in elements
            if e.tag.split("}")[-1] == "BOA_ADD_OFFSET"
        }
        baseline = float(item["properties"].get("s2:processing_baseline", "0"))
        ids = {"B02": "1", "B03": "2", "B04": "3", "B08": "7"}
        if baseline >= 4 and any(ids[b] not in offsets for b in bands):
            raise ValueError(
                "Missing radiometric offsets for this processing baseline."
            )
        return {b: (1 / quant, offsets.get(ids[b], 0) / quant) for b in bands}
    except Exception:
        raise ValueError(
            "Unable to load authoritative Sentinel-2 radiometric metadata. Retry provider access."
        ) from None


def read_optical(item, grid):
    crs, affine, width, height, _ = grid
    scl = read_asset(item, "SCL", crs, affine, width, height, True)
    bands = np.stack(
        [
            read_asset(item, b, crs, affine, width, height)
            for b in ("B04", "B03", "B02", "B08")
        ]
    )
    # Product XML is authoritative when MPC STAC omits radiometric scale/offset.
    scale_offsets = optical_scaling(item)
    for n, b in enumerate(("B04", "B03", "B02", "B08")):
        scale, offset = scale_offsets[b]
        bands[n] = bands[n] * scale + offset
    clear = np.isin(scl, [4, 5, 6, 7]) & np.isfinite(bands).all(axis=0)
    return bands, clear


def read_radar(item, grid):
    crs, affine, width, height, _ = grid
    bands = np.full((2, height, width), np.nan, dtype="float32")
    valid = np.zeros((height, width), dtype=bool)
    for member in radar_members(item):
        tile = np.stack(
            [read_asset(member, b, crs, affine, width, height) for b in ("vv", "vh")]
        )
        usable = np.isfinite(tile).all(axis=0) & (tile > 0).all(axis=0)
        if member["collection"] == "s1_rtc":
            mask = read_asset(member, "mask", crs, affine, width, height, True)
            usable &= mask == 1
        take = usable & ~valid
        # Both polarizations must come from the same valid tile. Do not fill
        # holes with a different pass, blend across dates, or invent pixels.
        bands[:, take] = tile[:, take]
        valid |= usable
    return bands, valid


def physical_scores(opt1, opt2, sar1, sar2, clear, valid):
    ndvi1 = (opt1[3] - opt1[0]) / (opt1[3] + opt1[0] + 1e-6)
    ndvi2 = (opt2[3] - opt2[0]) / (opt2[3] + opt2[0] + 1e-6)
    loss = np.nan_to_num(ndvi1 - ndvi2)
    db1 = 10 * np.log10(np.maximum(sar1[0], 1e-8))
    db2 = 10 * np.log10(np.maximum(sar2[0], 1e-8))
    db_change = median_filter(np.nan_to_num(db2 - db1), size=5)
    # Deliberately conservative: uncalibrated physical evidence, not mining probability.
    score = np.clip(loss / 0.6, 0, 1) * np.clip(np.abs(db_change) / 6, 0, 1)
    candidates = (
        clear & valid & (loss > 0.2) & (np.abs(db_change) > 2.5) & (ndvi1 > 0.25)
    )
    score[~candidates] = 0
    return score, {
        "clear_optical_fraction": float(clear[valid].mean()) if valid.any() else 0,
        "radar_valid_fraction": float(valid.mean()),
    }


def model_scores(opt1, opt2, sar1, sar2, clear1, clear2, legal):
    import torch
    from safetensors.torch import load_file

    from .ml.model import GeoMineXNet

    config = settings()
    manifest = json.loads(Path(config.model_manifest_path).read_text())
    if (
        manifest.get("architecture") != "geomine-xnet-swin-tiny-v1"
        or not manifest.get("validation_metrics")
        or not manifest.get("test_metrics")
        or manifest.get("release_approved") is not True
    ):
        raise ValueError(
            "Model manifest must declare the supported architecture and held-out validation metrics."
        )
    if hashlib.sha256(Path(config.model_path).read_bytes()).hexdigest() != manifest.get(
        "sha256"
    ):
        raise ValueError("Model checksum does not match its manifest.")
    model = GeoMineXNet()
    model.load_state_dict(load_file(config.model_path), strict=True)
    model.eval()

    def tensor(opt, sar):
        arr = np.concatenate(
            [np.clip(opt, 0, 1), (10 * np.log10(np.maximum(sar, 1e-8)) + 25) / 25]
        )
        return torch.from_numpy(np.nan_to_num(arr).astype("float32"))

    before, after = tensor(opt1, sar1), tensor(opt2, sar2)
    h, w = legal.shape
    output = np.zeros((h, w), dtype="float32")
    # Fixed-size tiles preserve exact 10m ground resolution. No image-wide downscaling.
    with torch.inference_mode():
        for y in range(0, h, 512):
            for x in range(0, w, 512):
                th, tw = min(512, h - y), min(512, w - x)

                def pad(t):
                    return torch.nn.functional.pad(
                        t[..., y : y + th, x : x + tw], (0, 512 - tw, 0, 512 - th)
                    )

                cloud = torch.from_numpy(np.stack([~clear1, ~clear2]).astype("float32"))
                result = model(pad(before)[None], pad(after)[None], pad(cloud)[None])[
                    "raw_logits"
                ].sigmoid()[0, 0, :th, :tw]
                output[y : y + th, x : x + tw] = result.numpy()
    return output, manifest


def analyze(
    geometry,
    optical_before,
    optical_after,
    radar_before,
    radar_after,
    concessions,
    engine,
    progress,
):
    resolution = max(
        radar_before["properties"].get("geomine:analysis_grid_m", 10),
        radar_after["properties"].get("geomine:analysis_grid_m", 10),
    )
    if engine == "geomine" and resolution != 10:
        raise ValueError(
            "This checkpoint expects 10m inputs. Public Africa RTC is analyzed on a 30m grid; use the physical detector or configure the 10m provider."
        )
    grid = grid_for(geometry, resolution)
    crs, affine, width, height, projected = grid
    progress("Reading and aligning Sentinel-2 pixels", 35)
    opt1, clear1 = read_optical(optical_before, grid)
    opt2, clear2 = read_optical(optical_after, grid)
    progress("Reading co-orbital Sentinel-1 radar", 55)
    sar1, valid1 = read_radar(radar_before, grid)
    sar2, valid2 = read_radar(radar_after, grid)
    aoi = rasterize(
        [(projected, 1)], out_shape=(height, width), transform=affine, fill=0
    ).astype(bool)
    valid = valid1 & valid2 & aoi
    if not valid.any():
        raise ValueError(
            "No valid overlapping radar pixels were returned for this area."
        )
    clear = clear1 & clear2 & aoi
    forward = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    projected_legal = [
        transform_geom(forward.transform, shape(c["geometry"])) for c in concessions
    ]
    legal = (
        rasterize(
            [(g, 1) for g in projected_legal],
            out_shape=(height, width),
            transform=affine,
            fill=0,
        ).astype(bool)
        if projected_legal
        else np.zeros((height, width), dtype=bool)
    )
    progress("Computing change evidence and phenology filter", 75)
    model_manifest = None
    if engine == "geomine":
        scores, model_manifest = model_scores(
            opt1, opt2, sar1, sar2, clear1, clear2, legal
        )
        scores[~valid] = 0
        threshold = float(model_manifest.get("threshold", 0.5))
        quality = {
            "clear_optical_fraction": float(clear[aoi].mean()),
            "radar_valid_fraction": float(valid[aoi].mean()),
        }
    else:
        scores, quality = physical_scores(opt1, opt2, sar1, sar2, clear, valid)
        quality["radar_valid_fraction"] = float(valid[aoi].mean())
        threshold = 0.15
    progress("Intersecting supplied concession boundaries", 90)
    # Legal and unknown candidates remain reviewable; do not silently discard evidence.
    reverse = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    candidates = []
    for inside in (False, True):
        mask = (scores >= threshold) & valid & (legal == inside)
        labeled, count = label(mask)
        sizes = np.bincount(labeled.ravel())
        keep = sizes >= 9  # Nine analysis pixels; minimum area depends on actual grid.
        keep[0] = False
        clean = keep[labeled]
        for geom, value in shapes(clean.astype("uint8"), mask=clean, transform=affine):
            poly = shape(geom).intersection(projected)
            if poly.is_empty:
                continue
            pix = rasterize(
                [(poly, 1)], out_shape=(height, width), transform=affine
            ).astype(bool)
            context = (
                "inside_supplied_concession"
                if inside
                else ("outside_supplied_concessions" if concessions else "unknown")
            )
            candidates.append(
                {
                    "geometry": mapping(
                        transform_geom(
                            reverse.transform, poly.simplify(5, preserve_topology=True)
                        )
                    ),
                    "area_ha": poly.area / 10000,
                    "score": float(scores[pix].mean()),
                    "legal_context": context,
                }
            )
    candidates.sort(key=lambda c: c["area_ha"], reverse=True)
    if len(candidates) > 2000:
        raise ValueError(
            "More than 2,000 candidate polygons. Reduce the analysis area before retrying."
        )
    scene_records = [
        {
            "id": i["id"],
            "collection": i["collection"],
            "datetime": i["properties"]["datetime"],
            "catalog_url": catalog_url(i),
            "provider": i["properties"].get("geomine:provider", "planetary-computer"),
        }
        for i in (
            optical_before,
            optical_after,
            *radar_members(radar_before),
            *radar_members(radar_after),
        )
    ]
    return {
        "engine": engine,
        "score_type": "uncalibrated_model_score"
        if engine == "geomine"
        else "physical_evidence_index",
        "quality": quality,
        "resolution_m": resolution,
        "radar_source": radar_before["properties"].get(
            "geomine:provider", "planetary-computer"
        ),
        "minimum_candidate_ha": 9 * resolution * resolution / 10000,
        "candidate_count": len(candidates),
        "area_ha": sum(c["area_ha"] for c in candidates),
        "scenes": scene_records,
        "concessions_used": [str(c["id"]) for c in concessions],
        "model": model_manifest,
        "optical_processing_baselines": [
            optical_before["properties"].get("s2:processing_baseline"),
            optical_after["properties"].get("s2:processing_baseline"),
        ],
        "radiometry": "Product XML BOA quantification/offset or explicit STAC raster metadata",
        "limitations": [
            "Candidate disturbance requires human interpretation; it is not proof of mining or illegality.",
            "Concession status refers only to user-supplied boundaries and their stated validity dates.",
            "Satellite observations update on acquisition and provider availability, not continuous live video.",
            *(
                [
                    "Public Digital Earth Africa RTC covers Africa. Native radar cells are 0.0002 degrees (approximately 20m); this analysis uses a conservative 30m grid and does not claim 10m detail."
                ]
                if resolution == 30
                else []
            ),
            *(
                [
                    "Physical mode excludes cloudy optical pixels; it does not reproduce the paper’s cloud-resilient neural model."
                ]
                if engine == "physical"
                else [
                    "Checkpoint performance depends on training geography and held-out evaluation."
                ]
            ),
        ],
    }, candidates


def render_optical_preview(geometry, item, resolution=10):
    """Render dated source pixels on exactly the analysis grid, with a fixed RGB stretch."""
    import io

    from PIL import Image

    grid = grid_for(geometry, resolution)
    bands, clear = read_optical(item, grid)
    rgb = np.nan_to_num(np.clip(bands[:3] / 0.3, 0, 1)) ** (1 / 1.8)
    pixels = (rgb.transpose(1, 2, 0) * 255).astype("uint8")
    output = io.BytesIO()
    image = Image.fromarray(pixels)
    image.thumbnail((1200, 1200))
    image.save(output, format="PNG")
    return output.getvalue()
