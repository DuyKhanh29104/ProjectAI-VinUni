# Huong Dan Development, Demo Va Cloud Dataset Pipeline

Tai lieu nay danh cho team chay Label Guardian tren may ca nhan nhung dung chung ha tang cloud:

- **Supabase PostgreSQL**: metadata, QA images/objects, provenance, ingestion jobs va QA cases.
- **Google Cloud Storage (GCS)**: raw official archives, normalized golden frames, manifests va derived artifacts.
- **Backend FastAPI**: doc Supabase, doc object private tu GCS, stream anh cho frontend.
- **Frontend Vite**: chi goi backend API, khong doc GCS truc tiep.

Khong dua password Supabase, service-account JSON, signed URL, cookie, token hoac file `.env` vao Git/chat. `.env.example` chi duoc chua placeholder khong nhay cam.

```text
Frontend local -> FastAPI local -> Supabase PostgreSQL
                              -> GCS private object streaming

Cloud trigger -> Workflows/Cloud Run Job -> Cloud Batch worker
                                      -> GCS raw/staging/official
                                      -> Supabase metadata
```

## 1. Chuan Bi Mot Lan

1. Cai Python 3.12+, Git, Docker Desktop, Node.js 22.6+ va Google Cloud CLI.
2. Clone repository, tao virtualenv va cai dependencies:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e ".[ingestion]"
   Copy-Item .env.example .env
   ```

3. Nho maintainer cap quyen vao:

   ```text
   GCP project: ai-lab-16-gcp-505508
   GCS bucket: gs://label_guardian_bucket
   Supabase dev project
   ```

Moi thanh vien dung tai khoan Google rieng. Khong dung chung service-account key neu co the dung ADC hoac Workload Identity.

## 2. Cau Hinh Supabase

Mo Supabase Dashboard -> **Connect** -> uu tien **Session pooler**, port `5432`. Khong dung Transaction pooler port `6543` cho app/runtime.

Neu password co ky tu dac biet, encode tren may cua ban:

```powershell
py -3.12 -c "import getpass; from urllib.parse import quote; print(quote(getpass.getpass('Supabase password: '), safe=''))"
```

Trong `.env`, dien URL that duoc maintainer cap:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres.<PROJECT_REF>:<URL_ENCODED_PASSWORD>@<SESSION_POOLER_HOST>:5432/postgres?ssl=require
LABEL_GUARDIAN_DATABASE_URL=postgresql+psycopg://postgres.<PROJECT_REF>:<URL_ENCODED_PASSWORD>@<SESSION_POOLER_HOST>:5432/postgres?sslmode=require
```

Chi **maintainer/CI** chay migration tren Supabase dung chung:

```powershell
python -m alembic upgrade head
```

Developer binh thuong chi kiem tra schema:

```powershell
python -m alembic current --check-heads
```

Tuyet doi khong chay `alembic downgrade`, `scripts/check_migrations.py` hoac pytest tro vao Supabase. Cac lenh nay co the reset/truncate database test.

## 3. Auth GCP Va Kiem Tra Bucket

Dat dung project ID, dang nhap `gcloud` va Application Default Credentials:

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project ai-lab-16-gcp-505508
gcloud storage ls gs://label_guardian_bucket/
```

Neu khong thay bucket, nho maintainer cap IAM toi thieu:

- Developer doc dataset: `Storage Object Viewer`.
- Nguoi chay ingestion/upload: quyen ghi dung prefix hoac `Storage Object Admin` tren bucket dev.
- Cloud Batch worker: doc/ghi bucket, doc Secret Manager, ghi Cloud Logging.

Test upload nho chi nen dung prefix ops/healthchecks:

```powershell
gcloud storage cp README.md gs://label_guardian_bucket/ops/healthchecks/<your-name>-readme.txt
gcloud storage ls gs://label_guardian_bucket/ops/healthchecks/
```

Sau khi xac nhan, chi xoa dung object test cua ban:

```powershell
gcloud storage rm gs://label_guardian_bucket/ops/healthchecks/<your-name>-readme.txt
```

## 4. Cau Hinh Runtime Cloud Dataset

Golden dataset runtime la database-backed. Backend lay danh sach anh tu Supabase, sau do stream object private tu GCS qua endpoint backend.

Trong `.env`:

```dotenv
DATASET_BACKEND=database
DATASET_DEFAULT_SPLIT=smoke

LABEL_GUARDIAN_STORAGE_BACKEND=gcs
LABEL_GUARDIAN_GCS_BUCKET=label_guardian_bucket
LABEL_GUARDIAN_GCS_PROJECT=ai-lab-16-gcp-505508
# LABEL_GUARDIAN_GCS_CREDENTIALS_PATH=C:/secure/gcp-dev-service-account.json
# LABEL_GUARDIAN_GCS_PUBLIC_URL=
```

De trong `LABEL_GUARDIAN_GCS_CREDENTIALS_PATH` neu da dung `gcloud auth application-default login`. Chi dung duong dan JSON khi maintainer cap service account rieng va file nam ngoai Git.

`DATASET_ROOT` chi con la filesystem fallback/local smoke. Khong can sync golden dataset ve may de UI load data cloud.

## 5. Golden Dataset Layout Tren Bucket

Tat ca data sach, da validate va duoc backend/UI su dung phai nam trong `datasets/official/...`.

```text
gs://label_guardian_bucket/
  raw/
    official/
      nuscenes/
        v1.0-mini/
          archives/
            v1.0-mini.tgz
      kitti/
        object/
          archives/
            data_object_image_2.zip
            data_object_label_2.zip
            data_object_calib.zip
            data_object_velodyne.zip

  datasets/
    staging/
      <run_id>/
        official/<dataset>/<release>/<split>/

    official/
      nuscenes/
        v1.0-mini/
          smoke/
            frames/
              <scene_id>/
                <frame_id>/
                  CAM_FRONT.jpg
                  CAM_FRONT_LEFT.jpg
                  CAM_FRONT_RIGHT.jpg
                  CAM_BACK.jpg
                  CAM_BACK_LEFT.jpg
                  CAM_BACK_RIGHT.jpg
            annotations/
              normalized_objects.jsonl
            manifests/
              image_manifest.jsonl
              ingest_manifest.json

      kitti/
        object/
          smoke/
            frames/
              sequence-default/
                <frame_id>/
                  CAM_FRONT.png
            annotations/
              normalized_objects.jsonl
            manifests/
              image_manifest.jsonl
              ingest_manifest.json

    derived/
      yolo/
        <dataset_run_id>/
          images/
          labels/
          dataset.yaml

  ops/
    healthchecks/
    ingestion-runs/
      <run_id>/
        request.json
        validation.json
        result.json
```

`raw/` la input official/audit. `datasets/staging/` la output tam theo run. `datasets/official/` la golden canonical sau khi validate pass. `datasets/derived/` la artifact tao lai duoc, khong phai source of truth. `ops/` chi chua thong tin van hanh.

## 6. Supabase Contract

Dang reuse cac bang hien co:

```text
qa_images
qa_objects
qa_object_provenance
qa_cases
qa_evaluations
ingestion_jobs
ingestion_job_events
ingestion_assets
cvat_dataset_image_mappings
```

Quy uoc hien tai:

- `qa_images.storage_key` tro toi object canonical trong `datasets/official/...`.
- `qa_images.object_url` luu URL/object URL GCS-backed.
- `qa_objects.image_id` lien ket label normalized voi tung image.
- `qa_object_provenance` luu bang chung tu provider goc.
- `ingestion_jobs.request_fingerprint` dam bao idempotency cho cloud run.
- Frame grouping tam thoi duoc bieu dien bang GCS path; migration frame-first se lam rieng sau.

Frontend khong doc Supabase/GCS truc tiep. Luong dung:

```text
Frontend -> /api -> FastAPI -> Supabase metadata -> GCS private object -> FastAPI stream
```

## 7. Chay Backend Local Voi Cloud Dataset

Kiem tra `.env` da co Supabase + GCS config, roi chay truc tiep:

```powershell
.\.venv\Scripts\Activate.ps1
python -m alembic current --check-heads
python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Hoac chay Docker khong khoi dong PostgreSQL local:

```powershell
docker compose -f docker-compose.yml -f docker-compose.supabase.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.supabase.yml up -d --build --wait --wait-timeout 120 backend
docker compose -f docker-compose.yml -f docker-compose.supabase.yml logs --tail 100 backend
```

Kiem tra API:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/health
Invoke-WebRequest "http://127.0.0.1:8000/api/v1/dataset/images?split=smoke&limit=2"
```

Endpoint stream image:

```text
http://127.0.0.1:8000/api/v1/dataset/images/<split>/<image_id>/content
```

## 8. Chay Frontend Local

Mo terminal moi:

```powershell
Set-Location frontend
npm install
Copy-Item .env.example .env.local
```

Trong `frontend/.env.local`:

```dotenv
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=
```

De trong `VITE_API_BASE_URL` de Vite proxy moi request `/api` toi `http://127.0.0.1:8000`. Khong dua Supabase password, CVAT PAT hay GCP key vao frontend env.

Khi backend dang chay:

```powershell
npm.cmd run dev
```

Mo:

```text
http://localhost:5173/qa-queue
```

Neu chi xem mock UI khong can backend:

```dotenv
VITE_DATA_SOURCE=mock
VITE_API_BASE_URL=
```

## 9. Cloud Pipeline Ingestion

Pipeline production dung **Hybrid Cloud Run/Workflows + Cloud Batch**. PC co the tat sau khi request da duoc submit len GCP.

Worker entrypoint:

```bash
python -m src.services.ingestion.cloud_worker \
  --request-gcs-uri gs://label_guardian_bucket/ops/ingestion-runs/<run_id>/request.json \
  --phase all
```

Request shape:

```json
{
  "dataset_type": "nuscenes",
  "release": "v1.0-mini|v1.0-trainval",
  "split": "smoke",
  "max_frames": 5,
  "max_blob_archives": 1,
  "modalities": ["camera", "labels", "calibration", "lidar"],
  "source": "official",
  "requested_by": "team-member",
  "publish": true
}
```

Cloud worker flow:

1. Doc request tu `ops/ingestion-runs/<run_id>/request.json`.
2. Stage/reuse raw archives trong `raw/official/...`.
3. Download raw archive tu GCS vao scratch disk cua Batch VM.
4. Extract, normalize va upload staging vao `datasets/staging/<run_id>/...`.
5. Validate required objects, manifests, labels va provenance.
6. Publish sang `datasets/official/...` neu validation pass.
7. Upsert Supabase rows va ghi `ingestion_assets`.
8. Ghi `validation.json`, `result.json`, cap nhat `ingestion_jobs.status`.

Worker co cache/checkpoint theo `run_id`:

- Raw archives da upload len `raw/official/...` se duoc reuse o lan retry sau.
- Staging manifest da normalize duoc reuse neu phase normalize da xong.
- Checkpoints nam trong `ops/ingestion-runs/<run_id>/checkpoints/`.
- Batch VM chi dung scratch disk tam thoi de extract/normalize; developer PC
  khong nam trong production pipeline.

Deployment assets:

- `Dockerfile.ingestion-worker`: worker image Dockerfile o root repo.
- `batch-nuscenes-smoke.json`: nuScenes mini smoke.
- `batch-nuscenes-trainval-scaleup.json`: nuScenes trainval smoke/full tren VM lon.
- `batch-kitti-smoke.json`: KITTI smoke.
- `batch-kitti-3d-scaleup.json`: KITTI camera + LiDAR smoke tren VM lon.
- `batch-full-scaleup-template.json`: template full run can thay placeholder.
- `batch-parameterized-template.json`: template cu cho run tuy bien nhe.
- `request-nuscenes-smoke.json`
- `request-nuscenes-trainval-smoke.json`
- `request-kitti-smoke.json`
- `workflow-run-ingestion.yaml`

Tat ca file JSON/YAML o tren nam trong `deploy/gcp/`.

Submit nuScenes smoke:

```bash
gcloud storage cp deploy/gcp/request-nuscenes-smoke.json \
  gs://label_guardian_bucket/ops/ingestion-runs/nuscenes-smoke/request.json

gcloud batch jobs submit label-guardian-nuscenes-smoke \
  --location asia-southeast1 \
  --config deploy/gcp/batch-nuscenes-smoke.json \
  --project ai-lab-16-gcp-505508
```

Submit nuScenes trainval smoke/full cloud-to-cloud:

```bash
gcloud storage cp deploy/gcp/request-nuscenes-trainval-smoke.json \
  gs://label_guardian_bucket/ops/ingestion-runs/nuscenes-trainval-smoke/request.json \
  --project ai-lab-16-gcp-505508

gcloud batch jobs submit label-guardian-nuscenes-trainval-smoke-$(date +%Y%m%d%H%M) \
  --location asia-southeast1 \
  --config deploy/gcp/batch-nuscenes-trainval-scaleup.json \
  --project ai-lab-16-gcp-505508
```

`request-nuscenes-trainval-smoke.json` dang dat `max_blob_archives: 1` de chi
stage metadata + `v1.0-trainval01_blobs.tgz` cho lan smoke dau tien. Khi chay
full trainval, bo field nay de worker stage du 10 blob archives.

Submit KITTI smoke sau khi maintainer tao Secret Manager direct archive URLs:

```bash
gcloud storage cp deploy/gcp/request-kitti-smoke.json \
  gs://label_guardian_bucket/ops/ingestion-runs/kitti-smoke/request.json

gcloud batch jobs submit label-guardian-kitti-smoke \
  --location asia-southeast1 \
  --config deploy/gcp/batch-kitti-smoke.json \
  --project ai-lab-16-gcp-505508
```

KITTI secrets expected:

```text
kitti-image-2-url
kitti-label-2-url
kitti-calib-url
kitti-velodyne-url
```

Supabase worker secret expected:

```text
supabase-database-url-sync
```

3D/LiDAR output duoc publish cung canonical dataset:

```text
datasets/official/nuscenes/<release>/<split>/pointclouds/<scene_id>/<sample_token>/LIDAR_TOP.pcd.bin
datasets/official/nuscenes/<release>/<split>/calibration/<scene_id>/<sample_token>/LIDAR_TOP.json
datasets/official/kitti/object/<split>/pointclouds/sequence-default/<frame_id>/LIDAR_TOP.bin
datasets/official/kitti/object/<split>/calibration/sequence-default/<frame_id>/calib.txt
```

## 10. Stage Official Archive Len GCS

Khi can luu raw official archive cho replay/audit, stream truc tiep tu official URL vao bucket, khong ghi vao repo:

```bash
python scripts/stage_official_archive_to_gcs.py \
  --url https://www.nuscenes.org/data/v1.0-mini.tgz \
  --destination gs://label_guardian_bucket/raw/official/nuscenes/v1.0-mini/archives/v1.0-mini.tgz \
  --gcp-project ai-lab-16-gcp-505508
```

Voi KITTI, direct archive URL/cookie khong duoc commit. Luu chung trong Secret Manager va de worker doc khi chay tren Cloud Batch.

## 11. Local Ingestion Smoke

Local CLI van huu ich de test adapter nho, nhung production/golden run nen chay tren Cloud Batch.

nuScenes smoke local, upload output canonical len GCS va ghi Supabase:

```bash
python scripts/label_guardian_run_ingestion.py \
  --source official \
  --selector nuscenes \
  --nuscenes-version v1.0-mini \
  --download-root /tmp/label-guardian-official \
  --bucket gs://label_guardian_bucket/datasets/official/nuscenes/v1.0-mini \
  --storage-prefix smoke \
  --max-images 5 \
  --database-url "$LABEL_GUARDIAN_DATABASE_URL" \
  --gcp-project ai-lab-16-gcp-505508
```

KITTI smoke local:

```bash
python scripts/label_guardian_run_ingestion.py \
  --source official \
  --selector kitti \
  --scenario baseline_easy \
  --download-root /tmp/label-guardian-official \
  --bucket gs://label_guardian_bucket/datasets/official/kitti/object \
  --storage-prefix smoke \
  --max-images 5 \
  --database-url "$LABEL_GUARDIAN_DATABASE_URL" \
  --gcp-project ai-lab-16-gcp-505508 \
  --kitti-login-with-browser
```

Khong chay nhieu ingestion dong thoi vao cung dataset/prefix.

## 12. Nghiem Thu Golden Dataset

Mot dataset chi duoc coi la golden khi:

- Object nam dung canonical prefix `datasets/official/...`.
- `qa_images.storage_key` tro toi object GCS ton tai.
- `qa_objects` co label normalized.
- `qa_object_provenance` co provenance tu dataset goc.
- Backend list duoc images qua `/api/v1/dataset/images`.
- Backend stream duoc image bytes qua `/content`.
- nuScenes giu du camera views dong bo trong cung frame khi source co du lieu.
- KITTI dung layout `sequence-default/<frame_id>/CAM_FRONT.png`.
- Khong co secret nao trong Git, docs hoac frontend env.

Kiem tra nhanh:

```bash
curl "http://127.0.0.1:8000/api/v1/dataset/images?split=smoke&limit=2"
curl "http://127.0.0.1:8000/api/v1/qa-cases?limit=200&sourceType=local_dataset"
curl "http://127.0.0.1:5173/api/v1/dataset/images?split=smoke&limit=2"
```

`qa-cases` co the tra `count: 0` neu chua persist evaluation; dataset API va image content endpoint moi la smoke check chinh cho cloud dataset.

## 13. Chay Test An Toan

Tests chi dung PostgreSQL local tam thoi o port `5433`, khong dung Supabase:

```powershell
docker compose --profile test up -d --wait postgres-test
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/label_guardian_test"
python -m pytest
```

Kiem tra truoc PR:

```bash
ruff check src tests scripts
MYPY_CACHE_DIR=/tmp/label_guardian_mypy_cache python -m mypy src
python scripts/check_openapi.py
```

Frontend:

```powershell
Set-Location frontend
npm.cmd run typecheck
npm.cmd test -- --run
```

## Loi Thuong Gap

- `getaddrinfo` hoac khong ket noi duoc `db.<ref>.supabase.co`: endpoint Direct co the chi co IPv6; doi sang Session pooler port `5432`.
- `password authentication failed`: kiem tra password da percent-encode va pooler username la `postgres.<PROJECT_REF>`.
- `Database is not on all head revisions`: bao maintainer chay `alembic upgrade head`; khong sua schema truc tiep bang Supabase Table Editor.
- Frontend goi `/api/v1/qa-cases` bi 500: kiem tra backend da chay, `.env` backend dang tro dung Supabase, `DATASET_BACKEND=database`, va Vite proxy de `VITE_API_BASE_URL=` khi chay local.
- Image list co row nhung content 404/500: kiem tra `qa_images.storage_key` co ton tai tren `gs://label_guardian_bucket/datasets/official/...` va backend co quyen doc GCS.
- `KITTI flat directory is invalid`: ban dang dua YOLO artifact vao raw KITTI ingestion. Raw KITTI can `image_2`, `label_2`, `calib`, `velodyne`.
- `403` khi doc/ghi GCS: chay lai ADC va kiem tra IAM tren dung bucket/prefix.
- Cloud Batch fail vi KITTI credential: kiem tra Secret Manager co du `kitti-image-2-url`, `kitti-label-2-url`, `kitti-calib-url`, `kitti-velodyne-url`.
