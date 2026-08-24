"""Cloud-ready orchestration for dataset ingestion jobs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.config import IngestionSettings
from src.models.ingestion import (
    IngestionAsset,
    IngestionJob,
    IngestionJobEvent,
    IngestionJobStatus,
    IngestionPhase,
)
from src.services.ingestion.dataset_selector import DatasetType, scenario_for_dataset, select_dataset_layout
from src.services.ingestion.ingestion_service import IngestionResult, IngestionService
from src.services.ingestion.nuscenes_adapter import NuScenesAdapter
from src.services.ingestion.official_dataset_downloader import (
    download_official_kitti_object,
    download_official_nuscenes,
)


class IngestionJobRequest(BaseModel):
    """User request for a local-first, cloud-ready ingestion job."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: str = "local"
    dataset_type: str
    scenario: str | None = None
    topic: str = "2d"
    city: str = "any"
    time_of_day: str = "any"
    dataset_root: Path | None = None
    version: str | None = None
    split: str | None = None
    requested_by: str | None = None
    download_official: bool = False
    download_root: Path = Path("data/raw")
    target_prefix: str = ""
    source_manifest: dict[str, Any] = Field(default_factory=dict)
    strict_layout: bool = True

    def fingerprint(self, bucket: str) -> str:
        payload = self.model_dump(mode="json")
        payload["target_bucket"] = bucket
        rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompletedIngestionJob:
    job_id: int
    result: IngestionResult


class IngestionAutomationService:
    """Create and run ingestion jobs using local resources or cloud-compatible clients."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        storage_client: Any,
        settings: IngestionSettings,
    ) -> None:
        self.session_factory = session_factory
        self.storage_client = storage_client
        self.settings = settings

    def create_job(self, request: IngestionJobRequest) -> IngestionJob:
        fingerprint = request.fingerprint(self.settings.bucket_name)
        with self.session_factory() as session, session.begin():
            existing = session.scalar(select(IngestionJob).where(IngestionJob.request_fingerprint == fingerprint))
            if existing is not None:
                return cast(IngestionJob, existing)
            job = IngestionJob(
                request_fingerprint=fingerprint,
                requested_by=request.requested_by,
                provider=request.provider,
                dataset_type=request.dataset_type,
                version=request.version,
                split=request.split,
                status=IngestionJobStatus.PENDING,
                source_manifest=request.source_manifest,
                target_bucket=self.settings.bucket_name,
                target_prefix=request.target_prefix.strip("/"),
            )
            session.add(job)
            session.flush()
            self._add_event(
                session,
                job,
                phase=IngestionPhase.REQUESTED,
                status=IngestionJobStatus.PENDING,
                message="Ingestion job accepted.",
            )
            return job

    def run_job(self, job_id: int, request: IngestionJobRequest) -> CompletedIngestionJob:
        with self.session_factory() as session, session.begin():
            job = session.get(IngestionJob, job_id)
            if job is None:
                raise ValueError(f"Ingestion job does not exist: {job_id}")
            job.status = IngestionJobStatus.RUNNING
            job.started_at = datetime.now(UTC)
            self._add_event(
                session,
                job,
                phase=IngestionPhase.RESOLVE_SOURCE,
                status=IngestionJobStatus.RUNNING,
                message="Resolving dataset source.",
            )
        try:
            dataset_root = self._resolve_dataset_root(request)
            result = self._run_adapter_ingestion(dataset_root, request)
        except Exception as error:
            with self.session_factory() as session, session.begin():
                job = session.get(IngestionJob, job_id)
                assert job is not None
                job.status = IngestionJobStatus.FAILED
                job.error_message = str(error)
                job.finished_at = datetime.now(UTC)
                self._add_event(
                    session,
                    job,
                    phase=IngestionPhase.FINALIZE,
                    status=IngestionJobStatus.FAILED,
                    message=str(error),
                )
            raise
        with self.session_factory() as session, session.begin():
            job = session.get(IngestionJob, job_id)
            assert job is not None
            job.status = IngestionJobStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            job.result_metrics = {
                "images": result.images,
                "objects": result.objects,
                "uploads": result.uploads,
            }
            session.add(
                IngestionAsset(
                    job=job,
                    object_key=f"{job.target_prefix}/manifests/result.json".lstrip("/"),
                    status="created",
                )
            )
            self._add_event(
                session,
                job,
                phase=IngestionPhase.FINALIZE,
                status=IngestionJobStatus.COMPLETED,
                message="Ingestion job completed.",
                metrics=job.result_metrics,
            )
        return CompletedIngestionJob(job_id=job_id, result=result)

    def create_and_run(self, request: IngestionJobRequest) -> CompletedIngestionJob:
        job = self.create_job(request)
        return self.run_job(job.id, request)

    def _resolve_dataset_root(self, request: IngestionJobRequest) -> Path:
        if not request.download_official:
            if request.dataset_root is None:
                raise ValueError("dataset_root is required when download_official is false")
            return request.dataset_root
        if request.dataset_type == "kitti":
            downloaded = download_official_kitti_object(request.download_root)
        elif request.dataset_type == "nuscenes":
            downloaded = download_official_nuscenes(request.download_root, version=request.version or "v1.0-mini")
        else:
            raise ValueError(f"Unsupported dataset_type: {request.dataset_type}")
        return downloaded.dataset_root

    def _run_adapter_ingestion(self, dataset_root: Path, request: IngestionJobRequest) -> IngestionResult:
        selected = select_dataset_layout(
            request.dataset_type,
            dataset_root,
            nuscenes_version=request.version or "v1.0-mini",
            strict=request.strict_layout,
            scenario=request.scenario or scenario_for_dataset(request.dataset_type),
        )
        settings = self.settings.model_copy(
            update={
                "object_key_prefix": request.target_prefix.strip("/"),
                "dataset_provider": request.dataset_type,
                "dataset_name": request.dataset_type,
                "dataset_release": request.version,
            }
        )
        service = IngestionService(
            selected.dataset_root,
            self.session_factory,
            self.storage_client,
            settings,
            dataset_split=request.split,
        )
        if selected.dataset_type == DatasetType.KITTI:
            return service.ingest()
        if selected.dataset_type == DatasetType.NUSCENES:
            images, cases = NuScenesAdapter(selected.dataset_root, selected.version or "v1.0-mini").load()
            return service.ingest_normalized(images, cases)
        raise ValueError(f"Unsupported dataset_type: {request.dataset_type}")

    @staticmethod
    def _add_event(
        session: Session,
        job: IngestionJob,
        *,
        phase: IngestionPhase,
        status: IngestionJobStatus,
        message: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            IngestionJobEvent(
                job=job,
                phase=phase,
                status=status,
                message=message,
                metrics=metrics or {},
            )
        )
