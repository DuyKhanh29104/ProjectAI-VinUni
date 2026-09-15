# Security Policy

> Cập nhật: 2026-08-27

## Supported code

Nhánh/release đang phục vụ production và commit mới nhất trên `main` là phạm vi được ưu tiên sửa lỗi bảo mật. Các branch thử nghiệm hoặc commit cũ không có cam kết backport; maintainer sẽ quyết định theo mức độ ảnh hưởng.

## Báo cáo lỗ hổng

Không mở public issue nếu báo cáo chứa exploit, credential, dữ liệu người dùng hoặc chi tiết đủ để tấn công production.

Ưu tiên theo thứ tự:

1. GitHub Private Vulnerability Reporting/Security Advisory của repository, nếu được bật.
2. Kênh riêng đã được nhóm dự án công bố cho thành viên/maintainer.
3. Liên hệ trực tiếp maintainer repository và chỉ gửi metadata tối thiểu trước khi thống nhất kênh chuyển bằng chứng.

Báo cáo nên có:

- thành phần và commit/version bị ảnh hưởng;
- điều kiện tái hiện và tác động;
- request/response đã loại token, cookie, PII và secret;
- proof of concept an toàn, không phá dữ liệu;
- đề xuất giảm thiểu nếu có.

Không kiểm thử trên tài khoản/dataset không được cấp quyền, không làm gián đoạn service và không tải xuống dữ liệu ngoài phạm vi cần chứng minh.

## Secret handling

- Secret backend chỉ nằm trong local secret store, Vercel environment phù hợp hoặc `/opt/label-guardian/.env.production` trên VM.
- `VITE_*` được compile vào browser và chỉ được chứa giá trị public; không đặt database password, JWT secret, GCS private key hoặc LLM key ở đó.
- Ưu tiên GCP Application Default Credentials/Workload Identity; service-account JSON phải nằm ngoài Git và được rotate theo policy.
- Không đưa access token, signed URL, cookie, `.env`, database dump hoặc raw incident log vào commit/chat/issue.
- Sample config chỉ dùng placeholder rõ ràng.

Nếu secret bị lộ:

1. Thu hồi/rotate credential ngay, không chờ xóa khỏi Git.
2. Xác định phạm vi log, artifact, cache và deployment đã nhận secret.
3. Xóa khỏi source/history theo quy trình được maintainer phê duyệt.
4. Redeploy/restart thành phần dùng credential mới.
5. Ghi incident timeline và biện pháp ngăn tái diễn qua kênh riêng.

## Security boundaries

- Supabase Auth sở hữu identity/password/session; FastAPI xác minh token và sở hữu authorization nghiệp vụ.
- `application_users` là nguồn role/disabled; frontend/localStorage không phải security boundary.
- Backend lấy actor từ access token và kiểm tra role ở endpoint write.
- PostgreSQL/GCS không được frontend truy cập bằng privileged credential.
- Private image/point-cloud content được stream qua authenticated FastAPI.
- Annotation write dùng immutable revision và optimistic locking để tránh silent overwrite.
- Production settings phải fail fast khi auth tắt, CORS không an toàn hoặc database còn trỏ localhost.

## Data handling

- Chỉ ingest dataset có quyền sử dụng và tuân theo điều khoản của provider.
- Không đưa raw dataset, ảnh nhạy cảm hoặc PII vào Git, public bucket, prompt LLM hoặc log không kiểm soát.
- LLM chỉ nhận evidence tối thiểu cần thiết; không gửi credential hoặc raw private asset nếu không có phê duyệt rõ ràng.
- Database backup, GCS versioning và restore drill phải được kiểm tra định kỳ trước thay đổi destructive.

## Dependency và supply chain

- Dependency Python/Node phải được pin bằng constraint/lockfile đang dùng và review khi nâng version lớn.
- CI phải chạy lint, typecheck, tests, migration/OpenAPI checks và Docker build trước release.
- Không dùng package/image không rõ nguồn; production base image và GitHub Action phải được version hóa.
- Lỗ hổng dependency phải được đánh giá theo khả năng reachability trong runtime, không chỉ dựa trên severity scanner.

## Production response baseline

Khi nghi ngờ compromise:

1. Hạn chế thay đổi phá hủy; chụp health/status/log metadata cần thiết.
2. Cô lập credential hoặc service bị ảnh hưởng.
3. Bảo toàn audit/database/GCS evidence theo quyền truy cập cho phép.
4. Rollback application bằng stable image nếu an toàn; không tự động downgrade database.
5. Rotate secret và xác minh Supabase, GCS, VM, Vercel cùng GitHub runner.
6. Chạy health/auth/private-asset smoke trước khi mở lại traffic đầy đủ.

Runbook vận hành nằm trong [`docs/VM_REMOTE_DEV_GUIDE.md`](docs/VM_REMOTE_DEV_GUIDE.md) và [`docs/HYBRID_VERCEL_VM_DEPLOYMENT.md`](docs/HYBRID_VERCEL_VM_DEPLOYMENT.md).
