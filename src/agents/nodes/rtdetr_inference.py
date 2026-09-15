from src.agents.state import LabelQAState
from src.config import get_settings
from src.services.yolo import get_rtdetr_model


async def run_rtdetr_inference_node(state: LabelQAState) -> dict:
    """Chạy RT-DETR như detector thay thế YOLO, output cùng dạng pred_labels.

    Đây là detector thứ 3 dùng để SO SÁNH qua UI (xem app.py), chưa nối vào
    match_labels/flag_issues — không ảnh hưởng kết quả QA gốc.

    Non-fatal: lỗi (model tải thất bại, ảnh hỏng...) chỉ ghi metadata, không
    set `error` — vì đây là nguồn phát hiện bổ sung (POC), không phải core
    dependency như run_yolo_inference.
    """
    settings = get_settings()
    if not state.get("enable_rtdetr", settings.enable_rtdetr):
        return {}

    image_path = state.get("image_path")
    if not image_path:
        return {}

    try:
        model = get_rtdetr_model()
        results = model(image_path, conf=settings.rtdetr_confidence_threshold, verbose=False)
    except Exception as e:
        return {"metadata": {**(state.get("metadata") or {}), "rtdetr_error": str(e)}}

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

    return {"rtdetr_pred_labels": pred_labels}
