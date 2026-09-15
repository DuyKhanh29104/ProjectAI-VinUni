import json
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from src.agents.state import LabelQAState


def _read_class_names(label_path: Path) -> dict[int, str] | None:
    """Read class names from common YOLO export locations and filenames."""
    filenames = ("classes.txt", "class.txt", "class.txt.txt")
    directories = tuple(label_path.parents)[:3]
    for directory in directories:
        for filename in filenames:
            candidate = directory / filename
            if candidate.is_file():
                names = candidate.read_text(encoding="utf-8-sig").splitlines()
                return {i: name.strip() for i, name in enumerate(names) if name.strip()}
    return None


def _parse_yolo_txt(label_path: Path, image_path: Path) -> list[dict]:
    """Parse nhãn YOLO: mỗi dòng `class_id cx cy w h` (normalized 0-1)."""
    with Image.open(image_path) as img:
        width, height = img.size

    class_names = _read_class_names(label_path)
    labels = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        class_id = int(parts[0])
        cx, cy, w, h = (float(v) for v in parts[1:5])
        bbox = {
            "x1": (cx - w / 2) * width,
            "y1": (cy - h / 2) * height,
            "x2": (cx + w / 2) * width,
            "y2": (cy + h / 2) * height,
        }
        class_name = class_names[class_id] if class_names and class_id in class_names else str(class_id)
        labels.append({"class_name": class_name, "bbox": bbox})
    return labels


def _parse_voc_xml(label_path: Path) -> list[dict]:
    """Parse nhãn Pascal VOC: <object><name>, <bndbox> đã là pixel tuyệt đối."""
    root = ET.parse(label_path).getroot()
    labels = []
    for obj in root.findall("object"):
        class_name = obj.findtext("name", default="unknown")
        box = obj.find("bndbox")
        if box is None:
            raise ValueError("VOC object is missing bndbox")

        def coordinate(name: str) -> float:
            value = box.findtext(name)
            if value is None:
                raise ValueError(f"VOC bndbox is missing {name}")
            return float(value)

        bbox = {
            "x1": coordinate("xmin"),
            "y1": coordinate("ymin"),
            "x2": coordinate("xmax"),
            "y2": coordinate("ymax"),
        }
        labels.append({"class_name": class_name, "bbox": bbox})
    return labels


def _parse_golden_json(label_path: Path) -> list[dict]:
    """Parse the JSON annotation schema used by ``eval/golden_v0_1``."""
    payload = json.loads(label_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("labels"), list):
        raise ValueError("Golden JSON must contain a labels list")

    labels = []
    for index, raw_label in enumerate(payload["labels"]):
        if not isinstance(raw_label, dict):
            raise ValueError(f"labels[{index}] must be an object")
        label_id = raw_label.get("label_id")
        class_name = raw_label.get("class_name")
        raw_bbox = raw_label.get("bbox")
        if not isinstance(label_id, str) or not label_id:
            raise ValueError(f"labels[{index}] is missing label_id")
        if not isinstance(class_name, str) or not class_name:
            raise ValueError(f"labels[{index}] is missing class_name")
        if not isinstance(raw_bbox, dict):
            raise ValueError(f"labels[{index}] is missing bbox")
        try:
            bbox = {key: float(raw_bbox[key]) for key in ("x1", "y1", "x2", "y2")}
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"labels[{index}] has an invalid bbox") from error
        if bbox["x2"] <= bbox["x1"] or bbox["y2"] <= bbox["y1"]:
            raise ValueError(f"labels[{index}] bbox must have positive area")
        labels.append({"label_id": label_id, "class_name": class_name, "bbox": bbox})
    return labels


def _candidate_label_paths(image_path: Path) -> list[Path]:
    """Đoán vị trí file nhãn gốc chỉ từ đường dẫn ảnh, theo các quy ước phổ biến.

    Ưu tiên layout dataset chuẩn của YOLO/Ultralytics (`images/` <-> `labels/`
    sibling folder, cùng tên file), sau đó fallback về cùng thư mục với ảnh,
    cùng tên khác đuôi.
    """
    candidates: list[Path] = []

    parts = list(image_path.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "images":
            swapped = parts.copy()
            swapped[i] = "labels"
            swapped_path = Path(*swapped)
            candidates += [swapped_path.with_suffix(".txt"), swapped_path.with_suffix(".xml")]
            break

    candidates += [image_path.with_suffix(".txt"), image_path.with_suffix(".xml")]
    return candidates


async def load_gt_labels_node(state: LabelQAState) -> dict:
    """Parse file nhãn gốc (YOLO, Pascal VOC, hoặc golden JSON) thành gt_labels.

    Nếu không truyền `label_path`, tự đoán vị trí file nhãn từ `image_path`
    (xem `_candidate_label_paths`) — cho phép input chỉ cần mỗi ảnh.
    """
    if state.get("gt_labels") is not None:
        return {}

    image_path = state.get("image_path")
    if not image_path:
        return {"error": "Thiếu image_path"}

    label_path = state.get("label_path")
    if not label_path:
        found = next((c for c in _candidate_label_paths(Path(image_path)) if c.exists()), None)
        if found is None:
            return {
                "error": (
                    f"Không tự tìm được file nhãn gốc cho {image_path} (đã thử thư mục "
                    "labels/ song song với images/, và cùng thư mục với ảnh, đuôi .txt/.xml). "
                    "Truyền label_path rõ ràng nếu nhãn không theo quy ước này."
                )
            }
        label_path = str(found)

    path = Path(label_path)
    if not path.exists():
        return {"error": f"Không tìm thấy file nhãn: {label_path}"}

    suffix = path.suffix.lower()
    if suffix not in {".txt", ".xml", ".json"}:
        return {
            "error": f"Định dạng nhãn không được hỗ trợ: {path.suffix} "
            "(chỉ hỗ trợ .txt YOLO, .xml Pascal VOC, hoặc .json golden testset)"
        }

    try:
        parsers = {
            ".txt": lambda: _parse_yolo_txt(path, Path(image_path)),
            ".xml": lambda: _parse_voc_xml(path),
            ".json": lambda: _parse_golden_json(path),
        }
        gt_labels = parsers[suffix]()
    except Exception as e:
        return {"error": f"Lỗi khi đọc file nhãn {label_path}: {e}"}

    if not gt_labels:
        return {"error": f"File nhãn {label_path} không có nhãn nào"}

    return {"gt_labels": gt_labels}
