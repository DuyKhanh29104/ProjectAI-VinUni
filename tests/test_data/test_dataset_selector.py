import json
from pathlib import Path

from src.services.ingestion.dataset_selector import (
    DatasetLayoutError,
    DatasetScenario,
    DatasetType,
    select_dataset_layout,
)


def test_selects_kitti_flat_directory(tmp_path: Path):
    for directory in ("image_2", "velodyne", "calib", "label_2"):
        (tmp_path / directory).mkdir()

    selected = select_dataset_layout("kitti", tmp_path)

    assert selected.dataset_type == DatasetType.KITTI
    assert selected.dataset_root == tmp_path
    assert "flat" in selected.description
    assert selected.scenario == DatasetScenario.BASELINE_EASY
    assert selected.tags == ("urban_daytime", "clear_weather", "mid_density", "europe")
    assert selected.context["region"] == "Karlsruhe, Germany / Europe"


def test_selects_kitti_derived_yolo_directory(tmp_path: Path):
    (tmp_path / "images" / "train").mkdir(parents=True)
    (tmp_path / "labels" / "train").mkdir(parents=True)
    (tmp_path / "images" / "train" / "frame.png").write_bytes(b"placeholder")
    (tmp_path / "class.txt.txt").write_text("car\npedestrian\n", encoding="utf-8")

    selected = select_dataset_layout("kitti", tmp_path)

    assert selected.dataset_type == DatasetType.KITTI
    assert "YOLO" in selected.description
    assert selected.context["annotation_format"] == "yolo"


def test_selects_ultralytics_yolo_yaml_directory(tmp_path: Path):
    (tmp_path / "images" / "train").mkdir(parents=True)
    (tmp_path / "labels" / "train").mkdir(parents=True)
    (tmp_path / "images" / "train" / "frame.png").write_bytes(b"placeholder")
    (tmp_path / "kitti.yaml").write_text("names:\n  0: car\n  1: pedestrian\n", encoding="utf-8")

    selected = select_dataset_layout("kitti", tmp_path)

    assert selected.dataset_type == DatasetType.KITTI
    assert "YOLO" in selected.description
    assert selected.context["annotation_format"] == "yolo"


def test_selects_nuscenes_relational_graph(tmp_path: Path):
    metadata_root = tmp_path / "v1.0-mini"
    metadata_root.mkdir()
    for table in ("scene", "sample", "sample_data", "sample_annotation", "calibrated_sensor"):
        (metadata_root / f"{table}.json").write_text(json.dumps([]))

    selected = select_dataset_layout("nuscenes", tmp_path, nuscenes_version="v1.0-mini")

    assert selected.dataset_type == DatasetType.NUSCENES
    assert selected.version == "v1.0-mini"
    assert "relational" in selected.description
    assert selected.scenario == DatasetScenario.CHALLENGING_HARD
    assert selected.tags == ("congested_urban", "night_time", "rainy", "high_density", "multi_region")
    assert selected.context["traffic_density"] == "high_density"


def test_rejects_scenario_dataset_mismatch(tmp_path: Path):
    for directory in ("image_2", "velodyne", "calib", "label_2"):
        (tmp_path / directory).mkdir()

    try:
        select_dataset_layout("kitti", tmp_path, scenario="challenging_hard")
    except DatasetLayoutError as error:
        assert "maps to nuscenes" in str(error)
    else:
        raise AssertionError("Expected mismatched scenario and dataset to fail")


def test_rejects_incomplete_kitti_flat_directory(tmp_path: Path):
    (tmp_path / "image_2").mkdir()

    try:
        select_dataset_layout("kitti", tmp_path)
    except DatasetLayoutError as error:
        assert "velodyne" in str(error)
        assert "label_2" in str(error)
    else:
        raise AssertionError("Expected incomplete KITTI layout to fail")


def test_rejects_incomplete_nuscenes_relational_graph(tmp_path: Path):
    (tmp_path / "v1.0-mini").mkdir()

    try:
        select_dataset_layout("nuscenes", tmp_path, nuscenes_version="v1.0-mini")
    except DatasetLayoutError as error:
        assert "scene.json" in str(error)
        assert "sample_annotation.json" in str(error)
    else:
        raise AssertionError("Expected incomplete nuScenes layout to fail")
