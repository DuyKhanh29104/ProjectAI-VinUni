# Contributing to Label Guardian

> Cập nhật: 2026-08-27

Tài liệu này là nguồn chuẩn cho workflow đóng góp và coding convention. Setup chi tiết nằm trong [`README.md`](README.md), [`docs/SUPABASE_DEVELOPMENT.md`](docs/SUPABASE_DEVELOPMENT.md) và [`docs/TESTING.md`](docs/TESTING.md).

## 1. Trước khi thay đổi

```powershell
git remote -v
git branch --show-current
git status --short
git fetch --all --prune
```

- Xác nhận đúng repository/remote: repo phát triển và repo deploy không có cùng mục đích.
- Không ghi đè hoặc gom chung các thay đổi chưa commit của người khác.
- Mỗi branch/commit chỉ giải quyết một phạm vi có thể review độc lập.
- Ưu tiên feature/fix branch và Pull Request theo branch protection của repository.
- Không force-push shared branch hoặc sửa lịch sử release đã được dùng để deploy.

## 2. Setup development

Backend:

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[agent-yolo,ingestion]" --group dev
Copy-Item .env.example .env
```

Frontend:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
```

Không dùng database production/Supabase dùng chung để chạy pytest hoặc migration lifecycle. Xem [`docs/TESTING.md`](docs/TESTING.md).

## 3. Coding convention — Python

Repository dùng Python 3.12, Ruff và mypy.

- Tuân theo cấu hình trong `pyproject.toml`; line length là 120.
- Dùng type annotation cho public function/method; không thêm `Any` để né typecheck nếu có thể mô hình hóa type rõ ràng.
- Route FastAPI chỉ parse/authorize/map lỗi; nghiệp vụ đặt trong service và persistence đặt trong repository/model boundary phù hợp.
- Dùng dependency injection cho session, settings, auth verifier và external service để test không cần network thật.
- Dùng async cho FastAPI/SQLAlchemy I/O; không gọi blocking GCS/model work trực tiếp trên event loop.
- Pydantic schema là API boundary; không trả thẳng ORM object hoặc raw upstream payload.
- Không log token, signed URL, credential, raw secret hoặc dữ liệu người dùng không cần thiết.
- Lỗi domain phải được map sang HTTP status ổn định; không trả stack trace/raw provider body cho client.
- Import được Ruff sắp xếp; tên module/function dùng `snake_case`, class dùng `PascalCase`, constant dùng `UPPER_SNAKE_CASE`.

Quality commands:

```powershell
python -m ruff check src tests migrations scripts/check_migrations.py scripts/check_openapi.py
python -m mypy src
```

## 4. Coding convention — TypeScript/React

- Giữ TypeScript strict; không dùng `any` hoặc non-null assertion để che lỗi dữ liệu nếu có thể validate/narrow.
- Component dùng function + hooks; hook phải ở top level và dependency list phải đầy đủ.
- Server state đi qua `frontend/src/api/` và TanStack Query; không gọi `fetch` rải rác trong view.
- Auth session đi qua `frontend/src/auth/`; role hiển thị phải lấy từ `/api/v1/auth/me`, không tin localStorage/user metadata.
- Domain logic tái sử dụng đặt trong `domain/`, state/repository hoặc feature module, không nhúng vào presentational component.
- Component shared dùng `PascalCase`; hook dùng tiền tố `use`; variable/function dùng `camelCase`.
- Ưu tiên CSS class và semantic token trong `styles/`; không lặp inline style cho UI có thể tái sử dụng.
- Shared visual giữa mock/API hoặc local/production phải dùng cùng component để tránh markup/CSS drift.
- Interactive element phải semantic, có accessible name và keyboard behavior phù hợp.

Quality commands:

```powershell
cd frontend
npm run typecheck
npm test
npm run build
```

## 5. Database và API contract

- Mọi schema change phải có Alembic migration; không sửa production schema bằng dashboard/manual SQL rồi bỏ qua migration.
- Migration production phải theo expand/contract khi cần rollback app; destructive migration cần backup/restore plan.
- Route/schema change phải cập nhật OpenAPI snapshot có chủ đích:

```powershell
python scripts/check_openapi.py --write
python scripts/check_openapi.py
```

- Review diff `docs/openapi.json`; không regenerate chỉ để che thay đổi ngoài phạm vi.
- API write phải xác thực actor từ token, kiểm tra role và xử lý conflict/idempotency phù hợp.

## 6. Tests

Mỗi thay đổi cần test ở tầng thấp nhất có thể bắt regression:

- Service/domain rule: unit test.
- Database/revision/auth/API: integration test với PostgreSQL test riêng.
- Frontend routing/domain/source contract: Node test.
- Layout, gesture, auth redirect hoặc flow end-to-end: browser smoke/E2E khi có tooling.
- Bug fix: thêm test thất bại trước bản sửa nếu hợp lý.

Không ghi số lượng test cố định trong PR hoặc docs; ghi lệnh và kết quả thực tế của commit.

## 7. Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) là nguồn chuẩn kiến trúc tổng thể.
- [`docs/README.md`](docs/README.md) là mục lục và ownership map.
- Không tạo thêm API reference thủ công; dùng `docs/openapi.json` và FastAPI `/docs`.
- Không tạo thêm deployment overview; production dùng [`docs/HYBRID_VERCEL_VM_DEPLOYMENT.md`](docs/HYBRID_VERCEL_VM_DEPLOYMENT.md).
- Ghi rõ **hiện tại** và **roadmap**; không mô tả ý tưởng như tính năng đã triển khai.
- Khi xóa/gộp tài liệu, cập nhật toàn bộ relative link trong cùng commit.

## 8. Commit và Pull Request

Commit message khuyến nghị:

```text
feat(scope): mô tả ngắn
fix(scope): mô tả ngắn
docs(scope): mô tả ngắn
test(scope): mô tả ngắn
chore(scope): mô tả ngắn
```

PR cần nêu:

- vấn đề và phạm vi;
- quyết định/trade-off quan trọng;
- migration/config/deployment impact;
- lệnh test đã chạy và kết quả;
- ảnh/video cho thay đổi UI khi cần;
- việc còn lại hoặc giới hạn đã biết.

Trước handoff:

```powershell
git status --short
git diff --check
git diff --stat
```

## 9. Không được commit

- `.env`, `.env.production`, token, cookie, signed URL hoặc password.
- GCP service-account JSON, Supabase JWT/database credential hoặc OpenAI key.
- Dataset/raw archive, database dump, runtime cache hoặc model artifact lớn ngoài policy đã thống nhất.
- `node_modules`, virtualenv, build output, coverage hoặc IDE state.

Xem [`SECURITY.md`](SECURITY.md) khi phát hiện secret leak hoặc lỗ hổng.
