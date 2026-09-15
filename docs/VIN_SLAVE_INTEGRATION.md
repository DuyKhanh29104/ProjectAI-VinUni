# Đồng bộ Vin-slave — 2026-09-14

Nguồn: `Kyanlulw/Vin-slave`, nhánh `main`, commit `b56b6f912b1497f1bfd36e7d55f5e40e9f48af7c`.
Local trước khi gộp: `0038da0d`, nhánh `feature/demo-onboarding-data-performance`.

Hai repo có lịch sử độc lập vì Vin-slave bắt đầu từ một deploy mirror. Việc gộp
dùng snapshot `37ea50fa` để so sánh thay đổi ba phía; commit này tương ứng đợt
polish editor `15b150f7` bên local, nhưng vẫn có khác biệt về cấu hình và tài liệu.
Các khác biệt đó được review riêng. Merge commit giữ cả hai lịch sử, không viết
lại commit cũ. Backup local: `backup/pre-vin-slave-20260914`.

## Giữ và tích hợp

- Giao diện, dashboard, workflow mock, demo login và onboarding theo role từ local.
- Truy vấn sequence riêng, phân trang, escape LIKE, batch revision lookup,
  cache ảnh có giới hạn, ghi cache nguyên tử và giới hạn số lock từ local.
- Inference service tùy chọn và batch detection từ Vin-slave; giữ local inference
  mặc định để cấu hình triển khai hiện tại tiếp tục hoạt động.
- Lưu đầy đủ report/predictions và đọc lại theo ảnh; dùng TanStack Query để quản lý
  kết quả từng ảnh, tránh một bản cache state trùng lặp trong view.
- Evidence gates hạn chế cảnh báo khi detector thiếu bằng chứng; giữ agent graph,
  provider OpenAI/Google, fallback và RT-DETR tùy chọn của local.
- Chuẩn hóa class để hiển thị, đồng thời giữ nguyên và hiển thị nhãn gốc kể cả
  khi detector không hỗ trợ class đó.
- Incremental ingestion bỏ qua frame/sample đã có; buffered GCS range reader.
- Bộ công cụ golden nuImages và tests; CI chạy thêm `scripts/tests`.
- Cloud Build dùng `$PROJECT_ID` của môi trường thay vì project cố định.

## Không đưa vào bản gộp

- API/UI Admin Control Plane và customer upload chưa hoàn chỉnh: có nhánh bỏ qua
  lỗi xác minh GCS nhưng vẫn đánh dấu uploaded; quyền chuyển trạng thái và quyền
  đọc/cập nhật dataset, case chưa thống nhất. Không mở các route này.
- Script vá/debug dùng một lần (`patch_p2.py`, `query_test*.py`, `scratch/*`),
  batch submitter gắn cứng project và cấu hình triển khai riêng của tác giả.
- Tài liệu boilerplate, thiết kế/thử nghiệm cũ và fixture đã bị local loại bỏ.
- Thay đổi làm lùi giao diện local, bỏ endpoint sequence, giới hạn danh sách
  sequence bằng cách tải 200 frame, hoặc thay lỗi database bằng response rỗng 200.
- Thay toàn bộ release/cache path hiện có bằng `product`. Chỉ hỗ trợ layout
  upstream khi cấu hình rõ `dataset_version/release=product`.

Schema/model và migration 0007 vẫn được giữ để nối tiếp 0008 mà không sửa lịch sử
migration đã dùng trên upstream. Các bảng này không có API hoạt động trong bản
gộp; migration 0009 bật RLS và thu hồi quyền Data API cho chúng.

## Sửa lỗi khi tích hợp

- Unique identity của evaluation bao gồm annotation revision; không xung đột khi
  evaluate sau Save/Restore và không ghép report cũ với nhãn mới.
- Kết quả cũ chỉ được trả khi ID deterministic khớp revision. Các bản ghi cũ không
  xác định được revision cần chạy đánh giá lại.
- Batch trả kết quả đúng thứ tự, nhận diện ảnh bị bỏ sót, rollback transaction lỗi
  trước khi xử lý ảnh tiếp theo và không trả nội dung lỗi provider/database thô.
- Remote inference dùng kích thước ảnh để clip/lọc nhãn giống local inference.
- Standalone inference bắt buộc token ở production, xử lý blocking work ngoài
  event loop và tuần tự hóa truy cập model dùng chung.
- Test không nạp `.env` phát triển vào process; database test phải được truyền rõ
  qua `TEST_DATABASE_URL` và vẫn chịu các kiểm tra an toàn hiện có.

## Xác minh

Chạy Ruff, mypy, OpenAPI snapshot, Alembic upgrade/check/downgrade/upgrade trên
PostgreSQL test riêng, `pytest tests scripts/tests`, frontend tests và production
build. Tests inference dùng detector/GCS giả lập; không dùng GPU hoặc GCS thật.

Trước khi chạy bản này với database ứng dụng, chạy `alembic upgrade head`.
Downgrade về unique constraint cũ sẽ bị từ chối nếu đã có nhiều evaluation
revision cho cùng ảnh/model; migration không tự xóa dữ liệu để ép downgrade.
