from __future__ import annotations

from src.agents.nodes.matching import match_labels

# best_iou >= ngưỡng này giữa gt và cả 2 model không match được coi là "có liên hệ"
# (cùng một vật thể nhưng bbox lệch), thay vì "không liên quan gì nhau".
# Cùng giá trị với BBOX_MISALIGN_IOU_MIN trong flagging.py, tách hằng số riêng để
# 2 bộ luật không phụ thuộc lẫn nhau.
BBOX_MISALIGN_IOU_MIN = 0.1

# Prediction "thừa" (không khớp GT nào) có confidence >= ngưỡng này mới đủ mạnh
# để nghi ngờ thiếu nhãn khi chỉ 1 model phát hiện được.
EXTRA_PRED_CONF_MIN = 0.6


def flag_issues_ensemble(
    gt_labels: list[dict],
    pred_labels: list[dict],
    rtdetr_pred_labels: list[dict],
) -> list[dict]:
    """Bộ luật riêng: đối chiếu nhãn gốc với ĐỒNG THỜI cả YOLO và RT-DETR.

    Khác với flag_issues (src/agents/nodes/flagging.py — chỉ dùng GT vs YOLO,
    chạy trong pipeline chính thức cho qa_report), hàm này KHÔNG được nối vào
    graph/qa_report — chỉ dùng để hiển thị thêm ở UI (xem app.py).

    QUAN TRỌNG — 2 model chỉ là tham chiếu bổ sung, KHÔNG phải ground truth:
    2 model đồng thuận với nhau không tự động nghĩa là chúng đúng. Vì vậy khi
    YOLO và RT-DETR đồng ý với NHAU (cùng dự đoán một class) nhưng class đó
    khác với GT, đây là bằng chứng đối lập trực tiếp với nhãn gốc và LUÔN LUÔN
    bị gắn cờ (severity "high", không có nhánh nào được phép bỏ qua/continue).
    Việc "2 model khớp nhau" chỉ được dùng để nâng độ ưu tiên cần xem xét lại,
    không được dùng để khẳng định nhãn gốc sai hay để tự động im lặng bỏ qua.

    Severity chung: "high" khi cả 2 model đồng ý với nhau về một kết luận khác
    GT (hoặc cùng không thấy object), "medium" khi 2 model bất đồng với nhau
    (không có sự đồng thuận rõ ràng để dựa vào), "low" khi chỉ 1 trong 2 model
    đưa ra được bằng chứng (model kia không match được vị trí này).

    Mỗi issue có thêm field `agreement` (không có trong flag_issues) để UI/LLM
    biết bằng chứng đến từ 1 hay cả 2 model:
    - "model_consensus_vs_gt": 2 model đồng ý với NHAU nhưng khác GT
    - "model_conflict": 2 model khớp vị trí GT nhưng bất đồng với nhau
    - "single_model": chỉ 1 trong 2 model đưa ra bằng chứng
    - "both_missing": không model nào khớp được GT ở vị trí này
    - "both_found": 2 model cùng phát hiện 1 vật thể mà GT không có
    """
    m_yolo = match_labels(gt_labels, pred_labels)
    m_rtdetr = match_labels(gt_labels, rtdetr_pred_labels)

    yolo_by_gt = {m["gt_id"]: m for m in m_yolo["matches"]}
    rtdetr_by_gt = {m["gt_id"]: m for m in m_rtdetr["matches"]}
    yolo_best_iou_by_gt = {u["label_id"]: u["best_iou"] for u in m_yolo["unmatched_gt"]}
    rtdetr_best_iou_by_gt = {u["label_id"]: u["best_iou"] for u in m_rtdetr["unmatched_gt"]}

    issues: list[dict] = []

    # 1. Từng GT: kết hợp verdict của 2 model (khớp đúng class / khớp sai class / không khớp)
    for gt in gt_labels:
        gid = gt["label_id"]
        my = yolo_by_gt.get(gid)
        mr = rtdetr_by_gt.get(gid)
        yolo_ok = bool(my and my["class_match"])
        rtdetr_ok = bool(mr and mr["class_match"])

        if my and mr:
            # cả 2 model đều khớp vị trí GT này
            models_agree_each_other = my["pred_class"] == mr["pred_class"]

            if yolo_ok and rtdetr_ok:
                continue  # GT + cả 2 model đều đồng ý -> không có issue

            if models_agree_each_other:
                # 2 model giống nhau nhưng khác GT -> LUÔN đặt cờ, không được bỏ qua
                issues.append(
                    {
                        "label_id": gid,
                        "issue_type": "wrong_class",
                        "severity": "high",
                        "agreement": "model_consensus_vs_gt",
                        "evidence": {"yolo": my, "rtdetr": mr},
                    }
                )
            elif not yolo_ok and not rtdetr_ok:
                # cả 2 đều chê GT nhưng mỗi model chê một kiểu khác nhau -> vẫn rất đáng ngờ
                issues.append(
                    {
                        "label_id": gid,
                        "issue_type": "wrong_class",
                        "severity": "high",
                        "agreement": "model_conflict",
                        "evidence": {"yolo": my, "rtdetr": mr},
                    }
                )
            else:
                # 1 model đồng ý GT, model kia bất đồng -> bằng chứng yếu hơn, chưa rõ ai đúng
                issues.append(
                    {
                        "label_id": gid,
                        "issue_type": "wrong_class",
                        "severity": "medium",
                        "agreement": "model_conflict",
                        "evidence": {"yolo": my, "rtdetr": mr},
                    }
                )
            continue

        if not my and not mr:
            # không model nào khớp được GT này
            best_iou = max(
                yolo_best_iou_by_gt.get(gid, 0.0),
                rtdetr_best_iou_by_gt.get(gid, 0.0),
            )
            issues.append(
                {
                    "label_id": gid,
                    "issue_type": "bbox_misaligned" if best_iou >= BBOX_MISALIGN_IOU_MIN else "extra_or_wrong_label",
                    "severity": "high",
                    "agreement": "both_missing",
                    "evidence": {"gt": gt, "best_iou": best_iou},
                }
            )
            continue

        # chỉ 1 trong 2 model khớp được GT này (dù đúng hay sai class) -> bằng chứng yếu hơn
        issues.append(
            {
                "label_id": gid,
                "issue_type": "wrong_class" if (my or mr) and not (yolo_ok or rtdetr_ok) else "bbox_misaligned",
                "severity": "low",
                "agreement": "single_model",
                "evidence": {"yolo": my, "rtdetr": mr},
            }
        )

    # 2. Prediction "thừa" (không khớp GT nào): chỉ coi là bằng chứng mạnh về thiếu nhãn
    #    khi CẢ 2 model cùng đồng ý phát hiện một vật thể ở cùng vị trí + cùng class.
    yolo_extra = [{**p, "label_id": f"yolo_extra_{i}"} for i, p in enumerate(m_yolo["unmatched_pred"])]
    rtdetr_extra = m_rtdetr["unmatched_pred"]
    cross = match_labels(yolo_extra, rtdetr_extra)

    matched_yolo_idx: set[int] = set()
    matched_rtdetr_idx: set[int] = set()
    for m in cross["matches"]:
        if not m["class_match"]:
            continue
        yolo_idx = int(m["gt_id"].split("_")[-1])
        matched_yolo_idx.add(yolo_idx)
        matched_rtdetr_idx.add(m["pred_index"])
        issues.append(
            {
                "label_id": None,
                "issue_type": "missing_label",
                "severity": "high",
                "agreement": "both_found",
                "evidence": {"yolo": m_yolo["unmatched_pred"][yolo_idx], "rtdetr": rtdetr_extra[m["pred_index"]]},
            }
        )

    for i, pred in enumerate(m_yolo["unmatched_pred"]):
        if i in matched_yolo_idx or pred.get("confidence", 0) < EXTRA_PRED_CONF_MIN:
            continue
        issues.append(
            {
                "label_id": None,
                "issue_type": "missing_label",
                "severity": "low",
                "agreement": "single_model",
                "evidence": {"yolo": pred},
            }
        )
    for j, pred in enumerate(rtdetr_extra):
        if j in matched_rtdetr_idx or pred.get("confidence", 0) < EXTRA_PRED_CONF_MIN:
            continue
        issues.append(
            {
                "label_id": None,
                "issue_type": "missing_label",
                "severity": "low",
                "agreement": "single_model",
                "evidence": {"rtdetr": pred},
            }
        )

    return issues
