"""Reject unusable labels, spatial leakage and duplicated scenes before GPU training."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from pyproj import Geod
from shapely.geometry import shape
from shapely.ops import nearest_points, unary_union

SPLITS = ("train", "validation", "test")


def audit_dataset(root):
    from .train import Scenes

    root = Path(root).resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    provenance = manifest.get("provenance", {})
    for field in ("dataset_name", "source_url", "license", "annotation_protocol"):
        if not isinstance(provenance.get(field), str) or not provenance[field].strip():
            raise ValueError(f"Dataset provenance requires {field}.")
    if (
        not provenance["source_url"].startswith("https://")
        or provenance.get("label_type") != "disturbance_change"
        or provenance.get("resolution_m") != 10
    ):
        raise ValueError(
            "Require HTTPS provenance, reviewed disturbance-change labels and the 10m input contract."
        )
    groups, paths, hashes = {}, {}, {}
    report = {
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "provenance": provenance,
        "splits": {},
    }
    geometry_by_group = {}
    for split in SPLITS:
        records = manifest.get(split)
        if not isinstance(records, list) or not records:
            raise ValueError(f"Require a nonempty {split} split.")
        dataset = Scenes(root, records)
        positive = negative = valid_pixels = 0
        for index, record in enumerate(records):
            group = record.get("group")
            if not isinstance(group, str) or not group.strip():
                raise ValueError("Every tile requires a geographic site group.")
            if groups.setdefault(group, split) != split:
                raise ValueError("Geographic groups must not cross splits.")
            geometry = shape(record.get("geometry", {}))
            if (
                geometry.geom_type not in ("Polygon", "MultiPolygon")
                or not geometry.is_valid
                or geometry.is_empty
            ):
                raise ValueError("Every tile requires its actual WGS84 study geometry.")
            if any(
                not -180 <= x <= 180 for x in (geometry.bounds[0], geometry.bounds[2])
            ) or any(
                not -90 <= y <= 90 for y in (geometry.bounds[1], geometry.bounds[3])
            ):
                raise ValueError("Study geometry must use WGS84 longitude/latitude.")
            geometry_by_group.setdefault(group, []).append(geometry)
            annotation = record.get("annotation", {})
            if (
                annotation.get("status") != "reviewed"
                or annotation.get("coverage") != "complete"
                or not str(annotation.get("reviewer", "")).strip()
            ):
                raise ValueError(
                    "Require complete, human-reviewed change annotations and reviewer attribution."
                )
            reviewed = datetime.fromisoformat(
                str(annotation.get("reviewed_at", "")).replace("Z", "+00:00")
            )
            if reviewed.tzinfo is None:
                raise ValueError("Annotation review time must include its timezone.")
            if len(record.get("source_ids", [])) < 4:
                raise ValueError(
                    "Record real before/after optical and radar source IDs."
                )
            path = (root / record["path"]).resolve()
            if not path.is_relative_to(root) or path in paths:
                raise ValueError("Dataset paths must be contained and unique.")
            paths[path] = split
            with path.open("rb") as content:
                checksum = hashlib.file_digest(content, "sha256").hexdigest()
            if hashes.setdefault(checksum, split) != split:
                raise ValueError(
                    "Identical tile content occurs across different splits."
                )
            if record.get("sha256") and record["sha256"] != checksum:
                raise ValueError("Training tile checksum does not match its manifest.")
            arrays = dataset[index]
            for epoch in ("before", "after"):
                optical = arrays[epoch][:4].numpy()
                if optical.min() < 0 or optical.max() > 1:
                    raise ValueError(
                        "Optical inputs must be normalized surface reflectance in 0..1."
                    )
            mask, valid = arrays["mask"].numpy() > 0.5, arrays["valid"].numpy() > 0.5
            if valid.mean() < 0.1:
                raise ValueError("A tile has less than 10% valid labeled coverage.")
            positive += int((mask & valid).sum())
            negative += int((~mask & valid).sum())
            valid_pixels += int(valid.sum())
        if not positive or not negative:
            raise ValueError(
                f"{split} must contain reviewed positive and negative change pixels."
            )
        report["splits"][split] = {
            "tiles": len(records),
            "sites": len({r["group"] for r in records}),
            "valid_pixels": valid_pixels,
            "positive_pixels": positive,
            "negative_pixels": negative,
        }
    sites = [
        (name, unary_union(geometries))
        for name, geometries in geometry_by_group.items()
    ]
    geod = Geod(ellps="WGS84")
    for i, (name, geometry) in enumerate(sites):
        for other, compared in sites[i + 1 :]:
            if groups[name] == groups[other]:
                continue
            if geometry.intersects(compared):
                raise ValueError(
                    "Study geometries overlap across splits; group the whole site together."
                )
            first, second = nearest_points(geometry, compared)
            _, _, distance = geod.inv(first.x, first.y, second.x, second.y)
            if distance < 1000:
                raise ValueError(
                    "Study sites in different splits are less than 1km apart."
                )
    report.update(
        status="passed",
        separation_buffer_m=1000,
        note="Checks reviewer attestations, data contracts and split leakage; it cannot certify annotation correctness or geographic generalization.",
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit_dataset(args.dataset)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "splits": result["splits"]}))


if __name__ == "__main__":
    main()
