# Golden Dataset

## Mục Tiêu

Golden dataset là bộ dữ liệu cloud chuẩn của Label Guardian, dùng làm nguồn thật cho QA, demo, kiểm thử pipeline, annotation review và đánh giá model.

Golden dataset không phải là thư mục local trên máy từng thành viên. Nó là một dataset dùng chung:

- Ảnh/frame sạch được lưu trong Google Cloud Storage.
- Metadata, bbox, provenance và QA records được lưu trong Supabase PostgreSQL.
- Backend đọc Supabase, lấy object từ GCS private, rồi stream ảnh cho frontend.

## Nguyên Tắc

- Official dataset là nguồn gốc, nhưng không phải mọi file official đều là golden.
- Golden dataset chỉ chứa phần đã được pipeline chọn, validate, chuẩn hóa và có metadata trong Supabase.
- GCS lưu artifact lớn như ảnh/frame, raw archive và derived export.
- Supabase là source of truth cho metadata, object labels, provenance, ingestion state và QA cases.
- Frontend không đọc GCS trực tiếp. Frontend chỉ gọi backend API.

## Cloud Location

GCP project:

```text
ai-lab-16-gcp-505508
```

GCS bucket:

```text
gs://label_guardian_bucket
```

Canonical clean dataset prefix:

```text
datasets/official/<dataset>/<release>/<split>/
```

Current nuScenes smoke prefix:

```text
datasets/official/nuscenes/v1.0-mini/smoke/
```

Current verified state on 2026-08-22:

```text
GCS objects under datasets/official/nuscenes/v1.0-mini/smoke/frames/: 30
Supabase qa_images rows: 35
Supabase rows with matching GCS objects: 30
Supabase stale rows from old flat sweeps layout: 5
```

The 5 stale rows point to the old `frames/sweeps/CAM_FRONT/...` layout and should
be removed only through an explicit DB cleanup step after maintainer approval.

## Bucket Structure

Target layout:

```text
gs://label_guardian_bucket/
  datasets/
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
              ingest_manifest.json

    derived/
      yolo/
        <dataset_run_id>/
          images/
          labels/
          dataset.yaml

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

  ops/
    healthchecks/
    ingestion-runs/
```

## Data Zones

### `raw/`

Raw official source archives.

This zone is optional for smoke runs and should only be populated when the team
wants replay, audit or long-running cloud workers. Use
`scripts/stage_official_archive_to_gcs.py` to stream official archives directly
to GCS without keeping archive files in the repo/workspace. Local CLI ETL still
needs temporary scratch space to extract and normalize archive contents; use
`/tmp` or move the ETL run to a GCP worker when the run must be fully
cloud-resident.

Examples:

```text
raw/official/nuscenes/v1.0-mini/archives/v1.0-mini.tgz
raw/official/kitti/object/archives/data_object_image_2.zip
```

### `datasets/official/`

Clean, normalized dataset used by backend and UI.

This is the primary golden zone. Cloud Batch writes here only after staging
validation passes.

Examples:

```text
datasets/official/nuscenes/v1.0-mini/smoke/frames/scene-0061/sample-1532402927647951/CAM_FRONT.jpg
datasets/official/kitti/object/smoke/frames/sequence-default/000000/CAM_FRONT.png
```

### `datasets/derived/`

Derived artifacts, such as YOLO exports, model outputs or benchmark-ready transformations.

These are not the official golden source, but they can be generated from it.

### `ops/`

Operational data: health checks, ingestion run summaries and logs.

This should not be mixed with dataset content.

Required per-run files:

```text
ops/ingestion-runs/<run_id>/request.json
ops/ingestion-runs/<run_id>/validation.json
ops/ingestion-runs/<run_id>/result.json
```

## Frame Semantics

A frame is one synchronized driving moment. A frame can contain multiple camera views.

### nuScenes

nuScenes is multi-camera by design.

Frame identity:

```text
sample.token
```

Scene identity:

```text
scene.name
```

Camera channels:

```text
CAM_FRONT
CAM_FRONT_LEFT
CAM_FRONT_RIGHT
CAM_BACK
CAM_BACK_LEFT
CAM_BACK_RIGHT
```

Golden object key pattern:

```text
datasets/official/nuscenes/<release>/<split>/frames/<scene_id>/<frame_id>/<camera_channel>.jpg
```

### KITTI Object

Current KITTI object detection support is image-first and effectively single-camera for the project scope.

Frame identity:

```text
image file stem, for example 000000
```

Scene identity:

```text
sequence-default
```

Camera channel:

```text
CAM_FRONT
```

Golden object key pattern:

```text
datasets/official/kitti/object/<split>/frames/sequence-default/<frame_id>/CAM_FRONT.png
```

## Supabase Contract

Current tables:

```text
qa_images
qa_objects
qa_object_provenance
ingestion_jobs
ingestion_job_events
ingestion_assets
qa_cases
qa_evaluations
annotation_revisions
```

Current source-of-truth behavior:

- `qa_images.storage_key` points to the GCS object.
- `qa_images.object_url` stores the object URL or GCS-backed URL.
- `qa_objects.image_id` links normalized labels to one image.
- `qa_object_provenance` stores original provider evidence.
- `qa_cases` is populated when evaluation is persisted.
- Cloud Batch worker writes `ingestion_jobs`, `ingestion_job_events` and
  `ingestion_assets` for each cloud run. The request fingerprint is the run ID
  when explicitly provided, otherwise it is a stable hash of the request.

Planned frame-first schema:

```text
qa_dataset_runs
  id
  provider
  dataset
  release
  split
  bucket
  root_prefix
  status
  metadata_json
  created_at
  updated_at

qa_frames
  id
  dataset_run_id
  source_frame_id
  scene_id
  timestamp_us
  frame_index
  storage_prefix
  manifest_key
  metadata_json
  created_at

qa_images
  frame_id
  camera_channel
  timestamp_us
  source_filename
```

Until the frame-first migration is implemented, frame grouping is represented in the GCS key path while Supabase remains image-first.

## Backend/UI Contract

Frontend does not access GCS directly.

Runtime flow:

```text
Frontend -> FastAPI -> Supabase metadata -> GCS private object -> FastAPI stream -> Frontend
```

Image content endpoint:

```text
/api/v1/dataset/images/<split>/<image_id>/content
```

Expected behavior:

- Dataset list comes from Supabase.
- Image bytes come from private GCS through backend streaming.
- Bucket public read access is not required.

## Ingestion Commands

Cloud Batch worker:

```bash
python -m src.services.ingestion.cloud_worker \
  --request-gcs-uri gs://label_guardian_bucket/ops/ingestion-runs/<run_id>/request.json \
  --phase all
```

Local CLI smoke remains useful for development, but production golden runs
should use the worker image and Batch templates in `deploy/gcp/`.

nuScenes smoke:

```bash
python scripts/label_guardian_run_ingestion.py \
  --source official \
  --selector nuscenes \
  --nuscenes-version v1.0-mini \
  --bucket gs://label_guardian_bucket/datasets/official/nuscenes/v1.0-mini \
  --storage-prefix smoke \
  --max-images 5 \
  --gcp-project ai-lab-16-gcp-505508
```

KITTI smoke:

```bash
python scripts/label_guardian_run_ingestion.py \
  --source official \
  --selector kitti \
  --scenario baseline_easy \
  --bucket gs://label_guardian_bucket/datasets/official/kitti/object \
  --storage-prefix smoke \
  --max-images 5 \
  --gcp-project ai-lab-16-gcp-505508 \
  --kitti-login-with-browser
```

## Golden Dataset Acceptance Criteria

A dataset can be called golden only when:

- GCS objects exist under the canonical `datasets/official/...` prefix.
- Every `qa_images.storage_key` points to an existing GCS object.
- Normalized labels exist in `qa_objects`.
- Provenance exists in `qa_object_provenance`.
- The backend can list images through `/api/v1/dataset/images`.
- The backend can stream image content through `/content`.
- For nuScenes, selected frame groups preserve synchronized camera views.
- For KITTI object, frames use `sequence-default/<frame_id>/CAM_FRONT.png`.
- No real secrets are committed to Git or documented in examples.

## Verification

Check backend:

```bash
curl "http://127.0.0.1:8000/api/v1/dataset/images?split=smoke&limit=2"
```

Check QA queue:

```bash
curl "http://127.0.0.1:8000/api/v1/qa-cases?limit=200&sourceType=local_dataset"
```

Check through Vite proxy:

```bash
curl "http://127.0.0.1:5173/api/v1/dataset/images?split=smoke&limit=2"
```

Healthy state:

- Dataset list returns cloud-backed image records.
- Image content endpoint returns image bytes.
- QA queue may return `count: 0` until evaluations are persisted.

Integrity check:

```bash
python - <<'PY'
import os
from dotenv import load_dotenv
from google.cloud import storage
from sqlalchemy import create_engine, text

load_dotenv(".env")
url = os.environ["LABEL_GUARDIAN_DATABASE_URL"]
sync = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1).replace(
    "postgresql://", "postgresql+psycopg://", 1
)
engine = create_engine(sync, connect_args={"prepare_threshold": None})
bucket = storage.Client(project=os.environ["LABEL_GUARDIAN_GCS_PROJECT"]).bucket(
    os.environ["LABEL_GUARDIAN_GCS_BUCKET"]
)
with engine.connect() as conn:
    rows = conn.execute(text("select source_image_id, storage_key from qa_images")).all()
missing = [(image_id, key) for image_id, key in rows if not key or not bucket.blob(key).exists()]
print({"db_images": len(rows), "missing_objects": len(missing)})
PY
```
