# Kiến trúc Label Guardian

## Quyền sở hữu dữ liệu

2D Editor tích hợp là công cụ chỉnh sửa annotation chính. Dataset gốc là revision 0; mỗi lần Save hoặc Restore tạo một revision bất biến mới trong `annotation_revisions`. QA Agent, dataset browser và QA Queue luôn đọc revision mới nhất.

```text
Dataset source
  ├─ ingestion → qa_images / qa_objects (revision 0)
  ├─ QA Agent → qa_evaluations → qa_cases
  └─ 2D Editor → annotation_revisions → effective labels
                                  ├─ re-evaluation
                                  ├─ QA evidence refresh
                                  └─ audit/history/restore
```

## Backend

- FastAPI cung cấp dataset, editor, evaluation và QA case APIs.
- PostgreSQL giữ dữ liệu ingest, evaluation, case, audit và annotation revision.
- `AnnotationEditorService` validate bbox, object ID và giới hạn ảnh; lưu full snapshot để đọc/restore đơn giản.
- Client gửi `expectedRevision`; revision cũ trả HTTP 409 để tránh ghi đè thay đổi của người khác.
- Save cập nhật evidence của case cùng dataset/version/split/image và chuyển case sang `corrected`.

## Xác thực và phân quyền

```text
Browser → Supabase Auth (login/refresh) → access token
       → FastAPI (verify issuer/audience/signature/expiry)
       → application_users (role + disabled)
       → endpoint permission → PostgreSQL/GCS/Agent
```

- Supabase Auth sở hữu email, mật khẩu và session; ứng dụng không lưu password hash.
- FastAPI xác minh JWT bằng public JWKS (ES256/RS256), hoặc secret server-side cho project HS256 cũ.
- `application_users.id` trùng claim `sub`; user mới mặc định `annotator`.
- Role không lấy từ body, localStorage hay metadata người dùng tự sửa. `actor_id` trong audit luôn lấy từ access token.
- Mọi dataset/case/content endpoint cần đăng nhập. Chạy Agent và quyết định case cần Reviewer/Admin; sửa revision cần Annotator/Reviewer/Admin; quản lý role cần Admin.
- Ảnh GCS private vẫn đi qua FastAPI và request ảnh từ frontend cũng kèm bearer token.

## Frontend

Route `/editor?split=...&imageId=...` mở đúng ảnh từ QA Queue. Editor gồm canvas SVG, object list, properties, toolbar, validation, history và frame strip. Tọa độ lưu dạng pixel `xyxy`; thao tác UI dùng `xywh` và chuyển đổi tại ranh giới API.

## Bảo toàn dữ liệu

- Revision 0 không bị sửa.
- Restore tạo revision mới, không xóa lịch sử.
- Optimistic locking phát hiện stale editor tab.
- Audit ghi actor, note, before/after revision và case status.
- Migration mới xóa schema tích hợp editor ngoài cũ và các case chỉ tồn tại ở nguồn đó; cần backup trước khi migrate production.
