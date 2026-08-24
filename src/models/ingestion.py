"""Shared QA contracts and persistence models for dataset adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class AnnotationSource(StrEnum):
    COCO = "coco"
    KITTI = "kitti"
    NUSCENES = "nuscenes"


class QAReviewStatus(StrEnum):
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    UNMATCHED = "unmatched"


class IngestionJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED_CREDENTIALS = "blocked_credentials"
    CANCELLED = "cancelled"


class IngestionPhase(StrEnum):
    REQUESTED = "requested"
    RESOLVE_SOURCE = "resolve_source"
    ACQUIRE_RAW = "acquire_raw"
    ADAPT = "adapt"
    PERSIST = "persist"
    FINALIZE = "finalize"


class BoundingBox(BaseModel):
    """Pixel-aligned xyxy rectangle."""

    model_config = ConfigDict(frozen=True)

    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @model_validator(mode="after")
    def has_positive_area(self) -> BoundingBox:
        if self.xmax <= self.xmin or self.ymax <= self.ymin:
            raise ValueError("bounding box must have positive area")
        return self

    @classmethod
    def from_xywh(cls, x: float, y: float, width: float, height: float) -> BoundingBox:
        return cls(xmin=x, ymin=y, xmax=x + width, ymax=y + height)

    def as_xyxy(self) -> list[float]:
        return [self.xmin, self.ymin, self.xmax, self.ymax]


class AnnotationProvenance(BaseModel):
    source: AnnotationSource
    source_annotation_id: str
    bbox: BoundingBox
    raw: dict[str, Any] = Field(default_factory=dict)


class QAObjectPayload(BaseModel):
    """Adapter output ready to be persisted as a QAObject."""

    source_image_id: str
    label: str
    bbox: BoundingBox
    review_status: QAReviewStatus
    provenance: list[AnnotationProvenance]
    calibration: dict[str, list[list[float]]] = Field(default_factory=dict)
    cuboid_corners: list[list[float]] | None = None


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str] = mapped_column(String(64))
    dataset_type: Mapped[str] = mapped_column(String(64))
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    split: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[IngestionJobStatus] = mapped_column(SqlEnum(IngestionJobStatus), default=IngestionJobStatus.PENDING)
    source_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    target_bucket: Mapped[str] = mapped_column(String(255))
    target_prefix: Mapped[str] = mapped_column(String(1024), default="")
    error_message: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    result_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events: Mapped[list[IngestionJobEvent]] = relationship(back_populates="job", cascade="all, delete-orphan")
    assets: Mapped[list[IngestionAsset]] = relationship(back_populates="job", cascade="all, delete-orphan")


class IngestionJobEvent(Base):
    __tablename__ = "ingestion_job_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("ingestion_jobs.id"), index=True)
    phase: Mapped[IngestionPhase] = mapped_column(SqlEnum(IngestionPhase))
    status: Mapped[IngestionJobStatus] = mapped_column(SqlEnum(IngestionJobStatus))
    message: Mapped[str] = mapped_column(String(2048))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    job: Mapped[IngestionJob] = relationship(back_populates="events")


class IngestionAsset(Base):
    __tablename__ = "ingestion_assets"
    __table_args__ = (UniqueConstraint("job_id", "object_key", name="uq_ingestion_asset_job_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("ingestion_jobs.id"), index=True)
    source_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    object_key: Mapped[str] = mapped_column(String(2048))
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    job: Mapped[IngestionJob] = relationship(back_populates="assets")


class QAImage(Base):
    __tablename__ = "qa_images"
    __table_args__ = (
        UniqueConstraint(
            "dataset",
            "release",
            "source_image_id",
            name="uq_qa_image_dataset_release_source",
        ),
        Index("ix_qa_images_dataset_release", "dataset", "release"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_image_id: Mapped[str] = mapped_column(String(255), index=True)
    filename: Mapped[str] = mapped_column(String(512), index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    object_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset: Mapped[str | None] = mapped_column(String(128), nullable=True)
    release: Mapped[str | None] = mapped_column(String(128), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    asset_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    objects: Mapped[list[QAObject]] = relationship(back_populates="image", cascade="all, delete-orphan")


class QAObject(Base):
    __tablename__ = "qa_objects"
    __table_args__ = (UniqueConstraint("image_id", "source_object_key", name="uq_qa_object_image_source_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("qa_images.id"), index=True)
    source_object_key: Mapped[str] = mapped_column(String(255))
    label: Mapped[str] = mapped_column(String(255))
    xmin: Mapped[float] = mapped_column("bbox_xmin", Float)
    ymin: Mapped[float] = mapped_column("bbox_ymin", Float)
    xmax: Mapped[float] = mapped_column("bbox_xmax", Float)
    ymax: Mapped[float] = mapped_column("bbox_ymax", Float)
    review_status: Mapped[QAReviewStatus] = mapped_column(SqlEnum(QAReviewStatus))
    calibration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cuboid_corners: Mapped[list[list[float]] | None] = mapped_column(JSON, nullable=True)
    image: Mapped[QAImage] = relationship(back_populates="objects")
    provenance_records: Mapped[list[QAObjectProvenance]] = relationship(
        back_populates="qa_object", cascade="all, delete-orphan"
    )


class QAObjectProvenance(Base):
    __tablename__ = "qa_object_provenance"
    __table_args__ = (UniqueConstraint("qa_object_id", "source", "source_annotation_id", name="uq_qa_provenance"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    qa_object_id: Mapped[int] = mapped_column(ForeignKey("qa_objects.id"), index=True)
    source: Mapped[AnnotationSource] = mapped_column(SqlEnum(AnnotationSource))
    source_annotation_id: Mapped[str] = mapped_column(String(255))
    xmin: Mapped[float] = mapped_column("bbox_xmin", Float)
    ymin: Mapped[float] = mapped_column("bbox_ymin", Float)
    xmax: Mapped[float] = mapped_column("bbox_xmax", Float)
    ymax: Mapped[float] = mapped_column("bbox_ymax", Float)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    qa_object: Mapped[QAObject] = relationship(back_populates="provenance_records")
