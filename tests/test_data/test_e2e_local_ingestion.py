from pathlib import Path

import numpy as np
from sqlalchemy import func, select

from src.config import IngestionSettings
from src.models.ingestion import QAImage, QAObject
from src.services.ingestion.ingestion_service import IngestionService
from src.services.ingestion.kitti_adapter import ImageMetadata
from src.services.ingestion.local_storage import LocalObjectStorageClient
from src.services.ingestion.nuscenes_adapter import project_cuboid_to_qa_object


def test_e2e_local_storage_normalizes_kitti_and_nuscenes(tmp_path: Path, postgres_sync_session_factory):
    object_root = tmp_path / "objects"
    settings = IngestionSettings(
        gcs_bucket="e2e-bucket",
        gcs_public_url=f"file://{object_root / 'e2e-bucket'}",
        object_key_prefix="",
        _env_file=None,
    )
    service = IngestionService(
        Path("eval/label_guardian_ingestion_mini"),
        postgres_sync_session_factory,
        LocalObjectStorageClient(object_root),
        settings,
    )
    kitti_result = service.ingest()
    assert kitti_result.images == 12
    assert (object_root / "e2e-bucket/frames/000000.png").is_file()

    corners = np.array(
        [[-1, -1, 10], [1, -1, 10], [1, 1, 10], [-1, 1, 10], [-1, -1, 12], [1, -1, 12], [1, 1, 12], [-1, 1, 12]]
    )
    nu_object = project_cuboid_to_qa_object(
        source_image_id="0",
        label="car",
        corners=corners,
        extrinsic=np.eye(4),
        intrinsic=np.array([[100, 0, 50], [0, 100, 40], [0, 0, 1]]),
        source_annotation_id="nuscenes-e2e-cuboid",
    )
    assert nu_object is not None
    result = service.ingest_normalized(
        [ImageMetadata(source_image_id="0", filename="000000.png", width=100, height=80)],
        [nu_object],
        replace_objects=False,
    )
    assert result.objects == 1
    with postgres_sync_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(QAImage)) == 12
        assert session.scalar(select(func.count()).select_from(QAObject)) == 2
        assert session.scalar(select(QAObject).where(QAObject.source_object_key.like("nuscenes%"))) is not None
