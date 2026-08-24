from pathlib import Path

import pytest
from PIL import Image

from src.models.ingestion import AnnotationSource, QAReviewStatus
from src.services.ingestion.yolo_detection_adapter import YoloDatasetLayoutError, YoloDetectionAdapter


def _write_yolo_dataset(root: Path) -> None:
    for split in ("train", "val"):
        (root / "images" / split).mkdir(parents=True)
        (root / "labels" / split).mkdir(parents=True)
    (root / "class.txt.txt").write_text("car\npedestrian\n", encoding="utf-8")
    Image.new("RGB", (100, 80)).save(root / "images" / "train" / "000001.png")
    (root / "labels" / "train" / "000001.txt").write_text("0 0.5 0.5 0.2 0.25\n", encoding="utf-8")
    Image.new("RGB", (200, 100)).save(root / "images" / "val" / "000001.png")
    (root / "labels" / "val" / "000001.txt").write_text("1 0.5 0.5 0.5 0.4\n", encoding="utf-8")


def test_loads_all_yolo_splits_with_pixel_bboxes_and_unique_ids(tmp_path: Path):
    _write_yolo_dataset(tmp_path)

    images, objects = YoloDetectionAdapter(tmp_path).load()

    assert [image.source_image_id for image in images] == ["kitti-yolo:train:000001", "kitti-yolo:val:000001"]
    assert [image.filename for image in images] == ["images/train/000001.png", "images/val/000001.png"]
    assert objects[0].label == "car"
    assert objects[0].bbox.as_xyxy() == [40.0, 30.0, 60.0, 50.0]
    assert objects[0].review_status == QAReviewStatus.VERIFIED
    assert objects[0].provenance[0].source == AnnotationSource.KITTI
    assert objects[0].provenance[0].raw["format"] == "yolo"
    assert objects[1].label == "pedestrian"
    assert objects[1].bbox.as_xyxy() == [50.0, 30.0, 150.0, 70.0]


def test_filters_yolo_dataset_by_split(tmp_path: Path):
    _write_yolo_dataset(tmp_path)

    images, objects = YoloDetectionAdapter(tmp_path, split="val").load()

    assert len(images) == 1
    assert images[0].source_image_id == "kitti-yolo:val:000001"
    assert len(objects) == 1
    assert objects[0].label == "pedestrian"


def test_loads_class_names_from_ultralytics_yaml(tmp_path: Path):
    for split in ("train",):
        (tmp_path / "images" / split).mkdir(parents=True)
        (tmp_path / "labels" / split).mkdir(parents=True)
    (tmp_path / "kitti.yaml").write_text("names:\n  0: car\n  1: pedestrian\n", encoding="utf-8")
    Image.new("RGB", (100, 80)).save(tmp_path / "images" / "train" / "000001.png")
    (tmp_path / "labels" / "train" / "000001.txt").write_text("1 0.5 0.5 0.2 0.25\n", encoding="utf-8")

    images, objects = YoloDetectionAdapter(tmp_path).load()

    assert images[0].filename == "images/train/000001.png"
    assert objects[0].label == "pedestrian"


def test_rejects_yolo_class_id_outside_class_file(tmp_path: Path):
    _write_yolo_dataset(tmp_path)
    (tmp_path / "labels" / "train" / "000001.txt").write_text("2 0.5 0.5 0.2 0.25\n", encoding="utf-8")

    with pytest.raises(YoloDatasetLayoutError, match="outside 0..1"):
        YoloDetectionAdapter(tmp_path, split="train").load()
