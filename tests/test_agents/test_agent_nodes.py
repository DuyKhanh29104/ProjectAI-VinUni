from pathlib import Path

import pytest
from PIL import Image

from src.agents.geometry import iou
from src.agents.nodes.flagging import flag_issues_node
from src.agents.nodes.load_gt_labels import load_gt_labels_node
from src.agents.nodes.matching import match_labels_node
from src.agents.nodes.metrics import compute_metrics_node
from src.agents.nodes.validate_input import validate_input_node
from src.agents.nodes.yolo_inference import run_yolo_inference_node


def test_iou_handles_overlap_and_disjoint_boxes():
    first = {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 10.0}
    overlap = {"x1": 5.0, "y1": 5.0, "x2": 15.0, "y2": 15.0}
    disjoint = {"x1": 20.0, "y1": 20.0, "x2": 30.0, "y2": 30.0}

    assert iou(first, overlap) == pytest.approx(25 / 175)
    assert iou(first, disjoint) == 0.0


@pytest.mark.asyncio
async def test_loads_yolo_ground_truth_from_sibling_labels_directory(tmp_path: Path):
    image_path = tmp_path / "images" / "frame.png"
    label_path = tmp_path / "labels" / "frame.txt"
    image_path.parent.mkdir()
    label_path.parent.mkdir()
    Image.new("RGB", (100, 80)).save(image_path)
    label_path.write_text("0 0.5 0.5 0.2 0.25\n", encoding="utf-8")
    (label_path.parent / "classes.txt").write_text("car\n", encoding="utf-8")

    result = await load_gt_labels_node({"image_path": str(image_path)})

    assert result["gt_labels"] == [{"class_name": "car", "bbox": {"x1": 40.0, "y1": 30.0, "x2": 60.0, "y2": 50.0}}]


@pytest.mark.asyncio
async def test_loads_class_names_from_export_root_with_nonstandard_filename(tmp_path: Path):
    image_path = tmp_path / "images" / "train" / "frame.png"
    label_path = tmp_path / "labels" / "train" / "frame.txt"
    image_path.parent.mkdir(parents=True)
    label_path.parent.mkdir(parents=True)
    Image.new("RGB", (100, 80)).save(image_path)
    label_path.write_text("1 0.5 0.5 0.2 0.25\n", encoding="utf-8")
    (tmp_path / "class.txt.txt").write_text("car\npedestrian\n", encoding="utf-8")

    result = await load_gt_labels_node({"image_path": str(image_path)})

    assert result["gt_labels"][0]["class_name"] == "pedestrian"


@pytest.mark.asyncio
async def test_matching_metrics_and_flagging_preserve_rule_based_decisions():
    gt_labels = [{"label_id": "gt-1", "class_name": "car", "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}}]
    pred_labels = [
        {
            "class_name": "truck",
            "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            "confidence": 0.9,
        }
    ]

    matched = await match_labels_node({"gt_labels": gt_labels, "pred_labels": pred_labels})
    metrics = await compute_metrics_node(matched)
    flagged = await flag_issues_node({**matched, **metrics, "gt_labels": gt_labels})

    assert metrics["metrics"]["class_accuracy"] == 0.0
    assert flagged["flagged_issues"][0]["issue_type"] == "wrong_class"
    assert flagged["flagged_issues"][0]["severity"] == "high"


@pytest.mark.asyncio
async def test_matching_normalizes_nuscenes_and_kitti_taxonomies():
    gt_labels = [
        {
            "label_id": "gt-vehicle",
            "class_name": "vehicle.car",
            "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
        }
    ]
    pred_labels = [
        {
            "class_name": "car",
            "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            "confidence": 0.9,
        }
    ]

    matched = await match_labels_node({"gt_labels": gt_labels, "pred_labels": pred_labels})

    assert matched["matches"][0]["class_match"] is True


@pytest.mark.asyncio
async def test_validation_excludes_outside_labels_and_clips_partial_boxes(tmp_path: Path):
    image_path = tmp_path / "frame.png"
    Image.new("RGB", (100, 80)).save(image_path)
    result = await validate_input_node(
        {
            "image_path": str(image_path),
            "gt_labels": [
                {"label_id": "outside", "class_name": "car", "bbox": {"x1": -40, "y1": 10, "x2": -10, "y2": 30}},
                {"label_id": "partial", "class_name": "car", "bbox": {"x1": -10, "y1": 10, "x2": 20, "y2": 30}},
            ],
            "pred_labels": [
                {"class_name": "car", "bbox": {"x1": 110, "y1": 10, "x2": 130, "y2": 30}, "confidence": 0.9}
            ],
        }
    )

    assert [label["label_id"] for label in result["gt_labels"]] == ["partial"]
    assert result["gt_labels"][0]["bbox"] == {"x1": 0.0, "y1": 10.0, "x2": 20.0, "y2": 30.0}
    assert result["gt_labels"][0]["source_bbox"]["x1"] == -10.0
    assert result["pred_labels"] == []
    assert result["metadata"]["label_scope"]["ground_truth_excluded_outside"] == 1
    assert result["metadata"]["label_scope"]["ground_truth_clipped"] == 1


@pytest.mark.asyncio
async def test_yolo_is_skipped_when_predictions_are_supplied(monkeypatch: pytest.MonkeyPatch):
    def fail_if_loaded():
        raise AssertionError("YOLO model must not load when predictions are supplied")

    monkeypatch.setattr("src.agents.nodes.yolo_inference.get_yolo_model", fail_if_loaded)
    result = await run_yolo_inference_node({"image_path": "fixture.png", "pred_labels": []})

    assert result == {}


@pytest.mark.asyncio
async def test_yolo_load_failure_becomes_pipeline_error(monkeypatch: pytest.MonkeyPatch):
    def fail_to_load():
        raise ModuleNotFoundError("ultralytics is not installed")

    monkeypatch.setattr("src.agents.nodes.yolo_inference.get_yolo_model", fail_to_load)
    result = await run_yolo_inference_node({"image_path": "fixture.png"})

    assert "ultralytics is not installed" in result["error"]
