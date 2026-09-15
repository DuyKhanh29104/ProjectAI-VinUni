# Label Guardian Frontend

React/Vite frontend cho QA nhãn camera 2D.

## Màn hình chính

- Landing page công khai tại `/` và application shell sau đăng nhập.
- QA Queue: chọn frame/dataset, chạy Agent và xem evidence.
- QA Cases: registry finding, lọc trạng thái/risk và mở Editor.
- 2D Editor: công cụ chỉnh sửa chính, mở bằng `/editor?split={split}&imageId={id}`.
- Dataset QA: duyệt frame và chạy Agent.
- Overview, Reports, Dataset Runs, Pipeline và Settings có API/mock presentation phù hợp.

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
npm test
npm run build
```

Frontend không giữ database, object-storage hoặc model credentials.

## Deploy Vercel

Đặt Vercel Root Directory là `frontend`, copy các biến public trong `../deploy/vercel.env.example`, rồi trỏ `VITE_API_BASE_URL` tới `https://api.labelguardian.space`. Giữ `VITE_DATASET_ID`/`VITE_DATASET_VERSION` khớp backend trên VM. `vercel.json` đã cấu hình Vite build, thư mục `dist`, API proxy, security headers và SPA deep-link rewrite.

Xem runbook tại [`../docs/HYBRID_VERCEL_VM_DEPLOYMENT.md`](../docs/HYBRID_VERCEL_VM_DEPLOYMENT.md).
