# Tài liệu Label Guardian

> Cập nhật: 2026-08-27

Trang này là mục lục tài liệu. Không lặp lại cùng một contract ở nhiều file; khi có mâu thuẫn, ưu tiên migration, OpenAPI và source code như quy định trong [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Bắt đầu

| Tài liệu | Mục đích |
| --- | --- |
| [`README.md`](../README.md) | Cài đặt, chạy local, API và kiểm thử nhanh |
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | Kiến trúc tổng thể đang chạy và các quyết định chính |
| [`architecture_diagram.md`](architecture_diagram.md) | Sơ đồ Mermaid rút gọn của topology và revision flow |
| [`PRODUCT.md`](../PRODUCT.md) | Product contract ngắn gọn dùng bởi repository tooling |
| [`PRODUCT_DESCRIPTION.md`](PRODUCT_DESCRIPTION.md) | Bài toán, giá trị sản phẩm và phạm vi |
| [`PROJECT_STATUS.md`](PROJECT_STATUS.md) | Tính năng đã có, giới hạn và việc tiếp theo |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | Workflow đóng góp, coding convention và quality gate |
| [`SECURITY.md`](../SECURITY.md) | Báo cáo lỗ hổng, secret handling và incident baseline |
| [`DESIGN.md`](../DESIGN.md) | Design tokens, component language và quy tắc UI |

## Phát triển

| Tài liệu | Phạm vi |
| --- | --- |
| [`FRONTEND_UI.md`](FRONTEND_UI.md) | Routes, data/auth modes và hành vi 2D Editor |
| [`label_qa_agent.md`](label_qa_agent.md) | Cách chạy và contract của Label QA Agent |
| [`label_qa_issue_types.md`](label_qa_issue_types.md) | Taxonomy issue và evidence |
| [`TESTING.md`](TESTING.md) | Test matrix, lệnh local và release gate |
| [`SUPABASE_DEVELOPMENT.md`](SUPABASE_DEVELOPMENT.md) | Supabase Auth/PostgreSQL trong development |
| [`GOLDEN_DATASET.md`](GOLDEN_DATASET.md) | Dataset, GCS layout và provenance |
| [`VIN_SLAVE_INTEGRATION.md`](VIN_SLAVE_INTEGRATION.md) | Nguồn commit, quyết định giữ/bỏ và kiểm tra tích hợp |

## Ingestion và hạ tầng

| Tài liệu | Phạm vi |
| --- | --- |
| [`HYBRID_VERCEL_VM_DEPLOYMENT.md`](HYBRID_VERCEL_VM_DEPLOYMENT.md) | Runbook production Vercel frontend + VM backend |
| [`SELF_HOSTED_DEPLOYMENT.md`](SELF_HOSTED_DEPLOYMENT.md) | Backend self-host/private staging bằng Compose |
| [`VM_REMOTE_DEV_GUIDE.md`](VM_REMOTE_DEV_GUIDE.md) | SSH, log và vận hành VM; không phải kiến trúc nguồn chuẩn |
| [`official_cloud_ingestion_automation.md`](official_cloud_ingestion_automation.md) | Thiết kế automation cho official datasets |
| [`../deploy/gcp/README.md`](../deploy/gcp/README.md) | Build và chạy GCP Batch ingestion worker |
| [`INFERENCE_SERVICE.md`](INFERENCE_SERVICE.md) | Cấu hình detector riêng và batch QA |

## Quy tắc duy trì

- Không ghi số lượng test cố định; dùng output CI của commit đang xét.
- Endpoint phải khớp `docs/openapi.json`; chạy `python scripts/check_openapi.py` sau khi đổi route/schema.
- Schema phải khớp migration head; không mô tả bảng đã bị migration xóa.
- Production topology phải khớp `frontend/vercel.json`, `docker-compose.selfhost.yml` và `.github/workflows/deploy-selfhost.yml`.
- Secret thật, token, database URL và service-account JSON không được đưa vào tài liệu.
- Nội dung roadmap phải có nhãn **chưa triển khai** hoặc **tương lai**.

## Tài liệu không duy trì riêng

Để tránh trùng lặp, không tạo lại các file sau nếu chưa có thay đổi kiến trúc rõ ràng:

- API reference viết tay: dùng `docs/openapi.json` và FastAPI `/docs`.
- Architecture deep-dive riêng cho auth/revision: nội dung đã gộp vào `ARCHITECTURE.md`.
- Deployment overview riêng: production runbook là `HYBRID_VERCEL_VM_DEPLOYMENT.md`; self-host và VM operations chỉ chứa thao tác chuyên biệt.
- Hướng dẫn cloud tổng hợp một file: Supabase, golden dataset và ingestion đã có owner document riêng.
- `CHANGELOG.md`: chỉ bổ sung khi dự án bắt đầu phát hành tag/version chính thức; hiện dùng Git history và `PROJECT_STATUS.md`.
