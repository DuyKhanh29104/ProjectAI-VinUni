from __future__ import annotations

from typing import TypedDict


class LabelQAState(TypedDict, total=False):
    """State schema cho Label QA Agent (LangGraph).

    Agent nhận nhãn gốc (ground truth) của một ảnh 2D cùng kết quả dự đoán
    từ mô hình YOLO trên chính ảnh đó, đối chiếu để phát hiện nhãn nghi
    ngờ có lỗi, tính chỉ số, và nhờ LLM giải thích + đề xuất chỉnh sửa.

    Mỗi node đọc và ghi vào state này. total=False cho phép các field là
    optional vì mỗi node chỉ cần một phần state để chạy.
    """

    # Input
    image_path: str
    label_path: str  # đường dẫn file nhãn gốc (.txt YOLO hoặc .xml Pascal VOC)

    # Kết quả parse nhãn gốc / YOLO inference (node load_gt_labels, run_yolo_inference)
    gt_labels: list[dict]  # [{label_id, class_name, bbox: {x1,y1,x2,y2}}]
    pred_labels: list[dict]  # [{class_name, bbox: {x1,y1,x2,y2}, confidence}]

    # Kết quả matching (node match_labels)
    matches: list[dict]  # [{gt_id, gt_class, pred_index, pred_class, iou, class_match}]
    unmatched_gt: list[dict]  # gt_labels không khớp prediction nào (kèm best_iou)
    unmatched_pred: list[dict]  # pred_labels không khớp gt nào (kèm best_iou)
    excluded_gt_labels: list[dict]  # giữ để audit nhưng không đưa vào matching
    excluded_pred_labels: list[dict]  # prediction ngoài ảnh, không đưa vào matching

    # Kết quả tính toán (node compute_metrics)
    metrics: dict

    # Nghi vấn đã gắn cờ + được LLM giải thích (node flag_issues, llm_explain)
    flagged_issues: list[dict]

    # Output cuối cùng (node build_report)
    qa_report: dict

    error: str
    metadata: dict
