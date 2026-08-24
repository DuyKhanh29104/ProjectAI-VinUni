"""persist local dataset to CVAT image/frame mappings

Revision ID: 4a7b8c9d0e1f
Revises: 9d2f3c4b5a6e
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a7b8c9d0e1f"
down_revision: str | None = "9d2f3c4b5a6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cvat_dataset_image_mappings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("source_split", sa.String(length=64), nullable=False),
        sa.Column("source_image_id", sa.String(length=255), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("cvat_project_id", sa.Integer(), nullable=True),
        sa.Column("cvat_task_id", sa.Integer(), nullable=False),
        sa.Column("cvat_job_id", sa.Integer(), nullable=False),
        sa.Column("cvat_frame_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cvat_dataset_image_mappings")),
        sa.UniqueConstraint(
            "dataset_id",
            "dataset_version",
            "source_split",
            "source_image_id",
            name="uq_cvat_dataset_image_mapping_identity",
        ),
    )
    op.create_index(
        "ix_cvat_dataset_mapping_cvat_frame",
        "cvat_dataset_image_mappings",
        ["cvat_task_id", "cvat_job_id", "cvat_frame_id"],
    )
    op.create_index(
        "ix_cvat_dataset_mapping_dataset_split",
        "cvat_dataset_image_mappings",
        ["dataset_id", "dataset_version", "source_split"],
    )
    op.create_index(
        "ix_cvat_dataset_image_mappings_dataset_id",
        "cvat_dataset_image_mappings",
        ["dataset_id"],
    )
    op.create_index(
        "ix_cvat_dataset_image_mappings_source_split",
        "cvat_dataset_image_mappings",
        ["source_split"],
    )
    op.create_index(
        "ix_cvat_dataset_image_mappings_source_image_id",
        "cvat_dataset_image_mappings",
        ["source_image_id"],
    )
    op.create_index(
        "ix_cvat_dataset_image_mappings_cvat_project_id",
        "cvat_dataset_image_mappings",
        ["cvat_project_id"],
    )
    op.create_index(
        "ix_cvat_dataset_image_mappings_cvat_task_id",
        "cvat_dataset_image_mappings",
        ["cvat_task_id"],
    )
    op.create_index(
        "ix_cvat_dataset_image_mappings_cvat_job_id",
        "cvat_dataset_image_mappings",
        ["cvat_job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cvat_dataset_image_mappings_cvat_job_id", table_name="cvat_dataset_image_mappings")
    op.drop_index("ix_cvat_dataset_image_mappings_cvat_task_id", table_name="cvat_dataset_image_mappings")
    op.drop_index("ix_cvat_dataset_image_mappings_cvat_project_id", table_name="cvat_dataset_image_mappings")
    op.drop_index("ix_cvat_dataset_image_mappings_source_image_id", table_name="cvat_dataset_image_mappings")
    op.drop_index("ix_cvat_dataset_image_mappings_source_split", table_name="cvat_dataset_image_mappings")
    op.drop_index("ix_cvat_dataset_image_mappings_dataset_id", table_name="cvat_dataset_image_mappings")
    op.drop_index("ix_cvat_dataset_mapping_dataset_split", table_name="cvat_dataset_image_mappings")
    op.drop_index("ix_cvat_dataset_mapping_cvat_frame", table_name="cvat_dataset_image_mappings")
    op.drop_table("cvat_dataset_image_mappings")
