"""Operator upload/import workflow. Runs on the training host or mounted Railway volume."""

import argparse
import hashlib
import json
import math
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def import_dataset(archive, destination):
    if destination.exists():
        raise ValueError("Destination already exists; import into a new directory.")
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 20 * 1024**3:
            raise ValueError("Dataset archive exceeds import limits.")
        for info in infos:
            path = Path(info.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Unsafe archive entry.")
            if not info.is_dir() and path.suffix not in (".json", ".npz"):
                raise ValueError("Only JSON manifests and NPZ tiles are accepted.")
        if "manifest.json" not in z.namelist():
            raise ValueError("manifest.json must be at the archive root.")
        destination.mkdir(parents=True)
        z.extractall(destination)
    from .train import Scenes

    manifest = json.loads((destination / "manifest.json").read_text())
    for split in ("train", "validation", "test"):
        if not manifest.get(split):
            raise ValueError(f"Missing {split} split.")
        dataset = Scenes(destination, manifest[split])
        for i in range(len(dataset)):
            dataset[i]
    from .audit import audit_dataset

    (destination / "dataset-audit.json").write_text(
        json.dumps(audit_dataset(destination), indent=2)
    )
    print(
        json.dumps(
            {
                "dataset": str(destination),
                "tiles": sum(len(manifest[s]) for s in ("train", "validation", "test")),
            }
        )
    )


def install_model(source, destination):
    manifest = json.loads((source / "manifest.json").read_text())
    weights = source / "model.safetensors"
    if (
        manifest.get("architecture") != "geomine-xnet-swin-tiny-v1"
        or not manifest.get("validation_metrics")
        or not manifest.get("test_metrics")
        or manifest.get("release_approved") is not True
    ):
        raise ValueError(
            "Require architecture, measured validation/test metrics and an explicit operator release review."
        )
    if hashlib.sha256(weights.read_bytes()).hexdigest() != manifest.get("sha256"):
        raise ValueError("Model checksum mismatch.")
    from safetensors.torch import load_file

    from .model import GeoMineXNet

    model = GeoMineXNet()
    model.load_state_dict(load_file(str(weights)), strict=True)
    if destination.exists():
        raise ValueError(
            "Use a new version directory; existing model versions are immutable."
        )
    destination.mkdir(parents=True)
    shutil.copy2(weights, destination / "model.safetensors")
    shutil.copy2(source / "manifest.json", destination / "manifest.json")
    print(
        json.dumps(
            {
                "model_path": str((destination / "model.safetensors").resolve()),
                "model_manifest_path": str((destination / "manifest.json").resolve()),
                "sha256": manifest["sha256"],
            }
        )
    )


def approve_model(source, reviewer, region, notes, minimum_f1, minimum_precision):
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    if manifest.get("dataset_audit", {}).get("status") != "passed":
        raise ValueError("Require a passed dataset audit before release review.")
    for split in ("validation_metrics", "test_metrics"):
        metrics = manifest.get(split, {})
        if not all(
            isinstance(metrics.get(k), (int, float))
            and math.isfinite(metrics[k])
            and 0 <= metrics[k] <= 1
            for k in ("precision", "recall", "f1", "foreground_iou")
        ):
            raise ValueError(
                "Require finite, measured validation and held-out test metrics."
            )
        if metrics["f1"] < minimum_f1 or metrics["precision"] < minimum_precision:
            raise ValueError(
                "Measured performance does not meet the declared release criteria."
            )
    if (
        not 0 <= minimum_f1 <= 1
        or not 0 <= minimum_precision <= 1
        or not reviewer.strip()
        or not region.strip()
        or not notes.read_text().strip()
    ):
        raise ValueError(
            "Provide explicit release criteria, reviewer, region and written evidence review."
        )
    if hashlib.sha256(
        (source / "model.safetensors").read_bytes()
    ).hexdigest() != manifest.get("sha256"):
        raise ValueError("Model checksum mismatch.")
    manifest["release_approved"] = True
    manifest["release_review"] = {
        "reviewer": reviewer,
        "region": region,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "minimum_f1": minimum_f1,
        "minimum_precision": minimum_precision,
        "review_notes_sha256": hashlib.sha256(notes.read_bytes()).hexdigest(),
    }
    path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"status": "operator-reviewed", "region": region}))


def main():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command", required=True)
    data = subs.add_parser("import-dataset")
    data.add_argument("--archive", type=Path, required=True)
    data.add_argument("--destination", type=Path, required=True)
    model = subs.add_parser("install-model")
    model.add_argument("--source", type=Path, required=True)
    model.add_argument("--destination", type=Path, required=True)
    review = subs.add_parser("approve-model")
    review.add_argument("--source", type=Path, required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--region", required=True)
    review.add_argument("--notes", type=Path, required=True)
    review.add_argument("--minimum-f1", type=float, required=True)
    review.add_argument("--minimum-precision", type=float, required=True)
    args = parser.parse_args()
    if args.command == "import-dataset":
        import_dataset(args.archive, args.destination)
    elif args.command == "install-model":
        install_model(args.source, args.destination)
    else:
        approve_model(
            args.source,
            args.reviewer,
            args.region,
            args.notes,
            args.minimum_f1,
            args.minimum_precision,
        )


if __name__ == "__main__":
    main()
