from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from scripts.convert_yolo_gold_annotations import convert_annotations


def test_converts_yolo_gold_annotation_to_json_template(tmp_path: Path) -> None:
    labels_dir = tmp_path / "labels"
    images_dir = tmp_path / "images"
    output_dir = tmp_path / "gold"
    labels_dir.mkdir()
    images_dir.mkdir()

    Image.new("RGB", (100, 80)).save(images_dir / "000001.png")
    (labels_dir / "000001.txt").write_text("3 0.5 0.5 0.2 0.4\n", encoding="utf-8")
    class_config = tmp_path / "kitti.yaml"
    class_config.write_text("names:\n  0: car\n  3: pedestrian\n", encoding="utf-8")

    image_count, label_count, class_counts = convert_annotations(
        labels_dir=labels_dir,
        images_dir=images_dir,
        output_dir=output_dir,
        class_config=class_config,
        overwrite=False,
    )

    payload = json.loads((output_dir / "000001.json").read_text(encoding="utf-8"))
    assert image_count == 1
    assert label_count == 1
    assert class_counts == {"pedestrian": 1}
    assert payload == {
        "image_id": "000001",
        "image_width": 100,
        "image_height": 80,
        "labels": [
            {
                "label_id": "gold-000001-001",
                "class_name": "pedestrian",
                "bbox": {"x1": 40.0, "y1": 24.0, "x2": 60.0, "y2": 56.0},
                "attributes": {"occluded": None, "truncated": None},
            }
        ],
    }
