# Trạng thái dự án

## Đã hoàn thành

- Dataset browser và frame samples qua FastAPI.
- QA Agent evaluation, cache và persistence QA cases.
- QA Queue API/mock với viewer GT/prediction.
- 2D Editor tích hợp làm công cụ chỉnh sửa chính.
- Bounding box CRUD, class, track ID, attributes, visibility, pan/zoom, undo/redo và phím tắt.
- Save & Next, validation, unsaved-change guard.
- Annotation revision, optimistic locking, history, restore và audit.
- Effective-label overlay cho dataset list/detail và lần đánh giá Agent tiếp theo.
- Đã loại bỏ runtime, API, schema, cấu hình, script và UI tích hợp editor ngoài.

## Tiếp theo

- Polygon/polyline và video interpolation nếu scope dataset yêu cầu.
- Assignment/locking theo người dùng ở mức frame.
- Export revision sang định dạng huấn luyện và tạo dataset version phát hành.
- E2E browser test cho gesture trên canvas.
