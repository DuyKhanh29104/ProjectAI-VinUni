from time import perf_counter
from typing import Any

from src.agents.state import LabelQAState
from src.config import get_settings
from src.services.yolo import TARGET_DETECTION_CLASSES, get_yolo_model, resolve_class_ids


async def run_yolo_inference_node(state: LabelQAState) -> dict:
    """Chạy YOLO trên ảnh để lấy pred_labels.

    Giới hạn YOLO chỉ detect các class trong TARGET_DETECTION_CLASSES (phương
    tiện giao thông + người + động vật) — cố định cho mọi dataset, không phụ
    thuộc classes.txt. Đổi lại, YOLO sẽ không output được class ngoài danh sách
    này nên không thể phát hiện wrong_class kiểu "model đoán 1 class hoàn toàn
    khác GT" nếu class đó nằm ngoài danh sách.
    """
    if state.get("pred_labels") is not None:
        return {}

    image_path = state.get("image_path")
    if not image_path:
        return {"error": "Thiếu image_path"}

    settings = get_settings()

    try:
        metadata = dict(state.get("metadata") or {})
        model_load_start = perf_counter()
        model = get_yolo_model()
        model_load_ms = (perf_counter() - model_load_start) * 1000
        predict_kwargs: dict[str, Any] = {
            "conf": settings.yolo_confidence_threshold,
            "verbose": False,
        }
        matched_ids, unmatched_names = resolve_class_ids(model, TARGET_DETECTION_CLASSES)
        if matched_ids:
            predict_kwargs["classes"] = matched_ids
        if unmatched_names:
            metadata["yolo_unmatched_classes"] = unmatched_names
        inference_start = perf_counter()
        results = model(image_path, **predict_kwargs)
        inference_wall_ms = (perf_counter() - inference_start) * 1000
    except Exception as e:
        return {"error": f"Lỗi khi chạy model inference trên {image_path}: {e}"}

    first_result = results[0]
    speed = getattr(first_result, "speed", None) or {}
    metadata["yolo_latency_ms"] = {
        "model_load": round(model_load_ms, 3),
        "inference_wall": round(inference_wall_ms, 3),
        "preprocess": round(float(speed["preprocess"]), 3) if "preprocess" in speed else None,
        "inference": round(float(speed["inference"]), 3) if "inference" in speed else None,
        "postprocess": round(float(speed["postprocess"]), 3) if "postprocess" in speed else None,
    }

    names = first_result.names
    pred_labels = []
    for box in first_result.boxes:
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
