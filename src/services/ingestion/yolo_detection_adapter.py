"""Adapter for YOLO detection datasets with images/ and labels/ directories."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.models.ingestion import (
    AnnotationProvenance,
    AnnotationSource,
    BoundingBox,
    QAObjectPayload,
    QAReviewStatus,
)
from src.services.ingestion.dataset_selector import YOLO_CLASS_FILENAMES, YOLO_CONFIG_EXTENSIONS, YOLO_IMAGE_EXTENSIONS
from src.services.ingestion.kitti_adapter import ImageMetadata


class YoloDatasetLayoutError(ValueError):
    """Raised when a YOLO dataset cannot be parsed safely."""


def find_yolo_class_file(root: Path) -> Path | None:
    """Find the class-name file used by common YOLO dataset exports."""
    return next((root / filename for filename in YOLO_CLASS_FILENAMES if (root / filename).is_file()), None)


def find_yolo_config_file(root: Path) -> Path | None:
    """Find an Ultralytics-style YAML config with a names section."""
    return next(
        (
            path
            for path in sorted(root.iterdir())
            if path.is_file() and path.suffix.lower() in YOLO_CONFIG_EXTENSIONS and _yaml_contains_names(path)
        ),
        None,
    )


def _yaml_contains_names(path: Path) -> bool:
    return any(line.lstrip().startswith("names:") for line in path.read_text(encoding="utf-8-sig").splitlines())


def _strip_yaml_scalar(value: str) -> str:
    value = value.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_inline_names(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        return [_strip_yaml_scalar(item) for item in value[1:-1].split(",") if _strip_yaml_scalar(item)]
    if value.startswith("{") and value.endswith("}"):
        entries: list[tuple[int, str]] = []
        for item in value[1:-1].split(","):
            if ":" not in item:
                continue
            key, raw_name = item.split(":", 1)
            try:
                index = int(_strip_yaml_scalar(key))
            except ValueError:
                index = len(entries)
            name = _strip_yaml_scalar(raw_name)
            if name:
                entries.append((index, name))
        return [name for _, name in sorted(entries)]
    return [_strip_yaml_scalar(value)] if _strip_yaml_scalar(value) else []


def _parse_yolo_yaml_names(path: Path) -> list[str]:
    """Parse the common Ultralytics `names:` list/dict without requiring PyYAML."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for line_number, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("names:"):
            continue
        inline_names = _parse_inline_names(stripped.removeprefix("names:"))
        if inline_names:
            return inline_names
        base_indent = len(line) - len(line.lstrip())
        entries: list[tuple[int, str]] = []
        for child in lines[line_number + 1 :]:
            child_stripped = child.strip()
            if not child_stripped or child_stripped.startswith("#"):
                continue
            child_indent = len(child) - len(child.lstrip())
            if child_indent <= base_indent:
                break
            if ":" not in child_stripped:
                continue
            key, raw_name = child_stripped.split(":", 1)
            try:
                index = int(_strip_yaml_scalar(key))
            except ValueError:
                index = len(entries)
            name = _strip_yaml_scalar(raw_name)
            if name:
                entries.append((index, name))
        return [name for _, name in sorted(entries)]
    return []


def available_yolo_splits(root: Path) -> list[str]:
    image_root = root / "images"
    label_root = root / "labels"
    direct_images = any(
        path.is_file() and path.suffix.lower() in YOLO_IMAGE_EXTENSIONS for path in image_root.iterdir()
    )
    splits = [""] if direct_images else []
    splits.extend(
        split.name
        for split in sorted(image_root.iterdir())
        if split.is_dir()
        and (label_root / split.name).is_dir()
        and any(path.is_file() and path.suffix.lower() in YOLO_IMAGE_EXTENSIONS for path in split.iterdir())
    )
    return splits


class YoloDetectionAdapter:
    """Convert normalized YOLO labels into Label Guardian ingestion payloads."""

    def __init__(self, root: Path, *, split: str | None = None) -> None:
        self.root = Path(root)
        self.split = None if split in {None, "", "all"} else split

    def load(self) -> tuple[list[ImageMetadata], list[QAObjectPayload]]:
        class_names = self.class_names()
        available = available_yolo_splits(self.root)
        if not available:
            raise YoloDatasetLayoutError(f"No YOLO images were found under {self.root / 'images'}")
        if self.split is not None and self.split not in available:
            rendered = ", ".join(name or "root" for name in available)
            raise YoloDatasetLayoutError(f"YOLO split '{self.split}' is unavailable; found: {rendered}")
        selected_splits = [self.split] if self.split is not None else available

        images: list[ImageMetadata] = []
        objects: list[QAObjectPayload] = []
        for split in selected_splits:
            assert split is not None
            image_directory = self.root / "images" / split
            label_directory = self.root / "labels" / split
            image_paths = sorted(
                path
                for path in image_directory.iterdir()
                if path.is_file() and path.suffix.lower() in YOLO_IMAGE_EXTENSIONS
            )
            image_stems = {path.stem for path in image_paths}
            orphan_labels = sorted(path.name for path in label_directory.glob("*.txt") if path.stem not in image_stems)
            if orphan_labels:
                preview = ", ".join(orphan_labels[:5])
                raise YoloDatasetLayoutError(f"YOLO labels without matching images in split '{split}': {preview}")

            split_name = split or "root"
            for image_path in image_paths:
                image, image_objects = self.load_image(split_name, image_path.stem, class_names=class_names)
                images.append(image)
                objects.extend(image_objects)
        return images, objects

    def class_names(self) -> list[str]:
        class_file = find_yolo_class_file(self.root)
        config_file = find_yolo_config_file(self.root) if class_file is None else None
        if class_file is not None:
            class_names = [
                name.strip() for name in class_file.read_text(encoding="utf-8-sig").splitlines() if name.strip()
            ]
            source = class_file
        elif config_file is not None:
            class_names = _parse_yolo_yaml_names(config_file)
            source = config_file
        else:
            expected = ", ".join((*YOLO_CLASS_FILENAMES, "*.yaml", "*.yml"))
            raise YoloDatasetLayoutError(f"YOLO class metadata is missing under {self.root}; expected one of: {expected}")
        if not class_names:
            raise YoloDatasetLayoutError(f"YOLO class metadata is empty: {source}")
        return class_names

    def image_ids(self, split: str) -> list[str]:
        if split not in available_yolo_splits(self.root):
            raise YoloDatasetLayoutError(f"YOLO split '{split}' is unavailable")
        image_directory = self.root / "images" / ("" if split == "root" else split)
        return sorted(
            path.stem
            for path in image_directory.iterdir()
            if path.is_file() and path.suffix.lower() in YOLO_IMAGE_EXTENSIONS
        )

    def image_path(self, split: str, image_id: str) -> Path:
        if Path(image_id).name != image_id or not image_id:
            raise FileNotFoundError("Invalid dataset image id")
        image_directory = self.root / "images" / ("" if split == "root" else split)
        match = next(
            (
                path
                for extension in YOLO_IMAGE_EXTENSIONS
                if (path := image_directory / f"{image_id}{extension}").is_file()
            ),
            None,
        )
        if match is None:
            raise FileNotFoundError(f"Dataset image was not found: {split}/{image_id}")
        return match

    def load_image(
        self,
        split: str,
        image_id: str,
        *,
        class_names: list[str] | None = None,
    ) -> tuple[ImageMetadata, list[QAObjectPayload]]:
        image_path = self.image_path(split, image_id)
        with Image.open(image_path) as image:
            width, height = (int(value) for value in image.size)
        source_image_id = f"kitti-yolo:{split}:{image_path.stem}"
        metadata = ImageMetadata(
            source_image_id=source_image_id,
            filename=image_path.relative_to(self.root).as_posix(),
            width=width,
            height=height,
        )
        label_split = "" if split == "root" else split
        label_path = self.root / "labels" / label_split / f"{image_path.stem}.txt"
        objects = (
            self._parse_label_file(
                label_path,
                source_image_id=source_image_id,
                split=split,
                width=width,
                height=height,
                class_names=class_names or self.class_names(),
            )
            if label_path.is_file()
            else []
        )
        return metadata, objects

    @staticmethod
    def _parse_label_file(
        label_path: Path,
        *,
        source_image_id: str,
        split: str,
        width: int,
        height: int,
        class_names: list[str],
    ) -> list[QAObjectPayload]:
        objects: list[QAObjectPayload] = []
        for line_number, raw_line in enumerate(label_path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            values = line.split()
            if len(values) != 5:
                raise YoloDatasetLayoutError(
                    f"Invalid YOLO row at {label_path}:{line_number}; expected 'class cx cy width height'"
                )
            try:
                class_id = int(values[0])
                center_x, center_y, box_width, box_height = (float(value) for value in values[1:])
            except ValueError as error:
                raise YoloDatasetLayoutError(f"Invalid numeric value at {label_path}:{line_number}") from error
            if class_id < 0 or class_id >= len(class_names):
                raise YoloDatasetLayoutError(
                    f"Class id {class_id} at {label_path}:{line_number} is outside 0..{len(class_names) - 1}"
                )
            normalized = (center_x, center_y, box_width, box_height)
            if any(value < 0.0 or value > 1.0 for value in normalized) or box_width == 0 or box_height == 0:
                raise YoloDatasetLayoutError(
                    f"Normalized YOLO bbox at {label_path}:{line_number} must be within 0..1 with positive size"
                )

            bbox = BoundingBox(
                xmin=max(0.0, (center_x - box_width / 2) * width),
                ymin=max(0.0, (center_y - box_height / 2) * height),
                xmax=min(float(width), (center_x + box_width / 2) * width),
                ymax=min(float(height), (center_y + box_height / 2) * height),
            )
            source_annotation_id = f"{split}:{label_path.stem}:{line_number - 1}"
            provenance = AnnotationProvenance(
                source=AnnotationSource.KITTI,
                source_annotation_id=source_annotation_id,
                bbox=bbox,
                raw={
                    "format": "yolo",
                    "class_id": class_id,
                    "normalized_bbox": [center_x, center_y, box_width, box_height],
                    "split": split,
                },
            )
            objects.append(
                QAObjectPayload(
                    source_image_id=source_image_id,
                    label=class_names[class_id],
                    bbox=bbox,
                    review_status=QAReviewStatus.VERIFIED,
                    provenance=[provenance],
                )
            )
        return objects
