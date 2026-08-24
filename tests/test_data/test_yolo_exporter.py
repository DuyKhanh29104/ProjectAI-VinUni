import json
from pathlib import Path

from PIL import Image

from src.models.ingestion import AnnotationProvenance, AnnotationSource, BoundingBox, QAObjectPayload, QAReviewStatus
from src.services.ingestion.kitti_adapter import ImageMetadata
from src.services.ingestion.yolo_exporter import export_normalized_to_yolo


def _payload(image_id: str, label: str, bbox: BoundingBox) -> QAObjectPayload:
    return QAObjectPayload(
        source_image_id=image_id,
        label=label,
        bbox=bbox,
        review_status=QAReviewStatus.VERIFIED,
        provenance=[
            AnnotationProvenance(
                source=AnnotationSource.KITTI,
                source_annotation_id=f"{image_id}:0",
                bbox=bbox,
            )
        ],
    )


def test_exports_normalized_kitti_and_nuscenes_labels_as_coco_yolo(tmp_path: Path):
    source = tmp_path / "source"
    (source / "training/image_2").mkdir(parents=True)
    (source / "samples/CAM_FRONT").mkdir(parents=True)
    Image.new("RGB", (100, 80)).save(source / "training/image_2/000001.png")
    Image.new("RGB", (100, 80)).save(source / "samples/CAM_FRONT/frame.jpg")
    images = [
        ImageMetadata("kitti:000001", "training/image_2/000001.png", 100, 80),
        ImageMetadata("camera-token", "samples/CAM_FRONT/frame.jpg", 100, 80),
    ]
    objects = [
        _payload("kitti:000001", "car", BoundingBox(xmin=10, ymin=20, xmax=50, ymax=60)),
        _payload("camera-token", "vehicle.car", BoundingBox(xmin=-5, ymin=10, xmax=30, ymax=50)),
        _payload("camera-token", "animal", BoundingBox(xmin=10, ymin=10, xmax=20, ymax=20)),
    ]

    result = export_normalized_to_yolo(
        source_root=source, images=images, objects=objects, output_root=tmp_path / "derived", split="val"
    )

    assert result.images == 2
    assert result.annotations == 2
    assert result.skipped_labels == {"animal": 1}
    assert (tmp_path / "derived/classes.txt").read_text().splitlines() == [
        "person", "bicycle", "car", "motorcycle", "bus", "truck", "train"
    ]
    assert (tmp_path / "derived/labels/val/kitti_000001.txt").read_text() == "2 0.300000 0.500000 0.400000 0.500000\n"
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["images"][1]["source_image_id"] == "camera-token"
