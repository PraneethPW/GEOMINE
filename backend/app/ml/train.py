"""Train from real labeled NPZ tiles. Explicit geography-separated splits are mandatory."""

import argparse
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import save_file
from scipy.ndimage import distance_transform_edt
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset

from .model import GeoMineXNet


class Scenes(Dataset):
    def __init__(self, root, records, augment=False):
        self.root = Path(root).resolve()
        self.records = records
        self.augment = augment

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        path = (self.root / self.records[index]["path"]).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Dataset path escapes dataset root.")
        with np.load(path, allow_pickle=False) as scene:
            arrays = {
                k: scene[k].astype("float32")
                for k in ("before", "after", "mask", "cloud", "valid")
            }
        if arrays["before"].shape != (6, 512, 512) or arrays["after"].shape != (
            6,
            512,
            512,
        ):
            raise ValueError(
                f"{path.name}: expected aligned 6×512×512 reflectance/radar tensors."
            )
        if arrays["cloud"].shape != (2, 512, 512) or any(
            arrays[k].shape != (1, 512, 512) for k in ("mask", "valid")
        ):
            raise ValueError("Expected cloud 2×512×512 and mask/valid 1×512×512.")
        if not all(np.isfinite(a).all() for a in arrays.values()):
            raise ValueError(
                "Training tensors must be finite; mask invalid pixels using valid."
            )
        for key in ("mask", "cloud", "valid"):
            if not np.isin(arrays[key], [0, 1]).all():
                raise ValueError(f"{key} must be binary.")
        if self.augment:
            axis = random.choice([None, -1, -2])
            if axis:
                arrays = {k: np.flip(v, axis).copy() for k, v in arrays.items()}
        foreground = arrays["mask"][0].astype(bool)
        distance = distance_transform_edt(~foreground) - distance_transform_edt(
            foreground
        )
        arrays["distance"] = (distance / (np.abs(distance).max() + 1e-6))[None].astype(
            "float32"
        )
        return {k: torch.from_numpy(v.copy()) for k, v in arrays.items()}


def loss_fn(logits, target, valid, distance):
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    probability = logits.sigmoid()
    pt = probability * target + (1 - probability) * (1 - target)
    focal = (1 - pt).pow(2) * bce * (0.25 * target + 0.75 * (1 - target))
    boundary = probability * distance
    return (
        (0.4 * bce + 0.4 * focal + 0.2 * boundary) * valid
    ).sum() / valid.sum().clamp_min(1)


def metrics(tp, fp, fn):
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / max(2 * tp + fp + fn, 1),
        "foreground_iou": tp / max(tp + fp + fn, 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--accumulate", type=int, default=1)
    parser.add_argument("--amp", action="store_true", help="Use CUDA mixed precision")
    parser.add_argument(
        "--warm-start",
        type=Path,
        help="Trusted safetensors weights; starts a new optimizer/run, not an exact resume",
    )
    parser.add_argument(
        "--evaluate-test",
        action="store_true",
        help="Evaluate the frozen validation-selected checkpoint on the test split",
    )
    parser.add_argument(
        "--device", default="cuda" if torch.cuda.is_available() else "cpu"
    )
    args = parser.parse_args()
    if min(args.epochs, args.batch_size, args.accumulate) < 1:
        raise ValueError("Epochs, batch size and accumulation must be positive.")
    from .audit import audit_dataset

    dataset_audit = audit_dataset(args.dataset)
    torch.manual_seed(42)
    random.seed(42)
    np.random.seed(42)
    manifest_path = args.dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for split in ("train", "validation", "test"):
        if not manifest.get(split):
            raise ValueError(
                f"Provide a nonempty {split} split with geographic group IDs."
            )
    groups = [
        {r["group"] for r in manifest[s]} for s in ("train", "validation", "test")
    ]
    paths = [{r["path"] for r in manifest[s]} for s in ("train", "validation", "test")]
    if any(
        groups[i] & groups[j] or paths[i] & paths[j]
        for i, j in ((0, 1), (0, 2), (1, 2))
    ):
        raise ValueError(
            "Training, validation and test geographic groups/files must be disjoint."
        )
    train = DataLoader(
        Scenes(args.dataset, manifest["train"], True),
        batch_size=args.batch_size,
        shuffle=True,
    )
    val = DataLoader(Scenes(args.dataset, manifest["validation"]), batch_size=1)
    test = DataLoader(Scenes(args.dataset, manifest["test"]), batch_size=1)
    model = GeoMineXNet().to(args.device)
    if args.warm_start:
        from safetensors.torch import load_file

        model.load_state_dict(load_file(str(args.warm_start)), strict=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-2)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "dataset-audit.json").write_text(json.dumps(dataset_audit, indent=2))
    mixed = args.amp and args.device.startswith("cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=mixed)
    best = -1.0
    history = []

    def evaluate(loader):
        model.eval()
        tp = fp = fn = 0
        with torch.inference_mode():
            for batch in loader:
                b = {k: v.to(args.device) for k, v in batch.items()}
                p = (
                    model(b["before"], b["after"], b["cloud"])["raw_logits"].sigmoid()
                    >= 0.5
                )
                truth = b["mask"] > 0.5
                valid = b["valid"] > 0.5
                tp += int((p & truth & valid).sum())
                fp += int((p & ~truth & valid).sum())
                fn += int((~p & truth & valid).sum())
        return metrics(tp, fp, fn)

    for epoch in range(args.epochs):
        model.train()
        total = 0
        optimizer.zero_grad(set_to_none=True)
        for batch_index, batch in enumerate(train):
            b = {k: v.to(args.device) for k, v in batch.items()}
            with torch.autocast(
                device_type="cuda" if mixed else "cpu",
                dtype=torch.float16,
                enabled=mixed,
            ):
                logits = model(b["before"], b["after"], b["cloud"])["raw_logits"]
                loss = loss_fn(logits, b["mask"], b["valid"], b["distance"])
            if not torch.isfinite(loss):
                raise ValueError(
                    "Training loss is not finite. Check input data and numerical precision."
                )
            group_size = min(
                args.accumulate,
                len(train) - (batch_index // args.accumulate) * args.accumulate,
            )
            scaler.scale(loss / group_size).backward()
            if (batch_index + 1) % args.accumulate == 0 or batch_index + 1 == len(
                train
            ):
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(
                    model.parameters(), 1.0, error_if_nonfinite=True
                )
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            total += loss.item()
        scheduler.step()
        measured = evaluate(val)
        record = {
            "epoch": epoch + 1,
            "train_loss": total / len(train),
            "validation": measured,
        }
        history.append(record)
        print(json.dumps(record), flush=True)
        if measured["f1"] > best:
            best = measured["f1"]
            path = args.output / "model.safetensors"
            save_file(
                {
                    k: v.detach().cpu().contiguous()
                    for k, v in model.state_dict().items()
                },
                str(path),
            )
            metadata = {
                "architecture": model.architecture,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "validation_metrics": measured,
                "epoch": epoch + 1,
                "threshold": 0.5,
                "resolution_m": 10,
                "channel_order": ["red", "green", "blue", "nir", "vv", "vh"],
                "normalization": "optical reflectance clipped 0..1; SAR gamma0: (10*log10(max(x,1e-8))+25)/25",
                "dataset_manifest_sha256": hashlib.sha256(
                    manifest_path.read_bytes()
                ).hexdigest(),
                "dataset_audit": dataset_audit,
                "release_approved": False,
                "warm_start": str(args.warm_start) if args.warm_start else None,
                "mixed_precision": mixed,
                "effective_batch_size": args.batch_size * args.accumulate,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "note": "Paper-informed implementation. Metrics belong to this dataset/checkpoint only.",
            }
            (args.output / "manifest.json").write_text(json.dumps(metadata, indent=2))
        (args.output / "history.json").write_text(json.dumps(history, indent=2))
    from safetensors.torch import load_file

    model.load_state_dict(load_file(str(args.output / "model.safetensors")))
    if not args.evaluate_test:
        print(
            json.dumps(
                {
                    "status": "validation-selected-checkpoint-saved",
                    "held_out_test": "not evaluated; requires explicit final evaluation",
                }
            ),
            flush=True,
        )
        return
    measured_test = evaluate(test)
    metadata = json.loads((args.output / "manifest.json").read_text())
    metadata["test_metrics"] = measured_test
    (args.output / "manifest.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps({"held_out_test": measured_test}), flush=True)


if __name__ == "__main__":
    main()
