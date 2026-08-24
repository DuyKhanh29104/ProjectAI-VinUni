# Frontend UI

## Điều hướng

- `/overview`: tổng quan QA.
- `/qa-queue`: hàng đợi case và viewer so sánh.
- `/editor?split={split}&imageId={id}`: công cụ chỉnh sửa nhãn chính.
- `/reports`, `/datasets`, `/settings`: màn hỗ trợ.

## 2D Editor

Editor dùng canvas SVG và server state từ TanStack Query. Người dùng có thể tạo/chọn/move/resize/delete bounding box, đổi label, track ID, màu và attributes; pan/zoom, visibility, undo/redo và phím tắt. Validation chặn box ngoài ảnh hoặc quá nhỏ. Save gửi `expectedRevision`; lỗi 409 yêu cầu reload trước khi ghi tiếp.

History hiển thị actor, note và label count. Restore không ghi đè lịch sử mà tạo revision mới. Save & Next lưu rồi chuyển frame. Khi có thay đổi chưa lưu, editor cảnh báo trước khi đổi frame, thoát hoặc đóng tab.

QA Queue mở editor bằng source split/image ID của case; không sao chép ảnh sang hệ thống khác.
