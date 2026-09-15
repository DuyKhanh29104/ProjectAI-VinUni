"""add project scoped admin control plane

Revision ID: 20260831_0007
Revises: 20260824_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0007"
down_revision: str | None = "20260824_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(255), sa.ForeignKey("application_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_status_created", "projects", ["status", "created_at"])
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), sa.ForeignKey("application_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_membership"),
    )
    op.create_index("ix_project_memberships_project_id", "project_memberships", ["project_id"])
    op.create_index("ix_project_memberships_user_id", "project_memberships", ["user_id"])
    op.create_table(
        "dataset_submissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_type", sa.String(32), nullable=False),
        sa.Column("source_method", sa.String(32), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("split", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("source_prefix", sa.String(2048), nullable=True),
        sa.Column("created_by", sa.String(255), sa.ForeignKey("application_users.id"), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dataset_submissions_project_id", "dataset_submissions", ["project_id"])
    op.create_index("ix_dataset_submissions_status", "dataset_submissions", ["status"])
    op.create_index("ix_dataset_submissions_project_status", "dataset_submissions", ["project_id", "status"])
    op.create_table(
        "submission_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("submission_id", sa.String(64), sa.ForeignKey("dataset_submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_key", sa.String(2048), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("submission_id", "object_key", name="uq_submission_asset_key"),
    )
    op.create_index("ix_submission_assets_submission_id", "submission_assets", ["submission_id"])
    op.create_table(
        "work_batches",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_version_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("scope_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("reviewer_id", sa.String(255), sa.ForeignKey("application_users.id"), nullable=True),
        sa.Column("created_by", sa.String(255), sa.ForeignKey("application_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_work_batches_project_id", "work_batches", ["project_id"])
    op.create_index("ix_work_batches_status", "work_batches", ["status"])
    op.create_index("ix_work_batches_project_status", "work_batches", ["project_id", "status"])
    op.create_index("ix_work_batches_reviewer_id", "work_batches", ["reviewer_id"])
    op.create_table(
        "frame_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("work_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", sa.String(255), nullable=False),
        sa.Column("annotator_id", sa.String(255), sa.ForeignKey("application_users.id"), nullable=True),
        sa.Column("reviewer_id", sa.String(255), sa.ForeignKey("application_users.id"), nullable=True),
        sa.Column("stage", sa.String(32), nullable=False, server_default="unassigned"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submitted_revision_id", sa.String(64), nullable=True),
        sa.Column("last_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("batch_id", "image_id", name="uq_frame_task_batch_image"),
    )
    for name, table, columns in (
        ("ix_frame_tasks_project_id", "frame_tasks", ["project_id"]),
        ("ix_frame_tasks_batch_id", "frame_tasks", ["batch_id"]),
        ("ix_frame_tasks_image_id", "frame_tasks", ["image_id"]),
        ("ix_frame_tasks_annotator_id", "frame_tasks", ["annotator_id"]),
        ("ix_frame_tasks_reviewer_id", "frame_tasks", ["reviewer_id"]),
        ("ix_frame_tasks_stage", "frame_tasks", ["stage"]),
        ("ix_frame_tasks_assignee_stage", "frame_tasks", ["annotator_id", "stage"]),
        ("ix_frame_tasks_project_stage", "frame_tasks", ["project_id", "stage"]),
    ):
        op.create_index(name, table, columns)
    op.create_table(
        "task_reviews",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("frame_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.String(255), sa.ForeignKey("application_users.id"), nullable=False),
        sa.Column("revision_id", sa.String(64), nullable=True),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_reviews_task_id", "task_reviews", ["task_id"])
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workflow_events_project_id", "workflow_events", ["project_id"])
    op.create_index("ix_workflow_events_actor_id", "workflow_events", ["actor_id"])
    op.create_index("ix_workflow_events_event_type", "workflow_events", ["event_type"])
    op.create_index("ix_workflow_events_entity_id", "workflow_events", ["entity_id"])
    op.create_index("ix_workflow_events_created_at", "workflow_events", ["created_at"])
    op.create_table(
        "releases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("work_batches.id"), nullable=True),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("artifact_prefix", sa.String(2048), nullable=True),
        sa.Column("manifest_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", sa.String(255), sa.ForeignKey("application_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_releases_project_id", "releases", ["project_id"])
    op.create_index("ix_releases_batch_id", "releases", ["batch_id"])
    op.create_index("ix_releases_status", "releases", ["status"])
    op.create_index("ix_releases_project_status", "releases", ["project_id", "status"])


def downgrade() -> None:
    for table in ("releases", "workflow_events", "task_reviews", "frame_tasks", "work_batches", "submission_assets", "dataset_submissions", "project_memberships", "projects"):
        op.drop_table(table)
