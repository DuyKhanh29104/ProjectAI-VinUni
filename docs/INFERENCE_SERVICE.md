# Inference Service

Inference Service is an optional detector runtime separate from the App Service. The
App Service keeps auth, DB workflow, annotation revisions and QA case creation.
Inference Service owns:

```text
GCS image reference -> read private GCS object -> preprocess -> YOLO -> detections JSON
```

## App Service env

Set these on the Railway/GCP VM App Service:

```env
INFERENCE_MODE=remote
INFERENCE_SERVICE_URL=https://<inference-service-url>
INFERENCE_SERVICE_TOKEN=<shared-secret>
INFERENCE_REQUEST_TIMEOUT_SECONDS=180
```

When remote mode is enabled, `/api/v1/dataset/images/{split}/{imageId}/evaluate`
sends only `datasetId`, `datasetVersion`, `split`, `imageId`, `bucket` and
`objectKey` to Inference Service. It does not download and forward image bytes.

## Inference Service env

Set these on Cloud Run GPU, Modal or another GPU host:

```env
INFERENCE_APP_ENV=production
INFERENCE_AUTH_TOKEN=<same-shared-secret-as-app>
INFERENCE_MODEL_NAME=gs://<bucket>/models/yolo26x.pt
INFERENCE_MODEL_VERSION=yolo26x@2026-08-27
INFERENCE_CONFIDENCE_THRESHOLD=0.25
INFERENCE_ALLOWED_OBJECT_PREFIXES=datasets/official
INFERENCE_MAX_BATCH_SIZE=64

LABEL_GUARDIAN_GCS_BUCKET=<bucket>
LABEL_GUARDIAN_GCS_PROJECT=<gcp-project>
# Use keyless ADC/workload identity where possible. JSON is supported for CI.
# LABEL_GUARDIAN_GCS_CREDENTIALS_JSON={"type":"service_account",...}
```

`INFERENCE_MODEL_NAME` can be a local path/model name or a `gs://...` artifact.
For `gs://...`, the service downloads the checkpoint into
`INFERENCE_MODEL_CACHE_DIR` before loading it.

## Run locally

```powershell
python -m pip install -e ".[cloud,agent-yolo]" --group dev
python -m uvicorn src.inference_app:app --host 127.0.0.1 --port 8010
```

Then point the App Service at it:

```env
INFERENCE_MODE=remote
INFERENCE_SERVICE_URL=http://127.0.0.1:8010
INFERENCE_SERVICE_TOKEN=<shared-secret>
```

## Container

App Service:

```powershell
docker build -f Dockerfile -t label-guardian-app .
```

The existing App Service image retains its CPU detector for local mode.
Set `INFERENCE_MODE=remote` explicitly to use the separate service. Production
inference refuses to start without `INFERENCE_AUTH_TOKEN`.

Inference Service:

```powershell
docker build -f Dockerfile.inference-service -t label-guardian-inference .
```

## Contract

The App Service exposes `POST /api/v1/dataset/images/{split}/evaluate-batch`
with `{ "imageIds": ["image-1", "image-2"], "persist": true }`. It sends chunks
of up to 64 images to `/v1/detect-batch`, runs QA on each detection result, and
returns per-image successes/errors. A failed item does not abort later items.

`GET /api/v1/dataset/images/{split}/{imageId}/evaluation` reloads the saved
report and predictions for the current annotation revision. Saving or restoring
annotations requires a new evaluation; a missing current report returns 404.
Apply `alembic upgrade head` before using these endpoints. Revisions 0007 and
0008 retain upstream migration history; 0009 adds annotation revision identity.

Request:

```json
{
  "image": {
    "datasetId": "nuscenes",
    "datasetVersion": "v1.0-mini",
    "split": "smoke",
    "imageId": "camera-token",
    "bucket": "label-guardian",
    "objectKey": "datasets/official/nuscenes/v1.0-mini/smoke/frames/scene/sample/CAM_FRONT.jpg"
  },
  "mode": "yolo"
}
```

Response:

```json
{
  "modelName": "gs://label-guardian/models/yolo26x.pt",
  "modelVersion": "yolo26x@2026-08-27",
  "detections": [
    {
      "className": "car",
      "bbox": {"x1": 10.0, "y1": 20.0, "x2": 80.0, "y2": 90.0},
      "confidence": 0.92
    }
  ],
  "latencyMs": {"inference": 18.4},
  "metadata": {}
}
```
