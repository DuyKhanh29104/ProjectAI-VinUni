from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class QaCase(Base):
    __tablename__ = "qa_cases"
    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="risk_score_range"),
        CheckConstraint(
            "status IN ('unreviewed', 'in_review', 'confirmed', 'corrected', 'rejected', 'skipped')",
            name="status_values",
        ),
        Index("ix_qa_cases_queue", "status", "risk_score"),
        Index("ix_qa_cases_source_image", "source_split", "source_image_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(128), index=True)
    dataset_version: Mapped[str] = mapped_column(String(64))
    source_split: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_image_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    evaluation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sequence_id: Mapped[str] = mapped_column(String(128), index=True)
    frame_index: Mapped[int] = mapped_column(Integer)
    frame_file_name: Mapped[str] = mapped_column(String(255))
    class_name: Mapped[str] = mapped_column(String(128), index=True)
    target_track_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_type: Mapped[str] = mapped_column(String(128), index=True)
    risk_score: Mapped[int] = mapped_column(Integer, index=True)
    priority: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    recommendation: Mapped[str] = mapped_column(Text)

    assigned_to: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="qa_case",
        cascade="all, delete-orphan",
        order_by="AuditLog.created_at",
    )


from src.models.audit_log import AuditLog  # noqa: E402
