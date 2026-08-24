from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import func, select

from src.config import IngestionSettings
from src.models.ingestion import QAImage, QAObject, QAObjectProvenance
from src.services.ingestion.ingestion_service import IngestionService
from src.services.ingestion.kitti_adapter import KittiAdapter


class FakeObjectStorageClient:
    def __init__(self) -> None:
        self.bucket_exists = False
        self.created_buckets: list[dict] = []
        self.uploads: list[tuple[str, str, str, dict]] = []

    def head_bucket(self, **kwargs) -> None:
        _ = kwargs["Bucket"]
        if not self.bucket_exists:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, **kwargs) -> None:
        self.bucket_exists = True
        self.created_buckets.append(kwargs)

    def upload_file(self, filename: str, bucket: str, key: str, **kwargs) -> None:
        self.uploads.append((filename, bucket, key, kwargs["ExtraArgs"]))


@pytest.mark.parametrize("model", [QAObject, QAObjectProvenance])
def test_bbox_attributes_use_postgres_safe_column_names(model) -> None:
    assert model.xmin.property.columns[0].name == "bbox_xmin"
    assert model.ymin.property.columns[0].name == "bbox_ymin"
    assert model.xmax.property.columns[0].name == "bbox_xmax"
    assert model.ymax.property.columns[0].name == "bbox_ymax"


@pytest.fixture
def ingestion_service(
    tmp_path: Path, postgres_sync_session_factory
) -> tuple[IngestionService, FakeObjectStorageClient, object]:
    settings = IngestionSettings(
        gcs_bucket="test-bucket",
        gcs_public_url="https://objects.example.test/test-bucket",
        object_key_prefix="",
        dataset_provider="kitti",
        dataset_name="kitti",
        dataset_release="object",
        _env_file=None,
    )
    fake_storage = FakeObjectStorageClient()
    service = IngestionService(
        Path("eval/label_guardian_ingestion_mini"), postgres_sync_session_factory, fake_storage, settings
    )
    return service, fake_storage, postgres_sync_session_factory


def test_ingests_images_uploads_files_and_persists_ground_truth(ingestion_service):
    service, fake_storage, session_factory = ingestion_service
    result = service.ingest()
    assert result.images == 12
    assert result.objects == 1
    assert result.uploads == 12
    assert fake_storage.created_buckets == [{"Bucket": "test-bucket"}]
    assert fake_storage.uploads[0][1:] == ("test-bucket", "frames/000000.png", {"ContentType": "image/png"})
    with session_factory() as session:
        image = session.scalar(select(QAImage).where(QAImage.filename == "000000.png"))
        assert image is not None
        assert image.object_url == "https://objects.example.test/test-bucket/frames/000000.png"
        assert image.storage_key == "frames/000000.png"
        assert image.provider == "kitti"
        assert image.dataset == "kitti"
        assert image.release == "object"
        assert image.modality == "camera"
        assert image.asset_type == "image"
        assert image.data_format == "png"
        assert session.scalar(select(func.count()).select_from(QAObject)) == 1
        assert session.scalar(select(func.count()).select_from(QAObjectProvenance)) == 1


def test_gcs_settings_build_stable_object_uri() -> None:
    settings = IngestionSettings(
        storage_backend="gcs",
        gcs_bucket="label-guardian-cloud",
        gcs_public_url=None,
        object_key_prefix="datasets/kitti",
        _env_file=None,
    )

    assert settings.bucket_name == "label-guardian-cloud"
    assert settings.object_uri("datasets/kitti/frames/000000.png") == (
        "gs://label-guardian-cloud/datasets/kitti/frames/000000.png"
    )


def test_repeated_ingestion_is_idempotent(ingestion_service):
    service, _, session_factory = ingestion_service
    service.ingest()
    service.ingest()
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(QAImage)) == 12
        assert session.scalar(select(func.count()).select_from(QAObject)) == 1
        assert session.scalar(select(func.count()).select_from(QAObjectProvenance)) == 1


def test_same_source_image_can_exist_in_multiple_releases(ingestion_service):
    service, fake_storage, session_factory = ingestion_service
    service.ingest()
    second_settings = service.settings.model_copy(
        update={"dataset_release": "object-v2", "object_key_prefix": "datasets/kitti/object-v2"}
    )
    second = IngestionService(service.dataset_root, session_factory, fake_storage, second_settings)

    second.ingest()

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(QAImage)) == 24


def test_reingestion_removes_labels_missing_from_latest_manifest(ingestion_service):
    service, _, session_factory = ingestion_service
    images, cases = KittiAdapter(service.dataset_root).load()
    service.ingest_normalized(images, cases)

    service.ingest_normalized(images, [])

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(QAObject)) == 0
        assert session.scalar(select(func.count()).select_from(QAObjectProvenance)) == 0
