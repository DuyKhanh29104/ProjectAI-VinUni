from src.agents.state import LabelQAState


async def build_report_node(state: LabelQAState) -> dict:
    """Tổng hợp kết quả cuối cùng thành QA report trả về cho API layer."""
    if state.get("error"):
        return {
            "qa_report": {
                "image_path": state.get("image_path"),
                "status": "error",
                "summary": state["error"],
                "metrics": {},
                "issues": [],
            }
        }

    issues = state.get("flagged_issues", [])
    metrics = state.get("metrics", {})
    # issue "blocking=False" (vd loose_bbox trên vật thể nhỏ, xem flagging.py)
    # vẫn được ghi nhận trong issues để audit, nhưng không tự đẩy status lên
    # needs_review một mình.
    blocking_issues = [i for i in issues if i.get("blocking", True)]
    status = "needs_review" if blocking_issues else "pass"
    if issues and not blocking_issues:
        summary = (
            f"Không có nhãn nào cần review — {len(issues)} issue được ghi nhận nhưng không chặn "
            f"(vd loose_bbox trên vật thể nhỏ), xem chi tiết trong issues."
        )
    elif issues:
        summary = (
            f"Phát hiện {len(blocking_issues)}/{len(issues)} nhãn nghi ngờ có lỗi cần review "
            f"(precision={metrics.get('precision')}, recall={metrics.get('recall')})."
        )
    else:
        summary = "Không phát hiện nhãn nghi ngờ có lỗi so với dự đoán YOLO."

    llm_error = (state.get("metadata") or {}).get("llm_explain_error")
    if llm_error:
        summary += " Lưu ý: LLM giải thích bị lỗi khi gọi API, vui lòng tự đánh giá dựa trên evidence."

    return {
        "qa_report": {
            "image_path": state.get("image_path"),
            "status": status,
            "summary": summary,
            "metrics": metrics,
            "issues": issues,
        }
    }
