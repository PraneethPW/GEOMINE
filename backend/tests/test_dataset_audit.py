"""Numerical data-contract fixtures only; never application observations."""

import json
import shutil

import numpy as np
import pytest
from shapely.geometry import box, mapping

pytest.importorskip("torch", reason="Install requirements-ml.txt to audit ML tensor contracts")

from app.ml.audit import audit_dataset


def dataset(tmp_path):
    manifest = {
        "provenance": {
            "dataset_name": "Isolated numerical contract test",
            "source_url": "https://example.invalid/unit-test",
            "license": "test-only",
            "annotation_protocol": "Explicit numerical unit fixtures, not ground truth",
            "label_type": "disturbance_change",
            "resolution_m": 10,
        }
    }
    for index, split in enumerate(("train", "validation", "test")):
        before = np.full((6, 512, 512), 0.2 + index * 0.1, dtype="float32")
        mask = np.zeros((1, 512, 512), dtype="float32")
        mask[:, :256] = 1
        np.savez_compressed(
            tmp_path / (split + ".npz"),
            before=before,
            after=before * 0.9,
            mask=mask,
            cloud=np.zeros((2, 512, 512), dtype="float32"),
            valid=np.ones((1, 512, 512), dtype="float32"),
        )
        manifest[split] = [
            {
                "path": split + ".npz",
                "group": "site-" + str(index),
                "geometry": mapping(box(index, 0, index + 0.02, 0.02)),
                "source_ids": ["test-" + str(i) for i in range(4)],
                "annotation": {
                    "status": "reviewed",
                    "coverage": "complete",
                    "reviewer": "numerical-fixture-only",
                    "reviewed_at": "2025-01-01T00:00:00Z",
                },
            }
        ]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_dataset_audit_reports_counts_and_rejects_geographic_leakage(tmp_path):
    manifest = dataset(tmp_path)
    report = audit_dataset(tmp_path)
    assert report["status"] == "passed"
    assert report["splits"]["test"]["positive_pixels"] == 512 * 256
    manifest["validation"][0]["geometry"] = manifest["train"][0]["geometry"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="overlap"):
        audit_dataset(tmp_path)


def test_dataset_audit_rejects_duplicate_content_and_unreviewed_labels(tmp_path):
    manifest = dataset(tmp_path)
    shutil.copyfile(tmp_path / "train.npz", tmp_path / "test.npz")
    with pytest.raises(ValueError, match="Identical"):
        audit_dataset(tmp_path)
    manifest["train"][0]["annotation"]["status"] = "unreviewed"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="human-reviewed"):
        audit_dataset(tmp_path)


def test_dataset_audit_rejects_static_extent_labels_as_temporal_truth(tmp_path):
    manifest = dataset(tmp_path)
    manifest["provenance"]["label_type"] = "static_mining_extent"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="disturbance-change"):
        audit_dataset(tmp_path)
