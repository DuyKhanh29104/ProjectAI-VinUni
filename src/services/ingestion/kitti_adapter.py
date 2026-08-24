"""Parser for official KITTI and COCO-based 2D fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.models.ingestion import (
    AnnotationProvenance,
    AnnotationSource,
    BoundingBox,
    QAObjectPayload,
    QAReviewStatus,
)


@dataclass(frozen=True)
class ImageMetadata:
    source_image_id: str
    filename: str
    width: int
    height: int
    storage_filename: str | None = None


@dataclass(frozen=True)
class ParsedAnnotation:
    image_id: str
    label: str
    provenance: AnnotationProvenance


def parse_kitti_calibration(path: Path) -> dict[str, list[list[float]]]:
    """Parse KITTI text calibration into named 3x3/3x4/4x4 matrices."""
    matrices: dict[str, list[list[float]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, raw_values = line.split(":", 1)
        values = [float(value) for value in raw_values.split()]
        if len(values) == 9:
            matrices[key] = [values[index : index + 3] for index in range(0, 9, 3)]
        elif len(values) == 12:
            matrices[key] = [values[index : index + 4] for index in range(0, 12, 4)]
        elif len(values) == 16:
            matrices[key] = [values[index : index + 4] for index in range(0, 16, 4)]
        else:
            raise ValueError(f"Unsupported KITTI calibration size for {key}: {len(values)}")
    if not matrices:
        raise ValueError(f"No calibration matrices found in {path}")
    return matrices


def _parse_coco(path: Path) -> tuple[dict[str, ImageMetadata], list[ParsedAnnotation]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    categories = {category["id"]: category["name"] for category in payload.get("categories", [])}
    images = {
        str(image["id"]): ImageMetadata(
            source_image_id=str(image["id"]), filename=image["file_name"], width=image["width"], height=image["height"]
        )
        for image in payload.get("images", [])
    }
    annotations = []
    for annotation in payload.get("annotations", []):
        bbox = BoundingBox.from_xywh(*annotation["bbox"])
        annotations.append(
            ParsedAnnotation(
                image_id=str(annotation["image_id"]),
                label=categories[annotation["category_id"]],
                provenance=AnnotationProvenance(
                    source=AnnotationSource.COCO,
                    source_annotation_id=str(annotation["id"]),
                    bbox=bbox,
                    raw=annotation,
                ),
            )
        )
    return images, annotations


def _load_image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
        return int(width), int(height)


def _parse_official_kitti(root: Path) -> tuple[dict[str, ImageMetadata], list[ParsedAnnotation]]:
    image_root = root / "training" / "image_2"
    label_root = root / "training" / "label_2"
    images: dict[str, ImageMetadata] = {}
    annotations: list[ParsedAnnotation] = []
    for image_path in sorted(image_root.glob("*.png")):
        frame_id = image_path.stem
        relative_name = image_path.relative_to(root).as_posix()
        width, height = _load_image_size(image_path)
        source_image_id = f"kitti:{frame_id}"
        images[source_image_id] = ImageMetadata(
            source_image_id=source_image_id,
            filename=relative_name,
            width=width,
            height=height,
            storage_filename=f"sequence-default/{frame_id}/CAM_FRONT{image_path.suffix}",
        )
        label_path = label_root / f"{frame_id}.txt"
        if not label_path.is_file():
            continue
        for index, line in enumerate(label_path.read_text(encoding="utf-8").splitlines()):
            values = line.split()
            if len(values) < 15 or values[0] == "DontCare":
                continue
            bbox = BoundingBox(
                xmin=float(values[4]),
                ymin=float(values[5]),
                xmax=float(values[6]),
                ymax=float(values[7]),
            )
            annotations.append(
                ParsedAnnotation(
                    image_id=source_image_id,
                    label=values[0].lower(),
                    provenance=AnnotationProvenance(
                        source=AnnotationSource.KITTI,
                        source_annotation_id=f"{frame_id}:{index}",
                        bbox=bbox,
                        raw={
                            "type": values[0],
                            "truncated": float(values[1]),
                            "occluded": int(values[2]),
                            "alpha": float(values[3]),
                            "dimensions_hwl": [float(values[8]), float(values[9]), float(values[10])],
                            "location_xyz": [float(values[11]), float(values[12]), float(values[13])],
                            "rotation_y": float(values[14]),
                        },
                    ),
                )
            )
    return images, annotations


class KittiAdapter:
    """Load official KITTI, KITTI-derived YOLO, or reconciled fixture labels."""

    def __init__(self, root: Path, match_iou: float = 0.9, *, split: str | None = None) -> None:
        self.root = Path(root)
        self.match_iou = match_iou
        self.split = split

    def load(self) -> tuple[list[ImageMetadata], list[QAObjectPayload]]:
        if self._is_official_layout():
            return self._load_official()
        if self._is_yolo_layout():
            from src.services.ingestion.yolo_detection_adapter import YoloDetectionAdapter

            return YoloDetectionAdapter(self.root, split=self.split).load()
        return self._load_coco_fixture()

    def _is_official_layout(self) -> bool:
        return (
            (self.root / "training" / "image_2").is_dir()
            and (self.root / "training" / "label_2").is_dir()
            and (self.root / "training" / "calib").is_dir()
        )

    def _is_yolo_layout(self) -> bool:
        from src.services.ingestion.dataset_selector import is_yolo_detection_layout

        return is_yolo_detection_layout(self.root)

    def _load_official(self) -> tuple[list[ImageMetadata], list[QAObjectPayload]]:
        images, annotations = _parse_official_kitti(self.root)
        calibration_by_frame = {
            path.stem: parse_kitti_calibration(path)
            for path in sorted((self.root / "training" / "calib").glob("*.txt"))
        }
        cases = [
            QAObjectPayload(
                source_image_id=annotation.image_id,
                label=annotation.label,
                bbox=annotation.provenance.bbox,
                review_status=QAReviewStatus.VERIFIED,
                provenance=[annotation.provenance],
                calibration=calibration_by_frame.get(annotation.image_id.split(":", 1)[1], {}),
            )
            for annotation in annotations
        ]
        return list(images.values()), cases

    def _load_coco_fixture(self) -> tuple[list[ImageMetadata], list[QAObjectPayload]]:
        images, coco_annotations = _parse_coco(self.root / "annotations.coco.json")
        calibration_by_image = {
            path.stem: parse_kitti_calibration(path) for path in sorted((self.root / "calib").glob("*.txt"))
        }
        cases = [
            QAObjectPayload(
                source_image_id=item.image_id,
                label=item.label,
                bbox=item.provenance.bbox,
                review_status=QAReviewStatus.VERIFIED,
                provenance=[item.provenance],
                calibration=calibration_by_image.get(Path(images[item.image_id].filename).stem, {}),
            )
            for item in coco_annotations
        ]
        return list(images.values()), cases
