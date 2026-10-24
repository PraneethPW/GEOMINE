"""Build real georegistered training tiles from STAC scene IDs and complete human labels."""

import argparse
import asyncio
import hashlib
import json
from datetime import date
from pathlib import Path

import httpx
import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as transform_geom

from ..catalog import STAC
from ..geo import normalize_geojson
from ..processing import grid_for, read_optical, read_radar
from .train import Scenes


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--samples",
        type=Path,
        required=True,
        help="JSON list of real sample records; see docs/TRAINING.md",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--provenance",
        type=Path,
        required=True,
        help="Dataset license, source URL, annotation protocol and 10m contract metadata",
    )
    args = parser.parse_args()
    records = json.loads(args.samples.read_text())
    if not isinstance(records, list) or not records:
        raise ValueError("Provide a nonempty list of real labeled samples.")
    args.output.mkdir(parents=True, exist_ok=True)
    output = {s: [] for s in ("train", "validation", "test")}
    provenance = json.loads(args.provenance.read_text())
    group_splits = {}
    async with httpx.AsyncClient(timeout=60) as client:
        for record in records:
            group, split = record["group"], record["split"]
            if split not in output or group_splits.get(group, split) != split:
                raise ValueError(
                    "Every geographic group must belong to exactly one split."
                )
            group_splits[group] = split
            annotation = record.get("annotation", {})
            if (
                annotation.get("status") != "reviewed"
                or annotation.get("coverage") != "complete"
                or not annotation.get("reviewer")
                or not annotation.get("reviewed_at")
            ):
                raise ValueError(
                    "Every sample requires complete human-reviewed labels, reviewer attribution and review time."
                )
            geometry, _ = normalize_geojson(record["geometry"], 100)
            grid = grid_for(geometry)

            async def item(collection, id_):
                if "/" in id_ or ".." in id_:
                    raise ValueError("Invalid STAC item ID.")
                response = await client.get(
                    f"{STAC}/collections/{collection}/items/{id_}"
                )
                response.raise_for_status()
                scene = response.json()
                if not shape(scene["geometry"]).covers(shape(geometry)):
                    raise ValueError("Scene does not cover the complete training area.")
                return scene

            ob, oa, rb, ra = await asyncio.gather(
                item("sentinel-2-l2a", record["optical_before"]),
                item("sentinel-2-l2a", record["optical_after"]),
                item("sentinel-1-rtc", record["radar_before"]),
                item("sentinel-1-rtc", record["radar_after"]),
            )
            if rb["properties"].get("sat:relative_orbit") != ra["properties"].get(
                "sat:relative_orbit"
            ) or rb["properties"].get("sat:orbit_state") != ra["properties"].get(
                "sat:orbit_state"
            ):
                raise ValueError(
                    "Training radar scenes must use the same relative orbit and direction."
                )
            times = [
                date.fromisoformat(i["properties"]["datetime"][:10])
                for i in (ob, oa, rb, ra)
            ]
            if (
                not times[0] < times[1]
                or not times[2] < times[3]
                or max(abs((times[0] - times[2]).days), abs((times[1] - times[3]).days))
                > 12
            ):
                raise ValueError(
                    "Choose ordered before/after scenes, with radar and optical no more than 12 days apart."
                )
            opt1, clear1 = read_optical(ob, grid)
            opt2, clear2 = read_optical(oa, grid)
            sar1, valid1 = read_radar(rb, grid)
            sar2, valid2 = read_radar(ra, grid)
            crs, affine, width, height, projected = grid
            convert = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            labels = record["labels"]
            if labels.get("type") != "FeatureCollection":
                raise ValueError(
                    "Labels must be a complete manually reviewed FeatureCollection of disturbance polygons."
                )
            positive = [
                (transform_geom(convert.transform, shape(f["geometry"])), 1)
                for f in labels["features"]
            ]
            mask = (
                rasterize(positive, out_shape=(height, width), transform=affine, fill=0)
                if positive
                else np.zeros((height, width), dtype="uint8")
            )
            aoi = rasterize(
                [(projected, 1)], out_shape=(height, width), transform=affine, fill=0
            ).astype(bool)
            valid = valid1 & valid2 & aoi

            def normalized(opt, sar):
                return np.nan_to_num(
                    np.concatenate(
                        [
                            np.clip(opt, 0, 1),
                            (10 * np.log10(np.maximum(sar, 1e-8)) + 25) / 25,
                        ]
                    )
                ).astype("float32")

            arrays = {
                "before": normalized(opt1, sar1),
                "after": normalized(opt2, sar2),
                "mask": mask[None].astype("float32"),
                "valid": valid[None].astype("float32"),
                "cloud": np.stack([~clear1, ~clear2]).astype("float32"),
            }
            index = len(output[split])
            for y in range(0, height, 512):
                for x in range(0, width, 512):
                    th, tw = min(512, height - y), min(512, width - x)
                    tiles = {
                        k: np.pad(
                            v[:, y : y + th, x : x + tw],
                            ((0, 0), (0, 512 - th), (0, 512 - tw)),
                        )
                        for k, v in arrays.items()
                    }
                    if tiles["valid"].sum() < 512 * 512 * 0.1:
                        continue
                    path = f"{split}-{index:06d}.npz"
                    if (args.output / path).exists():
                        raise ValueError(
                            "Output tile exists. Use a new empty output directory."
                        )
                    np.savez_compressed(args.output / path, **tiles)
                    output[split].append(
                        {
                            "path": path,
                            "group": group,
                            "source_ids": [ob["id"], oa["id"], rb["id"], ra["id"]],
                            "geometry": geometry,
                            "annotation": annotation,
                            "sha256": hashlib.sha256(
                                (args.output / path).read_bytes()
                            ).hexdigest(),
                        }
                    )
                    index += 1
            print(
                json.dumps({"group": group, "split": split, "tiles": index}), flush=True
            )
    # Validate every tile through the training loader before emitting the manifest.
    for split, records in output.items():
        dataset = Scenes(args.output, records)
        for i in range(len(dataset)):
            dataset[i]
    output["provenance"] = provenance
    (args.output / "manifest.json").write_text(json.dumps(output, indent=2))
    from .audit import audit_dataset

    report = audit_dataset(args.output)
    (args.output / "dataset-audit.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
