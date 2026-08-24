import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from src.agents.state import LabelQAState


def _read_class_names(label_path: Path) -> dict[int, str] | None:
    """Read class names from common YOLO export locations and filenames."""
    filenames = ("classes.txt", "class.txt", "class.txt.txt")
    directories = (label_path.parent, *tuple(label_path.parents)[:3])
    for directory in dict.fromkeys(directories):
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
    """Parse file nhãn gốc (YOLO .txt hoặc Pascal VOC .xml) thành gt_labels.

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
    if suffix not in {".txt", ".xml"}:
        return {
            "error": f"Định dạng nhãn không được hỗ trợ: {path.suffix} "
            "(chỉ hỗ trợ .txt YOLO hoặc .xml Pascal VOC)"
        }

    try:
        gt_labels = _parse_yolo_txt(path, Path(image_path)) if suffix == ".txt" else _parse_voc_xml(path)
    except Exception as e:
        return {"error": f"Lỗi khi đọc file nhãn {label_path}: {e}"}

    if not gt_labels:
        return {"error": f"File nhãn {label_path} không có nhãn nào"}

    return {"gt_labels": gt_labels}
