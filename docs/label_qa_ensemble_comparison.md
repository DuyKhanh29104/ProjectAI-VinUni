# So sánh nhãn gốc với cả 2 model (YOLO + RT-DETR) — bộ luật ensemble

Tài liệu này mô tả bộ luật **độc lập** để phát hiện issue bằng cách đối chiếu
nhãn gốc (`gt_labels`) với **đồng thời** cả hai detector — YOLO
(`pred_labels`) và RT-DETR (`rtdetr_pred_labels`) — implement tại
[`flag_issues_ensemble`](../src/agents/nodes/ensemble_flagging.py), hiển thị ở
mục 4 và mục 7 của [app.py](../app.py).

Đây **không** phải bản thay thế cho `flag_issues` (xem
[label_qa_agent.md § 6](label_qa_agent.md#6-các-loại-issue-flag_issues) và
[label_qa_issue_types.md](label_qa_issue_types.md)) — `flag_issues` (GT vs
YOLO) vẫn là bộ luật chính thức chạy trong pipeline và quyết định
`qa_report`. `flag_issues_ensemble` **không được nối vào graph**, chỉ chạy
thêm ở UI để tham khảo, khi cần bằng chứng chéo từ 2 model độc lập trước khi
quyết định sửa nhãn.

## 1. Nguyên tắc cốt lõi

**2 model chỉ là tham chiếu bổ sung, không phải ground truth.** Cụ thể:

- YOLO và RT-DETR đồng ý *với nhau* **không** tự động nghĩa là chúng đúng và
  nhãn gốc sai — chỉ là bằng chứng đáng để con người xem lại.
- Vì vậy, **mọi trường hợp 2 model đồng ý với nhau nhưng khác nhãn gốc đều
  phải bị gắn cờ** — không có nhánh nào trong code được phép âm thầm bỏ qua
  (`continue`) khi rơi vào tình huống này. Đây là bất biến (invariant) được
  test bằng ví dụ ở mục 4.
- Ngược lại, khi 2 model **bất đồng với nhau** (không có sự đồng thuận rõ
  ràng), độ tin cậy của bằng chứng thấp hơn — vẫn bị gắn cờ, nhưng severity
  thấp hơn trường hợp 2 model đồng thuận.
- Chỉ khi **cả nhãn gốc lẫn 2 model đều đồng ý** thì mới không có issue — đây
  là trường hợp duy nhất được `continue`.

Nói cách khác: sự đồng thuận giữa 2 model chỉ được dùng để **nâng độ ưu
tiên cần xem xét lại**, không bao giờ được dùng để **khẳng định** nhãn gốc
sai hay để hệ thống tự ý im lặng bỏ qua.

## 2. Cách xác định — từng nhãn gốc (`gt_labels`)

Với mỗi `gt`, hàm chạy `match_labels(gt_labels, pred_labels)` và
`match_labels(gt_labels, rtdetr_pred_labels)` riêng (Hungarian IoU matching,
xem [label_qa_agent.md § 4](label_qa_agent.md#4-matching-và-các-ngưỡng-threshold))
để lấy verdict của từng model tại vị trí `gt` đó: `my` (YOLO) và `mr`
(RT-DETR) — mỗi cái có thể `None` (model không khớp được gt này ở
`IOU_MATCH_THRESHOLD = 0.5`) hoặc là một `match` dict (`pred_class`,
`class_match`, `iou`...).

```python
yolo_ok = bool(my and my["class_match"])
rtdetr_ok = bool(mr and mr["class_match"])
```

### Bảng quyết định

| Điều kiện                                                                 | `issue_type`                                       | `severity` | `agreement`             |
| -------------------------------------------------------------------------- | ----------------------------------------------------- | ------------ | -------------------------- |
| `my`, `mr` đều khớp gt, cả 2 đều đúng class (`yolo_ok and rtdetr_ok`) | *(không có issue)*                                   | —          | —                         |
| `my`, `mr` đều khớp gt, **2 model dự đoán cùng 1 class** nhưng khác `gt_class` | `wrong_class`                                       | `high`     | `model_consensus_vs_gt` |
| `my`, `mr` đều khớp gt, cả 2 sai class nhưng **khác nhau** (không đồng thuận) | `wrong_class`                                       | `high`     | `model_conflict`         |
| `my`, `mr` đều khớp gt, chỉ 1 model đúng class (model kia sai)              | `wrong_class`                                       | `medium`   | `model_conflict`         |
| Không model nào khớp được gt này                                            | `bbox_misaligned` (best_iou ≥ 0.1) hoặc `extra_or_wrong_label` | `high`     | `both_missing`           |
| Chỉ 1 trong 2 model khớp được gt này (model kia không thấy vị trí đó)       | `wrong_class` hoặc `bbox_misaligned`               | `low`      | `single_model`           |

Dòng 2 (`model_consensus_vs_gt`) chính là trường hợp trọng tâm của nguyên tắc
ở mục 1 — implement trực tiếp bằng:

```python
if my and mr:
    models_agree_each_other = my["pred_class"] == mr["pred_class"]
    if yolo_ok and rtdetr_ok:
        continue  # GT + cả 2 model đều đồng ý -> không có issue
    if models_agree_each_other:
        # 2 model giống nhau nhưng khác GT -> LUÔN đặt cờ, không được bỏ qua
        severity = "high"; agreement = "model_consensus_vs_gt"
    elif not yolo_ok and not rtdetr_ok:
        severity = "high"; agreement = "model_conflict"   # cả 2 sai nhưng khác nhau
    else:
        severity = "medium"; agreement = "model_conflict"  # 1 đúng, 1 sai
```

So với dòng 3 (`model_conflict`, cả 2 sai nhưng khác nhau) cũng được đặt
`severity = "high"` — vì dù 2 model không thống nhất *với nhau*, cả hai vẫn
đồng thuận rằng **nhãn gốc sai** (chỉ bất đồng về class đúng là gì), nên vẫn
là tín hiệu mạnh cần xem lại, dù bằng chứng để chọn class thay thế yếu hơn
dòng 2.

Dòng cuối (`single_model`, `severity=low`) là bằng chứng yếu nhất: chỉ 1
model có ý kiến, model kia không phát hiện được gì ở vị trí này (có thể do
model đó yếu, không hẳn nhãn sai).

## 3. Cách xác định — prediction thừa không khớp gt nào

Ngoài đối chiếu theo từng `gt`, hàm còn xét các prediction **không khớp gt
nào** ở cả 2 model (`unmatched_pred` từ mỗi `match_labels`) — nghi ngờ nhãn
gốc **thiếu** một object mà model phát hiện được.

Cách làm: ghép chéo `unmatched_pred` của YOLO với `unmatched_pred` của
RT-DETR bằng chính `match_labels` (coi các box YOLO thừa như "gt" tạm thời
bằng `label_id` sinh sẵn `yolo_extra_<i>`), để tìm cặp mà **cả 2 model cùng
đồng ý** phát hiện một vật thể ở cùng vị trí + cùng class:

| Điều kiện                                                                              | `issue_type`      | `severity` | `agreement`   |
| ----------------------------------------------------------------------------------------- | -------------------- | ------------ | --------------- |
| Cả 2 model cùng phát hiện 1 vật thể (khớp IoU + cùng class) mà không có gt nào              | `missing_label`   | `high`     | `both_found`   |
| Chỉ 1 model phát hiện (model kia không thấy), `confidence ≥ EXTRA_PRED_CONF_MIN = 0.6` | `missing_label`   | `low`      | `single_model` |

Cũng tuân theo đúng nguyên tắc mục 1: 2 model đồng thuận → severity cao nhất
(`high`), 1 model đơn lẻ → bằng chứng yếu (`low`), và **không có trường hợp
nào bị bỏ qua hoàn toàn** nếu có bằng chứng đủ mạnh — kể cả khi cả 2 model
"thừa" prediction ở đây, nhãn gốc không có gì để tham chiếu, hệ thống vẫn chủ
động gắn cờ thay vì im lặng.

## 4. Field `agreement` — mức độ tin cậy của bằng chứng

Khác với `flag_issues` gốc, mỗi issue ở đây có thêm field `agreement` để UI
và người review biết ngay bằng chứng đến từ 1 hay 2 model, không phải suy ra
từ `evidence` thô:

| `agreement`                | Ý nghĩa                                                                 | Độ tin cậy       |
| --------------------------- | -------------------------------------------------------------------------- | ------------------ |
| `model_consensus_vs_gt`   | 2 model đồng ý **với nhau** nhưng khác nhãn gốc                       | Cao nhất          |
| `both_missing`             | Không model nào tìm thấy gt này ở đâu cả                                | Cao               |
| `both_found`               | 2 model cùng phát hiện 1 vật thể mà nhãn gốc không có                    | Cao               |
| `model_conflict`           | 2 model bất đồng với nhau (có thể 1 đúng 1 sai, hoặc cả 2 sai khác nhau) | Trung bình đến cao |
| `single_model`             | Chỉ 1 trong 2 model đưa ra được bằng chứng                              | Thấp              |

`evidence` đi kèm mỗi issue giữ nguyên `match` dict gốc từ `match_labels`
(khoá `"yolo"`/`"rtdetr"`, có thể `None` nếu model đó không có ý kiến) hoặc
`{"gt": ..., "best_iou": ...}` cho trường hợp `both_missing` — đủ để LLM hoặc
người review truy lại số liệu gốc (IoU, confidence, class từng model) mà
không cần chạy lại inference.

## 5. Ví dụ minh hoạ

```python
gt_labels = [{"label_id": "gt_1", "class_name": "dog", "bbox": {...}}]
pred_labels = [{"class_name": "cat", "bbox": {...cùng vị trí gt_1...}, "confidence": 0.9}]      # YOLO
rtdetr_pred_labels = [{"class_name": "cat", "bbox": {...cùng vị trí gt_1...}, "confidence": 0.85}]  # RT-DETR

flag_issues_ensemble(gt_labels, pred_labels, rtdetr_pred_labels)
# -> [{"label_id": "gt_1", "issue_type": "wrong_class", "severity": "high",
#      "agreement": "model_consensus_vs_gt", "evidence": {"yolo": ..., "rtdetr": ...}}]
```

Cả YOLO và RT-DETR đều đoán "cat" tại đúng vị trí nhãn gốc ghi "dog" — dù 2
model đồng thuận, hệ thống **không** kết luận nhãn gốc chắc chắn sai (đúng
nguyên tắc mục 1), chỉ gắn cờ `severity=high` để người review tự quyết định
có đổi `dog` → `cat` hay giữ nguyên (có thể ảnh có yếu tố khiến cả 2 model
cùng nhầm, ví dụ chó giống mèo hoặc góc chụp lạ).

## 6. Ngưỡng dùng riêng cho bộ luật này

| Hằng số                                        | Giá trị | Ý nghĩa                                                                            |
| ------------------------------------------------- | --------- | --------------------------------------------------------------------------------------- |
| `BBOX_MISALIGN_IOU_MIN` (`ensemble_flagging.py`) | 0.1       | Giống `flagging.py` nhưng tách hằng số riêng để 2 bộ luật không phụ thuộc lẫn nhau |
| `EXTRA_PRED_CONF_MIN` (`ensemble_flagging.py`)   | 0.6       | Ngưỡng confidence tối thiểu để 1 model đơn lẻ (không được model kia xác nhận) đủ mạnh để nghi `missing_label` |

`IOU_MATCH_THRESHOLD = 0.5` dùng chung với `matching.py` (không định nghĩa
lại) vì bản thân việc ghép gt↔pred của từng model vẫn tái dùng
`match_labels` — xem [label_qa_agent.md § 4](label_qa_agent.md#4-matching-và-các-ngưỡng-threshold).

## 7. Hiển thị ở UI (`app.py`)

| Mục UI | Hàm vẽ | Nội dung |
| --- | --- | --- |
| **4. So sánh kết hợp YOLO + RT-DETR trên ảnh gốc** | `draw_comparison` | So sánh 2 model **với nhau** (không xét nhãn gốc): box xanh lá = 2 model khớp vị trí + cùng class, đỏ = model kia không đồng ý hoặc không thấy — dùng `match_labels` coi YOLO như "gt" tạm thời |
| **7. Nhãn bị gắn cờ — GT vs CẢ 2 model (bộ luật ensemble riêng)** | `draw_ensemble_flagged` | Kết quả `flag_issues_ensemble` — nhãn gốc đối chiếu với cả 2 model, tô màu theo `severity` (đỏ=high, cam=medium, vàng=low), caption hiển thị cả `agreement` |

Cả 2 mục chỉ hiện khi bật checkbox "Bật RT-DETR" ở sidebar (cần
`rtdetr_pred_labels`). Mục 5 (`GT vs YOLO`, dùng `flag_issues` chính thức) và
mục 6 (`GT vs RT-DETR` riêng lẻ) giữ nguyên, không liên quan tới bộ luật
ensemble này.

## 8. Bản đồ file

```
src/agents/nodes/
├── matching.py            # match_labels() — tái dùng cho cả flag_issues và flag_issues_ensemble
├── flagging.py             # flag_issues() — bộ luật CHÍNH THỨC (GT vs YOLO), nối vào graph/qa_report
└── ensemble_flagging.py    # flag_issues_ensemble() — bộ luật RIÊNG (GT vs YOLO+RT-DETR), KHÔNG nối vào graph

app.py                      # mục 4 (draw_comparison) và mục 7 (draw_ensemble_flagged) dùng bộ luật này
```
