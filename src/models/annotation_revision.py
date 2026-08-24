"""Immutable annotation revisions produced by the built-in 2D editor."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class AnnotationRevision(Base):
    __tablename__ = "annotation_revisions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "dataset_version",
            "split",
            "image_id",
            "version",
            name="uq_annotation_revision_identity",
        ),
        Index(
            "ix_annotation_revisions_image_version",
            "dataset_id",
            "dataset_version",
            "split",
            "image_id",
            "version",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(128), index=True)
    dataset_version: Mapped[str] = mapped_column(String(64))
    split: Mapped[str] = mapped_column(String(64), index=True)
    image_id: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[int] = mapped_column(Integer)
    labels_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    original_labels_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
