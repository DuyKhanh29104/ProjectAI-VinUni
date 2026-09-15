# Frontend UI

> Cập nhật: 2026-08-27

## Công nghệ và mode

Frontend dùng React 19, TypeScript, Vite, React Router và TanStack Query.

| Biến | Production | Local/demo |
| --- | --- | --- |
| `VITE_DATA_SOURCE` | `api` | `mock` hoặc `api` |
| `VITE_AUTH_MODE` | `supabase` | `mock` hoặc `supabase` |

Production fail-closed về API và Supabase khi biến build bị thiếu. Mock state chỉ dùng cho demo, lưu trong `localStorage` và không phải security boundary.

## Điều hướng

| Route | Màn hình |
| --- | --- |
| `/` | Landing page công khai |
| `/overview` | KPI, work batch và health của QA workflow |
| `/qa-queue` | Work Queue: dataset/frame selection và Agent evaluation |
| `/qa-cases` | QA Cases registry: finding, filter và review action |
| `/cases/:findingId` | Mock case detail; API mode dùng registry/editor |
| `/editor?split={split}&imageId={id}` | 2D Editor |
| `/reports` | QA metrics và report view |
| `/dataset-runs` | Dataset/version/coverage |
| `/pipeline` | Cloud ingestion runs và logs |
| `/settings` | Profile, role administration và demo config |

`/real-data` là compatibility redirect sang QA Queue. Mọi deep link production phải được Vercel rewrite về `index.html`.

## Authentication shell

- `VITE_AUTH_MODE=supabase` render `AuthenticatedLoginScreen` và dùng Supabase session.
- `VITE_AUTH_MODE=mock` render `MockLoginScreen`.
- Hai màn dùng chung `LoginVisualPanel` để tránh local/deploy khác markup và CSS.
- Sau đăng nhập, frontend gọi `/api/v1/auth/me`; role từ backend quyết định route/navigation.
- Mọi JSON request và private image blob request đều kèm bearer token.

## Work Queue và QA Cases

QA Queue và QA Cases là hai khái niệm riêng:

- **Work Queue** tập trung vào dataset/sequence/frame cần chạy hoặc xem Agent QA.
- **QA Cases** là registry các finding đã persist, có risk, issue type, evidence và review status.

API mode dùng `ApiQAQueueView` và QA Cases API. Mock mode dùng `MockWorkQueueView`/`MockCaseRegistryView`, work batches, assignment và feedback fixture.

Điều hướng từ case sang Editor phải giữ đúng `dataset`, `split` và `imageId`; điều hướng top-level phải loại các query parameter thuộc frame trước đó.

## 2D Editor

Editor dùng SVG canvas và server state từ TanStack Query. Người dùng có thể:

- tạo, chọn, move, resize và delete bounding box;
- đổi class, track ID, màu và attributes;
- bật/tắt visibility, chọn suggestion và object tương ứng;
- pan/zoom, undo/redo và dùng phím tắt;
- chọn Sequence → Frame → Camera, phân trang hoặc jump tới frame;
- Save, Save & Next, xem history và Restore.

Frontend dùng `xywh` cho gesture; API dùng pixel `xyxy`. Validation chặn ID trùng, class rỗng, tọa độ không hợp lệ và box ngoài giới hạn hiển thị.

Save gửi `expectedRevision`. Nếu server trả 409, UI phải yêu cầu reload; không tự merge hoặc retry write. Restore tạo revision mới, không ghi đè lịch sử.

## API-aware dashboard views

- Overview kết hợp QA case, frame sample và ingestion run data.
- Reports tổng hợp QA cases/frame samples; export hiện chưa phải backend artifact production.
- Dataset Runs hiển thị official dataset scope; assignment/release telemetry chưa được API cung cấp phải ghi rõ là unavailable.
- Pipeline đọc `/api/v1/ingestion/runs` và detail event/artifact.
- Settings dùng `/api/v1/auth/users` cho Admin; mock mode vẫn có cấu hình fixture.

## CSS và assets

- `src/styles/index.css` là entrypoint import token/base/shell/feature/view CSS.
- Asset import từ `src/data` được Vite hash vào bundle; asset tĩnh thuộc `public/` giữ URL gốc.
- Không tạo markup khác nhau giữa mock/production nếu cùng một visual contract; dùng shared component.
- Vercel CSP chỉ cho asset/script/style theo `frontend/vercel.json`; thay đổi third-party origin phải cập nhật CSP có chủ đích.

## Accessibility và responsive baseline

- Interactive element phải dùng button/link semantic và có accessible name.
- Dialog/error/status dùng role/ARIA phù hợp.
- Layout phải hoạt động ở desktop và breakpoint mobile hiện có; login visual được ẩn/thu gọn theo CSS trên màn nhỏ.
- Canvas keyboard shortcut không được chặn input đang focus.

## Kiểm tra thay đổi UI

Chạy `npm run typecheck`, `npm test` và `npm run build`. Với thay đổi gesture/layout quan trọng, thực hiện browser smoke theo checklist trong [`TESTING.md`](TESTING.md).
