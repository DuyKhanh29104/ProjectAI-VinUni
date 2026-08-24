from __future__ import annotations


def iou(box_a: dict, box_b: dict) -> float:
    """Tính Intersection over Union giữa hai bbox dạng {x1, y1, x2, y2}."""
    ax1, ay1, ax2, ay2 = box_a["x1"], box_a["y1"], box_a["x2"], box_a["y2"]
    bx1, by1, bx2, by2 = box_b["x1"], box_b["y1"], box_b["x2"], box_b["y2"]

    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area

    return inter_area / union if union > 0 else 0.0
