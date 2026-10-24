# Đánh giá và chọn lọc ba phiên bản — 2026-10-24

## Phạm vi và nguồn

Đánh giá source code, lịch sử Git và tests trên nhánh mặc định `main` sau khi fetch cả ba remote:

| Repo | Commit được kiểm tra |
| --- | --- |
| [8uandj/Label_guardian](https://github.com/8uandj/Label_guardian) | `2e9523c57adbfeaf7d0c7bbede0126db81ad5496` |
| [Kyanlulw/Vin-slave](https://github.com/Kyanlulw/Vin-slave) | `b56b6f912b1497f1bfd36e7d55f5e40e9f48af7c` |
| [DuyKhanh29104/ProjectAI-VinUni](https://github.com/DuyKhanh29104/ProjectAI-VinUni) | `ff1d54ae95103fdc3800339c9a9a2bfff9971b61` trước đợt sửa này |

Repo đích đã nhận snapshot của integration commit `7bad1c41` từ ngày 2026-09-15.
`git diff projectai/main 7bad1c41` không có khác biệt. Cả hai commit nguồn đều là
ancestor của `7bad1c41`. Vì repo đích được publish bằng snapshot, chỉ đếm commit
chưa có trong lịch sử repo đích sẽ dẫn tới kết luận sai rằng toàn bộ upstream chưa được tích hợp.
Đợt này giữ repo đích làm nền, chọn lại phần còn thiếu và sửa lỗi ở ranh giới tích hợp.

## Đánh giá từng phiên bản

| Phiên bản | Điểm mạnh có trong mã nguồn | Hạn chế và quyết định |
| --- | --- | --- |
| Label_guardian | Tách inference service; incremental ingestion; phân trang và batch revision lookup; cache ảnh; demo login/onboarding; giải thích lỗi kèm vật thể và vị trí | Những phần nền đã có trong repo đích. Bổ sung lại giải thích có vị trí từ `src/agents/nodes/llm_explain.py`, với diễn giải thận trọng hơn. Không nhập toàn bộ Admin Control Plane. |
| Vin-slave | Batch detection thực; lưu và hydrate report/predictions; evidence gates theo confidence, nhóm class và diện tích vật thể; golden nuImages evaluation harness | Giữ các phần đã tích hợp. Không thay cơ chế revision của repo đích bằng bản upstream; không coi các ngưỡng heuristic là bằng chứng chất lượng tổng quát trên mọi dataset. |
| ProjectAI-VinUni | Có các cải tiến trên cùng editor/history/restore, optimistic locking, RBAC; evaluation gắn annotation revision; sequence endpoint riêng; cache có giới hạn; inference local hoặc remote; tùy chọn RT-DETR và nhiều LLM provider | Là nền phù hợp nhất để tiếp tục. Còn thiếu giải thích vị trí của upstream; batch response chưa đối chiếu đầy đủ danh tính ảnh và lỗi inference có thể trả nội dung thô. Sửa các điểm này trong đợt hiện tại. |

Các lựa chọn tích hợp trước đây và tác động migration được ghi tại
[VIN_SLAVE_INTEGRATION.md](VIN_SLAVE_INTEGRATION.md). Đánh giá này dựa trên tính đúng đắn,
khả năng duy trì, contract và tests; không phải benchmark tốc độ hoặc độ chính xác detector.

## Phần áp dụng trong đợt này

### Giải thích QA có vị trí

Adapt từ Label_guardian: lấy loại đối tượng và bounding box từ evidence hoặc nhãn gốc,
tính khu vực trái/phải/trên/dưới khi biết kích thước ảnh, đưa cùng context cho LLM
và nhánh fallback khi offline hoặc LLM bỏ sót issue. Giữ nguyên loại lỗi, severity,
blocking và evidence đã được rule quyết định; giữ provider abstraction hiện có.

Điều chỉnh lời giải thích upstream: độ chồng khung thấp không chứng minh phần còn lại
là nền, không tự chứng minh phải thu nhỏ khung; điểm confidence không phải xác suất
hiệu chuẩn rằng vật thể thật sự tồn tại. Detector không thấy cũng có thể là bỏ sót.
Khi không biết kích thước ảnh, chỉ hiển thị tọa độ, không đoán vị trí tương đối.

### Kiểm tra kết quả batch inference

`RemoteInferenceClient` đối chiếu tập kết quả với yêu cầu bằng toàn bộ tuple
`dataset_id, dataset_version, split, image_id, bucket, object_key`, bao gồm số lần
xuất hiện. Chấp nhận thứ tự khác nhưng từ chối kết quả thiếu, thừa, trùng hoặc sai
release/ảnh. Trường content type không tham gia định danh vì là metadata tùy chọn.

Response không khớp làm thất bại chunk tương ứng, không lưu prediction vào ảnh sai;
các chunk khác vẫn được xử lý. Response hợp lệ có lỗi riêng từng ảnh vẫn giữ luồng
thành công một phần. Endpoint batch trả thông báo lỗi ổn định thay cho exception hoặc
chuỗi lỗi thô do inference service cung cấp. Không đổi schema API hay database.

## Phần chưa chọn

- **Admin Control Plane / customer upload**: `complete_upload` ở upstream vẫn bắt lỗi
  GCS bằng `except Exception: pass` rồi đánh dấu `uploaded`. `transition_task` kiểm tra
  người được giao việc, nhưng chỉ khóa riêng bước `approved` theo role, chưa có ma trận
  quyền đầy đủ cho các bước review. Không bật các route/UI này trong repo đích.
- **Thay toàn bộ cấu hình bằng `product` hoặc hạ cấp UI**: giữ release cấu hình được,
  sequence endpoint và editor hiện tại; tránh làm mất các cải tiến đã kiểm thử.
- **Script debug, project cloud gắn cứng, tài liệu boilerplate**: không phục vụ runtime
  và không nhập lại vào repo đích.
- **Chỉnh evidence thresholds thêm**: chưa có benchmark mới trên dữ liệu thật để
  biện minh thay đổi; giữ các ngưỡng Vin-slave đã tích hợp.

## Xác minh và giới hạn

Các lệnh kiểm tra của đợt này:

```text
python -m ruff check src tests migrations scripts/check_migrations.py scripts/check_openapi.py
python -m mypy src
python scripts/check_openapi.py
python scripts/check_migrations.py
python -m pytest tests scripts/tests -q --tb=short
cd frontend
npm run typecheck
npm test
npm run build
```

PostgreSQL 16 chạy trong container test riêng, database kết thúc bằng `_test`;
đã kiểm tra upgrade/check/downgrade/upgrade, không sử dụng database ứng dụng.
Tests mới bảo vệ identity batch, lỗi upstream, vị trí vật thể, fallback và tính bất biến
của rule QA. Frontend không thay đổi trong đợt này.

Inference/GCS/LLM dùng test doubles trong các kiểm thử liên quan. Không chạy benchmark
GPU, golden dataset đầy đủ hoặc browser E2E với Supabase/GCS production. Push source
không đồng nghĩa deployment production đã thành công; các workflow self-hosted còn
phụ thuộc runner và cấu hình hạ tầng của repo đích.
