from functools import lru_cache
from importlib import import_module
from typing import Any

from src.config import get_settings

# Tên class cố định (theo taxonomy COCO 80 class mà yolo26x.pt dùng) để giới
# hạn YOLO chỉ detect phương tiện giao thông + người + động vật — áp dụng cho
# MỌI dataset, không phụ thuộc classes.txt của từng ảnh (khác cách cũ dựa vào
# classes.txt: dễ lỗi khi tên dataset không khớp model).
TARGET_DETECTION_CLASSES: list[str] = [
    # Người
    "person",
    # Phương tiện giao thông
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
    "train",
    "boat",
    # Động vật (toàn bộ nhóm animal của COCO)
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
]

_TARGET_CLASS_SET = frozenset(TARGET_DETECTION_CLASSES)
DETECTION_CLASS_ALIASES: dict[str, str] = {
    "pedestrian": "person",
    "person_sitting": "person",
    "cyclist": "bicycle",
    "van": "car",
    "tram": "train",
    "human.pedestrian.adult": "person",
    "human.pedestrian.child": "person",
    "human.pedestrian.construction_worker": "person",
    "human.pedestrian.police_officer": "person",
    "vehicle.bicycle": "bicycle",
    "vehicle.bus.bendy": "bus",
    "vehicle.bus.rigid": "bus",
    "vehicle.car": "car",
    "vehicle.construction": "truck",
    "vehicle.motorcycle": "motorcycle",
    "vehicle.trailer": "truck",
    "vehicle.truck": "truck",
}


def canonical_detection_class(class_name: str) -> str | None:
    """Return the detector's COCO class for a supported source label.

    The source taxonomy remains unchanged in storage and in the editor. This
    normalization is used only for Agent comparison.
    """
    normalized = class_name.strip().lower()
    canonical = DETECTION_CLASS_ALIASES.get(normalized, normalized)
    return canonical if canonical in _TARGET_CLASS_SET else None


@lru_cache
def get_yolo_model() -> Any:
    """Load model YOLO — cache lại vì load weights (và tải về lần đầu) khá tốn thời gian."""
    settings = get_settings()
    model_type = getattr(import_module("ultralytics"), "YOLO")
    return model_type(settings.yolo_model_name)


def resolve_class_ids(model: Any, class_names: list[str]) -> tuple[list[int], list[str]]:
    """Map tên class (vd TARGET_DETECTION_CLASSES) sang class id nội bộ của model
    — so khớp không phân biệt hoa/thường/khoảng trắng thừa.

    Dùng để giới hạn model chỉ detect đúng các class được truyền vào (tham số
    `classes=` của Ultralytics predict). Trả về (matched_ids, unmatched_names) —
    unmatched_names là tên không tồn tại trong vocab của checkpoint, nên
    không bao giờ detect được dù có lọc hay không (tên khác hoàn toàn với
    model, không phải model kém nhạy).
    """
    name_to_id = {name.strip().lower(): idx for idx, name in model.names.items()}
    matched_ids: list[int] = []
    unmatched_names: list[str] = []
    for name in class_names:
        idx = name_to_id.get(name.strip().lower())
        if idx is None:
            unmatched_names.append(name)
        else:
            matched_ids.append(idx)
    return matched_ids, unmatched_names
