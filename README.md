# Label Guardian

Label Guardian là hệ thống QA và chỉnh sửa nhãn camera 2D cho dữ liệu perception. QA Agent phát hiện lỗi, xếp hạng rủi ro và tạo case; người dùng review rồi chỉnh trực tiếp bằng 2D Editor tích hợp.

## Luồng chính

```text
Dataset → Ingestion → Model inference + QA Agent → QA Queue
       → 2D Editor → Annotation revision → Re-evaluate / Review decision
```

- QA Queue lọc và ưu tiên lỗi theo risk score.
- Viewer so sánh annotation hiện tại với prediction.
- 2D Editor hỗ trợ tạo, chọn, di chuyển, resize, xóa bounding box; đổi class, track ID và attributes.
- Undo/redo, phím tắt, validation, cảnh báo thay đổi chưa lưu và Save & Next.
- Backend lưu snapshot bất biến theo revision, optimistic locking, audit, history và restore.
- Mọi API dataset và lần chạy Agent đọc annotation revision mới nhất.
- Supabase Auth quản lý mật khẩu/session; FastAPI xác minh JWT và PostgreSQL lưu role ứng dụng.

## Chạy local

Yêu cầu Python 3.12+, Node.js 20+ và PostgreSQL.

```powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
python -m uvicorn src.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Mặc định frontend gọi backend tại `http://127.0.0.1:8000`. Có thể dùng dữ liệu mock bằng `VITE_DATA_SOURCE=mock`.

## Xác thực và phân quyền

Không lưu mật khẩu trong bảng nghiệp vụ. Supabase Auth giữ identity, mật khẩu, email confirmation và refresh session; bảng `application_users` chỉ giữ `display_name`, `role` và trạng thái khóa.

| Role | Quyền chính |
|---|---|
| Annotator | Đọc dataset/case, mở và lưu/restore nhãn trong 2D Editor |
| Reviewer | Quyền Annotator, chạy Agent và cập nhật trạng thái QA case |
| Admin | Toàn bộ thao tác và quản lý role người dùng |

Sau khi điền biến Supabase trong `.env` và `frontend/.env.local`, chạy `alembic upgrade head`. Email trong `AUTH_BOOTSTRAP_ADMIN_EMAILS` trở thành Admin ở request đăng nhập đầu tiên; tài khoản mới còn lại mặc định là Annotator. Trong production, backend từ chối khởi động nếu `AUTH_ENABLED` không bật.

## API chính

| Method | Endpoint | Mục đích |
|---|---|---|
| GET | `/api/v1/dataset/frame-samples` | Duyệt frame/camera |
| GET | `/api/v1/dataset/images/{split}/{imageId}/annotations` | Đọc document và revision hiện tại |
| PUT | `/api/v1/dataset/images/{split}/{imageId}/annotations` | Lưu revision mới |
| GET | `.../annotations/history` | Đọc lịch sử |
| POST | `.../annotations/restore` | Khôi phục original hoặc revision cũ |
| POST | `/api/v1/dataset/images/{split}/{imageId}/evaluate` | Chạy QA Agent trên nhãn hiện tại |
| GET | `/api/v1/qa-cases` | Đọc QA Queue |
| POST | `/api/v1/qa-cases/{caseId}/status` | Cập nhật quyết định review |
| GET | `/api/v1/auth/me` | Hồ sơ và role của phiên hiện tại |
| GET | `/api/v1/auth/users` | Danh sách người dùng (Admin) |
| PATCH | `/api/v1/auth/users/{userId}/role` | Cấp role (Admin) |

## Kiểm thử

```powershell
python -m ruff check src tests migrations
python -m pytest -q
cd frontend
npm run typecheck
npm test -- --run
npm run build
```

PostgreSQL test phải là database riêng. Xem [docs/TESTING.md](docs/TESTING.md) và [docs/LABEL_GUARDIAN_ARCHITECTURE.md](docs/LABEL_GUARDIAN_ARCHITECTURE.md).

## Deploy

Production dùng Vercel cho React/Vite SPA, Railway cho FastAPI container, Supabase cho Auth/PostgreSQL và GCS private cho ảnh. Railway chạy migration ở pre-deploy và health check `/ready`; Vercel đã có SPA rewrite trong `frontend/vercel.json`.

Xem checklist, biến môi trường mẫu và smoke test tại [docs/CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md).
