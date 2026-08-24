"""Create QA cases and append-only audit storage.

Revision ID: 20260809_0001
Revises:
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "qa_cases",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("sequence_id", sa.String(length=128), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("frame_file_name", sa.String(length=255), nullable=False),
        sa.Column("class_name", sa.String(length=128), nullable=False),
        sa.Column("target_track_id", sa.String(length=255), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("cvat_project_id", sa.Integer(), nullable=False),
        sa.Column("cvat_task_id", sa.Integer(), nullable=False),
        sa.Column("cvat_job_id", sa.Integer(), nullable=False),
        sa.Column("cvat_frame_id", sa.Integer(), nullable=False),
        sa.Column("cvat_annotation_id", sa.Integer(), nullable=True),
        sa.Column("last_cvat_version", sa.Integer(), nullable=True),
        sa.Column("assigned_to", sa.String(length=128), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name=op.f("ck_qa_cases_risk_score_range"),
        ),
        sa.CheckConstraint(
            "status IN ('unreviewed', 'in_review', 'confirmed', 'corrected', 'rejected', 'skipped')",
            name=op.f("ck_qa_cases_status_values"),
        ),
        sa.CheckConstraint(
            "sync_status IN ('not_requested', 'awaiting_annotation', 'awaiting_sync', "
            "'approved_pending_sync', 'synced', 'sync_failed', 'stale')",
            name=op.f("ck_qa_cases_sync_status_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_cases")),
    )
    op.create_index("ix_qa_cases_assigned_to", "qa_cases", ["assigned_to"])
    op.create_index("ix_qa_cases_class_name", "qa_cases", ["class_name"])
    op.create_index("ix_qa_cases_cvat_job_frame", "qa_cases", ["cvat_job_id", "cvat_frame_id"])
    op.create_index("ix_qa_cases_cvat_job_id", "qa_cases", ["cvat_job_id"])
    op.create_index("ix_qa_cases_cvat_project_id", "qa_cases", ["cvat_project_id"])
    op.create_index("ix_qa_cases_cvat_task_id", "qa_cases", ["cvat_task_id"])
    op.create_index("ix_qa_cases_dataset_id", "qa_cases", ["dataset_id"])
    op.create_index("ix_qa_cases_error_type", "qa_cases", ["error_type"])
    op.create_index("ix_qa_cases_priority", "qa_cases", ["priority"])
    op.create_index("ix_qa_cases_queue", "qa_cases", ["status", "risk_score"])
    op.create_index("ix_qa_cases_risk_score", "qa_cases", ["risk_score"])
    op.create_index("ix_qa_cases_sequence_id", "qa_cases", ["sequence_id"])
    op.create_index("ix_qa_cases_status", "qa_cases", ["status"])
    op.create_index("ix_qa_cases_sync_status", "qa_cases", ["sync_status"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('user', 'system', 'agent')",
            name=op.f("ck_audit_logs_actor_type_values"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["qa_cases.id"],
            name=op.f("fk_audit_logs_case_id_qa_cases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index("ix_audit_logs_case_created", "audit_logs", ["case_id", "created_at"])
    op.create_index("ix_audit_logs_case_id", "audit_logs", ["case_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_case_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_case_created", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_qa_cases_sync_status", table_name="qa_cases")
    op.drop_index("ix_qa_cases_status", table_name="qa_cases")
    op.drop_index("ix_qa_cases_sequence_id", table_name="qa_cases")
    op.drop_index("ix_qa_cases_risk_score", table_name="qa_cases")
    op.drop_index("ix_qa_cases_queue", table_name="qa_cases")
    op.drop_index("ix_qa_cases_priority", table_name="qa_cases")
    op.drop_index("ix_qa_cases_error_type", table_name="qa_cases")
    op.drop_index("ix_qa_cases_dataset_id", table_name="qa_cases")
    op.drop_index("ix_qa_cases_cvat_task_id", table_name="qa_cases")
    op.drop_index("ix_qa_cases_cvat_project_id", table_name="qa_cases")
    op.drop_index("ix_qa_cases_cvat_job_id", table_name="qa_cases")
    op.drop_index("ix_qa_cases_cvat_job_frame", table_name="qa_cases")
    op.drop_index("ix_qa_cases_class_name", table_name="qa_cases")
    op.drop_index("ix_qa_cases_assigned_to", table_name="qa_cases")
    op.drop_table("qa_cases")
