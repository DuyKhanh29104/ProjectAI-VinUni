# Kiểm thử

> Cập nhật: 2026-08-27

Không dùng database development/production cho test migration hoặc pytest. CI tạo PostgreSQL 16 riêng; local dùng service `postgres-test` ở cổng mặc định `5433`.

## Cài dependency

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[agent-yolo,ingestion]" --group dev
cd frontend
npm ci
```

## Backend quality gate

Từ repository root:

```powershell
python -m ruff check src tests migrations scripts/check_migrations.py scripts/check_openapi.py
python -m mypy src
python scripts/check_openapi.py
```

OpenAPI check phải không có drift với `docs/openapi.json`. Khi route/schema được đổi có chủ đích:

```powershell
python scripts/check_openapi.py --write
python scripts/check_openapi.py
```

Review diff của `docs/openapi.json`; không cập nhật file chỉ để làm CI xanh nếu contract thay đổi ngoài ý muốn.

## PostgreSQL và migration

Khởi động database test riêng:

```powershell
docker compose --profile test up -d --wait postgres-test
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/label_guardian_test"
python scripts/check_migrations.py
```

Migration lifecycle kiểm tra upgrade head, current head, downgrade và upgrade lại. Migration destructive cần backup/restore plan riêng trước production.

## Backend tests

```powershell
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:LABEL_GUARDIAN_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/label_guardian_test"
python -m pytest tests/ -v --tb=short
```

Các nhóm contract quan trọng:

| Nhóm | Hành vi cần bảo vệ |
| --- | --- |
| Auth/RBAC | JWT verify, profile bootstrap, disabled user, role permission, actor từ token |
| Dataset | Database/filesystem adapter, pagination/filter, private image/point-cloud streaming |
| Agent | Matching, metrics, deterministic issue taxonomy, LLM fallback và report |
| QA cases | Persist, filter, transition, conflict và audit |
| Annotation | Revision 0, Save, stale 409, history, restore và effective labels |
| Ingestion | Claim/lease, retry, stale recovery, adapter, GCS artifact và pipeline status |
| API contract | OpenAPI không drift và production settings fail closed |

## Frontend tests

```powershell
cd frontend
npm run typecheck
npm test
npm run build
```

Frontend tests hiện là Node source-contract/domain tests, không thay thế browser E2E. Khi chỉ sửa một phạm vi có thể chạy file cụ thể, nhưng trước merge vẫn chạy toàn bộ suite:

```powershell
node --experimental-strip-types --test test/routing.test.ts
```

Production build cần được kiểm tra với các mode thực tế. Không dùng secret thật trong lệnh kiểm tra:

```powershell
$env:VITE_AUTH_MODE = "supabase"
$env:VITE_DATA_SOURCE = "api"
$env:VITE_SUPABASE_URL = "https://example.supabase.co"
$env:VITE_SUPABASE_ANON_KEY = "build-verification-placeholder"
npm run build
```

## Browser smoke checklist

1. `/` tải landing page và chuyển EN/VI.
2. Supabase login/register hiển thị đúng shared visual panel và không có console/CSP error.
3. Đăng nhập xong mở `/overview`, refresh deep link không trả 404.
4. QA Queue lọc dataset/sequence và mở đúng frame.
5. Run Agent, persist case và thấy QA Cases cập nhật.
6. Mở Editor, tạo/move/resize/delete box, đổi class/track/attributes.
7. Save, Save & Next, reload, history và Restore hoạt động.
8. Hai tab cùng ảnh: tab lưu sau nhận revision conflict 409.
9. Annotator không chạy Agent/cập nhật decision; Reviewer không quản lý role; Admin có đủ quyền.
10. Private image request có bearer token và không lộ GCS credential.

## Deployment smoke

```powershell
curl.exe -I https://labelguardian.space
curl.exe -f https://api.labelguardian.space/health
curl.exe -f https://api.labelguardian.space/ready
curl.exe -f https://api.labelguardian.space/api/v1/health
```

Dataset/auth endpoint cần bearer token nên kiểm tra qua UI đã đăng nhập hoặc client bảo mật. Không ghi token vào shell history, log CI hoặc tài liệu.

## CI

`.github/workflows/ci.yml` chạy trên self-hosted Linux runner cho push/PR vào `main` và `develop`:

- backend lint, mypy, OpenAPI, migration lifecycle và pytest coverage;
- frontend test, typecheck và Vite build;
- backend Docker build và runtime dependency smoke.

Không ghi số lượng test cố định trong tài liệu. Số liệu đúng là output CI của commit đang review.
