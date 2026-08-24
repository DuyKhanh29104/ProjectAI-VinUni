# Deploy Vercel + Railway

Kiến trúc production được hỗ trợ:

```text
Browser -> Vercel (React/Vite SPA) -> Railway (FastAPI)
                                      |-> Supabase Auth/JWKS
                                      |-> Supabase PostgreSQL
                                      `-> GCS private bucket
```

Production hiện phục vụ một dataset release trên mỗi API service:
`DATASET_ID`/`DATASET_VERSION` trên Railway phải khớp với
`VITE_DATASET_ID`/`VITE_DATASET_VERSION` trên Vercel. Ảnh vẫn private trong
GCS và chỉ được stream qua endpoint FastAPI đã xác thực.

## 0. Release gate và backup database

Trước lần deploy đầu tiên của nhánh này:

1. tạo backup Supabase có thể restore hoặc checkpoint point-in-time recovery;
2. chạy `python -m alembic current` và ghi lại revision hiện tại;
3. chạy migrations trên PostgreSQL tạm được nạp từ snapshot production đã ẩn
   dữ liệu nhạy cảm;
4. chỉ giữ một pre-deploy migration command và không bật `RUN_MIGRATIONS` trên
   web replica.

Migration `20260822_0002` chủ ý xóa dữ liệu/bảng CVAT cũ. Migration
`20260824_0006` đổi uniqueness của `qa_images` từ image ID toàn cục sang
`(dataset, release, source_image_id)` và có thể khóa bảng trong lúc thay index.
Với bảng lớn, cần maintenance window. Sau khi nhiều release đã dùng trùng source
image ID, không dùng Alembic downgrade để rollback; hãy restore backup.

Frontend không giữ database URL, GCS credential, JWT secret hoặc model key. Supabase publishable/anon key được phép xuất hiện trong browser, nhưng các bảng nghiệp vụ trong `public` đã bật RLS và thu hồi quyền của `anon`/`authenticated`; browser chỉ truy cập dữ liệu qua FastAPI.

## 1. Chuẩn bị Supabase và GCS

1. Tạo user trong Supabase Auth và bật email confirmation nếu cần.
2. Dùng Session pooler port `5432` cho `DATABASE_URL`; percent-encode password.
3. Tạo service account GCP chỉ có quyền đọc object cần thiết (ví dụ Storage Object Viewer trên bucket dataset).
4. Giữ bucket private. FastAPI xác thực người dùng rồi stream ảnh qua endpoint `/content`.
5. Không chạy migration lifecycle hoặc downgrade trên database thật.

Migration `20260824_0004` và `20260824_0005` bật RLS cho toàn bộ bảng backend-only (kể cả migration state), thu hồi quyền bảng/sequence khỏi hai role Data API `anon` và `authenticated`, đồng thời đặt default privileges an toàn cho bảng mới.

## 2. Deploy backend lên Railway

Thứ tự tạo service khuyến nghị:

1. Tạo Railway service từ repository root và generate public domain. Không đặt
   Start Command riêng; Docker image dùng `scripts/start_server.sh`.
2. Tạo Vercel project/domain, sau đó đặt đúng HTTPS origin đó vào
   `CORS_ORIGINS` trên Railway, không có dấu `/` cuối.
3. Thêm các biến trong `deploy/railway.env.example`; đánh dấu credential/key là
   sealed secret.
4. Với demo inference CPU đầu tiên, cấp tối thiểu khoảng 2 vCPU/4 GB RAM, giữ
   một web worker rồi điều chỉnh theo số liệu latency/RAM thực tế.
5. Deploy. Railway chạy migration trước traffic và kiểm tra `/ready`; entrypoint
   cũng từ chối serve nếu schema chưa ở Alembic head.

Docker image cài Ultralytics và bundle `yolo26n.pt` ngay lúc build, nên request
Agent đầu tiên không phải tải weight vào filesystem tạm của Railway. Build cần
outbound network tới model artifact. Cần rà soát điều khoản AGPL/Enterprise của
Ultralytics trước khi dùng cho sản phẩm thương mại.

Tạo một Railway service từ thư mục gốc repository. Railway tự đọc [railway.json](../railway.json) và [Dockerfile](../Dockerfile):

- build bằng Dockerfile;
- chạy `python -m alembic upgrade head` ở pre-deploy;
- kiểm tra `/ready` trước khi chuyển traffic;
- restart khi process lỗi.

Copy các biến trong [deploy/railway.env.example](../deploy/railway.env.example) vào Railway Variables rồi thay toàn bộ placeholder. Những biến bắt buộc nhất:

```dotenv
APP_ENV=production
AUTH_ENABLED=true
DATABASE_URL=postgresql+asyncpg://...
SUPABASE_URL=https://<PROJECT_REF>.supabase.co
DATASET_BACKEND=database
DATASET_ID=nuscenes
DATASET_VERSION=v1.0-mini
DATASET_DEFAULT_SPLIT=smoke
CORS_ORIGINS=https://<VERCEL_PRODUCTION_DOMAIN>
LABEL_GUARDIAN_GCS_BUCKET=<BUCKET>
LABEL_GUARDIAN_GCS_PROJECT=<PROJECT>
LABEL_GUARDIAN_GCS_CREDENTIALS_JSON={...service account JSON...}
```

Đánh dấu `DATABASE_URL`, `LABEL_GUARDIAN_GCS_CREDENTIALS_JSON` và các model API key là sealed secrets. Không đặt `RUN_MIGRATIONS=true`: migration đã nằm ở pre-deploy để tránh nhiều web replica cùng sửa schema.

Sau deploy, tạo public domain cho service rồi kiểm tra:

## Cloud Batch Ingestion Worker

Use Cloud Batch for ingestion runs that must continue after the operator turns
off their PC. The worker entrypoint is:

```bash
python -m src.services.ingestion.cloud_worker \
  --request-gcs-uri gs://label_guardian_bucket/ops/ingestion-runs/<run_id>/request.json \
  --phase all
```

The worker stages raw archives under `raw/official/...`, extracts them on the
Batch VM scratch disk, uploads normalized data to `datasets/staging/<run_id>/...`,
validates staging, publishes canonical objects under `datasets/official/...`,
and upserts Supabase metadata only after validation passes.

Each phase writes a resumable checkpoint under
`ops/ingestion-runs/<run_id>/checkpoints/`. A retry reuses raw archives already
present in GCS and skips normalization when staging manifests already exist.
This makes failed jobs restart from the last durable cloud artifact instead of
downloading everything again.

Deployment assets live in `deploy/gcp/`:

- `Dockerfile.ingestion-worker`: container image for Artifact Registry.
- `batch-nuscenes-smoke.json`: Cloud Batch smoke job for nuScenes.
- `batch-kitti-smoke.json`: Cloud Batch smoke job for KITTI with Secret Manager
  archive URL injection.
- `batch-parameterized-template.json`: larger/full-run template with explicit
  placeholders for project, bucket, run ID and image tag.
- `batch-kitti-3d-scaleup.json`: ready-to-run KITTI 3D smoke job on a larger
  VM and disk for LiDAR processing.
- `batch-full-scaleup-template.json`: one-task full-run template using a larger
  VM and 1 TB boot disk.
- `request-nuscenes-smoke.json` and `request-kitti-smoke.json`: request examples.
- `workflow-run-ingestion.yaml`: Workflows wrapper that creates a Batch job.
- `cloudbuild-ingestion-worker.yaml`: Cloud Build config for
  `Dockerfile.ingestion-worker`.

Required GCP services: Artifact Registry, Secret Manager, Cloud Storage, Cloud
Batch, Workflows or Cloud Run Jobs, Cloud Logging and Cloud Monitoring.

Minimum worker service account permissions: read/write `label_guardian_bucket`,
access the configured Secret Manager versions, write Cloud Logging entries and
run as the configured Batch service account.

### Demo data runbook

1. Create the private GCS bucket, for example `label_guardian_bucket`. Give the
   worker read/write access to ingestion prefixes and the backend read access to
   clean dataset prefixes.
2. Stage raw official archives to GCS when replay/audit is required. This
   command streams the official URL directly into the bucket without writing
   the archive to the repo/workspace:

   ```bash
   python scripts/stage_official_archive_to_gcs.py \
     --url https://www.nuscenes.org/data/v1.0-mini.tgz \
     --destination gs://label_guardian_bucket/raw/official/nuscenes/v1.0-mini/archives/v1.0-mini.tgz \
     --gcp-project ai-lab-16-gcp-505508
   ```

3. Run the ingest CLI. It downloads or reuses official source archives in a
   temporary scratch directory, uploads normalized frames to GCS, and persists
   QA records to Supabase. Until the ETL worker moves to GCP, keep this scratch
   outside the repo and treat GCS/Supabase as the source of truth:

   ```bash
   python scripts/label_guardian_run_ingestion.py \
     --source official --selector nuscenes --nuscenes-version v1.0-mini \
     --download-root /tmp/label-guardian-official \
     --bucket gs://label_guardian_bucket/datasets/official/nuscenes/v1.0-mini \
     --storage-prefix smoke \
     --max-images 5 \
     --database-url 'postgresql+psycopg://postgres.<PROJECT_REF>:<DB_PASSWORD>@<HOST>:5432/postgres?sslmode=require' \
     --gcp-project ai-lab-16-gcp-505508
   ```

4. Run Alembic against Supabase, start backend/frontend, open `/qa-queue`, choose
   a cloud-backed frame, and select **Chạy Agent & thêm vào Queue**.

For official downloads, switch `--source local` to `--source official` and pass
the KITTI/CVLIBS or nuScenes credentials/URLs described in
`docs/official_cloud_ingestion_automation.md`.

### Cloud Batch smoke run

Upload a request and submit the matching Batch template:

```bash
gcloud storage cp deploy/gcp/request-nuscenes-smoke.json \
  gs://label_guardian_bucket/ops/ingestion-runs/nuscenes-smoke/request.json

gcloud batch jobs submit label-guardian-nuscenes-smoke \
  --location asia-southeast1 \
  --config deploy/gcp/batch-nuscenes-smoke.json \
  --project ai-lab-16-gcp-505508
```

For KITTI, first create Secret Manager values for the four official direct
archive URLs, then upload `deploy/gcp/request-kitti-smoke.json` and submit
`deploy/gcp/batch-kitti-smoke.json`.

KITTI smoke includes `camera`, `labels`, `calibration` and `lidar` modalities.
When `max_frames` is set, the worker selectively extracts only those frame IDs
from `image_2`, `label_2`, `calib` and `velodyne`. 3D-ready artifacts are
published under:

```text
datasets/official/kitti/object/<split>/pointclouds/sequence-default/<frame_id>/LIDAR_TOP.bin
datasets/official/kitti/object/<split>/calibration/sequence-default/<frame_id>/calib.txt
```

For larger KITTI 3D runs, prefer the parameterized template with a larger disk
or sharded run IDs. Multiple independent dataset jobs can run in parallel, but
one logical run is not horizontally sharded unless request partitioning is
introduced.

### Scaling policy

Use vertical scale-up for the current worker: one Batch task on a larger VM.
This is the safe option because each request owns one staging prefix and one
canonical publish transaction. Raising `taskCount` for the same request before
sharding support exists would make multiple tasks normalize and publish the same
run concurrently.

Use `deploy/gcp/batch-kitti-3d-scaleup.json` for immediate KITTI LiDAR smoke
runs:

```bash
gcloud batch jobs submit label-guardian-kitti-smoke-3d-scaleup-$(date +%Y%m%d%H%M) \
  --location asia-southeast1 \
  --config deploy/gcp/batch-kitti-3d-scaleup.json \
  --project ai-lab-16-gcp-505508
```

Use `deploy/gcp/batch-full-scaleup-template.json` for full dataset attempts. It
uses one `e2-standard-16` VM with a 1 TB boot disk and 24 hour max duration.
Replace placeholders with the project, region, bucket, image tag and run ID
before submission.

Horizontal scaling is the next design step for full train/val scale. The worker
needs explicit shard fields such as `shard_index`, `shard_count` and a finalizer
phase so each VM owns a disjoint scene/frame range and only one final task
publishes Supabase metadata.

### Full nuScenes links

`v1.0-mini` uses the stable public mini archive. For full `v1.0-trainval`, use
the public AWS Open Data/CloudFront mirror so archives move cloud-to-cloud and
never pass through a developer PC. The checked-in trainval smoke request
contains public CloudFront URLs for all 11 trainval archives.

```bash
gcloud storage cp deploy/gcp/request-nuscenes-trainval-smoke.json \
  gs://label_guardian_bucket/ops/ingestion-runs/nuscenes-trainval-smoke/request.json \
  --project ai-lab-16-gcp-505508

gcloud batch jobs submit label-guardian-nuscenes-trainval-smoke-$(date +%Y%m%d%H%M) \
  --location asia-southeast1 \
  --config deploy/gcp/batch-nuscenes-trainval-scaleup.json \
  --project ai-lab-16-gcp-505508
```

The trainval smoke request sets `max_blob_archives: 1`, so the Batch worker
stages metadata plus `v1.0-trainval01_blobs.tgz` only for the first end-to-end
proof. Remove `max_blob_archives` for a full trainval run. The worker normalizes
five synchronized frame groups and publishes camera frames plus `LIDAR_TOP`
point clouds and calibration JSON when validation passes.

If the AWS mirror is unavailable, fall back to a registered nuScenes account on
the official download page and capture these archive URLs into Secret Manager
or an ops-only request object:

```text
v1.0-trainval_meta.tgz
v1.0-trainval01_blobs.tgz
v1.0-trainval02_blobs.tgz
v1.0-trainval03_blobs.tgz
v1.0-trainval04_blobs.tgz
v1.0-trainval05_blobs.tgz
v1.0-trainval06_blobs.tgz
v1.0-trainval07_blobs.tgz
v1.0-trainval08_blobs.tgz
v1.0-trainval09_blobs.tgz
v1.0-trainval10_blobs.tgz
```

Keep captured official URLs out of the repo. Some official URLs may be
session-bound, so refresh them if a cloud run later receives HTTP 403/404 while
staging raw archives.

Acceptance files:

```text
ops/ingestion-runs/<run_id>/request.json
ops/ingestion-runs/<run_id>/validation.json
ops/ingestion-runs/<run_id>/result.json
datasets/official/<dataset>/<release>/<split>/manifests/ingest_manifest.json
datasets/official/<dataset>/<release>/<split>/manifests/image_manifest.jsonl
datasets/official/<dataset>/<release>/<split>/annotations/normalized_objects.jsonl
```

```powershell
$Api = "https://<RAILWAY_PUBLIC_DOMAIN>"
Invoke-RestMethod "$Api/health"
Invoke-RestMethod "$Api/ready"
Invoke-WebRequest "$Api/openapi.json"
```

`/health` chỉ là liveness. `/ready` chạy `SELECT 1` tới PostgreSQL và trả 503
khi database chưa sẵn sàng. Endpoint này chủ ý không list bucket GCS vì service
account backend chỉ cần quyền đọc object. Kiểm tra quyền GCS bằng cách mở một
URL `/content` đã xác thực trong smoke test sau deploy.

## 3. Deploy frontend lên Vercel

Import cùng repository nhưng đặt **Root Directory** là `frontend`. Vercel đọc [frontend/vercel.json](../frontend/vercel.json), chạy Vite build và rewrite deep-link của React Router về `index.html`.

Thêm các biến từ [deploy/vercel.env.example](../deploy/vercel.env.example):

```dotenv
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=https://<RAILWAY_PUBLIC_DOMAIN>
VITE_DATASET_ID=nuscenes
VITE_DATASET_NAME=nuScenes cloud dataset
VITE_DATASET_FORMAT=nuScenes
VITE_DATASET_VERSION=v1.0-mini
VITE_AUTH_MODE=supabase
VITE_SUPABASE_URL=https://<PROJECT_REF>.supabase.co
VITE_SUPABASE_ANON_KEY=<PUBLISHABLE_OR_ANON_KEY>
```

Sau khi có domain production của Vercel:

1. cập nhật `CORS_ORIGINS` bên Railway bằng đúng origin, không có dấu `/` cuối;
2. thêm domain và callback URL của Vercel vào Supabase Auth URL Configuration;
3. redeploy Railway nếu biến CORS thay đổi;
4. chỉ cấu hình preview domain vào CORS khi thực sự cần test preview.

Frontend mặc định fail-closed: nếu build quên `VITE_AUTH_MODE`, nó vẫn chọn Supabase chứ không tạo mock admin; nếu quên `VITE_DATA_SOURCE`, nó vẫn gọi API thật.

Các biến `VITE_*` được compile vào browser bundle. Sau khi đổi Railway domain,
Supabase project hoặc dataset identity, phải redeploy Vercel; chỉ sửa dashboard
variable không làm thay đổi bundle cũ. Không bao giờ đặt database URL, GCS
service-account JSON hoặc model-provider key trong biến `VITE_*`.

## 4. Kiểm tra trước và sau rollout

Chạy ở máy local trước khi push:

```powershell
python -m ruff check src tests migrations
python -m pytest -q
python scripts/check_openapi.py
docker build -t label-guardian:deploy-check .
docker run --rm label-guardian:deploy-check python -c "import ultralytics; from src.main import app; assert app"

Set-Location frontend
npm ci
npm run typecheck
npm test -- --run
npm run build
```

Smoke test production theo thứ tự:

1. `/ready` trả 200.
2. Đăng nhập Supabase trên frontend.
3. Mở Dataset QA và xác nhận chỉ thấy đúng `DATASET_ID/DATASET_VERSION/split`.
4. Mở một ảnh; request `/content` trả ảnh GCS private.
5. Lưu một revision trong 2D Editor rồi reload.
6. Reviewer chạy Agent, mở QA Cases và cập nhật trạng thái.
7. Admin mở Settings và đổi role của một tài khoản test.
8. Chọn suggestion có nhãn gốc và xác nhận box được highlight; chọn suggestion
   thiếu nhãn và xác nhận prediction box nét đứt hiển thị mà chưa sửa annotation.

Nếu deployment fail:

- lỗi ở pre-deploy thường là `DATABASE_URL` hoặc migration;
- process boot fail sớm thường là auth, CORS, dataset placeholder hoặc GCS credential;
- `/health` 200 nhưng `/ready` 503 là lỗi kết nối PostgreSQL;
- ảnh 404 cần kiểm tra đồng thời dataset/release/split trong `qa_images` và `storage_key` trong bucket.

Tài liệu nền tảng: [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite),
[Vercel Environment Variables](https://vercel.com/docs/environment-variables),
[Railway Config as Code](https://docs.railway.com/config-as-code/reference),
[Railway Pre-deploy Command](https://docs.railway.com/deployments/pre-deploy-command),
[Railway Healthchecks](https://docs.railway.com/deployments/healthchecks),
[Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
và [Ultralytics License](https://www.ultralytics.com/license).
