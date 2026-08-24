"""add real dataset QA evaluations

Revision ID: 9d2f3c4b5a6e
Revises: 3944daf20671
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d2f3c4b5a6e"
down_revision: str | None = "3944daf20671"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "qa_evaluations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("split", sa.String(length=64), nullable=False),
        sa.Column("image_id", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("predictions_json", sa.JSON(), nullable=False),
        sa.Column("matches_json", sa.JSON(), nullable=False),
        sa.Column("unmatched_ground_truth_json", sa.JSON(), nullable=False),
        sa.Column("unmatched_predictions_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pass', 'needs_review', 'error')",
            name=op.f("ck_qa_evaluations_status_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_evaluations")),
        sa.UniqueConstraint(
            "dataset_id",
            "dataset_version",
            "split",
            "image_id",
            "model_name",
            name="uq_qa_evaluation_identity",
        ),
    )
    op.create_index("ix_qa_evaluations_dataset_id", "qa_evaluations", ["dataset_id"])
    op.create_index("ix_qa_evaluations_dataset_split", "qa_evaluations", ["dataset_id", "split"])
    op.create_index("ix_qa_evaluations_image_id", "qa_evaluations", ["image_id"])
    op.create_index("ix_qa_evaluations_split", "qa_evaluations", ["split"])
    op.create_index("ix_qa_evaluations_status", "qa_evaluations", ["status"])

    with op.batch_alter_table("qa_cases") as batch_op:
        batch_op.add_column(sa.Column("source_type", sa.String(length=32), server_default="cvat", nullable=False))
        batch_op.add_column(sa.Column("source_split", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("source_image_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("evaluation_id", sa.String(length=64), nullable=True))
        batch_op.alter_column("cvat_project_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("cvat_task_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("cvat_job_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("cvat_frame_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_check_constraint(
            batch_op.f("ck_qa_cases_source_type_values"),
            "source_type IN ('local_dataset', 'cvat')",
        )
    op.create_index("ix_qa_cases_evaluation_id", "qa_cases", ["evaluation_id"])
    op.create_index("ix_qa_cases_source_image_id", "qa_cases", ["source_image_id"])
    op.create_index("ix_qa_cases_source_split", "qa_cases", ["source_split"])
    op.create_index("ix_qa_cases_source_type", "qa_cases", ["source_type"])
    op.create_index(
        "ix_qa_cases_source_image",
        "qa_cases",
        ["source_type", "source_split", "source_image_id"],
    )


def downgrade() -> None:
    op.execute("DELETE FROM audit_logs WHERE case_id IN (SELECT id FROM qa_cases WHERE source_type = 'local_dataset')")
    op.execute("DELETE FROM qa_cases WHERE source_type = 'local_dataset'")
    op.drop_index("ix_qa_cases_source_image", table_name="qa_cases")
    op.drop_index("ix_qa_cases_source_type", table_name="qa_cases")
    op.drop_index("ix_qa_cases_source_split", table_name="qa_cases")
    op.drop_index("ix_qa_cases_source_image_id", table_name="qa_cases")
    op.drop_index("ix_qa_cases_evaluation_id", table_name="qa_cases")
    with op.batch_alter_table("qa_cases") as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_qa_cases_source_type_values"), type_="check")
        batch_op.alter_column("cvat_frame_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("cvat_job_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("cvat_task_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("cvat_project_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("evaluation_id")
        batch_op.drop_column("source_image_id")
        batch_op.drop_column("source_split")
        batch_op.drop_column("source_type")

    op.drop_index("ix_qa_evaluations_status", table_name="qa_evaluations")
    op.drop_index("ix_qa_evaluations_split", table_name="qa_evaluations")
    op.drop_index("ix_qa_evaluations_image_id", table_name="qa_evaluations")
    op.drop_index("ix_qa_evaluations_dataset_split", table_name="qa_evaluations")
    op.drop_index("ix_qa_evaluations_dataset_id", table_name="qa_evaluations")
    op.drop_table("qa_evaluations")
