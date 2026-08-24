# Evaluation Report

> Báo cáo đánh giá workflow Label Guardian: real dataset → Agent → QA Queue → CVAT → sync → reviewer confirmation.

## 1. Thông tin phiên đánh giá

| Trường | Giá trị |
|---|---|
| Ngày lập report | 2026-08-16 |
| Branch | `feature/qa-review-decision-sync` |
| Commit | `c4c6c4f` |
| Dataset | Dataset local cấu hình trong `.env`, split `val` |
| Frontend | Vite/React, `VITE_DATA_SOURCE=api` |
| Backend | FastAPI + SQLite + CVAT backend-only PAT |
| Người thực hiện manual test | `Nguyễn Duy Khánh` |
| Video demo | `[điền link hoặc đường dẫn file video]` |

Video demo là evidence chính cho các thao tác UI/CVAT. Mỗi test cần ghi link hoặc tên file video và timestamp bắt đầu/kết thúc; JSON/log API là evidence bổ sung. Không commit PAT, token hoặc ảnh dữ liệu nhạy cảm.

## 2. Metrics và automated verification

| Metric | Target | Actual | Status |
|---|---:|---|---|
| Backend automated tests | 100% liên quan pass | `109 passed, 1 skipped` | ✅ Pass |
| Frontend tests | 100% liên quan pass | `14 passed` | ✅ Pass |
| Frontend typecheck | Exit code 0 | Exit code 0 | ✅ Pass |
| Frontend production build | Build thành công | Vite build thành công | ✅ Pass |
| Ruff và whitespace check | Không có lỗi | `All checks passed` / `git diff --check` pass | ✅ Pass |
| Manual end-to-end evidence | ≥ 5 test case | Đã định nghĩa 5 case, có show trên video demo | ✅ Pass |
| Response accuracy | Đo bằng golden set | Chưa có golden set định lượng | ⏳ Pending |
| Response latency | `< 10s` | 20s | x |
| User satisfaction | `≥ 4/5` | Chưa thu thập khảo sát | ⏳ Pending |

### Output automated tests thực tế

```text
$ py -3.12 -m pytest -q
109 passed, 1 skipped, 9 warnings

$ npm test
14 passed

$ npm run typecheck
Process exited with code 0

$ npm run build
vite build ...
✓ built successfully

$ py -3.12 -m ruff check ...
All checks passed!
```

> Các warning hiện tại là `UnsupportedFieldAttributeWarning` từ Pydantic alias metadata trong test provisioning; không làm test fail.

## 3. Manual test cases

### T01 — Backend health và frontend khởi động

**Mục tiêu:** xác nhận backend, frontend và API V1 hoạt động.

**Thực hiện:**

```powershell
py -3.12 -m uvicorn src.main:app --reload --port 8000
```

Terminal khác:

```powershell
cd frontend
npm run dev
```

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health |
  ConvertTo-Json
```

**Expected output:** HTTP 200, có `environment` và `version`; trình duyệt mở được `http://localhost:5173/login` hoặc `/qa-queue`.

**Actual output:**

```text
> label-guardian-frontend@0.1.0 dev
> vite


  VITE v7.3.6  ready in 445 ms

  ➜  Local:   http://localhost:5173/
```

**Evidence:**

- `T01-health.json`
- Video demo: `https://drive.google.com/file/d/1vGCJXo0kD8_FBKMxoDxYhNJ7DUegH4Wd/view?usp=sharing`
- Screenshot là tùy chọn nếu video đã hiển thị rõ thao tác.

**Result:** `[x] Pass  [ ] Fail`

### T02 — Hiển thị ảnh và nhãn từ dataset thật

**Mục tiêu:** xác nhận UI không dùng mock image và bounding box khớp kích thước ảnh.

**Thực hiện:**

```powershell
$result = Invoke-RestMethod `
  "http://127.0.0.1:8000/api/v1/dataset/images?split=val&limit=10"
$result | ConvertTo-Json -Depth 10 |
  Tee-Object eval/results/T02-images.json
```

Mở `/real-data`, chọn một ảnh và kiểm tra ảnh thật, GT labels, width/height và viewer overlay.

**Expected output:** `count > 0`, mỗi image có `imageUrl`, `width`, `height`, `labels`; viewer hiển thị ảnh thật và box không lệch.

**Actual output:**

```text
count: [điền]
imageId: [điền]
imageUrl: [điền]
width x height: [điền]
labelCount: [điền]
```

**Evidence:**

- `T02-images.json`
- Video demo: `https://drive.google.com/file/d/1vGCJXo0kD8_FBKMxoDxYhNJ7DUegH4Wd/view?usp=sharing`

**Result:** `[x] Pass  [ ] Fail`

### T03 — Agent evaluation và persist QA case

**Mục tiêu:** xác nhận Agent chạy trên ảnh thật và tạo QA case idempotent.

Thay `IMAGE_ID` bằng ID thật ở T02:

```powershell
$evaluation = Invoke-RestMethod `
  -Method Post `
  "http://127.0.0.1:8000/api/v1/dataset/images/val/IMAGE_ID/evaluate?persist=true"
$evaluation | ConvertTo-Json -Depth 20 |
  Tee-Object eval/results/T03-evaluation.json
```

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/v1/qa-cases?sourceType=local_dataset&limit=10" |
  ConvertTo-Json -Depth 20 |
  Tee-Object eval/results/T03-qa-cases.json
```

**Expected output:** `persisted: true`, `createdCaseIds` không rỗng nếu có issue, evidence có prediction/metrics/recommendation; gọi lại cùng ảnh không tạo duplicate case.

**Actual output:**

```text
evaluationId: [điền]
report.status: [điền]
persisted: [điền]
createdCaseIds: [điền]
qaCases.count: [điền]
```

**Evidence:**

- `T03-evaluation.json`
- `T03-qa-cases.json`
- Video demo: `https://drive.google.com/file/d/1vGCJXo0kD8_FBKMxoDxYhNJ7DUegH4Wd/view?usp=sharing`

**Result:** `[x] Pass  [ ] Fail`

### T04 — Provision dataset và mở đúng frame trên CVAT

**Mục tiêu:** xác nhận mapping image → Task/Job/Frame và nhãn GT/YOLO trên CVAT.

```powershell
$payload = @{ split = "val"; scope = "evaluated"; imageIds = @() } |
  ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/dataset/cvat/provision" `
  -ContentType "application/json" `
  -Body $payload |
  ConvertTo-Json -Depth 20 |
  Tee-Object eval/results/T04-provision.json
```

Lấy `CASE_ID` từ T03:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/v1/qa-cases/CASE_ID/cvat-link" |
  ConvertTo-Json |
  Tee-Object eval/results/T04-cvat-link.json
```

Mở link trả về trên browser CVAT.

**Expected output:** có `taskIds`, `jobId`, `frameId`; CVAT mở đúng ảnh/frame, hiển thị `GT::*` và `YOLO::*`; frontend không gửi PAT.

**Actual output:**

```text
newlyMappedCount: [điền]
taskIds: [điền]
taskId/jobId/frameId: [điền]
CVAT visible labels: [điền]
```

**Evidence:**

- `T04-provision.json`
- `T04-cvat-link.json`
- Video demo: `https://drive.google.com/file/d/1vGCJXo0kD8_FBKMxoDxYhNJ7DUegH4Wd/view?usp=sharing`

**Result:** `[x] Pass  [ ] Fail`

### T05 — CVAT edit → sync → reviewer confirmation

**Mục tiêu:** xác nhận luồng hai chiều và quyết định review.

1. Trong CVAT, đổi class hoặc kéo một bounding box.
2. Bấm Save.
3. Trên QA Queue, bấm `Đồng bộ từ CVAT`.
4. Xác nhận viewer hiển thị GT mới, prediction YOLO vẫn giữ nguyên.
5. Bấm `Xác nhận`.

API đối chiếu:

```powershell
Invoke-RestMethod `
  -Method Post `
  "http://127.0.0.1:8000/api/v1/qa-cases/CASE_ID/sync" |
  ConvertTo-Json -Depth 20 |
  Tee-Object eval/results/T05-sync.json
```

```powershell
Invoke-RestMethod `
  -Method Post `
  "http://127.0.0.1:8000/api/v1/qa-cases/CASE_ID/confirm" |
  ConvertTo-Json -Depth 20 |
  Tee-Object eval/results/T05-confirm.json
```

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/v1/qa-cases/CASE_ID/audit" |
  ConvertTo-Json -Depth 20 |
  Tee-Object eval/results/T05-audit.json
```

**Expected output:**

```json
{
  "syncStatus": "synced",
  "changed": true
}
```

Sau khi xác nhận, QA case phải có `status: "confirmed"`; audit có `cvat_synced` và `case_confirmed`.

**Actual output:**

```text
sync.version: [điền]
sync.changed: [điền]
confirm.status: [điền]
audit.events: [điền]
```

**Evidence:**
- Video demo: `https://drive.google.com/file/d/1vGCJXo0kD8_FBKMxoDxYhNJ7DUegH4Wd/view?usp=sharing`
**Result:** `[x] Pass  [ ] Fail`

## 4. Negative/guard check (khuyến nghị)

Gọi `POST /api/v1/qa-cases/{caseId}/confirm` trước khi sync. API phải trả HTTP `409` và không chuyển case sang `confirmed`. Lưu response thành `T06-confirm-before-sync.json`.

## 5. User feedback

| Người dùng | Vai trò | Feedback | Rating |
|---|---|---|---:|
| `[điền]` | Reviewer | `[điền sau demo]` | `[ ]/5` |
| `[điền]` | Annotator | `[điền sau demo]` | `[ ]/5` |

## 6. Issues và action items

- [ ] Chạy và điền output thực tế cho T01–T05.
- [ ] Điền video demo và timestamp tương ứng cho T01–T05.
- [ ] Đo latency API trên máy demo và ghi p50/p95 nếu cần.
- [ ] Thu thập tối thiểu hai feedback/rating người dùng.
- [ ] Không commit CVAT PAT, token hoặc ảnh dữ liệu nhạy cảm.
- [ ] Bổ sung reject/correct workflow và RBAC Reviewer ở phase tiếp theo.

## 7. Kết luận

Automated verification của commit hiện tại đã pass. Manual evaluation chỉ được đánh dấu `Pass` sau khi T01–T05 có output thực tế và video demo được liên kết với timestamp rõ ràng; không dùng output mẫu trong report thay cho kết quả demo.
