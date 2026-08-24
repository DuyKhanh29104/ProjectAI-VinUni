from __future__ import annotations

from importlib import import_module

import numpy as np

from src.agents.geometry import iou
from src.agents.state import LabelQAState
from src.services.yolo import canonical_detection_class

# Ngưỡng IoU để coi một cặp (gt, pred) là "cùng khớp một vật thể".
# Dưới ngưỡng này, dù là cặp tốt nhất tìm được cũng không tính là match
# mà chuyển sang nghi vấn bbox lệch / thiếu / thừa nhãn ở node flag_issues.
IOU_MATCH_THRESHOLD = 0.6


def match_labels(gt_labels: list[dict], pred_labels: list[dict]) -> dict:
    """Ghép cặp gt_labels <-> pred_labels bằng IoU (Hungarian algorithm).

    Dùng linear_sum_assignment tối đa hoá tổng IoU thay vì greedy, để tránh
    trường hợp một prediction "chiếm" nhầm gt tốt hơn của prediction khác.
    Matching không lọc theo class, để phát hiện được nhãn sai class
    (khớp vị trí tốt nhưng khác class) thay vì bị coi là không khớp.

    Hàm thuần (không đụng LabelQAState) để dễ test độc lập — xem match_labels_node bên dưới.
    """
    if not gt_labels or not pred_labels:
        return {
            "matches": [],
            "unmatched_gt": [{**gt, "best_iou": 0.0, "best_pred_class": None} for gt in gt_labels],
            "unmatched_pred": [
                {**pred, "prediction_index": index, "best_iou": 0.0}
                for index, pred in enumerate(pred_labels)
            ],
        }

    iou_matrix = np.zeros((len(gt_labels), len(pred_labels)))
    for i, gt in enumerate(gt_labels):
        for j, pred in enumerate(pred_labels):
            iou_matrix[i, j] = iou(gt["bbox"], pred["bbox"])

    linear_sum_assignment = getattr(import_module("scipy.optimize"), "linear_sum_assignment")
    gt_idx, pred_idx = linear_sum_assignment(-iou_matrix)

    matches: list[dict] = []
    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    for i, j in zip((int(x) for x in gt_idx), (int(x) for x in pred_idx)):
        score = float(iou_matrix[i, j])
        if score < IOU_MATCH_THRESHOLD:
            continue
        gt, pred = gt_labels[i], pred_labels[j]
        gt_class = canonical_detection_class(gt["class_name"]) or gt["class_name"].strip().lower()
        pred_class = canonical_detection_class(pred["class_name"]) or pred["class_name"].strip().lower()
        matches.append(
            {
                "gt_id": gt["label_id"],
                "gt_class": gt["class_name"],
                "pred_index": j,
                "pred_class": pred["class_name"],
                "pred_confidence": pred["confidence"],
                "iou": score,
                "class_match": gt_class == pred_class,
            }
        )
        matched_gt.add(i)
        matched_pred.add(j)

    unmatched_gt = []
    for i, gt in enumerate(gt_labels):
        if i in matched_gt:
            continue
        best_j = int(np.argmax(iou_matrix[i]))
        best_iou = float(iou_matrix[i, best_j])
        unmatched_gt.append(
            {
                **gt,
                "best_iou": best_iou,
                "best_pred_class": pred_labels[best_j]["class_name"] if best_iou > 0 else None,
            }
        )

    unmatched_pred = []
    for j, pred in enumerate(pred_labels):
        if j in matched_pred:
            continue
        best_i = int(np.argmax(iou_matrix[:, j]))
        best_iou = float(iou_matrix[best_i, j])
        unmatched_pred.append({**pred, "prediction_index": j, "best_iou": best_iou})

    return {"matches": matches, "unmatched_gt": unmatched_gt, "unmatched_pred": unmatched_pred}


async def match_labels_node(state: LabelQAState) -> dict:
    gt_labels = state.get("gt_labels", [])
    pred_labels = state.get("pred_labels", [])
    return match_labels(gt_labels, pred_labels)
