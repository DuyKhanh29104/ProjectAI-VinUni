from pathlib import Path

from PIL import Image

from src.agents.state import LabelQAState

_REQUIRED_BBOX_KEYS = {"x1", "y1", "x2", "y2"}


def _scope_labels_to_image(
    labels: list[dict],
    *,
    image_width: int,
    image_height: int,
) -> tuple[list[dict], list[dict], int]:
    """Return an evaluation-only view without mutating source annotations."""
    included: list[dict] = []
    excluded: list[dict] = []
    clipped_count = 0
    for label in labels:
        source_bbox = {key: float(label["bbox"][key]) for key in _REQUIRED_BBOX_KEYS}
        if (
            source_bbox["x2"] <= 0
            or source_bbox["y2"] <= 0
            or source_bbox["x1"] >= image_width
            or source_bbox["y1"] >= image_height
        ):
            excluded.append({**label, "bbox": source_bbox, "scope_reason": "outside_image"})
            continue

        clipped_bbox = {
            "x1": max(0.0, source_bbox["x1"]),
            "y1": max(0.0, source_bbox["y1"]),
            "x2": min(float(image_width), source_bbox["x2"]),
            "y2": min(float(image_height), source_bbox["y2"]),
        }
        scoped_label = {**label, "bbox": clipped_bbox}
        if clipped_bbox != source_bbox:
            scoped_label["source_bbox"] = source_bbox
            clipped_count += 1
        included.append(scoped_label)
    return included, excluded, clipped_count


async def validate_input_node(state: LabelQAState) -> dict:
    """Kiểm tra và chuẩn hoá gt_labels/pred_labels trước khi xử lý.

    Gán label_id tự động cho gt_labels chưa có, để các node sau có thể
    tham chiếu ngược lại từng nhãn cụ thể trong report.
    """
    if not state.get("image_path"):
        return {"error": "Thiếu image_path"}

    gt_labels = state.get("gt_labels") or []
    pred_labels = state.get("pred_labels") or []

    for i, label in enumerate(gt_labels):
        bbox = label.get("bbox")
        if not bbox or not _REQUIRED_BBOX_KEYS.issubset(bbox):
            return {"error": f"gt_labels[{i}] thiếu bbox hợp lệ (x1, y1, x2, y2)"}
        if not label.get("class_name"):
            return {"error": f"gt_labels[{i}] thiếu class_name"}
        if not label.get("label_id"):
            label["label_id"] = f"gt_{i}"

    for i, pred in enumerate(pred_labels):
        bbox = pred.get("bbox")
        if not bbox or not _REQUIRED_BBOX_KEYS.issubset(bbox):
            return {"error": f"pred_labels[{i}] thiếu bbox hợp lệ (x1, y1, x2, y2)"}
        if not pred.get("class_name"):
            return {"error": f"pred_labels[{i}] thiếu class_name"}
        if pred.get("confidence") is None:
            return {"error": f"pred_labels[{i}] thiếu confidence"}

    metadata = dict(state.get("metadata") or {})
    image_path = Path(state["image_path"])
    if image_path.is_file():
        try:
            with Image.open(image_path) as image:
                image_width, image_height = image.size
            scoped_gt, excluded_gt, clipped_gt = _scope_labels_to_image(
                gt_labels,
                image_width=image_width,
                image_height=image_height,
            )
            scoped_predictions, excluded_predictions, clipped_predictions = _scope_labels_to_image(
                pred_labels,
                image_width=image_width,
                image_height=image_height,
            )
        except (OSError, TypeError, ValueError) as error:
            return {"error": f"Không thể xác định phạm vi nhãn theo ảnh: {error}"}
        metadata["label_scope"] = {
            "image_width": image_width,
            "image_height": image_height,
            "ground_truth_total": len(gt_labels),
            "ground_truth_evaluated": len(scoped_gt),
            "ground_truth_excluded_outside": len(excluded_gt),
            "ground_truth_clipped": clipped_gt,
            "predictions_total": len(pred_labels),
            "predictions_evaluated": len(scoped_predictions),
            "predictions_excluded_outside": len(excluded_predictions),
            "predictions_clipped": clipped_predictions,
        }
        return {
            "gt_labels": scoped_gt,
            "pred_labels": scoped_predictions,
            "excluded_gt_labels": excluded_gt,
            "excluded_pred_labels": excluded_predictions,
            "metadata": metadata,
        }

    return {"gt_labels": gt_labels, "pred_labels": pred_labels, "metadata": metadata}
