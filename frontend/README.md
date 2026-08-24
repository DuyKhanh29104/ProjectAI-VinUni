# Label Guardian Frontend

React/Vite frontend cho QA nhãn camera 2D.

## Màn hình chính

- QA Queue: lọc case, xem evidence và so sánh annotation/prediction.
- 2D Editor: công cụ chỉnh sửa chính, mở bằng `/editor?split={split}&imageId={id}`.
- Dataset QA: duyệt frame và chạy Agent.
- Overview, Reports, Dataset, Settings và các màn mock hỗ trợ demo.

2D Editor dùng API revision của FastAPI và hỗ trợ bounding box CRUD, class/track/attributes, pan/zoom, undo/redo, validation, Save & Next, history và restore. Save dùng optimistic locking để tránh ghi đè giữa hai tab.

## Chạy local

```powershell
npm install
npm run dev
```

Dùng backend thật:

```text
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Dùng dữ liệu demo: `VITE_DATA_SOURCE=mock`.

Dùng xác thực thật:

```text
VITE_AUTH_MODE=supabase
VITE_SUPABASE_URL=https://<PROJECT_REF>.supabase.co
VITE_SUPABASE_ANON_KEY=<SUPABASE_PUBLISHABLE_OR_ANON_KEY>
```

Frontend chỉ giữ session do Supabase client quản lý. Mọi JSON request và request tải ảnh private đều gửi access token tới FastAPI. Role hiển thị lấy từ `/api/v1/auth/me`; người dùng không thể tự đổi role trên UI.

## Kiểm thử

```powershell
npm run typecheck
npm test -- --run
npm run build
```

Frontend không giữ database, object-storage hoặc model credentials.

## Deploy Vercel

Đặt Vercel Root Directory là `frontend`, copy các biến trong `../deploy/vercel.env.example`, rồi trỏ `VITE_API_BASE_URL` tới public domain Railway. Giữ `VITE_DATASET_ID`/`VITE_DATASET_VERSION` khớp với Railway. `vercel.json` đã cấu hình Vite build, thư mục `dist`, security headers và SPA deep-link rewrite.
