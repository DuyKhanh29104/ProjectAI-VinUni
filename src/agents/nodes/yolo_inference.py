from typing import Any

from src.agents.state import LabelQAState
from src.config import get_settings
from src.services.yolo import TARGET_DETECTION_CLASSES, get_yolo_model, resolve_class_ids


async def run_yolo_inference_node(state: LabelQAState) -> dict:
    """Chạy YOLO trên ảnh để lấy pred_labels.

    Bỏ qua nếu bước trước (load_gt_labels) đã lỗi.

    Giới hạn YOLO chỉ detect các class trong TARGET_DETECTION_CLASSES (phương
    tiện giao thông + người + động vật) — cố định cho mọi dataset, không phụ
    thuộc classes.txt. Đổi lại, YOLO sẽ không output được class ngoài danh sách
    này nên không thể phát hiện wrong_class kiểu "model đoán 1 class hoàn toàn
    khác GT" nếu class đó nằm ngoài danh sách.
    """
    if state.get("error"):
        return {}

    if state.get("pred_labels") is not None:
        return {}

    image_path = state.get("image_path")
    if not image_path:
        return {"error": "Thiếu image_path"}

    settings = get_settings()

    try:
        model = get_yolo_model()
        predict_kwargs: dict[str, Any] = {
            "conf": settings.yolo_confidence_threshold,
            "verbose": False,
        }
        metadata = dict(state.get("metadata") or {})
        matched_ids, unmatched_names = resolve_class_ids(model, TARGET_DETECTION_CLASSES)
        if matched_ids:
            predict_kwargs["classes"] = matched_ids
        if unmatched_names:
            metadata["yolo_unmatched_classes"] = unmatched_names
        results = model(image_path, **predict_kwargs)
    except Exception as e:
        return {"error": f"Lỗi khi chạy YOLO inference trên {image_path}: {e}"}

    names = results[0].names
    pred_labels = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
        class_id = int(box.cls[0])
        pred_labels.append(
            {
                "class_name": names[class_id],
                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "confidence": float(box.conf[0]),
            }
        )

    output: dict = {"pred_labels": pred_labels}
    if metadata:
        output["metadata"] = metadata
    return output
