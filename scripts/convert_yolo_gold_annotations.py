"""Convert YOLO-normalized gold labels to the golden testset JSON schema.

Example:
    python scripts/convert_yolo_gold_annotations.py \
        --labels-dir eval/golden_v0_1/gold_annotations \
        --images-dir eval/golden_v0_1/images \
        --class-config eval/golden_v0_1/manifests/kitti_class_names.yaml
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def load_class_names(config_path: Path) -> dict[int, str]:
    """Read an Ultralytics-style numeric ``names:`` mapping."""
    lines = config_path.read_text(encoding="utf-8-sig").splitlines()
    names_line = next(
        (index for index, line in enumerate(lines) if line.strip().startswith("names:")),
        None,
    )
    if names_line is None:
        raise ValueError(f"{config_path}: missing names section")

    names_indent = len(lines[names_line]) - len(lines[names_line].lstrip())
    class_names: dict[int, str] = {}
    for line in lines[names_line + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= names_indent:
            break
        match = re.fullmatch(r"(\d+)\s*:\s*(.+?)\s*", stripped)
        if match is None:
            continue
        class_id = int(match.group(1))
        class_name = match.group(2).split("#", 1)[0].strip().strip("'\"")
        if class_name:
            class_names[class_id] = class_name.lower()

    if not class_names:
        raise ValueError(f"{config_path}: names section has no numeric class entries")
    return class_names


def find_image(images_dir: Path, image_id: str) -> Path:
    matches = [images_dir / f"{image_id}{extension}" for extension in IMAGE_EXTENSIONS]
    existing = [path for path in matches if path.is_file()]
    if len(existing) != 1:
        raise ValueError(f"{images_dir}: expected exactly one image for {image_id}, found {len(existing)}")
    return existing[0]


def parse_yolo_labels(
    label_path: Path,
    *,
    image_id: str,
    image_width: int,
    image_height: int,
    class_names: dict[int, str],
) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(label_path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        values = line.split()
        if len(values) != 5:
            raise ValueError(f"{label_path}:{line_number}: expected 'class_id cx cy width height'")
        try:
            class_id = int(values[0])
            center_x, center_y, box_width, box_height = map(float, values[1:])
        except ValueError as error:
            raise ValueError(f"{label_path}:{line_number}: invalid numeric value") from error

        if class_id not in class_names:
            raise ValueError(f"{label_path}:{line_number}: unknown class id {class_id}")
        normalized = (center_x, center_y, box_width, box_height)
        if any(value < 0.0 or value > 1.0 for value in normalized):
            raise ValueError(f"{label_path}:{line_number}: normalized bbox values must be within 0..1")
        if box_width <= 0.0 or box_height <= 0.0:
            raise ValueError(f"{label_path}:{line_number}: bbox must have positive area")

        x1 = max(0.0, (center_x - box_width / 2.0) * image_width)
        y1 = max(0.0, (center_y - box_height / 2.0) * image_height)
        x2 = min(float(image_width), (center_x + box_width / 2.0) * image_width)
        y2 = min(float(image_height), (center_y + box_height / 2.0) * image_height)
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"{label_path}:{line_number}: bbox has no area after conversion and clipping")

        labels.append(
            {
                "label_id": f"gold-{image_id}-{len(labels) + 1:03d}",
                "class_name": class_names[class_id],
                "bbox": {
                    "x1": round(x1, 6),
                    "y1": round(y1, 6),
                    "x2": round(x2, 6),
                    "y2": round(y2, 6),
                },
                # The provided YOLO rows do not retain KITTI occlusion/truncation metadata.
                "attributes": {"occluded": None, "truncated": None},
            }
        )
    return labels


def convert_annotations(
    *,
    labels_dir: Path,
    images_dir: Path,
    output_dir: Path,
    class_config: Path,
    overwrite: bool,
) -> tuple[int, int, Counter[str]]:
    class_names = load_class_names(class_config)
    label_paths = sorted(labels_dir.glob("*.txt"))
    if not label_paths:
        raise ValueError(f"{labels_dir}: no .txt label files found")

    output_dir.mkdir(parents=True, exist_ok=True)
    image_count = 0
    label_count = 0
    class_counts: Counter[str] = Counter()
    for label_path in label_paths:
        image_id = label_path.stem
        image_path = find_image(images_dir, image_id)
        output_path = output_dir / f"{image_id}.json"
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"{output_path} already exists; pass --overwrite to replace it")

        with Image.open(image_path) as image:
            image_width, image_height = (int(value) for value in image.size)
        labels = parse_yolo_labels(
            label_path,
            image_id=image_id,
            image_width=image_width,
            image_height=image_height,
            class_names=class_names,
        )
        payload = {
            "image_id": image_id,
            "image_width": image_width,
            "image_height": image_height,
            "labels": labels,
        }
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        image_count += 1
        label_count += len(labels)
        class_counts.update(label["class_name"] for label in labels)

    return image_count, label_count, class_counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert YOLO gold labels into the golden testset annotation JSON format."
    )
    parser.add_argument("--labels-dir", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--class-config", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to --labels-dir, keeping the original .txt files alongside JSON.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    labels_dir = args.labels_dir.resolve()
    images_dir = args.images_dir.resolve()
    output_dir = (args.output_dir or args.labels_dir).resolve()
    class_config = args.class_config.resolve()
    image_count, label_count, class_counts = convert_annotations(
        labels_dir=labels_dir,
        images_dir=images_dir,
        output_dir=output_dir,
        class_config=class_config,
        overwrite=args.overwrite,
    )
    print(f"Converted {image_count} images and {label_count} labels to {output_dir}")
    print("Class counts:")
    for class_name, count in sorted(class_counts.items()):
        print(f"- {class_name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
