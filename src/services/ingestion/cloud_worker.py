"""Cloud Batch worker for official KITTI/nuScenes ingestion."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tarfile
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from mimetypes import guess_type
from pathlib import Path
from typing import Any, BinaryIO, Literal, Protocol, cast

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.config import IngestionSettings
from src.models.ingestion import (
    IngestionAsset,
    IngestionJob,
    IngestionJobEvent,
    IngestionJobStatus,
    IngestionPhase,
    QAImage,
    QAObject,
    QAObjectPayload,
    QAObjectProvenance,
)
from src.services.ingestion.ingestion_service import create_object_storage_client, create_session_factory
from src.services.ingestion.kitti_adapter import ImageMetadata, KittiAdapter
from src.services.ingestion.nuscenes_adapter import NUSCENES_CAMERA_CHANNEL_ORDER, NuScenesAdapter
from src.services.ingestion.official_dataset_downloader import (
    NUSCENES_MINI_URL,
    DatasetDownloadError,
    _format_bytes,
    _safe_extract_tar,
)


class CloudStorageClient(Protocol):
    def upload_file(self, filename: str, bucket: str, key: str, **kwargs: Any) -> None: ...

    def download_file(self, bucket: str, key: str, filename: str) -> None: ...

    def object_exists(self, bucket: str, key: str) -> bool: ...

    def copy_object(self, bucket: str, source_key: str, destination_key: str) -> None: ...

    def list_objects(self, bucket: str, prefix: str) -> list[str]: ...

    def object_size(self, bucket: str, key: str) -> int | None: ...

    def open_reader(self, bucket: str, key: str) -> BinaryIO: ...


class CloudIngestionRequest(BaseModel):
    """Serializable request passed from Workflows/Cloud Run to Cloud Batch."""

    dataset_type: Literal["kitti", "nuscenes"]
    release: str | None = None
    split: str = "smoke"
    max_frames: int | None = Field(default=None, ge=1)
    source: Literal["official"] = "official"
    requested_by: str | None = None
    publish: bool = True
    run_id: str | None = None
    raw_urls: dict[str, str] = Field(default_factory=dict)
    max_blob_archives: int | None = Field(default=None, ge=1, le=10)
    modalities: list[Literal["camera", "labels", "calibration", "lidar"]] = Field(
        default_factory=lambda: ["camera", "labels", "calibration"]
    )

    @property
    def normalized_release(self) -> str:
        if self.release:
            return self.release
        return "v1.0-mini" if self.dataset_type == "nuscenes" else "object"

    @property
    def stable_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        payload = self.model_dump(mode="json", exclude={"run_id"})
        rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        import hashlib

        return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:16]

    @property
    def includes_lidar(self) -> bool:
        return "lidar" in self.modalities

    @property
    def is_nuscenes_full_release(self) -> bool:
        return self.dataset_type == "nuscenes" and self.normalized_release in {"v1.0-trainval", "v1.0-test"}


class ValidationReport(BaseModel):
    run_id: str
    dataset_type: str
    release: str
    split: str
    staging_prefix: str
    canonical_prefix: str
    raw_archives: list[dict[str, object]]
    images: int
    objects: int
    pointclouds: int = 0
    calibration_files: int = 0
    frame_groups: dict[str, int]
    passed: bool
    errors: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class NormalizedPayload:
    dataset_root: Path
    images: list[ImageMetadata]
    objects: list[QAObjectPayload]


@dataclass(frozen=True)
class WorkerResult:
    run_id: str
    job_id: int | None
    validation: ValidationReport | None
    published: bool


class CloudIngestionWorker:
    """Run official dataset ingestion entirely inside cloud compute."""

    def __init__(
        self,
        *,
        settings: IngestionSettings,
        storage_client: CloudStorageClient,
        session_factory: sessionmaker[Session] | None = None,
        scratch_root: Path = Path("/tmp/label-guardian-cloud-worker"),
    ) -> None:
        self.settings = settings
        self.storage_client = storage_client
        self.session_factory = session_factory
        self.scratch_root = scratch_root

    def run(self, request: CloudIngestionRequest, phase: Literal["stage", "normalize", "validate", "publish", "all"]) -> WorkerResult:
        job_id = self._create_job(request) if self.session_factory else None
        try:
            self._record_event(job_id, IngestionPhase.RESOLVE_SOURCE, IngestionJobStatus.RUNNING, "Cloud worker started.")
            if phase in {"stage", "all"}:
                self._record_event(job_id, IngestionPhase.ACQUIRE_RAW, IngestionJobStatus.RUNNING, "Staging raw archives.")
                self.stage_raw(request)
            payload: NormalizedPayload | None = None
            if phase in {"normalize", "all"}:
                self._record_event(job_id, IngestionPhase.ADAPT, IngestionJobStatus.RUNNING, "Normalizing dataset.")
                payload = self.normalize_to_staging(request)
            validation: ValidationReport | None = None
            if phase in {"validate", "publish", "all"}:
                self._record_event(job_id, IngestionPhase.FINALIZE, IngestionJobStatus.RUNNING, "Validating staging output.")
                validation = self.validate(request)
            if phase in {"publish", "all"}:
                if validation is None:
                    validation = self.validate(request)
                if not validation.passed:
                    raise RuntimeError(f"Validation failed: {'; '.join(validation.errors)}")
                self.publish(request, payload=payload)
            self._complete_job(job_id, validation)
            return WorkerResult(
                run_id=request.stable_run_id,
                job_id=job_id,
                validation=validation,
                published=phase in {"publish", "all"} and request.publish,
            )
        except Exception as error:
            self._fail_job(job_id, str(error))
            raise

    def stage_raw(self, request: CloudIngestionRequest) -> list[str]:
        self._record_event(None, IngestionPhase.ACQUIRE_RAW, IngestionJobStatus.RUNNING, "Staging raw archives.")
        staged: list[str] = []
        for archive_name, raw_key in self.raw_archive_keys(request).items():
            if self.storage_client.object_exists(self.settings.bucket_name, raw_key):
                staged.append(raw_key)
                continue
            url = self._source_url(request, archive_name)
            if not url:
                raise RuntimeError(f"Missing official source URL for {archive_name}.")
            scratch_archive = self._scratch_path(request) / "stage" / archive_name
            self._download_url(url, scratch_archive)
            self.storage_client.upload_file(
                str(scratch_archive),
                self.settings.bucket_name,
                raw_key,
                ExtraArgs={"ContentType": guess_type(archive_name)[0] or "application/octet-stream"},
            )
            scratch_archive.unlink(missing_ok=True)
            staged.append(raw_key)
        self._write_checkpoint(request, "stage", {"raw_archives": staged})
        return staged

    def normalize_to_staging(self, request: CloudIngestionRequest) -> NormalizedPayload:
        self._record_event(None, IngestionPhase.ADAPT, IngestionJobStatus.RUNNING, "Normalizing dataset into staging.")
        if self._staging_payload_exists(request):
            images, objects = self._load_payload_from_staging(request)
            self._write_checkpoint(
                request,
                "normalize",
                {"resumed": True, "images": len(images), "objects": len(objects), "staging_prefix": self.staging_prefix(request)},
            )
            return NormalizedPayload(dataset_root=self._scratch_path(request) / "dataset", images=images, objects=objects)
        dataset_root = self._materialize_raw_dataset(request)
        if request.dataset_type == "nuscenes":
            images, objects = NuScenesAdapter(
                dataset_root,
                request.normalized_release,
                max_images=request.max_frames,
            ).load()
        else:
            images, objects = KittiAdapter(dataset_root, split=request.split).load()
            if request.max_frames is not None:
                images, objects = self._limit_images(images, objects, request.max_frames)
        payload = NormalizedPayload(dataset_root=dataset_root, images=images, objects=objects)
        self._upload_normalized_payload(request, payload, self.staging_prefix(request))
        if request.dataset_type == "kitti" and request.includes_lidar:
            self._upload_kitti_3d_artifacts(request, payload, self.staging_prefix(request))
        if request.dataset_type == "nuscenes" and request.includes_lidar:
            self._upload_nuscenes_3d_artifacts(request, payload, self.staging_prefix(request))
        self._write_checkpoint(
            request,
            "normalize",
            {"resumed": False, "images": len(images), "objects": len(objects), "staging_prefix": self.staging_prefix(request)},
        )
        return payload

    def validate(self, request: CloudIngestionRequest) -> ValidationReport:
        staging_prefix = self.staging_prefix(request)
        manifest = self._read_json(f"{staging_prefix}/manifests/ingest_manifest.json")
        images = [ImageMetadata(**row) for row in self._read_jsonl(f"{staging_prefix}/manifests/image_manifest.jsonl")]
        objects = [QAObjectPayload.model_validate(row) for row in self._read_jsonl(f"{staging_prefix}/annotations/normalized_objects.jsonl")]
        raw_archives = []
        errors: list[str] = []
        for archive_name, key in self.raw_archive_keys(request).items():
            size = self.storage_client.object_size(self.settings.bucket_name, key)
            raw_archives.append({"name": archive_name, "storage_key": key, "size_bytes": size})
            if size is None:
                errors.append(f"Missing raw archive: {key}")
        frame_objects = self.storage_client.list_objects(self.settings.bucket_name, f"{staging_prefix}/frames/")
        expected_frame_objects = [f"{staging_prefix}/frames/{image.storage_filename or image.filename}" for image in images]
        missing_objects = [key for key in expected_frame_objects if key not in set(frame_objects)]
        if missing_objects:
            errors.append(f"Missing normalized frame objects: {len(missing_objects)}")
        pointcloud_count = 0
        calibration_count = 0
        if request.includes_lidar:
            pointcloud_count = len(self.storage_client.list_objects(self.settings.bucket_name, f"{staging_prefix}/pointclouds/"))
            calibration_count = len(self.storage_client.list_objects(self.settings.bucket_name, f"{staging_prefix}/calibration/"))
        frame_groups = self._frame_groups(images)
        if request.includes_lidar:
            expected_3d_count = len(images) if request.dataset_type == "kitti" else len(frame_groups)
            if pointcloud_count != expected_3d_count:
                errors.append(f"Expected {expected_3d_count} {request.dataset_type} point cloud object(s), got {pointcloud_count}")
            if calibration_count != expected_3d_count:
                errors.append(f"Expected {expected_3d_count} {request.dataset_type} calibration object(s), got {calibration_count}")
        if request.max_frames is not None and len(frame_groups) != request.max_frames:
            errors.append(f"Expected {request.max_frames} frame group(s), got {len(frame_groups)}")
        if request.dataset_type == "nuscenes":
            invalid_camera_sets = self._invalid_nuscenes_camera_sets(images)
            if invalid_camera_sets:
                errors.append(f"nuScenes frame groups must contain exactly 6 synchronized camera views: {invalid_camera_sets}")
        if not images:
            errors.append("No normalized images were produced.")
        if not objects:
            errors.append("No normalized objects were produced.")
        if manifest.get("images") != len(images) or manifest.get("objects") != len(objects):
            errors.append("Manifest counts do not match normalized files.")
        report = ValidationReport(
            run_id=request.stable_run_id,
            dataset_type=request.dataset_type,
            release=request.normalized_release,
            split=request.split,
            staging_prefix=staging_prefix,
            canonical_prefix=self.canonical_prefix(request),
            raw_archives=raw_archives,
            images=len(images),
            objects=len(objects),
            pointclouds=pointcloud_count,
            calibration_files=calibration_count,
            frame_groups=frame_groups,
            passed=not errors,
            errors=errors,
        )
        self._write_json(f"ops/ingestion-runs/{request.stable_run_id}/validation.json", report.model_dump(mode="json"))
        self._write_checkpoint(request, "validate", {"passed": report.passed, "errors": report.errors})
        return report

    def publish(self, request: CloudIngestionRequest, *, payload: NormalizedPayload | None = None) -> None:
        if not request.publish:
            return
        result_key = f"ops/ingestion-runs/{request.stable_run_id}/result.json"
        if self.storage_client.object_exists(self.settings.bucket_name, result_key):
            if self.session_factory is not None:
                images, objects = self._load_payload_from_staging(request) if payload is None else (payload.images, payload.objects)
                self._persist_metadata(request, images, objects)
            self._write_checkpoint(request, "publish", {"resumed": True, "result": result_key})
            return
        self._record_event(None, IngestionPhase.PERSIST, IngestionJobStatus.RUNNING, "Publishing canonical dataset.")
        staging_prefix = self.staging_prefix(request)
        canonical_prefix = self.canonical_prefix(request)
        for source_key in self.storage_client.list_objects(self.settings.bucket_name, f"{staging_prefix}/"):
            destination_key = f"{canonical_prefix}/{source_key.removeprefix(staging_prefix + '/')}"
            self.storage_client.copy_object(self.settings.bucket_name, source_key, destination_key)
        images, objects = self._load_payload_from_staging(request) if payload is None else (payload.images, payload.objects)
        self._persist_metadata(request, images, objects)
        self._write_json(
            result_key,
            {
                "run_id": request.stable_run_id,
                "published": True,
                "canonical_prefix": canonical_prefix,
                "images": len(images),
                "objects": len(objects),
            },
        )
        self._write_checkpoint(request, "publish", {"resumed": False, "result": result_key})

    def raw_archive_keys(self, request: CloudIngestionRequest) -> dict[str, str]:
        if request.dataset_type == "nuscenes":
            if request.normalized_release == "v1.0-trainval":
                blob_count = request.max_blob_archives or 10
                archive_names = ["v1.0-trainval_meta.tgz"] + [
                    f"v1.0-trainval{index:02d}_blobs.tgz" for index in range(1, blob_count + 1)
                ]
            elif request.normalized_release == "v1.0-test":
                archive_names = ["v1.0-test_meta.tgz", "v1.0-test_blobs.tgz"]
            else:
                archive_names = ["v1.0-mini.tgz"]
            return {
                archive_name: f"raw/official/nuscenes/{request.normalized_release}/archives/{archive_name}"
                for archive_name in archive_names
            }
        archives = {
            name: f"raw/official/kitti/object/archives/{name}"
            for name in (
                "data_object_image_2.zip",
                "data_object_label_2.zip",
                "data_object_calib.zip",
            )
        }
        if request.includes_lidar:
            archives["data_object_velodyne.zip"] = "raw/official/kitti/object/archives/data_object_velodyne.zip"
        return archives

    def staging_prefix(self, request: CloudIngestionRequest) -> str:
        return (
            f"datasets/staging/{request.stable_run_id}/official/"
            f"{request.dataset_type}/{request.normalized_release}/{request.split}"
        )

    def canonical_prefix(self, request: CloudIngestionRequest) -> str:
        return f"datasets/official/{request.dataset_type}/{request.normalized_release}/{request.split}"

    def _materialize_raw_dataset(self, request: CloudIngestionRequest) -> Path:
        root = self._scratch_path(request)
        shutil.rmtree(root / "dataset", ignore_errors=True)
        archive_root = root / "archives"
        dataset_root = root / "dataset" / ("nuscenes" if request.dataset_type == "nuscenes" else "kitti_object")
        archive_keys = self.raw_archive_keys(request)
        selected_kitti_frames: set[str] | None = None
        for key in archive_keys.values():
            if not self.storage_client.object_exists(self.settings.bucket_name, key):
                raise RuntimeError(f"Missing raw archive in GCS: gs://{self.settings.bucket_name}/{key}")
        if request.dataset_type == "kitti" and request.max_frames is not None:
            image_key = archive_keys["data_object_image_2.zip"]
            with self.storage_client.open_reader(self.settings.bucket_name, image_key) as image_archive:
                selected_kitti_frames = self._selected_kitti_frame_ids_from_zip(image_archive, request.max_frames)
        for archive_name, key in archive_keys.items():
            if request.dataset_type == "nuscenes":
                archive_path = archive_root / archive_name
                self.storage_client.download_file(self.settings.bucket_name, key, str(archive_path))
                if request.is_nuscenes_full_release:
                    self._extract_nuscenes_archive(
                        archive_path,
                        dataset_root,
                        request=request,
                        selected_sensor_files=self._selected_nuscenes_sensor_files(dataset_root, request),
                    )
                else:
                    _safe_extract_tar(archive_path, dataset_root)
                archive_path.unlink(missing_ok=True)
            else:
                with self.storage_client.open_reader(self.settings.bucket_name, key) as archive:
                    self._extract_kitti_archive_subset(
                        archive,
                        dataset_root,
                        archive_name=archive_name,
                        frame_ids=selected_kitti_frames,
                        include_lidar=request.includes_lidar,
                    )
        return dataset_root

    def _extract_nuscenes_archive(
        self,
        archive_path: Path,
        destination: Path,
        *,
        request: CloudIngestionRequest,
        selected_sensor_files: set[str] | None,
    ) -> None:
        if archive_path.name.endswith("_meta.tgz"):
            _safe_extract_tar(archive_path, destination)
            return
        if request.max_frames is None:
            _safe_extract_tar(archive_path, destination)
            return
        if selected_sensor_files is None:
            raise RuntimeError("nuScenes metadata must be extracted before blob archives for selective full-release ingest.")
        self._safe_extract_tar_subset(archive_path, destination, selected_sensor_files)

    @staticmethod
    def _safe_extract_tar_subset(archive_path: Path, destination: Path, selected_names: set[str]) -> None:
        try:
            with tarfile.open(archive_path) as archive:
                for member in archive.getmembers():
                    if member.issym() or member.islnk():
                        raise DatasetDownloadError(
                            f"Refusing to extract archive link outside the trusted dataset contract: {member.name}"
                        )
                    normalized_name = member.name.removeprefix("./")
                    target = destination / normalized_name
                    try:
                        target.resolve().relative_to(destination.resolve())
                    except ValueError as error:
                        raise DatasetDownloadError(f"Archive member escapes destination: {target}") from error
                    if member.isdir() or normalized_name not in selected_names:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        continue
                    with source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
        except (EOFError, OSError, tarfile.TarError) as error:
            raise DatasetDownloadError(f"Could not extract nuScenes archive subset: {archive_path}: {error}") from error

    def _selected_nuscenes_sensor_files(
        self,
        dataset_root: Path,
        request: CloudIngestionRequest,
    ) -> set[str] | None:
        if request.max_frames is None:
            return None
        metadata_root = dataset_root / request.normalized_release
        sample_path = metadata_root / "sample.json"
        sample_data_path = metadata_root / "sample_data.json"
        calibrated_sensor_path = metadata_root / "calibrated_sensor.json"
        sensor_path = metadata_root / "sensor.json"
        if not sample_path.is_file() or not sample_data_path.is_file():
            return None
        samples = json.loads(sample_path.read_text(encoding="utf-8"))
        sample_data = json.loads(sample_data_path.read_text(encoding="utf-8"))
        calibrated = {
            row["token"]: row
            for row in json.loads(calibrated_sensor_path.read_text(encoding="utf-8"))
        } if calibrated_sensor_path.is_file() else {}
        sensors = {
            row["token"]: row
            for row in json.loads(sensor_path.read_text(encoding="utf-8"))
        } if sensor_path.is_file() else {}
        selected_sample_tokens = [
            row["token"]
            for row in sorted(samples, key=lambda sample: (sample.get("timestamp", 0), sample.get("token", "")))[: request.max_frames]
        ]
        selected: set[str] = set()
        for row in sample_data:
            if row.get("sample_token") not in selected_sample_tokens or not row.get("is_key_frame", True):
                continue
            filename = str(row.get("filename", "")).removeprefix("./")
            if not filename.startswith("samples/"):
                continue
            sensor = calibrated.get(row.get("calibrated_sensor_token", ""), {})
            sensor_metadata = sensors.get(sensor.get("sensor_token", ""), {})
            modality = sensor_metadata.get("modality")
            is_camera = modality in (None, "camera") and bool(sensor.get("camera_intrinsic"))
            is_lidar = modality == "lidar" or "/LIDAR_TOP/" in filename
            if is_camera or (request.includes_lidar and is_lidar):
                selected.add(filename)
        return selected

    def _staging_payload_exists(self, request: CloudIngestionRequest) -> bool:
        prefix = self.staging_prefix(request)
        return (
            self.storage_client.object_exists(self.settings.bucket_name, f"{prefix}/manifests/ingest_manifest.json")
            and self.storage_client.object_exists(self.settings.bucket_name, f"{prefix}/manifests/image_manifest.jsonl")
            and self.storage_client.object_exists(self.settings.bucket_name, f"{prefix}/annotations/normalized_objects.jsonl")
        )

    @staticmethod
    def _selected_kitti_frame_ids(image_archive: Path, max_frames: int | None) -> set[str] | None:
        if max_frames is None:
            return None
        with image_archive.open("rb") as archive:
            return CloudIngestionWorker._selected_kitti_frame_ids_from_zip(archive, max_frames)

    @staticmethod
    def _selected_kitti_frame_ids_from_zip(image_archive: BinaryIO, max_frames: int | None) -> set[str] | None:
        if max_frames is None:
            return None
        with zipfile.ZipFile(image_archive) as archive:
            frame_ids = [
                Path(member.filename).stem
                for member in archive.infolist()
                if not member.is_dir()
                and member.filename.startswith("training/image_2/")
                and Path(member.filename).suffix.lower() == ".png"
            ]
        return set(sorted(frame_ids)[:max_frames])

    @staticmethod
    def _extract_kitti_archive_subset(
        archive_file: BinaryIO,
        destination: Path,
        *,
        archive_name: str,
        frame_ids: set[str] | None,
        include_lidar: bool,
    ) -> None:
        with zipfile.ZipFile(archive_file) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_path = Path(member.filename)
                if not CloudIngestionWorker._should_extract_kitti_member(
                    member_path,
                    archive_name=archive_name,
                    frame_ids=frame_ids,
                    include_lidar=include_lidar,
                ):
                    continue
                target = destination / member.filename
                try:
                    target.resolve().relative_to(destination.resolve())
                except ValueError as error:
                    raise RuntimeError(f"Archive member escapes destination: {member.filename}") from error
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

    @staticmethod
    def _should_extract_kitti_member(
        member_path: Path,
        *,
        archive_name: str,
        frame_ids: set[str] | None,
        include_lidar: bool,
    ) -> bool:
        parts = member_path.parts
        if len(parts) != 3 or parts[0] != "training":
            return False
        expected_folder = {
            "data_object_image_2.zip": "image_2",
            "data_object_label_2.zip": "label_2",
            "data_object_calib.zip": "calib",
            "data_object_velodyne.zip": "velodyne",
        }.get(archive_name)
        if expected_folder is None or parts[1] != expected_folder:
            return False
        if expected_folder == "velodyne" and not include_lidar:
            return False
        return frame_ids is None or member_path.stem in frame_ids

    def _upload_normalized_payload(self, request: CloudIngestionRequest, payload: NormalizedPayload, prefix: str) -> None:
        for image in payload.images:
            image_path = payload.dataset_root / image.filename
            storage_filename = image.storage_filename or image.filename
            key = f"{prefix}/frames/{storage_filename}"
            self.storage_client.upload_file(
                str(image_path),
                self.settings.bucket_name,
                key,
                ExtraArgs={"ContentType": guess_type(image_path.name)[0] or "application/octet-stream"},
            )
        self._write_jsonl(
            f"{prefix}/manifests/image_manifest.jsonl",
            [
                {
                    "source_image_id": image.source_image_id,
                    "filename": image.filename,
                    "width": image.width,
                    "height": image.height,
                    "storage_filename": image.storage_filename,
                }
                for image in payload.images
            ],
        )
        self._write_jsonl(
            f"{prefix}/annotations/normalized_objects.jsonl",
            [qa_object.model_dump(mode="json") for qa_object in payload.objects],
        )
        self._write_json(
            f"{prefix}/manifests/ingest_manifest.json",
            {
                "run_id": request.stable_run_id,
                "dataset_type": request.dataset_type,
                "release": request.normalized_release,
                "split": request.split,
                "images": len(payload.images),
                "objects": len(payload.objects),
                "pointclouds": self._count_local_kitti_3d_files(payload.dataset_root, payload.images, "velodyne"),
                "calibration_files": self._count_local_kitti_3d_files(payload.dataset_root, payload.images, "calib"),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        self._write_json(f"ops/ingestion-runs/{request.stable_run_id}/request.json", request.model_dump(mode="json"))

    def _upload_kitti_3d_artifacts(self, request: CloudIngestionRequest, payload: NormalizedPayload, prefix: str) -> None:
        for image in payload.images:
            frame_id = Path(image.filename).stem
            pointcloud_path = payload.dataset_root / "training" / "velodyne" / f"{frame_id}.bin"
            calibration_path = payload.dataset_root / "training" / "calib" / f"{frame_id}.txt"
            if not pointcloud_path.is_file():
                raise RuntimeError(f"Missing KITTI LiDAR file for selected frame: {pointcloud_path}")
            if not calibration_path.is_file():
                raise RuntimeError(f"Missing KITTI calibration file for selected frame: {calibration_path}")
            base_key = f"sequence-default/{frame_id}"
            self.storage_client.upload_file(
                str(pointcloud_path),
                self.settings.bucket_name,
                f"{prefix}/pointclouds/{base_key}/LIDAR_TOP.bin",
                ExtraArgs={"ContentType": "application/octet-stream"},
            )
            self.storage_client.upload_file(
                str(calibration_path),
                self.settings.bucket_name,
                f"{prefix}/calibration/{base_key}/calib.txt",
                ExtraArgs={"ContentType": "text/plain"},
            )

    def _upload_nuscenes_3d_artifacts(self, request: CloudIngestionRequest, payload: NormalizedPayload, prefix: str) -> None:
        metadata_root = payload.dataset_root / request.normalized_release
        sample_data_path = metadata_root / "sample_data.json"
        calibrated_sensor_path = metadata_root / "calibrated_sensor.json"
        ego_pose_path = metadata_root / "ego_pose.json"
        sensor_path = metadata_root / "sensor.json"
        if not sample_data_path.is_file():
            raise RuntimeError(f"Missing nuScenes sample_data table for LiDAR upload: {sample_data_path}")
        sample_data = json.loads(sample_data_path.read_text(encoding="utf-8"))
        calibrated = {
            row["token"]: row
            for row in json.loads(calibrated_sensor_path.read_text(encoding="utf-8"))
        } if calibrated_sensor_path.is_file() else {}
        ego_poses = {
            row["token"]: row
            for row in json.loads(ego_pose_path.read_text(encoding="utf-8"))
        } if ego_pose_path.is_file() else {}
        sensors = {
            row["token"]: row
            for row in json.loads(sensor_path.read_text(encoding="utf-8"))
        } if sensor_path.is_file() else {}
        frame_groups: dict[str, str] = {}
        for image in payload.images:
            storage_filename = image.storage_filename or image.filename
            parts = storage_filename.split("/")
            if len(parts) >= 2:
                frame_groups[parts[1]] = parts[0]
        for row in sample_data:
            sample_token = row.get("sample_token")
            if sample_token not in frame_groups or not row.get("is_key_frame", True):
                continue
            filename = str(row.get("filename", ""))
            calibration = calibrated.get(row.get("calibrated_sensor_token", ""), {})
            sensor = sensors.get(calibration.get("sensor_token", ""), {})
            channel = sensor.get("channel") or (Path(filename).parts[-2] if len(Path(filename).parts) >= 2 else "")
            modality = sensor.get("modality")
            if modality != "lidar" and channel != "LIDAR_TOP":
                continue
            pointcloud_path = payload.dataset_root / filename
            if not pointcloud_path.is_file():
                raise RuntimeError(f"Missing nuScenes LiDAR file for selected frame: {pointcloud_path}")
            base_key = f"{frame_groups[sample_token]}/{sample_token}"
            suffix = "".join(pointcloud_path.suffixes) or ".bin"
            self.storage_client.upload_file(
                str(pointcloud_path),
                self.settings.bucket_name,
                f"{prefix}/pointclouds/{base_key}/{channel}{suffix}",
                ExtraArgs={"ContentType": "application/octet-stream"},
            )
            self._write_json(
                f"{prefix}/calibration/{base_key}/{channel}.json",
                {
                    "sample_data": row,
                    "calibrated_sensor": calibration,
                    "ego_pose": ego_poses.get(row.get("ego_pose_token", ""), {}),
                },
            )

    @staticmethod
    def _count_local_kitti_3d_files(dataset_root: Path, images: list[ImageMetadata], folder: str) -> int:
        return sum(
            1
            for image in images
            if (dataset_root / "training" / folder / f"{Path(image.filename).stem}.{'bin' if folder == 'velodyne' else 'txt'}").is_file()
        )

    def _persist_metadata(
        self,
        request: CloudIngestionRequest,
        images: list[ImageMetadata],
        objects: list[QAObjectPayload],
    ) -> None:
        if self.session_factory is None:
            return
        objects_by_image: dict[str, list[QAObjectPayload]] = defaultdict(list)
        for qa_object in objects:
            objects_by_image[qa_object.source_image_id].append(qa_object)
        canonical_prefix = self.canonical_prefix(request)
        current_frame_keys = {
            f"{canonical_prefix}/frames/{image.storage_filename or image.filename}"
            for image in images
        }
        with self.session_factory() as session, session.begin():
            job = self._current_job(session, request)
            for image in images:
                storage_filename = image.storage_filename or image.filename
                object_key = f"{canonical_prefix}/frames/{storage_filename}"
                db_image = session.scalar(
                    select(QAImage).where(
                        QAImage.source_image_id == image.source_image_id,
                        QAImage.dataset == request.dataset_type,
                        QAImage.release == request.normalized_release,
                    )
                )
                if db_image is None:
                    db_image = QAImage(source_image_id=image.source_image_id)
                    session.add(db_image)
                db_image.filename = image.filename
                db_image.width = image.width
                db_image.height = image.height
                db_image.object_url = self.settings.object_uri(object_key)
                db_image.provider = request.dataset_type
                db_image.dataset = request.dataset_type
                db_image.release = request.normalized_release
                db_image.modality = "camera"
                db_image.asset_type = "image"
                db_image.data_format = Path(storage_filename).suffix.lower().lstrip(".") or None
                db_image.storage_key = object_key
                session.flush()
                image_objects = objects_by_image[image.source_image_id]
                self._remove_stale_objects(session, db_image, image_objects)
                for qa_object in image_objects:
                    self._upsert_object(session, db_image, qa_object)
                if job is not None:
                    existing_asset = session.scalar(
                        select(IngestionAsset).where(
                            IngestionAsset.job_id == job.id,
                            IngestionAsset.object_key == object_key,
                        )
                    )
                    if existing_asset is None:
                        session.add(IngestionAsset(job=job, object_key=object_key, status="published"))
            stale_images = (
                session.scalars(
                    select(QAImage).where(
                        QAImage.storage_key.like(f"{canonical_prefix}/frames/%"),
                        QAImage.storage_key.not_in(current_frame_keys),
                    )
                )
            ).all()
            for stale_image in stale_images:
                session.delete(stale_image)

    @staticmethod
    def _source_object_key(qa_case: QAObjectPayload) -> str:
        return "|".join(sorted(f"{entry.source}:{entry.source_annotation_id}" for entry in qa_case.provenance))

    @classmethod
    def _remove_stale_objects(
        cls,
        session: Session,
        image: QAImage,
        cases: list[QAObjectPayload],
    ) -> None:
        incoming_keys = {cls._source_object_key(item) for item in cases}
        existing = session.scalars(select(QAObject).where(QAObject.image_id == image.id)).all()
        for db_object in existing:
            if db_object.source_object_key not in incoming_keys:
                session.delete(db_object)

    @staticmethod
    def _upsert_object(session: Session, image: QAImage, qa_case: QAObjectPayload) -> None:
        source_object_key = CloudIngestionWorker._source_object_key(qa_case)
        db_object = session.scalar(
            select(QAObject).where(QAObject.image_id == image.id, QAObject.source_object_key == source_object_key)
        )
        if db_object is None:
            db_object = QAObject(image=image, source_object_key=source_object_key)
            session.add(db_object)
        db_object.label = qa_case.label
        db_object.xmin = qa_case.bbox.xmin
        db_object.ymin = qa_case.bbox.ymin
        db_object.xmax = qa_case.bbox.xmax
        db_object.ymax = qa_case.bbox.ymax
        db_object.review_status = qa_case.review_status
        db_object.calibration = qa_case.calibration
        db_object.cuboid_corners = qa_case.cuboid_corners
        db_object.provenance_records.clear()
        session.flush()
        for entry in qa_case.provenance:
            db_object.provenance_records.append(
                QAObjectProvenance(
                    source=entry.source,
                    source_annotation_id=entry.source_annotation_id,
                    xmin=entry.bbox.xmin,
                    ymin=entry.bbox.ymin,
                    xmax=entry.bbox.xmax,
                    ymax=entry.bbox.ymax,
                    raw=entry.raw,
                )
            )

    def _load_payload_from_staging(self, request: CloudIngestionRequest) -> tuple[list[ImageMetadata], list[QAObjectPayload]]:
        prefix = self.staging_prefix(request)
        images = [ImageMetadata(**row) for row in self._read_jsonl(f"{prefix}/manifests/image_manifest.jsonl")]
        objects = [QAObjectPayload.model_validate(row) for row in self._read_jsonl(f"{prefix}/annotations/normalized_objects.jsonl")]
        return images, objects

    def _write_json(self, key: str, payload: dict[str, object]) -> None:
        path = self.scratch_root / "objects" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.storage_client.upload_file(
            str(path),
            self.settings.bucket_name,
            key,
            ExtraArgs={"ContentType": "application/json"},
        )

    def _write_checkpoint(self, request: CloudIngestionRequest, phase: str, payload: dict[str, object]) -> None:
        self._write_json(
            f"ops/ingestion-runs/{request.stable_run_id}/checkpoints/{phase}.json",
            {
                "run_id": request.stable_run_id,
                "phase": phase,
                "created_at": datetime.now(UTC).isoformat(),
                **payload,
            },
        )

    def _write_jsonl(self, key: str, rows: list[dict[str, object]]) -> None:
        path = self.scratch_root / "objects" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        self.storage_client.upload_file(
            str(path),
            self.settings.bucket_name,
            key,
            ExtraArgs={"ContentType": "application/jsonl"},
        )

    def _read_json(self, key: str) -> dict[str, Any]:
        path = self.scratch_root / "downloads" / key
        self.storage_client.download_file(self.settings.bucket_name, key, str(path))
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    def _read_jsonl(self, key: str) -> list[dict[str, Any]]:
        path = self.scratch_root / "downloads" / key
        self.storage_client.download_file(self.settings.bucket_name, key, str(path))
        return [cast(dict[str, Any], json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line]

    @staticmethod
    def _frame_groups(images: list[ImageMetadata]) -> dict[str, int]:
        groups: dict[str, int] = defaultdict(int)
        for image in images:
            storage_filename = image.storage_filename or image.filename
            parts = storage_filename.split("/")
            if len(parts) >= 3:
                groups["/".join(parts[:2])] += 1
            else:
                groups[Path(storage_filename).stem] += 1
        return dict(sorted(groups.items()))

    @staticmethod
    def _invalid_nuscenes_camera_sets(images: list[ImageMetadata]) -> dict[str, list[str]]:
        expected_channels = set(NUSCENES_CAMERA_CHANNEL_ORDER)
        groups: dict[str, set[str]] = defaultdict(set)
        for image in images:
            storage_filename = image.storage_filename or image.filename
            parts = storage_filename.split("/")
            if len(parts) < 3:
                groups[Path(storage_filename).stem].add(Path(storage_filename).stem)
                continue
            groups["/".join(parts[:2])].add(Path(parts[2]).stem)
        return {
            group: sorted(channels)
            for group, channels in sorted(groups.items())
            if channels != expected_channels
        }

    @staticmethod
    def _limit_images(
        images: list[ImageMetadata],
        objects: list[QAObjectPayload],
        max_frames: int,
    ) -> tuple[list[ImageMetadata], list[QAObjectPayload]]:
        selected = images[:max_frames]
        selected_ids = {image.source_image_id for image in selected}
        return selected, [obj for obj in objects if obj.source_image_id in selected_ids]

    def _source_url(self, request: CloudIngestionRequest, archive_name: str) -> str | None:
        if archive_name in request.raw_urls:
            return request.raw_urls[archive_name]
        env_name = {
            "data_object_image_2.zip": "KITTI_IMAGE_2_URL",
            "data_object_label_2.zip": "KITTI_LABEL_2_URL",
            "data_object_calib.zip": "KITTI_CALIB_URL",
            "data_object_velodyne.zip": "KITTI_VELODYNE_URL",
        }.get(archive_name)
        if env_name:
            return os.environ.get(env_name)
        if request.dataset_type == "nuscenes":
            return request.raw_urls.get("v1.0-mini.tgz") or os.environ.get("NUSCENES_URL") or NUSCENES_MINI_URL
        return None

    @staticmethod
    def _download_url(url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(url), timeout=120) as response, destination.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            copied = 0
            while chunk := response.read(8 * 1024 * 1024):
                out.write(chunk)
                copied += len(chunk)
                if total:
                    print(f"[stage] {destination.name}: {_format_bytes(copied)} / {_format_bytes(total)}", flush=True)

    def _scratch_path(self, request: CloudIngestionRequest) -> Path:
        return self.scratch_root / request.stable_run_id

    def _create_job(self, request: CloudIngestionRequest) -> int:
        assert self.session_factory is not None
        fingerprint = request.stable_run_id
        with self.session_factory() as session, session.begin():
            existing = session.scalar(select(IngestionJob).where(IngestionJob.request_fingerprint == fingerprint))
            if existing is not None:
                existing.status = IngestionJobStatus.RUNNING
                existing.started_at = datetime.now(UTC)
                existing.finished_at = None
                existing.error_message = None
                existing.result_metrics = {}
                existing.source_manifest = request.model_dump(mode="json")
                existing.target_bucket = self.settings.bucket_name
                existing.target_prefix = self.canonical_prefix(request)
                return int(existing.id)
            job = IngestionJob(
                request_fingerprint=fingerprint,
                requested_by=request.requested_by,
                provider=request.source,
                dataset_type=request.dataset_type,
                version=request.normalized_release,
                split=request.split,
                status=IngestionJobStatus.RUNNING,
                source_manifest=request.model_dump(mode="json"),
                target_bucket=self.settings.bucket_name,
                target_prefix=self.canonical_prefix(request),
                started_at=datetime.now(UTC),
            )
            session.add(job)
            session.flush()
            return int(job.id)

    def _current_job(self, session: Session, request: CloudIngestionRequest) -> IngestionJob | None:
        return cast(
            IngestionJob | None,
            session.scalar(select(IngestionJob).where(IngestionJob.request_fingerprint == request.stable_run_id)),
        )

    def _record_event(
        self,
        job_id: int | None,
        phase: IngestionPhase,
        status: IngestionJobStatus,
        message: str,
        metrics: dict[str, object] | None = None,
    ) -> None:
        if self.session_factory is None or job_id is None:
            return
        with self.session_factory() as session, session.begin():
            job = session.get(IngestionJob, job_id)
            if job is None:
                return
            session.add(
                IngestionJobEvent(
                    job=job,
                    phase=phase,
                    status=status,
                    message=message,
                    metrics=metrics or {},
                )
            )

    def _complete_job(self, job_id: int | None, validation: ValidationReport | None) -> None:
        if self.session_factory is None or job_id is None:
            return
        with self.session_factory() as session, session.begin():
            job = session.get(IngestionJob, job_id)
            if job is None:
                return
            job.status = IngestionJobStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            job.result_metrics = validation.model_dump(mode="json") if validation else {}
            session.add(
                IngestionJobEvent(
                    job=job,
                    phase=IngestionPhase.FINALIZE,
                    status=IngestionJobStatus.COMPLETED,
                    message="Cloud ingestion completed.",
                    metrics=job.result_metrics,
                )
            )

    def _fail_job(self, job_id: int | None, message: str) -> None:
        if self.session_factory is None or job_id is None:
            return
        status = IngestionJobStatus.BLOCKED_CREDENTIALS if "Missing official source URL" in message else IngestionJobStatus.FAILED
        with self.session_factory() as session, session.begin():
            job = session.get(IngestionJob, job_id)
            if job is None:
                return
            job.status = status
            job.error_message = message
            job.finished_at = datetime.now(UTC)
            session.add(
                IngestionJobEvent(
                    job=job,
                    phase=IngestionPhase.FINALIZE,
                    status=status,
                    message=message,
                    metrics={},
                )
            )


def _load_request_from_gcs(uri: str, storage_client: CloudStorageClient, scratch_root: Path) -> CloudIngestionRequest:
    if not uri.startswith("gs://"):
        raise ValueError("--request-gcs-uri must be a gs:// URI.")
    bucket_key = uri.removeprefix("gs://")
    bucket, _, key = bucket_key.partition("/")
    if not bucket or not key:
        raise ValueError("--request-gcs-uri must include bucket and object key.")
    path = scratch_root / "request.json"
    storage_client.download_file(bucket, key, str(path))
    return cast(CloudIngestionRequest, CloudIngestionRequest.model_validate_json(path.read_text(encoding="utf-8")))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Label Guardian cloud ingestion worker phases.")
    parser.add_argument("--request-gcs-uri")
    parser.add_argument("--request-file", type=Path)
    parser.add_argument("--phase", choices=("stage", "normalize", "validate", "publish", "all"), default="all")
    parser.add_argument("--scratch-root", type=Path, default=Path("/tmp/label-guardian-cloud-worker"))
    args = parser.parse_args()
    if not args.request_gcs_uri and not args.request_file:
        parser.error("Provide --request-gcs-uri or --request-file.")
    settings = IngestionSettings()
    storage_client = create_object_storage_client(settings)
    request = (
        _load_request_from_gcs(args.request_gcs_uri, storage_client, args.scratch_root)
        if args.request_gcs_uri
        else CloudIngestionRequest.model_validate_json(args.request_file.read_text(encoding="utf-8"))
    )
    worker = CloudIngestionWorker(
        settings=settings,
        storage_client=storage_client,
        session_factory=create_session_factory(settings.database_url),
        scratch_root=args.scratch_root,
    )
    result = worker.run(request, phase=cast(Literal["stage", "normalize", "validate", "publish", "all"], args.phase))
    print(json.dumps({"run_id": result.run_id, "job_id": result.job_id, "published": result.published}, sort_keys=True))


if __name__ == "__main__":
    main()
