"""Historical Vin-slave control-plane schema retained for migration compatibility.

No control-plane routes are exposed by this integration. Registering these
models keeps Alembic drift checks and test cleanup aligned with revision 0007.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    customer_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_by: Mapped[str] = mapped_column(String(255), ForeignKey("application_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_membership"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("application_users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DatasetSubmission(Base):
    __tablename__ = "dataset_submissions"
    __table_args__ = (Index("ix_dataset_submissions_project_status", "project_id", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dataset_type: Mapped[str] = mapped_column(String(32))
    source_method: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(128))
    split: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    source_prefix: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), ForeignKey("application_users.id"))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SubmissionAsset(Base):
    __tablename__ = "submission_assets"
    __table_args__ = (UniqueConstraint("submission_id", "object_key", name="uq_submission_asset_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    submission_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("dataset_submissions.id", ondelete="CASCADE"), index=True
    )
    object_key: Mapped[str] = mapped_column(String(2048))
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkBatch(Base):
    __tablename__ = "work_batches"
    __table_args__ = (Index("ix_work_batches_project_status", "project_id", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dataset_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    reviewer_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("application_users.id"), nullable=True, index=True
    )
    created_by: Mapped[str] = mapped_column(String(255), ForeignKey("application_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FrameTask(Base):
    __tablename__ = "frame_tasks"
    __table_args__ = (
        UniqueConstraint("batch_id", "image_id", name="uq_frame_task_batch_image"),
        Index("ix_frame_tasks_assignee_stage", "annotator_id", "stage"),
        Index("ix_frame_tasks_project_stage", "project_id", "stage"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[str] = mapped_column(String(64), ForeignKey("work_batches.id", ondelete="CASCADE"), index=True)
    image_id: Mapped[str] = mapped_column(String(255), index=True)
    annotator_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("application_users.id"), nullable=True, index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("application_users.id"), nullable=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(32), default="unassigned", index=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium")
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskReview(Base):
    __tablename__ = "task_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("frame_tasks.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(255), ForeignKey("application_users.id"))
    revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (Index("ix_releases_project_status", "project_id", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("work_batches.id"), nullable=True, index=True)
    version: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    artifact_prefix: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    manifest_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), ForeignKey("application_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
