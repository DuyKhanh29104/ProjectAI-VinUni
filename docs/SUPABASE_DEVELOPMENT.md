# Chạy development với Supabase

Tài liệu này giúp một developer mới chạy Label Guardian trên máy cá nhân nhưng
dùng chung PostgreSQL Supabase của team.

```text
Backend trên máy developer ──> Supabase PostgreSQL (metadata dùng chung)
Backend trên máy developer ──> GCS private bucket qua ADC/service account
Pytest                    ──> postgres-test local, port 5433
```

Supabase trong workflow này là database PostgreSQL dùng chung. File ảnh và artifact
chuẩn của dự án nằm trên Google Cloud Storage; FastAPI đọc `qa_images.storage_key`
từ Supabase rồi stream object private qua `/api/v1/dataset/images/{split}/{image_id}/content`.
Frontend không đọc GCS trực tiếp.

## 1. Chuẩn bị

- Docker Desktop/Docker Engine đang chạy.
- Docker Compose 2.24.4 trở lên (`docker compose version`).
- File `.env` không được commit lên Git.
- Hai URL database Supabase được maintainer chia sẻ qua password manager hoặc
  kênh bí mật.
- Google Cloud SDK đã login Application Default Credentials nếu cần chạy ingestion
  hoặc backend local cần stream GCS private.
- Golden dataset đã có metadata trong Supabase và object trong GCS dưới prefix
  `datasets/official/...`.

Từ thư mục repository:

```powershell
Copy-Item .env.example .env
```

## 2. Điền URL Supabase

Trong Supabase Dashboard, mở **Connect**. Với máy developer, ưu tiên **Session
pooler**, port `5432`, vì endpoint này hỗ trợ mạng IPv4. Copy đúng hostname,
project ref và username mà Dashboard cung cấp.

Sửa hai dòng trong `.env`:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres.<PROJECT_REF>:<URL_ENCODED_PASSWORD>@<SESSION_POOLER_HOST>:5432/postgres?ssl=require
LABEL_GUARDIAN_DATABASE_URL=postgresql+psycopg://postgres.<PROJECT_REF>:<URL_ENCODED_PASSWORD>@<SESSION_POOLER_HOST>:5432/postgres?sslmode=require
```

Direct Connection cũng dùng port `5432`, nhưng username là `postgres` và thường
cần IPv6. Không dùng Transaction pooler port `6543` cho Alembic hoặc backend hiện
tại.

Nếu password có ký tự đặc biệt, encode ngay trên máy; không dùng website encode
password và không gửi password vào chat:

```powershell
py -3.12 -c "import getpass; from urllib.parse import quote; print(quote(getpass.getpass('Supabase password: '), safe=''))"
```

## 3. Chuẩn bị golden dataset

`.env.example` mặc định dùng chế độ database-backed cloud dataset:

```dotenv
DATASET_BACKEND=database
DATASET_ROOT=data/cloud-db-placeholder
DOCKER_DATASET_ROOT=/app/data/cloud-db-placeholder
DATASET_DEFAULT_SPLIT=smoke
```

`DATASET_ROOT` chỉ còn dùng cho chế độ `DATASET_BACKEND=filesystem`. Ở chế độ
cloud mặc định, Supabase chứa metadata và GCS chứa ảnh/frame. Backend dùng ADC
hoặc runtime credential để đọc GCS private và stream ảnh cho frontend.

Đăng nhập GCP CLI/ADC trên mỗi máy developer:

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project ai-lab-16-gcp-505508
```

Các giá trị GCS trong `.env` local:

```dotenv
LABEL_GUARDIAN_STORAGE_BACKEND=gcs
LABEL_GUARDIAN_GCS_BUCKET=label_guardian_bucket
LABEL_GUARDIAN_GCS_PROJECT=ai-lab-16-gcp-505508
LABEL_GUARDIAN_OBJECT_KEY_PREFIX=datasets/official/nuscenes/v1.0-mini/smoke
```

## 4. Chạy migration — chỉ maintainer

Chỉ một maintainer hoặc CI được chạy lệnh sau khi migration đã merge:

```powershell
docker compose -f docker-compose.yml -f docker-compose.supabase.yml run --rm --no-deps --build backend python -m alembic upgrade head
```

Không chạy `scripts/check_migrations.py`, `alembic downgrade` hoặc pytest trên
Supabase. Migration checker có chủ ý downgrade database test về `base`.

## 5. Chạy backend — mọi developer

Kiểm tra cấu hình mà không in connection string:

```powershell
docker compose -f docker-compose.yml -f docker-compose.supabase.yml config --quiet
```

Build và chạy backend:

```powershell
docker compose -f docker-compose.yml -f docker-compose.supabase.yml up -d --build --wait --wait-timeout 120 backend
```

Supabase override thực hiện ba việc:

- Không khởi động PostgreSQL local.
- Đưa URL Supabase từ `.env` vào backend container.
- Ép `RUN_MIGRATIONS=false`; startup kiểm tra database đang ở Alembic head và
  dừng ngay nếu password sai hoặc migration còn thiếu.

Kiểm tra:

```powershell
docker compose -f docker-compose.yml -f docker-compose.supabase.yml ps
docker compose -f docker-compose.yml -f docker-compose.supabase.yml logs --tail 100 backend
Invoke-WebRequest http://127.0.0.1:8000/api/health
```

Backend: `http://127.0.0.1:8000`; Swagger: `http://127.0.0.1:8000/docs`.

Khi dừng:

```powershell
docker compose -f docker-compose.yml -f docker-compose.supabase.yml stop backend
```

## 6. Chạy backend trực tiếp, không dùng container

Khi `.env` đã chứa URL Supabase:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m alembic current --check-heads
python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Developer thông thường chỉ kiểm tra `current`; không tự chạy `upgrade` trên
database dùng chung.

## 7. Test vẫn dùng PostgreSQL local

Giữ nguyên URL test trong `.env`:

```dotenv
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/label_guardian_test
```

Sau đó:

```powershell
docker compose --profile test up -d --wait postgres-test
$env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/label_guardian_test"
python -m pytest
```

## 8. Lỗi thường gặp

- **Network unreachable với host `db.<ref>.supabase.co`:** máy không có IPv6;
  chuyển sang Session pooler port `5432`.
- **Password authentication failed:** kiểm tra password đã percent-encode và
  username pooler có dạng `postgres.<PROJECT_REF>`.
- **Database is not on all head revisions:** maintainer chưa chạy `alembic
  upgrade head`; không tự sửa schema bằng Supabase Table Editor.
- **Real dataset API báo thiếu object GCS:** kiểm tra `qa_images.storage_key` còn
  trỏ tới object tồn tại trong `gs://label_guardian_bucket` hay không. Không sửa
  bằng cách public bucket; backend phải stream private object qua `/content`.

Không đưa URL database vào frontend. Supabase Auth quản lý identity/session; FastAPI
xác minh access token và thực thi RBAC. Các bảng nghiệp vụ trong schema `public` đã
bật RLS và thu hồi quyền từ `anon`/`authenticated`, vì workflow dữ liệu chỉ dùng kết
nối PostgreSQL server-side từ FastAPI/worker.

Tài liệu chính thức:

- [Supabase: chọn loại kết nối PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Docker: merge và reset Compose configuration](https://docs.docker.com/reference/compose-file/merge/)
