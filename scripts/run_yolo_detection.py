from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.nodes.yolo_inference import run_yolo_inference_node  # noqa: E402


def _default_output_path(image_path: Path) -> Path:
    suffix = image_path.suffix or ".jpg"
    return image_path.with_name(f"{image_path.stem}_yolo{suffix}")


def _draw_label(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, color: str) -> None:
    font = ImageFont.load_default()
    left, top = xy
    bbox = draw.textbbox((left, top), text, font=font)
    padding = 3
    background = (
        bbox[0] - padding,
        bbox[1] - padding,
        bbox[2] + padding,
        bbox[3] + padding,
    )
    draw.rectangle(background, fill=color)
    draw.text((left, top), text, fill="black", font=font)


def draw_detections(image_path: Path, detections: list[dict[str, Any]], output_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    for detection in detections:
        bbox = detection["bbox"]
        x1 = float(bbox["x1"])
        y1 = float(bbox["y1"])
        x2 = float(bbox["x2"])
        y2 = float(bbox["y2"])
        class_name = detection.get("class_name", "?")
        confidence = float(detection.get("confidence", 0.0))
        label = f"{class_name} {confidence:.2f}"

        draw.rectangle((x1, y1, x2, y2), outline="lime", width=3)
        _draw_label(draw, (x1 + 2, max(0, y1 - 14)), label, "lime")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


async def run(image_path: Path, output_path: Path) -> dict[str, Any]:
    result = await run_yolo_inference_node({"image_path": str(image_path)})
    if "error" in result:
        raise RuntimeError(result["error"])

    detections = result.get("pred_labels", [])
    draw_detections(image_path, detections, output_path)

    return {
        "input": str(image_path),
        "output": str(output_path),
        "detections": len(detections),
        "metadata": result.get("metadata", {}),
        "pred_labels": detections,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO detection and save an annotated output image.")
    parser.add_argument("image", type=Path, help="Path to the input image.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Path for the annotated output image. Defaults to <input_stem>_yolo<input_suffix>.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        print(f"Input image not found: {image_path}", file=sys.stderr)
        return 2

    output_path = (args.output or _default_output_path(image_path)).expanduser().resolve()
    try:
        summary = asyncio.run(run(image_path, output_path))
    except Exception as error:
        print(f"YOLO detection failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
