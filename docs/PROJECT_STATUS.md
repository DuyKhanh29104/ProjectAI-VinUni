# Trạng thái dự án

> Cập nhật: 2026-08-27
> Nguồn chuẩn: source code, migration head và `docs/openapi.json`.

## Đã có trong phiên bản hiện tại

### Sản phẩm và frontend

- Landing page song ngữ và application shell responsive.
- Đăng nhập/đăng ký Supabase; mock auth dành cho local demo.
- Overview dùng dữ liệu API khi có và mock projection khi chạy demo.
- QA Queue tách Work Queue và QA Cases registry; hỗ trợ lọc dataset, sequence, risk và status.
- Dataset/frame browser, camera strip và Agent evaluation theo ảnh.
- Reports, Dataset Runs và Pipeline views có API-aware states.
- Settings hiển thị profile và cho Admin quản lý application role.

### 2D Editor

- Editor tích hợp là công cụ chỉnh annotation chính; CVAT runtime đã bị loại bỏ.
- Bounding-box CRUD, class, track ID, attributes và visibility.
- Pan/zoom, undo/redo, keyboard shortcuts, validation và unsaved-change guard.
- Điều hướng Sequence → Frame → Camera, phân trang và jump-to-frame.
- Save & Next, history và restore.
- Optimistic locking bằng `expectedRevision`; stale editor nhận HTTP 409.

### Backend và dữ liệu

- FastAPI `/api/v1` cho auth, dataset, private asset, evaluation, QA case, annotation revision và ingestion status.
- Supabase Auth JWT verification và RBAC `annotator`/`reviewer`/`admin`.
- PostgreSQL/Alembic cho user, ingestion, image/object provenance, evaluation, case, audit và revision.
- GCS private cho image/point-cloud/artifact; frontend tải qua authenticated FastAPI.
- Effective-label overlay: dataset, Editor và lần Agent evaluation sau đọc revision mới nhất.
- QA case status command ghi audit và lấy actor từ access token.

### Agent và ingestion

- LangGraph pipeline: load labels → YOLO → validate → matching → metrics → deterministic flags → optional LLM explanation → report.
- Persist evaluation và QA cases; cache evaluation theo process.
- KITTI/nuScenes adapters, local ingestion và GCP Batch worker.
- Ingestion job lease/retry/stale recovery, GCS artifacts và read-only pipeline status API.

### Deployment và chất lượng

- Production frontend trên Vercel; backend/Caddy trên GCP VM; Supabase Auth/PostgreSQL và GCS private.
- CI chạy lint, mypy, OpenAPI drift, migration lifecycle, pytest/coverage, frontend tests/typecheck/build và Docker smoke.
- Self-host deploy workflow chạy migration một lần, health check và rollback candidate khi lỗi.

## Giới hạn hiện tại

- UI vẫn giữ mock mode và một số telemetry/assignment/report export chỉ là demo khi backend chưa có contract tương ứng.
- Editor mới hỗ trợ bounding box 2D; chưa có polygon/polyline, interpolation hoặc point-cloud editing.
- Point-cloud API chỉ stream bytes; frontend chưa có 3D viewer.
- Assignment/lease cho reviewer ở cấp frame chưa có.
- Chưa có dataset release/export workflow từ annotation revisions.
- Full KITTI/nuScenes ingestion tốn tài nguyên và vẫn cần vận hành bằng batch profile phù hợp.
- Chưa có rate limiting, distributed tracing và browser E2E hoàn chỉnh.

## Ưu tiên tiếp theo

1. Hoàn thiện ingestion full dataset và validation report có thể tái lập.
2. Tune Agent threshold/risk ranking bằng golden dataset và reviewer feedback.
3. Bổ sung assignment/locking để tránh hai reviewer xử lý cùng work item.
4. Chuẩn hóa export revision thành dataset version có provenance.
5. Bổ sung E2E cho auth, QA case → Editor, canvas gesture và revision conflict.
6. Thêm observability, rate limiting, secret rotation và backup/restore drill.

Roadmap dài hạn cho 3D/multi-sensor nằm trong [`PRODUCT_DESCRIPTION.md`](PRODUCT_DESCRIPTION.md), không được xem là tính năng đã triển khai.
