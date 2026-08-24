"""Read-only cloud ingestion pipeline status API."""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import desc, select

from src.api.dependencies import require_roles
from src.config import IngestionSettings
from src.models.base_schemas import ApiModel
from src.models.ingestion import IngestionJob, IngestionJobEvent
from src.services.google_cloud import create_gcs_storage_client

router = APIRouter(
    prefix="/ingestion",
    tags=["Cloud Ingestion"],
    dependencies=[Depends(require_roles("reviewer", "admin"))],
)


class PipelineProgressDto(ApiModel):
    phase: str
    percent: int
    detail: str


class PipelineLogDto(ApiModel):
    timestamp: str | None = None
    message: str


class PipelineEventDto(ApiModel):
    phase: str
    status: str
    message: str
    created_at: str


class PipelineRunDto(ApiModel):
    run_id: str
    dataset_type: str
    release: str | None = None
    split: str | None = None
    status: str
    requested_by: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    batch_job_id: str | None = None
    request_gcs_uri: str | None = None
    canonical_prefix: str | None = None
    images: int = 0
    objects: int = 0
    stages: list[PipelineProgressDto] = Field(default_factory=list)
    events: list[PipelineEventDto] = Field(default_factory=list)
    logs: list[PipelineLogDto] = Field(default_factory=list)
    validation: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class PipelineRunListDto(ApiModel):
    count: int
    results: list[PipelineRunDto]


def _settings() -> IngestionSettings:
    return IngestionSettings()


def _read_json(settings: IngestionSettings, key: str) -> dict[str, Any] | None:
    client = create_gcs_storage_client(settings)
    blob = client.bucket(settings.bucket_name).blob(key)
    if not blob.exists(client=client):
        return None
    return cast(dict[str, Any], json.loads(blob.download_as_text()))


def _stage_progress(
    events: list[IngestionJobEvent],
    max_frames: int | None,
    validation: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> list[PipelineProgressDto]:
    seen_phases = {
        str(event.phase.value if hasattr(event.phase, "value") else event.phase)
        for event in events
    }
    failed = any(
        str(event.status.value if hasattr(event.status, "value") else event.status) == "failed"
        for event in events
    )
    images = int((result or validation or {}).get("images", 0) or 0)
    expected = str(max_frames) if max_frames else "?"
    return [
        PipelineProgressDto(
            phase="acquire_raw",
            percent=100 if seen_phases.intersection({"adapt", "persist", "finalize"}) else 10 if "acquire_raw" in seen_phases else 0,
            detail="Raw archives",
        ),
        PipelineProgressDto(
            phase="normalize",
            percent=100 if validation or seen_phases.intersection({"persist", "finalize"}) else 10 if "adapt" in seen_phases else 0,
            detail=f"{images}/{expected} frames" if images else "Normalized frames",
        ),
        PipelineProgressDto(
            phase="validate",
            percent=100 if validation and validation.get("passed") else 0,
            detail="Validation failed" if failed else "Validation",
        ),
        PipelineProgressDto(
            phase="publish",
            percent=100 if result else 10 if "persist" in seen_phases else 0,
            detail=f"{images}/{expected} frames" if images else "Canonical dataset",
        ),
    ]


def _run_from_job(job: IngestionJob) -> PipelineRunDto:
    manifest = job.source_manifest or {}
    run_id = str(manifest.get("run_id") or job.request_fingerprint)
    return PipelineRunDto(
        run_id=run_id,
        dataset_type=job.dataset_type,
        release=job.version,
        split=job.split,
        status=str(job.status.value if hasattr(job.status, "value") else job.status),
        requested_by=job.requested_by,
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        canonical_prefix=job.target_prefix,
        images=int((job.result_metrics or {}).get("images", 0) or 0),
        objects=int((job.result_metrics or {}).get("objects", 0) or 0),
    )


@router.get("/runs", response_model=PipelineRunListDto)
async def list_runs(request: Request, limit: int = 20) -> PipelineRunListDto:
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        jobs = (
            await session.scalars(
                select(IngestionJob).order_by(desc(IngestionJob.created_at)).limit(min(max(limit, 1), 100))
            )
        ).all()
    results = [_run_from_job(job) for job in jobs]
    return PipelineRunListDto(count=len(results), results=results)


@router.get("/runs/{run_id}", response_model=PipelineRunDto)
async def get_run(run_id: str, request: Request) -> PipelineRunDto:
    settings = _settings()
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        job = await session.scalar(select(IngestionJob).where(IngestionJob.request_fingerprint == run_id))
        events = (
            await session.scalars(
                select(IngestionJobEvent)
                .join(IngestionJob)
                .where(IngestionJob.request_fingerprint == run_id)
                .order_by(IngestionJobEvent.created_at)
            )
        ).all()
    request_payload, submission, validation, result = await asyncio.gather(
        asyncio.to_thread(_read_json, settings, f"ops/ingestion-runs/{run_id}/request.json"),
        asyncio.to_thread(_read_json, settings, f"ops/ingestion-runs/{run_id}/submission.json"),
        asyncio.to_thread(_read_json, settings, f"ops/ingestion-runs/{run_id}/validation.json"),
        asyncio.to_thread(_read_json, settings, f"ops/ingestion-runs/{run_id}/result.json"),
    )
    if job is None and request_payload is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    request_data = request_payload or {}
    view = _run_from_job(job) if job else PipelineRunDto(
        run_id=run_id,
        dataset_type=str(request_data.get("dataset_type", "unknown")),
        release=request_data.get("release"),
        split=request_data.get("split"),
        status="submitted",
        requested_by=request_data.get("requested_by"),
    )
    submission = submission or {}
    batch_job_id = submission.get("batch_job_id")
    max_frames = request_payload.get("max_frames") if request_payload else None
    view.batch_job_id = batch_job_id
    view.request_gcs_uri = submission.get("request_gcs_uri") or (
        f"gs://{settings.bucket_name}/ops/ingestion-runs/{run_id}/request.json" if request_payload else None
    )
    view.validation = validation
    view.result = result
    view.images = int((result or validation or {}).get("images", view.images) or 0)
    view.objects = int((result or validation or {}).get("objects", view.objects) or 0)
    view.canonical_prefix = (result or validation or {}).get("canonical_prefix") or view.canonical_prefix
    view.events = [
        PipelineEventDto(
            phase=str(event.phase.value if hasattr(event.phase, "value") else event.phase),
            status=str(event.status.value if hasattr(event.status, "value") else event.status),
            message=event.message,
            created_at=event.created_at.isoformat(),
        )
        for event in events
    ]
    view.logs = [
        PipelineLogDto(timestamp=event.created_at.isoformat(), message=event.message)
        for event in events[-50:]
    ]
    view.stages = _stage_progress(
        list(events),
        int(max_frames) if max_frames else None,
        validation,
        result,
    )
    return view
