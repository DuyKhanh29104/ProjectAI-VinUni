# Các loại lỗi nhãn — cách xác định và đề xuất sửa

Tài liệu này tách riêng phần "lỗi nhãn" (`issue_type`) từ [label_qa_agent.md](label_qa_agent.md)
mục 6, trình bày chi tiết theo 3 khía cạnh: **loại lỗi là gì**, **agent xác định
bằng cách nào** (rule + số liệu trong `flagging.py`), và **đề xuất sửa** (theo
`suggested_fix` mà LLM sinh ra ở `llm_explain.py`, dựa trên `evidence` gốc).

Lưu ý xuyên suốt: mọi rule ở đây do **code** quyết định (`issue_type` +
`severity` + `blocking`), LLM chỉ diễn giải bằng lời và gợi ý cách sửa —
không được tự đổi loại lỗi hay mức độ nghiêm trọng. Xem thêm mục 1 và mục 8
của [label_qa_agent.md](label_qa_agent.md).

Các threshold trong tài liệu này đọc theo giá trị hiện tại của code tại thời
điểm viết — chúng được tinh chỉnh khá thường xuyên, nên khi cần số chính xác
hãy đọc trực tiếp từ `flagging.py`/`matching.py` thay vì tin tuyệt đối vào
con số ghi cứng ở đây.

## Tổng quan 6 loại lỗi

| `issue_type`           | Ý nghĩa ngắn gọn                                  | Severity                                | Có thể `blocking=False`? |
| ---------------------- | -------------------------------------------------- | ---------------------------------------- | --- |
| `wrong_class`          | Đúng vị trí, sai tên class                         | `high` nếu IoU ≥ 0.85, else `medium` | Không |
| `loose_bbox`           | Match hợp lệ, đúng class, nhưng bbox chưa khít     | `low`                                   | Có — nếu GT là vật thể nhỏ |
| `missing_label`        | Model thấy vật thể nhưng annotator không gán nhãn | `high` / `low` theo confidence       | Không |
| `bbox_misaligned`      | Có nhãn, có prediction gần đó, nhưng bbox lệch nhiều | `medium`                              | Không |
| `extra_or_wrong_label` | Nhãn không khớp gì cả (thừa hoặc sai hoàn toàn)   | `medium`                                | Không |
| `duplicate_label`      | Hai nhãn cùng class trùng gần như hoàn toàn        | `medium`                                | Không |

`blocking` (mặc định `True` cho mọi issue) quyết định issue đó có tự đẩy
`qa_report.status` lên `needs_review` hay không — `False` chỉ xảy ra với
`loose_bbox` trên vật thể nhỏ (xem mục 2 và [report.py](../src/agents/nodes/report.py)).
Issue `blocking=False` vẫn được tạo và ghi nhận đầy đủ trong `issues`, chỉ
không một mình đẩy status lên review.

---

## 1. `wrong_class` — Sai class

**Lỗi là gì:** bbox của ground truth và prediction khớp vị trí tốt (được
Hungarian matching ghép cặp, IoU ≥ `IOU_MATCH_THRESHOLD`), nhưng
`class_name` của hai bên khác nhau. Ví dụ: annotator gán "car" nhưng model
đoán "truck" tại đúng vị trí đó.

**Cách xác định (`flagging.py`, bước 1):**

```python
for m in matches:
    if not m["class_match"]:
        severity = "high" if m["iou"] >= 0.85 else "medium"
```

- Chỉ xét trong `matches` (đã ghép cặp thành công theo vị trí) — nếu
  `class_match == False` thì bị gắn cờ.
- `severity = high` khi IoU ≥ 0.85 (bbox khớp rất khít, nên khả năng cao là
  đúng vật thể chỉ sai nhãn class, đáng tin hơn) — ngược lại `medium`.
- `evidence` đi kèm: `gt_class`, `pred_class`, `iou`, `class_match`.
- `blocking` luôn `True`.

**Đề xuất sửa:** đổi `class_name` của nhãn từ `gt_class` sang `pred_class`
(hoặc class đúng theo review thủ công) — giữ nguyên toạ độ bbox vì vị trí đã
khớp. Vì YOLO không phải ground truth tuyệt đối, cần người review xác nhận
class nào đúng trước khi sửa, đặc biệt khi `severity=medium` (IoU thấp hơn,
độ tin cậy thấp hơn).

---

## 2. `loose_bbox` — Bbox chưa khít

**Lỗi là gì:** ground truth và prediction vẫn ghép cặp thành công (IoU ≥
`IOU_MATCH_THRESHOLD`) và đúng class, nhưng chưa đạt IoU đủ cao để coi là
khít hoàn toàn — bbox có thể hơi thừa nền hoặc thiếu một phần vật thể. Khác
với `bbox_misaligned` (mục 4): ở đây match **đã thành công**, đây chỉ là
nghi vấn nhẹ về độ chính xác của bbox, không phải "không tìm được vị trí
tương ứng".

**Cách xác định (`flagging.py`, bước 1, nhánh else):**

```python
for m in matches:
    if not m["class_match"]:
        ...  # wrong_class
    elif m["iou"] < LOOSE_BBOX_IOU_MAX:   # 0.85
        gt = gt_by_id[m["gt_id"]]
        area = (gt["bbox"]["x2"] - gt["bbox"]["x1"]) * (gt["bbox"]["y2"] - gt["bbox"]["y1"])
        is_small = area < SMALL_OBJECT_AREA_MAX   # 32*32 px
        blocking = not is_small
```

- Điều kiện: match hợp lệ (`class_match=True`), nhưng `IOU_MATCH_THRESHOLD ≤ iou < LOOSE_BBOX_IOU_MAX`.
- **Vật thể nhỏ** (diện tích GT < `SMALL_OBJECT_AREA_MAX`, quy ước COCO
  small-object = 32×32 px): issue vẫn được tạo (ghi nhận đầy đủ để audit)
  nhưng `blocking=False` — không tự đẩy `status` lên `needs_review`. Lý do:
  vật thể càng nhỏ, IoU càng nhạy với sai số vài pixel, nên lệch nhẹ ở vật
  thể nhỏ thường phản ánh độ nhạy của phép đo hơn là annotator vẽ ẩu thật sự.
- `evidence` đi kèm: `match` dict gốc (`gt_id`, `gt_class`, `pred_class`, `iou`, `class_match`).

**Đề xuất sửa:** chỉnh nhẹ toạ độ bbox cho khít hơn quanh biên vật thể —
mức độ ưu tiên thấp hơn nhiều so với các lỗi khác (severity luôn `low`); với
vật thể nhỏ có thể bỏ qua nếu không có tác động thực tế đến việc dùng nhãn.

---

## 3. `missing_label` — Thiếu nhãn

**Lỗi là gì:** model tự tin phát hiện một vật thể ở vị trí không có ground
truth nào gần đó — nghi ngờ annotator bỏ sót nhãn tại vị trí này.

**Cách xác định (`flagging.py`, bước 2):**

```python
for pred in unmatched_pred:
    if pred["best_iou"] >= BBOX_MISALIGN_IOU_MIN:   # 0.1
        continue  # đã có gt gần đó -> xử lý ở bbox_misaligned
    if pred["confidence"] >= MISSING_LABEL_CONF_HIGH:   # 0.6
        severity = "high"
    elif pred["confidence"] >= MISSING_LABEL_CONF_LOW:  # 0.25
        severity = "low"
    else:
        continue  # model không đủ chắc để nghi ngờ
```

- Xét trong `unmatched_pred` (prediction không ghép được với gt nào).
- Điều kiện bắt buộc: `best_iou < 0.1` — nghĩa là không có gt nào ở gần vị trí
  này (nếu có, đó là lỗi khác — xem `bbox_misaligned`).
- `confidence ≥ 0.6` → `high`; `0.25 ≤ confidence < 0.6` → `low`;
  `confidence < 0.25` → bỏ qua, không đủ tin cậy để nghi ngờ.
- `evidence`: `class_name`, `bbox`, `confidence`, `best_iou` của prediction đó.
- `blocking` luôn `True`.

**Đề xuất sửa:** bổ sung nhãn mới tại toạ độ `bbox` của prediction, với class
là `class_name` model dự đoán — cần người review xác nhận trực quan trên ảnh
trước khi thêm, đặc biệt với `severity=low` (model cũng chỉ tự tin vừa phải).

---

## 4. `bbox_misaligned` — Bbox lệch vị trí/kích thước

**Lỗi là gì:** ground truth không ghép được với prediction nào (dưới
`IOU_MATCH_THRESHOLD`), nhưng vẫn có một prediction ở gần đó (cùng vùng,
khác class hoặc không) — nghi ngờ bbox của nhãn bị vẽ lệch, quá to/nhỏ so
với vật thể thật, chứ không phải nhãn thừa hoàn toàn.

**Cách xác định (`flagging.py`, bước 3, nhánh đầu):**

```python
for gt in unmatched_gt:
    if gt["label_id"] in redundant_unmatched_ids:
        continue  # đã giải thích bằng duplicate_label ở bước 0 — xem mục 6
    if gt["best_iou"] >= BBOX_MISALIGN_IOU_MIN:   # 0.1
        issue_type = "bbox_misaligned"
        severity = "medium"
```

- Xét trong `unmatched_gt` (gt không ghép được pred nào ở
  `IOU_MATCH_THRESHOLD`).
- Điều kiện: `best_iou ≥ 0.1` — có prediction "gần đó" dù không đủ khớp để
  match chính thức → đây là tín hiệu "cùng một vật thể nhưng bbox lệch nhau",
  không phải "không liên quan gì cả".
- **Loại trừ trước** các GT đã được giải thích bởi `duplicate_label` (bước 0
  chạy trước, xem mục 6) — nếu không sẽ double-flag 1 lỗi vật lý (nhãn bị
  duplicate) thành 2 issue khác nhau.
- `evidence`: gt gốc kèm `best_iou`, `best_pred_class` (class của prediction
  gần nhất tìm được).
- `blocking` luôn `True`.

**Đề xuất sửa:** điều chỉnh lại toạ độ bbox (`x1,y1,x2,y2`) của nhãn cho khớp
sát hơn với vùng model phát hiện — không cần đổi class trừ khi
`best_pred_class` khác với `class_name` hiện tại của gt (khi đó nên xem xét
đồng thời cả sai class).

---

## 5. `extra_or_wrong_label` — Nhãn thừa hoặc sai hoàn toàn vị trí

**Lỗi là gì:** ground truth không ghép được với bất kỳ prediction nào, và
cũng không có prediction nào ở gần — nghi ngờ đây là nhãn thừa (vật thể không
tồn tại, hoặc đã bị xoá khỏi ảnh) hoặc bbox nằm sai vị trí hoàn toàn (không
còn liên quan gì tới vùng model detect được).

**Cách xác định (`flagging.py`, bước 3, nhánh else):**

```python
for gt in unmatched_gt:
    if gt["label_id"] in redundant_unmatched_ids:
        continue  # xem mục 6
    if gt["best_iou"] >= BBOX_MISALIGN_IOU_MIN:
        ...  # bbox_misaligned
    else:
        issue_type = "extra_or_wrong_label"
        severity = "medium"
```

- Điều kiện: `best_iou < 0.1` — không tìm được bất kỳ prediction nào ở gần vị
  trí gt này, dù là lỏng lẻo.
- Khác với `bbox_misaligned` chỉ ở mức `best_iou` — cùng nguồn dữ liệu
  (`unmatched_gt`), khác nhánh rẽ, cùng được loại trừ trước nếu đã thuộc
  `redundant_unmatched_ids` (xem mục 6).
- `blocking` luôn `True`.

**Đề xuất sửa:** kiểm tra trực quan trên ảnh gốc — nếu vật thể thực sự không
tồn tại tại vị trí đó, xoá nhãn; nếu vật thể có tồn tại nhưng model không
nhận ra (model yếu với domain/class hiếm), giữ nhãn nhưng ghi chú để review
kỹ hơn thay vì tin luôn theo model.

---

## 6. `duplicate_label` — Nhãn trùng lặp

**Lỗi là gì:** hai nhãn ground truth cùng class được vẽ chồng lên gần như
cùng một vùng — nhiều khả năng annotator gán nhãn trùng lặp cho cùng một vật
thể (double-click, copy-paste nhầm...).

**Cách xác định (`flagging.py`, bước 0 — chạy TRƯỚC mọi loại issue khác):**

```python
for i in range(len(gt_labels)):
    for j in range(i + 1, len(gt_labels)):
        a, b = gt_labels[i], gt_labels[j]
        if a["class_name"] != b["class_name"]:
            continue
        if iou(a["bbox"], b["bbox"]) >= DUPLICATE_GT_IOU_THRESHOLD:  # 0.8
            issue_type = "duplicate_label"
            # ghi nhớ box nào trong cặp còn "chưa match" để bước 3 bỏ qua
            a_matched, b_matched = a["label_id"] in matched_gt_ids, b["label_id"] in matched_gt_ids
            if a_matched and not b_matched:
                redundant_unmatched_ids.add(b["label_id"])
            elif b_matched and not a_matched:
                redundant_unmatched_ids.add(a["label_id"])
```

- **Duy nhất** trong 6 loại lỗi không dựa trên `matches`/`unmatched_*` (tức
  không liên quan tới prediction/YOLO) — so trực tiếp từng cặp `gt_labels`
  với nhau.
- Điều kiện: cùng `class_name` và `IoU(bbox_a, bbox_b) ≥ 0.8` (ngưỡng cao vì
  chỉ coi là trùng khi overlap gần như hoàn toàn, tránh nhầm với hai vật thể
  cùng loại đứng sát nhau).
- Vì không liên quan tới matching, loại lỗi này **không** ảnh hưởng tới
  `metrics` (precision/recall/f1...) — chỉ xuất hiện trong `flagged_issues`.
- `evidence`: `label_a`, `label_b` (id của hai nhãn trùng).
- `blocking` luôn `True`.

**Vì sao chạy trước (bước 0) — bug đã sửa:** khi 2 box GT trùng lặp cùng 1
vật thể nhưng chỉ có 1 prediction thật, Hungarian matching (`match_labels`)
chỉ ghép được 1 trong 2 box. Box duplicate còn lại thành `unmatched_gt`, và
vì nó overlap cao với chính box đã match (cùng vật thể) nên `best_iou` của
nó với prediction cũng cao — trước đây bị bước 3 (mục 4) gắn cờ thêm
`bbox_misaligned` giả, dù không hề lệch vị trí, chỉ là bản sao thừa. Từ khi
sửa: bước 0 chạy trước, đánh dấu box nào trong cặp duplicate "không match
được nhưng có anh em đã match" vào `redundant_unmatched_ids`, để bước 3 bỏ
qua — mỗi lỗi vật lý chỉ còn tạo đúng 1 issue.

**Đề xuất sửa:** xoá một trong hai nhãn trùng (giữ lại nhãn có toạ độ chính
xác hơn nếu có sự khác biệt nhỏ), không cần chạy lại YOLO vì lỗi này độc lập
với model.

---

## Bảng ngưỡng dùng chung

Xem đầy đủ tại [label_qa_agent.md § 4](label_qa_agent.md#4-matching-và-các-ngưỡng-threshold).

| Hằng số                    | File | Vai trò trong việc xác định lỗi                              |
| --------------------------- | --- | ---------------------------------------------------------------- |
| `IOU_MATCH_THRESHOLD`     | `matching.py` | Ngưỡng để một cặp gt↔pred được coi là "match" — chi phối `wrong_class`/`loose_bbox` vs các lỗi còn lại |
| `LOOSE_BBOX_IOU_MAX`      | `flagging.py` | Match hợp lệ nhưng IoU dưới mốc này vẫn coi là `loose_bbox` |
| `SMALL_OBJECT_AREA_MAX`   | `flagging.py` | GT nhỏ hơn diện tích này: `loose_bbox` có `blocking=False` |
| `MISSING_LABEL_CONF_HIGH` | `flagging.py` | Ngưỡng confidence để `missing_label` = `high`                |
| `MISSING_LABEL_CONF_LOW`  | `flagging.py` | Dưới ngưỡng này bỏ qua, không đủ tin cậy để nghi `missing_label` |
| `BBOX_MISALIGN_IOU_MIN`   | `flagging.py` | Ngưỡng phân biệt "có liên quan" (`bbox_misaligned`) và "không liên quan gì" (`extra_or_wrong_label`) |
| `DUPLICATE_GT_IOU_THRESHOLD` | `flagging.py` | Ngưỡng coi hai gt cùng class là trùng lặp                          |

Đây là giá trị khởi điểm, nên tinh chỉnh theo domain thực tế (vật thể
nhỏ/dày đặc thường cần threshold IoU thấp hơn để tránh flag sai hàng loạt).
Không ghi cứng giá trị số ở bảng này (khác bản trước) vì các threshold được
tinh chỉnh khá thường xuyên — đọc trực tiếp từ code khi cần số chính xác.

## Vai trò của LLM trong bước "đề xuất sửa"

Các đề xuất sửa ở trên là mô tả chung theo rule; trong thực tế `suggested_fix`
cụ thể cho từng issue do LLM sinh ra (`llm_explain.py`), dựa **chỉ** trên
`evidence` của issue đó — không suy đoán thêm. LLM được yêu cầu dùng mức độ
ngôn ngữ phù hợp với `severity` và không khẳng định chắc chắn 100% nhãn sai
(vì YOLO cũng có thể sai). Nếu LLM gọi lỗi (hết quota, mất mạng...),
`explanation`/`suggested_fix` sẽ có fallback báo lỗi, còn `issue_type`,
`severity` và `blocking` (đã tính bằng code) vẫn giữ nguyên và đáng tin cậy.
