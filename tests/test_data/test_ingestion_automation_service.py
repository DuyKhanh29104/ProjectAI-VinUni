from pathlib import Path

from sqlalchemy import func, select

from src.config import IngestionSettings
from src.models.ingestion import IngestionAsset, IngestionJob, IngestionJobEvent, IngestionJobStatus, QAImage, QAObject
from src.services.ingestion.ingestion_automation_service import IngestionAutomationService, IngestionJobRequest
from src.services.ingestion.local_storage import LocalObjectStorageClient


def test_local_first_automation_creates_job_and_ingests_to_prefixed_storage(
    tmp_path: Path,
    postgres_sync_session_factory,
):
    object_root = tmp_path / "objects"
    settings = IngestionSettings(
        gcs_bucket="automation-bucket",
        gcs_public_url=f"file://{object_root / 'automation-bucket'}",
    )
    service = IngestionAutomationService(
        session_factory=postgres_sync_session_factory,
        storage_client=LocalObjectStorageClient(object_root),
        settings=settings,
    )
    request = IngestionJobRequest(
        provider="local",
        dataset_type="kitti",
        dataset_root=Path("eval/label_guardian_ingestion_mini"),
        requested_by="qa-user",
        target_prefix="datasets/kitti/mini",
        strict_layout=False,
    )

    completed = service.create_and_run(request)

    assert completed.result.images == 12
    assert completed.result.objects == 1
    assert (object_root / "automation-bucket/datasets/kitti/mini/frames/000000.png").is_file()
    with postgres_sync_session_factory() as session:
        job = session.get(IngestionJob, completed.job_id)
        assert job is not None
        assert job.status == IngestionJobStatus.COMPLETED
        assert job.result_metrics == {"images": 12, "objects": 1, "uploads": 12}
        assert session.scalar(select(func.count()).select_from(IngestionJobEvent)) >= 3
        assert session.scalar(select(func.count()).select_from(IngestionAsset)) == 1
        assert session.scalar(select(func.count()).select_from(QAImage)) == 12
        assert session.scalar(select(func.count()).select_from(QAObject)) == 1


def test_duplicate_automation_request_reuses_existing_job(tmp_path: Path, postgres_sync_session_factory):
    settings = IngestionSettings(gcs_bucket="automation-bucket")
    service = IngestionAutomationService(
        session_factory=postgres_sync_session_factory,
        storage_client=LocalObjectStorageClient(tmp_path / "objects"),
        settings=settings,
    )
    request = IngestionJobRequest(
        provider="local",
        dataset_type="kitti",
        dataset_root=Path("eval/label_guardian_ingestion_mini"),
        target_prefix="datasets/kitti/mini",
        strict_layout=False,
    )

    first = service.create_job(request)
    second = service.create_job(request)

    assert first.id == second.id
    with postgres_sync_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(IngestionJob)) == 1
