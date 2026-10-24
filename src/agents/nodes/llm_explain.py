from math import isfinite

from src.agents.state import LabelQAState
from src.models.agent_schemas import QAIssueExplanationBatch
from src.services.agent_llm import get_agent_llm

_SYSTEM_PROMPT = """Bạn là người soát lại chất lượng nhãn (khung bao quanh vật thể) trên ảnh 2D.

Bạn nhận một danh sách nghi vấn đã được hệ thống rà soát tự động phát hiện và tính sẵn bằng \
số liệu (mức độ trùng khớp giữa khung nhãn và vật thể, độ chắc chắn có vật thể, có khớp loại \
đối tượng hay không...). Với MỖI nghi vấn, hãy viết:

1. "explanation": giải thích ngắn gọn, bằng lời dễ hiểu cho người gán nhãn không rành kỹ thuật, \
vì sao khung nhãn này bị nghi ngờ. BẮT BUỘC nêu rõ đang nói tới vật thể nào — dựa vào trường \
"object" (loại đối tượng + vị trí trên ảnh) đã cho sẵn, nhắc lại vị trí đó trong câu để người \
đọc biết cần nhìn vào đâu. CHỈ dựa trên số liệu trong "evidence"/"object", không bịa thêm chi \
tiết. KHÔNG dùng thuật ngữ hoặc từ viết tắt (IoU, confidence, class, bbox, ground truth, \
prediction...); diễn đạt bằng lời thường ("khung nhãn lệch khá nhiều so với vật thể", "hệ \
thống khá chắc ở đây có một vật thể"...). KHÔNG nhắc tên mô hình, YOLO, hay "AI/model" — chỉ \
gọi chung là "hệ thống rà soát".

2. "suggested_fix": một hành động chỉnh sửa cụ thể, làm được ngay, có nhắc vị trí/khu vực cần \
thao tác (ví dụ: "kéo lại các cạnh khung ở phía trên bên trái cho ôm sát vật thể", "đổi loại \
đối tượng của khung này từ X sang Y", "xoá khung bị trùng", "thêm khung cho vật thể còn thiếu \
ở khu vực ...").

Đây mới là "nghi ngờ", chưa chắc nhãn sai — hệ thống rà soát cũng có thể nhầm. Chọn giọng văn \
nặng hay nhẹ theo mức độ (high/medium/low) của từng nghi vấn.

Trả lời đúng issue_index tương ứng với từng nghi vấn trong danh sách đầu vào.
"""


# Câu mô tả "loại lỗi" — phần cụ thể (vật thể nào, số liệu bao nhiêu) được ghép thêm ở
# _local_fallback_issue() từ evidence + toạ độ khung.
_LOCAL_EXPLANATIONS = {
    "wrong_class": (
        "Khung nhãn nằm đúng vị trí một vật thể trên ảnh, nhưng loại đối tượng đang gán khác với "
        "loại mà hệ thống rà soát nhận ra.",
        "Nhìn lại vật thể trong khung rồi sửa loại đối tượng cho đúng, hoặc giữ nguyên nếu hệ thống rà soát nhận nhầm.",
    ),
    "missing_label": (
        "Hệ thống rà soát khá chắc chắn ở khu vực này có một vật thể, nhưng chưa có khung nhãn nào được gán cho nó.",
        "Kiểm tra khu vực được chỉ ra và thêm một khung nhãn mới nếu đúng là có vật thể thuộc phạm vi cần gán.",
    ),
    "extra_or_wrong_label": (
        "Không tìm thấy vật thể nào khớp với khung nhãn này, nên nhãn có thể bị thừa, sai loại "
        "đối tượng, hoặc khung vẽ chưa đúng chỗ.",
        "Xem lại nhãn: chỉnh khung cho ôm đúng vật thể và sửa loại đối tượng; xoá nhãn nếu ở đó "
        "không có vật thể hợp lệ.",
    ),
    "bbox_misaligned": (
        "Khung nhãn và khung hệ thống rà soát tìm thấy có giao nhau nhưng chưa khớp; cần kiểm tra lại vị trí.",
        "Đối chiếu vật thể trên ảnh rồi điều chỉnh khung nếu cần; hệ thống rà soát cũng có thể nhầm.",
    ),
    "loose_bbox": (
        "Khung nhãn và khung hệ thống rà soát tìm thấy chưa khớp hoàn toàn dù cùng loại đối tượng.",
        "Kiểm tra các cạnh khung trên ảnh và chỉnh nếu cần; giữ nguyên nếu nhãn đã đúng.",
    ),
    "duplicate_label": (
        "Có từ hai khung nhãn trở lên gần như chồng khít lên nhau cho cùng một vật thể.",
        "Giữ lại một khung chính xác nhất và xoá (hoặc gộp) những khung bị trùng.",
    ),
}

_DEFAULT_EXPLANATION = (
    "Nghi vấn này được phát hiện tự động khi đối chiếu khung nhãn với vật thể trên ảnh.",
    "Kiểm tra lại khung nhãn và vật thể tương ứng trên ảnh.",
)


def _num(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _issue_bbox(issue: dict, gt_by_id: dict[str, dict]) -> dict | None:
    """Toạ độ khung liên quan tới issue: ưu tiên bbox trong evidence, sau đó tra theo label_id."""
    evidence = issue.get("evidence") or {}
    bbox = evidence.get("bbox")
    if isinstance(bbox, dict) and {"x1", "y1", "x2", "y2"} <= bbox.keys():
        return bbox
    ref_id = issue.get("label_id") or evidence.get("gt_id") or evidence.get("label_a")
    target = gt_by_id.get(ref_id) if ref_id else None
    target_bbox = target.get("bbox") if target else None
    if isinstance(target_bbox, dict):
        return target_bbox
    return None


def _relative_position(bbox: dict, width: float | None, height: float | None) -> str:
    """'phía trên bên trái ảnh' — giúp người soát biết nhìn vào đâu mà không cần toạ độ thô."""
    if width is None or height is None or width <= 0 or height <= 0:
        return ""
    cx = (bbox["x1"] + bbox["x2"]) / 2 / width
    cy = (bbox["y1"] + bbox["y2"]) / 2 / height
    horizontal = "bên trái" if cx < 0.34 else "bên phải" if cx > 0.66 else "chính giữa"
    vertical = "phía trên" if cy < 0.34 else "phía dưới" if cy > 0.66 else "khoảng giữa"
    if horizontal == "chính giữa" and vertical == "khoảng giữa":
        return "ở khu vực giữa ảnh"
    if horizontal == "chính giữa":
        return f"ở {vertical} ảnh"
    if vertical == "khoảng giữa":
        return f"ở {horizontal} ảnh"
    return f"ở {vertical} {horizontal} ảnh"


def _box_region(bbox: dict, *, with_unit: bool = True) -> str:
    region = f"x: {round(bbox['x1'])}-{round(bbox['x2'])}, y: {round(bbox['y1'])}-{round(bbox['y2'])}"
    return f"{region} (theo pixel)" if with_unit else region


def _object_phrase(issue: dict, gt_by_id: dict[str, dict], width: float | None, height: float | None) -> str:
    """Mô tả vật thể/khung mà issue đang nói tới: loại + vị trí."""
    evidence = issue.get("evidence") or {}
    issue_type = issue.get("issue_type")

    if issue_type == "duplicate_label":
        a = evidence.get("label_a")
        b = evidence.get("label_b")
        return f"hai khung nhãn trùng nhau ({a} và {b})" if a and b else "các khung nhãn bị trùng"

    class_name = (
        evidence.get("gt_class")
        or evidence.get("class_name")
        or (gt_by_id.get(issue.get("label_id") or "", {}) or {}).get("class_name")
    )
    bbox = _issue_bbox(issue, gt_by_id)

    if issue_type == "missing_label":
        head = f'vật thể "{class_name}"' if class_name else "vật thể"
        head += " mà hệ thống rà soát tìm thấy"
    else:
        head = f'khung nhãn "{class_name}"' if class_name else "khung nhãn"

    location_bits = []
    rel = _relative_position(bbox, width, height) if bbox else ""
    if rel:
        location_bits.append(rel)
    if bbox:
        location_bits.append(_box_region(bbox))
    if location_bits:
        head += " nằm " + ", ".join(location_bits)
    return head


def _evidence_note(issue: dict) -> str:
    """Diễn giải con số quan trọng nhất trong evidence bằng lời thường."""
    evidence = issue.get("evidence") or {}
    issue_type = issue.get("issue_type")
    iou = _num(evidence.get("iou"))
    best_iou = _num(evidence.get("best_iou"))
    confidence = _num(evidence.get("confidence"))
    gt_class = evidence.get("gt_class")
    pred_class = evidence.get("pred_class") or evidence.get("best_pred_class")

    if issue_type == "wrong_class":
        parts = []
        if iou is not None:
            parts.append(f"khung khớp vị trí vật thể tới khoảng {iou:.0%}")
        if gt_class and pred_class:
            parts.append(f'đang gán là "{gt_class}" nhưng hệ thống rà soát cho là "{pred_class}"')
        return "; ".join(parts)
    if issue_type == "loose_bbox":
        return f"hai khung trùng nhau khoảng {iou:.0%} theo tỉ lệ diện tích giao trên hợp" if iou is not None else ""
    if issue_type == "missing_label":
        return (
            f"điểm tin cậy của phát hiện là {confidence:.0%}, cần đối chiếu lại ảnh" if confidence is not None else ""
        )
    if issue_type == "bbox_misaligned":
        base = f"chỗ gần nhất chỉ trùng khoảng {best_iou:.0%} với vật thể" if best_iou is not None else ""
        if pred_class:
            base += f' "{pred_class}"'
        return base
    if issue_type == "extra_or_wrong_label":
        if best_iou is not None and best_iou > 0:
            return f"vật thể gần nhất cũng chỉ trùng khoảng {best_iou:.0%}"
        return "hệ thống rà soát không tìm thấy vật thể khớp với khung này; có thể đã bỏ sót"
    return ""


def _local_fallback_issue(
    issue: dict, gt_by_id: dict[str, dict] | None = None, width: float | None = None, height: float | None = None
) -> dict:
    """Giải thích rule-based khi không gọi được LLM — vẫn nêu rõ vật thể nào + số liệu."""
    gt_by_id = gt_by_id or {}
    base_explanation, base_fix = _LOCAL_EXPLANATIONS.get(issue.get("issue_type") or "", _DEFAULT_EXPLANATION)

    obj = _object_phrase(issue, gt_by_id, width, height)
    note = _evidence_note(issue)
    explanation = base_explanation
    if obj:
        explanation += f" Cụ thể: {obj}"
        explanation += f" — {note}." if note else "."
    elif note:
        explanation += f" ({note})."

    suggested_fix = base_fix
    bbox = _issue_bbox(issue, gt_by_id)
    if bbox and issue.get("issue_type") in {"missing_label", "bbox_misaligned", "loose_bbox", "extra_or_wrong_label"}:
        rel = _relative_position(bbox, width, height)
        suggested_fix += f" Khu vực cần xem: {rel + ', ' if rel else ''}{_box_region(bbox, with_unit=False)}."

    return {**issue, "explanation": explanation, "suggested_fix": suggested_fix}


def _image_size(state: LabelQAState) -> tuple[float | None, float | None]:
    scope = (state.get("metadata") or {}).get("label_scope") or {}
    metrics = state.get("metrics") or {}
    width = scope.get("image_width") or metrics.get("image_width")
    height = scope.get("image_height") or metrics.get("image_height")
    return _num(width), _num(height)


async def llm_explain_node(state: LabelQAState) -> dict:
    """Đưa các issue đã rule-based flag cho LLM để giải thích + đề xuất fix.

    LLM chỉ được sinh `explanation`/`suggested_fix`; `issue_type` và `severity`
    do node flag_issues quyết định từ trước và được giữ nguyên khi merge lại,
    tránh việc LLM tự đổi mức độ nghiêm trọng hoặc loại lỗi không dựa trên số liệu.
    """
    issues = state.get("flagged_issues", [])
    if not issues:
        return {}

    gt_by_id = {g["label_id"]: g for g in state.get("gt_labels", []) if g.get("label_id")}
    width, height = _image_size(state)

    indexed_issues = [
        {
            "issue_index": i,
            "issue_type": issue["issue_type"],
            "severity": issue["severity"],
            "object": _object_phrase(issue, gt_by_id, width, height),
            "evidence": issue["evidence"],
        }
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
        fallback_issues = [_local_fallback_issue(issue, gt_by_id, width, height) for issue in issues]
        return {
            "flagged_issues": fallback_issues,
            "metadata": {**(state.get("metadata") or {}), "llm_explain_fallback_reason": str(e)},
        }

    explanation_map = {e.issue_index: e for e in result.explanations}
    enriched = []
    for i, issue in enumerate(issues):
        exp = explanation_map.get(i)
        if exp:
            enriched.append({**issue, "explanation": exp.explanation, "suggested_fix": exp.suggested_fix})
        else:
            # LLM bỏ sót issue_index này -> vẫn trả lời cụ thể bằng nhánh rule-based.
            enriched.append(_local_fallback_issue(issue, gt_by_id, width, height))

    return {"flagged_issues": enriched}
