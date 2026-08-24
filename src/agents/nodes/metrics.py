from src.agents.state import LabelQAState


def compute_metrics(matches: list[dict], unmatched_gt: list[dict], unmatched_pred: list[dict]) -> dict:
    """Tính precision/recall/F1, class accuracy và IoU trung bình từ kết quả matching.

    Hàm thuần (không đụng LabelQAState) để dễ test độc lập — xem compute_metrics_node bên dưới.
    """
    tp = len(matches)
    fn = len(unmatched_gt)
    fp = len(unmatched_pred)
    class_correct = sum(1 for m in matches if m["class_match"])

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    avg_iou = sum(m["iou"] for m in matches) / tp if tp else 0.0

    return {
        "true_positive": tp,
        "false_negative": fn,
        "false_positive": fp,
        "class_accuracy": round(class_correct / tp, 4) if tp else 1.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "avg_iou": round(avg_iou, 4),
    }
async def compute_metrics_node(state: LabelQAState) -> dict:
    matches = state.get("matches", [])
    unmatched_gt = state.get("unmatched_gt", [])
    unmatched_pred = state.get("unmatched_pred", [])
    metrics = compute_metrics(matches, unmatched_gt, unmatched_pred)
    label_scope = (state.get("metadata") or {}).get("label_scope")
    if label_scope:
        metrics.update(label_scope)
    return {"metrics": metrics}
