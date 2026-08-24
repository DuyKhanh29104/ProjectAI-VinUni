# GCP Cloud Ingestion Deployment

These templates run Label Guardian dataset ingestion after the workstation is
offline. They assume:

- Project: `ai-lab-16-gcp-505508`
- Bucket: `gs://label_guardian_bucket`
- Worker service account: `label-guardian-ingestion-sa`
- Worker image: `REGION-docker.pkg.dev/ai-lab-16-gcp-505508/label-guardian/label-guardian-ingestion-worker:TAG`

## Required Services

Enable Artifact Registry, Secret Manager, Cloud Storage, Cloud Batch, Cloud
Run, Workflows, Cloud Logging and IAM.

## Required Secrets

Create these Secret Manager entries with real values outside the repo:

```text
supabase-database-url-sync
kitti-image-2-url
kitti-label-2-url
kitti-calib-url
kitti-velodyne-url
```

The Batch templates inject secret values into environment variables. Do not
commit concrete database URLs, KITTI URLs, cookies or service-account keys.

## Build Worker Image

```bash
gcloud artifacts repositories create label-guardian \
  --repository-format=docker \
  --location=asia-southeast1 \
  --project=ai-lab-16-gcp-505508

gcloud builds submit \
  --config deploy/gcp/cloudbuild-ingestion-worker.yaml \
  --project=ai-lab-16-gcp-505508
```

## Run Pattern

1. Write request JSON to `gs://label_guardian_bucket/ops/ingestion-runs/<run_id>/request.json`.
2. Submit a Cloud Batch job from one of the templates.
3. The worker stages raw archives, normalizes into `datasets/staging/<run_id>/...`,
   validates, publishes to `datasets/official/...`, and writes Supabase metadata.
4. Inspect `ops/ingestion-runs/<run_id>/validation.json` and `result.json`.

The worker writes resumable checkpoints under
`ops/ingestion-runs/<run_id>/checkpoints/`. On retry it reuses raw archives
already staged in GCS and reuses normalized staging manifests when they exist.

KITTI smoke requests can include `modalities: ["camera", "labels",
"calibration", "lidar"]`. With `max_frames` set, the worker extracts only the
selected frame IDs from `image_2`, `label_2`, `calib` and `velodyne` instead of
unpacking the full LiDAR archive. Normalized 3D artifacts are written to:

```text
datasets/official/kitti/object/<split>/pointclouds/sequence-default/<frame_id>/LIDAR_TOP.bin
datasets/official/kitti/object/<split>/calibration/sequence-default/<frame_id>/calib.txt
```

Use `batch-parameterized-template.json` for larger/full runs by replacing
`PROJECT_ID`, `REGION`, `BUCKET_NAME`, `RUN_ID` and `TAG`, then uploading a
matching request JSON under `ops/ingestion-runs/RUN_ID/request.json`.

## Scale Profiles

The safe immediate scaling mode is vertical scale-up: run one logical ingestion
task on a larger Batch VM. Do not raise `taskCount` for the same request until
the worker supports explicit shard IDs, because duplicated tasks would write the
same staging prefix and Supabase rows.

Ready-to-use KITTI 3D smoke scale-up:

```bash
gcloud batch jobs submit label-guardian-kitti-smoke-3d-scaleup-$(date +%Y%m%d%H%M) \
  --location asia-southeast1 \
  --config deploy/gcp/batch-kitti-3d-scaleup.json \
  --project ai-lab-16-gcp-505508
```

Use `batch-full-scaleup-template.json` for full runs. It defaults to one
`e2-standard-16` worker with a 1 TB boot disk and a 24 hour max duration. Replace
all placeholders before submission:

```bash
cp deploy/gcp/batch-full-scaleup-template.json /tmp/batch-full-scaleup.json
sed -i \
  -e 's/PROJECT_ID/ai-lab-16-gcp-505508/g' \
  -e 's/REGION/asia-southeast1/g' \
  -e 's/BUCKET_NAME/label_guardian_bucket/g' \
  -e 's/RUN_ID/<run_id>/g' \
  -e 's/TAG/latest/g' \
  /tmp/batch-full-scaleup.json
```

Multiple datasets can run in parallel as separate jobs, for example one KITTI
run and one nuScenes run. Multiple VMs inside one dataset run require a
follow-up sharding design where each task owns a non-overlapping scene/frame
range and publishes through a single finalizer.

## Full nuScenes Source Links

For `v1.0-mini`, the public URL is already supported by the worker. For full
nuScenes train/val, use the public AWS Open Data/CloudFront mirror instead of
browser download buttons. The checked-in smoke request contains public
CloudFront URLs for the 11 trainval archives, so Cloud Batch can stage raw data
directly to GCS without routing bytes through a PC.

Upload the request and start the cloud smoke:

```bash
gcloud storage cp deploy/gcp/request-nuscenes-trainval-smoke.json \
  gs://label_guardian_bucket/ops/ingestion-runs/nuscenes-trainval-smoke/request.json \
  --project ai-lab-16-gcp-505508

gcloud batch jobs submit label-guardian-nuscenes-trainval-smoke-$(date +%Y%m%d%H%M) \
  --location asia-southeast1 \
  --config deploy/gcp/batch-nuscenes-trainval-scaleup.json \
  --project ai-lab-16-gcp-505508
```

The smoke request sets `max_blob_archives: 1`, so the worker stages metadata
plus `v1.0-trainval01_blobs.tgz` only. This is enough for a fast first
end-to-end proof when the selected frames live in blob01. Remove
`max_blob_archives` for a full trainval run. The worker selectively extracts the
requested frame groups when `max_frames` is set, then publishes normalized
camera frames and LiDAR artifacts under `datasets/official/...`.

If the AWS mirror is unavailable and official website links are required:

1. Register and log in at `https://www.nuscenes.org/nuscenes`.
2. Open **Downloads** and choose the `v1.0-trainval` release.
3. Copy the link address for the metadata archive and every trainval blob
   archive. The expected archive set is:

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

4. Store these URLs in Secret Manager or an ops-only request object. Do not add
   them to `.env.example`, docs or committed request files.
