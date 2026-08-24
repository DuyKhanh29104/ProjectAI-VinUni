"""Upload normalized dataset assets to object storage and persist QA metadata."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import Path
from typing import Any, cast

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from src.config import IngestionSettings
from src.db.session import normalize_sync_database_url
from src.models.ingestion import QAImage, QAObject, QAObjectPayload, QAObjectProvenance
from src.services.ingestion.kitti_adapter import ImageMetadata, KittiAdapter


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create a PostgreSQL session factory for the offline ingestion worker.

    Database schemas are always managed by Alembic before the worker starts.
    """
    engine: Engine = create_engine(normalize_sync_database_url(database_url), pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_object_storage_client(settings: IngestionSettings) -> Any:
    """Create the configured GCS object-storage client."""
    from src.services.ingestion.gcs_storage import create_gcs_client

    return create_gcs_client(settings)


@dataclass(frozen=True)
class IngestionResult:
    images: int
    objects: int
    uploads: int


class IngestionService:
    """Idempotently ingest fixture images and normalized adapter output."""

    def __init__(
        self,
        dataset_root: Path,
        session_factory: sessionmaker[Session],
        storage_client: Any,
        settings: IngestionSettings,
        dataset_split: str | None = None,
        upload_images: bool = True,
    ) -> None:
        self.dataset_root = Path(dataset_root)
        self.session_factory = session_factory
        self.storage_client = storage_client
        self.settings = settings
        self.dataset_split = dataset_split
        self.upload_images = upload_images

    def ensure_bucket(self) -> None:
        try:
            self.storage_client.head_bucket(Bucket=self.settings.bucket_name)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self.storage_client.create_bucket(Bucket=self.settings.bucket_name)

    def ingest(self) -> IngestionResult:
        """Upload images and upsert their normalized QA records."""
        self.ensure_bucket()
        images, cases = KittiAdapter(self.dataset_root, split=self.dataset_split).load()
        return self.ingest_normalized(images, cases)

    def ingest_normalized(
        self,
        images: list[ImageMetadata],
        cases: list[QAObjectPayload],
        *,
        replace_objects: bool = True,
    ) -> IngestionResult:
        """Persist normalized output, treating each image as an authoritative snapshot by default.

        Callers intentionally merging independent annotation sources into the
        same dataset image can opt out of stale-object removal explicitly.
        """
        self.ensure_bucket()
        cases_by_image: dict[str, list[QAObjectPayload]] = defaultdict(list)
        for qa_case in cases:
            cases_by_image[qa_case.source_image_id].append(qa_case)

        uploads = 0
        with self.session_factory() as session, session.begin():
            for image in images:
                uploads += self._upload_and_upsert_image(session, image)
                db_image = self._find_image(session, image.source_image_id)
                assert db_image is not None
                image_cases = cases_by_image[image.source_image_id]
                if replace_objects:
                    self._remove_stale_objects(session, db_image, image_cases)
                for qa_case in image_cases:
                    self._upsert_object(session, db_image, qa_case)
        return IngestionResult(images=len(images), objects=len(cases), uploads=uploads)

    def _upload_and_upsert_image(self, session: Session, image: ImageMetadata) -> int:
        image_path = self.dataset_root / image.filename
        if not image_path.is_file():
            raise FileNotFoundError(f"Dataset image is missing: {image_path}")
        key_prefix = self.settings.object_key_prefix.strip("/")
        storage_filename = image.storage_filename or image.filename
        object_key = f"{key_prefix}/frames/{storage_filename}" if key_prefix else f"frames/{storage_filename}"
        content_type = guess_type(image_path.name)[0] or "application/octet-stream"
        uploaded = 0
        if self.upload_images:
            self.storage_client.upload_file(
                str(image_path),
                self.settings.bucket_name,
                object_key,
                ExtraArgs={"ContentType": content_type},
            )
            uploaded = 1
        object_url = self.settings.object_uri(object_key)
        db_image = self._find_image(session, image.source_image_id)
        if db_image is None:
            session.add(
                QAImage(
                    source_image_id=image.source_image_id,
                    filename=image.filename,
                    width=image.width,
                    height=image.height,
                    object_url=object_url,
                    provider=self.settings.dataset_provider,
                    dataset=self.settings.dataset_name,
                    release=self.settings.dataset_release,
                    modality="camera",
                    asset_type="image",
                    data_format=image_path.suffix.lower().lstrip(".") or None,
                    storage_key=object_key,
                )
            )
        else:
            db_image.filename = image.filename
            db_image.width = image.width
            db_image.height = image.height
            db_image.object_url = object_url
            db_image.provider = self.settings.dataset_provider
            db_image.dataset = self.settings.dataset_name
            db_image.release = self.settings.dataset_release
            db_image.modality = "camera"
            db_image.asset_type = "image"
            db_image.data_format = image_path.suffix.lower().lstrip(".") or None
            db_image.storage_key = object_key
        session.flush()
        return uploaded

    def _find_image(self, session: Session, source_image_id: str) -> QAImage | None:
        return cast(
            QAImage | None,
            session.scalar(
                select(QAImage).where(
                    QAImage.source_image_id == source_image_id,
                    QAImage.dataset == self.settings.dataset_name,
                    QAImage.release == self.settings.dataset_release,
                )
            )
        )

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

    def _upsert_object(self, session: Session, image: QAImage, qa_case: QAObjectPayload) -> None:
        source_object_key = self._source_object_key(qa_case)
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
        # Flush orphan removals before inserting records with the same unique source key.
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
