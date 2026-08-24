# Kiểm thử

## Backend

Cài dependency và cấu hình một PostgreSQL test riêng:

```powershell
python -m pip install -e ".[dev]"
python -m ruff check src tests migrations
python -m pytest -q
python -m scripts.check_migrations
python -m scripts.check_openapi
```

Các contract quan trọng:

- document ban đầu là revision 0;
- Save tạo revision 1 và dataset list trả nhãn mới;
- save bằng expected revision cũ trả 409;
- history trả actor/note/count;
- restore revision 0 tạo revision tiếp theo;
- QA status transition ghi audit;
- OpenAPI không chứa route editor ngoài.

Cloud ingestion worker:

```powershell
python -m pytest -q tests/test_data/test_cloud_worker.py
```

Nhóm test này kiểm tra claim run, retry, stale-run recovery và cập nhật tiến độ pipeline.

## Frontend

```powershell
cd frontend
npm ci
npm run typecheck
npm test -- --run
npm run build
```

Kiểm tra thủ công: mở case từ QA Queue, tạo/move/resize/delete box, đổi class/track/attributes, undo/redo, Save, Save & Next, reload, xem history và restore. Mở hai tab cùng ảnh để xác nhận tab lưu sau nhận conflict 409.
