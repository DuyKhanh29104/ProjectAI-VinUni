"""Export normalized KITTI/nuScenes annotations as a self-contained YOLO dataset."""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from src.models.ingestion import QAObjectPayload
from src.services.ingestion.kitti_adapter import ImageMetadata


class YoloExportError(ValueError):
    """Raised when normalized records cannot be represented safely as YOLO."""


# These names deliberately match the COCO labels produced by the bundled
# pretrained Ultralytics model.  The mapping makes GT-vs-prediction comparison
# meaningful without requiring a custom-trained model for the MVP demo.
COCO_TRAFFIC_CLASSES = ("person", "bicycle", "car", "motorcycle", "bus", "truck", "train")
DEFAULT_SOURCE_LABEL_MAP = {
    "pedestrian": "person",
    "person_sitting": "person",
    "cyclist": "bicycle",
    "car": "car",
    "van": "car",
    "truck": "truck",
    "tram": "train",
    "vehicle.car": "car",
    "vehicle.truck": "truck",
    "vehicle.trailer": "truck",
    "vehicle.bus.bendy": "bus",
    "vehicle.bus.rigid": "bus",
    "vehicle.bicycle": "bicycle",
    "vehicle.motorcycle": "motorcycle",
}


@dataclass(frozen=True)
class YoloExportResult:
    images: int
    annotations: int
    skipped_annotations: int
    output_root: Path
    manifest_path: Path
    skipped_labels: dict[str, int]


def _safe_image_id(source_image_id: str, used_ids: set[str]) -> str:
    """Create a flat YOLO filename while retaining a stable source identifier."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", source_image_id).strip("._") or "image"
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _normalized_label(label: str, label_map: dict[str, str]) -> str | None:
    key = label.strip().lower()
    return label_map.get(key) or (key if key in COCO_TRAFFIC_CLASSES else None)


def _yolo_row(payload: QAObjectPayload, image: ImageMetadata, class_id: int) -> str | None:
    """Clip a pixel bbox and serialize it in normalized YOLO cx/cy/w/h form."""
    left = min(max(payload.bbox.xmin, 0.0), float(image.width))
    top = min(max(payload.bbox.ymin, 0.0), float(image.height))
    right = min(max(payload.bbox.xmax, 0.0), float(image.width))
    bottom = min(max(payload.bbox.ymax, 0.0), float(image.height))
    if right <= left or bottom <= top:
        return None
    center_x = (left + right) / 2 / image.width
    center_y = (top + bottom) / 2 / image.height
    width = (right - left) / image.width
    height = (bottom - top) / image.height
    return f"{class_id} {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}"


def export_normalized_to_yolo(
    *,
    source_root: Path,
    images: list[ImageMetadata],
    objects: list[QAObjectPayload],
    output_root: Path,
    split: str = "val",
    label_map: dict[str, str] | None = None,
) -> YoloExportResult:
    """Copy normalized image records and write valid YOLO labels plus a manifest.

    Unsupported source categories are skipped and recorded in the manifest. This
    is intentional: relabelling an unknown category as a COCO class would make
    the QA demo misleading.
    """
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root == source_root or output_root.is_relative_to(source_root):
        raise YoloExportError("YOLO output must be outside the source dataset root to preserve raw data.")
    if not split or Path(split).name != split:
        raise YoloExportError("YOLO split must be a simple directory name such as 'train' or 'val'.")

    images_by_id = {image.source_image_id: image for image in images}
    if len(images_by_id) != len(images):
        raise YoloExportError("Normalized images have duplicate source_image_id values.")
    cases_by_image: dict[str, list[QAObjectPayload]] = defaultdict(list)
    for item in objects:
        if item.source_image_id not in images_by_id:
            raise YoloExportError(f"Annotation references unknown image: {item.source_image_id}")
        cases_by_image[item.source_image_id].append(item)

    effective_map = {key.lower(): value.lower() for key, value in DEFAULT_SOURCE_LABEL_MAP.items()}
    effective_map.update({key.lower(): value.lower() for key, value in (label_map or {}).items()})
    invalid_targets = sorted({value for value in effective_map.values() if value not in COCO_TRAFFIC_CLASSES})
    if invalid_targets:
        raise YoloExportError(f"Label map targets must be supported COCO traffic classes: {', '.join(invalid_targets)}")

    image_dir = output_root / "images" / split
    label_dir = output_root / "labels" / split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    (output_root / "classes.txt").write_text("\n".join(COCO_TRAFFIC_CLASSES) + "\n", encoding="utf-8")

    used_ids: set[str] = set()
    skipped_labels: Counter[str] = Counter()
    annotation_count = 0
    manifest_images: list[dict[str, object]] = []
    for image in images:
        source_path = (source_root / image.filename).resolve()
        if not source_path.is_file() or not source_path.is_relative_to(source_root):
            raise YoloExportError(f"Source image is missing or outside dataset root: {image.filename}")
        image_id = _safe_image_id(image.source_image_id, used_ids)
        destination = image_dir / f"{image_id}{source_path.suffix.lower()}"
        shutil.copy2(source_path, destination)
        rows: list[str] = []
        for payload in cases_by_image[image.source_image_id]:
            mapped_label = _normalized_label(payload.label, effective_map)
            if mapped_label is None:
                skipped_labels[payload.label] += 1
                continue
            row = _yolo_row(payload, image, COCO_TRAFFIC_CLASSES.index(mapped_label))
            if row is None:
                skipped_labels[f"invalid_bbox:{payload.label}"] += 1
                continue
            rows.append(row)
        (label_dir / f"{image_id}.txt").write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
        annotation_count += len(rows)
        manifest_images.append(
            {
                "yolo_image_id": image_id,
                "source_image_id": image.source_image_id,
                "source_filename": image.filename,
                "annotations": len(rows),
            }
        )

    manifest_path = output_root / "label_guardian_export_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format": "yolo-detection-v1",
                "split": split,
                "classes": list(COCO_TRAFFIC_CLASSES),
                "images": manifest_images,
                "skipped_labels": dict(sorted(skipped_labels.items())),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return YoloExportResult(
        images=len(images),
        annotations=annotation_count,
        skipped_annotations=sum(skipped_labels.values()),
        output_root=output_root,
        manifest_path=manifest_path,
        skipped_labels=dict(sorted(skipped_labels.items())),
    )
