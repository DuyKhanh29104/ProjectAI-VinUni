from src.agents.state import LabelQAState
from src.models.agent_schemas import QAIssueExplanationBatch
from src.services.agent_llm import get_agent_llm

_SYSTEM_PROMPT = """Bạn là một QA reviewer chuyên kiểm tra chất lượng nhãn (label) cho ảnh 2D \
dùng để train mô hình object detection.

Bạn sẽ nhận một danh sách các nghi vấn (issue) đã được hệ thống tính toán sẵn bằng số liệu \
(IoU, confidence, so khớp class...). Với MỖI issue, hãy:
1. Giải thích ngắn gọn, dễ hiểu vì sao nhãn này bị nghi ngờ — CHỈ dựa trên số liệu trong \
"evidence" được cung cấp, không suy đoán thêm chi tiết không có trong dữ liệu.
2. Đề xuất cách chỉnh sửa cụ thể, khả thi (ví dụ: "điều chỉnh lại toạ độ bbox cho khớp vùng \
model phát hiện", "đổi class từ X sang Y", "xoá nhãn trùng lặp", "bổ sung nhãn còn thiếu tại \
vị trí ...").

Không khẳng định chắc chắn 100% nhãn sai — mô hình phát hiện cũng có thể sai, nhãn chỉ đang bị \
"nghi ngờ". Dùng mức độ ngôn ngữ phù hợp với severity (high/medium/low) của từng issue.

Trả lời cho ĐÚNG issue_index tương ứng với từng issue trong danh sách đầu vào.
"""


def _format_bbox(bbox: dict) -> str:
    return f"({bbox['x1']:.0f}, {bbox['y1']:.0f}) - ({bbox['x2']:.0f}, {bbox['y2']:.0f})"


def _explain_wrong_class(evidence: dict) -> tuple[str, str]:
    gt_class, pred_class, iou = evidence["gt_class"], evidence["pred_class"], evidence["iou"]
    return (
        f"Ground truth ghi class '{gt_class}', nhưng model dự đoán '{pred_class}' tại cùng vị trí "
        f"(IoU={iou:.2f}) — ground truth và prediction đang khác class.",
        f"Đối chiếu đối tượng trên ảnh: nếu đúng là '{pred_class}' thì đổi class ground truth từ "
        f"'{gt_class}' sang '{pred_class}'; nếu model đoán sai thì giữ nguyên '{gt_class}'.",
    )


def _explain_missing_label(evidence: dict) -> tuple[str, str]:
    class_name, confidence = evidence["class_name"], evidence["confidence"]
    return (
        f"Mô hình phát hiện một đối tượng '{class_name}' với độ tin cậy {confidence:.0%} nhưng không có "
        "ground truth nào ở vị trí đó.",
        f"Kiểm tra vùng ảnh quanh {_format_bbox(evidence['bbox'])} và bổ sung nhãn nếu đối tượng thực "
        "sự thuộc phạm vi đánh giá.",
    )


def _explain_extra_or_wrong_label(evidence: dict) -> tuple[str, str]:
    class_name, best_iou = evidence["class_name"], evidence["best_iou"]
    return (
        f"Nhãn '{class_name}' không có prediction nào của model ở gần (IoU tốt nhất chỉ {best_iou:.2f}) "
        "— có thể nhãn dư, sai class, hoặc bounding box lệch quá xa vật thể.",
        "Kiểm tra lại đối tượng, class và bounding box; xoá nhãn nếu đó không phải đối tượng hợp lệ.",
    )


def _explain_bbox_misaligned(evidence: dict) -> tuple[str, str]:
    class_name, best_iou = evidence["class_name"], evidence["best_iou"]
    best_pred_class = evidence.get("best_pred_class") or "đối tượng khác"
    return (
        f"Có prediction '{best_pred_class}' gần nhãn '{class_name}' nhưng IoU chỉ {best_iou:.2f} (dưới "
        "ngưỡng khớp) — bounding box có thể đang lệch khỏi vật thể.",
        "Điều chỉnh lại toạ độ bounding box ground truth để bao đúng vùng model đã phát hiện.",
    )


def _explain_loose_bbox(evidence: dict) -> tuple[str, str]:
    gt_class, iou = evidence["gt_class"], evidence["iou"]
    return (
        f"Bounding box '{gt_class}' đúng class với model nhưng IoU chỉ {iou:.2f} — bbox có vẻ vẽ chưa "
        "khít quanh vật thể.",
        "Vẽ lại bounding box ground truth sát viền vật thể hơn cho khớp với vùng model phát hiện.",
    )


def _explain_duplicate_label(evidence: dict) -> tuple[str, str]:
    label_a, label_b = evidence["label_a"], evidence["label_b"]
    return (
        f"Nhãn '{label_a}' và '{label_b}' cùng class và chồng lấp gần như hoàn toàn lên nhau — nhiều khả "
        "năng 1 vật thể bị gán nhãn 2 lần.",
        f"Giữ lại nhãn chính xác hơn giữa '{label_a}' và '{label_b}', xoá nhãn còn lại.",
    )


_LOCAL_EXPLANATIONS = {
    "wrong_class": _explain_wrong_class,
    "missing_label": _explain_missing_label,
    "extra_or_wrong_label": _explain_extra_or_wrong_label,
    "bbox_misaligned": _explain_bbox_misaligned,
    "loose_bbox": _explain_loose_bbox,
    "duplicate_label": _explain_duplicate_label,
}

_MINIMAL_LOCAL_EXPLANATIONS = {
    "wrong_class": (
        "Nhãn ground truth và lớp dự đoán có IoU đủ cao nhưng khác class, nên cần kiểm tra lại class của đối tượng.",
        "Đối chiếu đối tượng trên ảnh; đổi class ground truth hoặc giữ nguyên nếu prediction của model không đúng.",
    ),
    "missing_label": (
        "YOLO phát hiện một đối tượng có confidence đáng kể nhưng không tìm thấy ground truth tương ứng.",
        "Kiểm tra vùng bounding box được phát hiện và bổ sung nhãn nếu đối tượng thuộc phạm vi đánh giá.",
    ),
    "extra_or_wrong_label": (
        "Ground truth không có prediction phù hợp, nên nhãn có thể dư, sai class hoặc có bounding box chưa khớp.",
        "Kiểm tra lại đối tượng, class và bounding box; xoá nhãn nếu đó không phải đối tượng hợp lệ.",
    ),
    "bbox_misaligned": (
        "Prediction và ground truth có liên quan nhưng IoU thấp hơn ngưỡng, cho thấy bounding box có thể lệch.",
        "Điều chỉnh toạ độ bounding box để bao phủ đúng đối tượng trên ảnh.",
    ),
    "loose_bbox": (
        "Prediction và ground truth đúng class nhưng IoU còn thấp, nên bounding box có thể chưa khít.",
        "Vẽ lại bounding box ground truth sát viền vật thể hơn.",
    ),
    "duplicate_label": (
        "Có nhiều ground-truth box chồng lấp mạnh cho cùng đối tượng.",
        "Giữ lại một annotation chính xác và xoá hoặc hợp nhất nhãn trùng lặp.",
    ),
}

_GENERIC_FALLBACK = (
    "Issue được phát hiện từ rule-based evidence.",
    "Kiểm tra evidence và annotation tương ứng.",
)


def _local_fallback_issue(issue: dict) -> dict:
    """Return an actionable, evidence-specific explanation when an optional cloud LLM is unavailable."""
    build_explanation = _LOCAL_EXPLANATIONS.get(issue["issue_type"])
    minimal_explanation = _MINIMAL_LOCAL_EXPLANATIONS.get(issue["issue_type"], _GENERIC_FALLBACK)
    try:
        explanation, suggested_fix = (
            build_explanation(issue["evidence"]) if build_explanation else minimal_explanation
        )
    except (KeyError, TypeError):
        explanation, suggested_fix = minimal_explanation
    return {**issue, "explanation": explanation, "suggested_fix": suggested_fix}


async def llm_explain_node(state: LabelQAState) -> dict:
    """Đưa các issue đã rule-based flag cho LLM để giải thích + đề xuất fix.

    LLM chỉ được sinh `explanation`/`suggested_fix`; `issue_type` và `severity`
    do node flag_issues quyết định từ trước và được giữ nguyên khi merge lại,
    tránh việc LLM tự đổi mức độ nghiêm trọng hoặc loại lỗi không dựa trên số liệu.
    """
    issues = state.get("flagged_issues", [])
    if not issues:
        return {}

    indexed_issues = [
        {"issue_index": i, "issue_type": issue["issue_type"], "severity": issue["severity"], "evidence": issue["evidence"]}
        for i, issue in enumerate(issues)
    ]
    user_prompt = (
        f"Ảnh: {state.get('image_path')}\n"
        f"Metrics tổng quan: {state.get('metrics')}\n\n"
        f"Danh sách issue cần giải thích:\n{indexed_issues}"
    )

    try:
        llm = get_agent_llm().with_structured_output(QAIssueExplanationBatch)
        result: QAIssueExplanationBatch = await llm.ainvoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
    except Exception as e:
        # LLM only enriches rule-based results. Keep the demo actionable even
        # without a cloud credential, quota, or network connection.
        fallback_issues = [_local_fallback_issue(issue) for issue in issues]
        return {
            "flagged_issues": fallback_issues,
            "metadata": {**(state.get("metadata") or {}), "llm_explain_fallback_reason": str(e)},
        }

    explanation_map = {e.issue_index: e for e in result.explanations}
    enriched = []
    for i, issue in enumerate(issues):
        exp = explanation_map.get(i)
        enriched.append(
            {
                **issue,
                "explanation": exp.explanation if exp else "Không có giải thích từ LLM.",
                "suggested_fix": exp.suggested_fix if exp else "",
            }
        )

    return {"flagged_issues": enriched}
