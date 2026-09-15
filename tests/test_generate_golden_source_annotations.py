from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_golden_source_annotations import _iou, generate_sources


def _gold_payload(image_id: str) -> dict:
    return {
        "image_id": image_id,
        "image_width": 100,
        "image_height": 100,
        "labels": [
            {
                "label_id": f"gold-{image_id}-001",
                "class_name": "car",
                "bbox": {"x1": 10.0, "y1": 10.0, "x2": 40.0, "y2": 40.0},
                "attributes": {"occluded": None, "truncated": None},
            }
        ],
    }


def test_generates_one_pending_review_source_for_each_issue(tmp_path: Path) -> None:
    dataset_root = tmp_path / "golden"
    images_dir = dataset_root / "images"
    gold_dir = dataset_root / "gold_annotations"
    images_dir.mkdir(parents=True)
    gold_dir.mkdir()

    issue_specs = {
        "wrong_class": {
            "image_id": "000001",
            "target_gold_label_id": "gold-000001-001",
            "replacement_class": "truck",
            "severity": "high",
            "split": "dev",
        },
        "missing_label": {
            "image_id": "000002",
            "target_gold_label_id": "gold-000002-001",
            "severity": "medium",
            "split": "dev",
        },
        "extra_or_wrong_label": {
            "image_id": "000003",
            "extra_class": "car",
            "extra_bbox": {"x1": 60.0, "y1": 60.0, "x2": 80.0, "y2": 80.0},
            "severity": "medium",
            "split": "dev",
        },
        "bbox_misaligned": {
            "image_id": "000004",
            "target_gold_label_id": "gold-000004-001",
            "severity": "medium",
            "split": "dev",
        },
        "duplicate_label": {
            "image_id": "000005",
            "target_gold_label_id": "gold-000005-001",
            "severity": "medium",
            "split": "dev",
        },
        "clean_no_issue": {"image_id": "000006", "split": "blind"},
    }
    for spec in issue_specs.values():
        image_id = spec["image_id"]
        (images_dir / f"{image_id}.png").write_bytes(b"fixture")
        (gold_dir / f"{image_id}.json").write_text(json.dumps(_gold_payload(image_id)), encoding="utf-8")

    plan_path = dataset_root / "manifests" / "plan.json"
    plan_path.parent.mkdir()
    plan_path.write_text(
        json.dumps(
            {
                "version": "test-plan",
                "groups": {issue_type: [spec] for issue_type, spec in issue_specs.items()},
            }
        ),
        encoding="utf-8",
    )
    manifest_path = dataset_root / "manifests" / "samples.jsonl"

    counts = generate_sources(
        dataset_root=dataset_root,
        plan_path=plan_path,
        manifest_path=manifest_path,
        overwrite=False,
    )

    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert counts == {issue_type: 1 for issue_type in issue_specs}
    assert len(list((dataset_root / "source_annotations").glob("*.json"))) == 6
    assert all(row["review_status"] == "pending_human_review" for row in rows)
    assert all(row["use_for_metric"] is False for row in rows)

    bbox_row = next(row for row in rows if row["primary_issue_type"] == "bbox_misaligned")
    assert 0.2 <= bbox_row["gold_issues"][0]["source_gold_iou"] < 0.5
    duplicate_source = json.loads((dataset_root / "source_annotations" / "000005.json").read_text(encoding="utf-8"))
    first_bbox = duplicate_source["labels"][0]["bbox"]
    duplicate_bbox = duplicate_source["labels"][1]["bbox"]
    assert first_bbox != duplicate_bbox
    assert _iou(first_bbox, duplicate_bbox) >= 0.8

    with pytest.raises(FileExistsError):
        generate_sources(
            dataset_root=dataset_root,
            plan_path=plan_path,
            manifest_path=manifest_path,
            overwrite=False,
        )
