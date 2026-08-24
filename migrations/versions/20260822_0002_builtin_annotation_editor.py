"""replace CVAT integration with the built-in versioned annotation editor

Revision ID: 20260822_0002
Revises: cceb13cd2021
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0002"
down_revision: str | None = "cceb13cd2021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "annotation_revisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("split", sa.String(length=64), nullable=False),
        sa.Column("image_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("labels_json", sa.JSON(), nullable=False),
        sa.Column("original_labels_json", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_annotation_revisions")),
        sa.UniqueConstraint(
            "dataset_id",
            "dataset_version",
            "split",
            "image_id",
            "version",
            name="uq_annotation_revision_identity",
        ),
    )
    op.create_index("ix_annotation_revisions_dataset_id", "annotation_revisions", ["dataset_id"])
    op.create_index("ix_annotation_revisions_split", "annotation_revisions", ["split"])
    op.create_index("ix_annotation_revisions_image_id", "annotation_revisions", ["image_id"])
    op.create_index("ix_annotation_revisions_created_at", "annotation_revisions", ["created_at"])
    op.create_index(
        "ix_annotation_revisions_image_version",
        "annotation_revisions",
        ["dataset_id", "dataset_version", "split", "image_id", "version"],
    )

    # Legacy cases that only point to CVAT do not have a dataset image that the
    # built-in editor can open. Remove them together with their cascading audit.
    op.execute("DELETE FROM qa_cases WHERE source_type = 'cvat'")
    op.execute("DELETE FROM qa_object_provenance WHERE source = 'CVAT'")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE annotationsource RENAME TO annotationsource_legacy")
        op.execute("CREATE TYPE annotationsource AS ENUM ('COCO', 'KITTI', 'NUSCENES')")
        op.execute(
            "ALTER TABLE qa_object_provenance ALTER COLUMN source TYPE annotationsource "
            "USING source::text::annotationsource"
        )
        op.execute("DROP TYPE annotationsource_legacy")
    op.drop_table("cvat_dataset_image_mappings")

    op.drop_index("ix_qa_cases_source_image", table_name="qa_cases")
    op.drop_index("ix_qa_cases_source_type", table_name="qa_cases")
    op.drop_index("ix_qa_cases_sync_status", table_name="qa_cases")
    op.drop_index("ix_qa_cases_cvat_job_frame", table_name="qa_cases")
    op.drop_index("ix_qa_cases_cvat_job_id", table_name="qa_cases")
    op.drop_index("ix_qa_cases_cvat_project_id", table_name="qa_cases")
    op.drop_index("ix_qa_cases_cvat_task_id", table_name="qa_cases")
    with op.batch_alter_table("qa_cases") as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_qa_cases_source_type_values"), type_="check")
        batch_op.drop_constraint(batch_op.f("ck_qa_cases_sync_status_values"), type_="check")
        batch_op.drop_column("source_type")
        batch_op.drop_column("sync_status")
        batch_op.drop_column("cvat_project_id")
        batch_op.drop_column("cvat_task_id")
        batch_op.drop_column("cvat_job_id")
        batch_op.drop_column("cvat_frame_id")
        batch_op.drop_column("cvat_annotation_id")
        batch_op.drop_column("last_cvat_version")
        batch_op.drop_column("last_synced_at")
    op.create_index("ix_qa_cases_source_image", "qa_cases", ["source_split", "source_image_id"])


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE annotationsource RENAME TO annotationsource_without_cvat")
        op.execute("CREATE TYPE annotationsource AS ENUM ('COCO', 'CVAT', 'KITTI', 'NUSCENES')")
        op.execute(
            "ALTER TABLE qa_object_provenance ALTER COLUMN source TYPE annotationsource "
            "USING source::text::annotationsource"
        )
        op.execute("DROP TYPE annotationsource_without_cvat")
    op.drop_index("ix_qa_cases_source_image", table_name="qa_cases")
    with op.batch_alter_table("qa_cases") as batch_op:
        batch_op.add_column(sa.Column("source_type", sa.String(length=32), server_default="local_dataset", nullable=False))
        batch_op.add_column(sa.Column("sync_status", sa.String(length=32), server_default="not_requested", nullable=False))
        batch_op.add_column(sa.Column("cvat_project_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cvat_task_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cvat_job_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cvat_frame_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cvat_annotation_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_cvat_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            batch_op.f("ck_qa_cases_source_type_values"),
            "source_type IN ('local_dataset', 'cvat')",
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_qa_cases_sync_status_values"),
            "sync_status IN ('not_requested', 'awaiting_annotation', 'awaiting_sync', "
            "'approved_pending_sync', 'synced', 'sync_failed', 'stale')",
        )
    op.create_index("ix_qa_cases_source_image", "qa_cases", ["source_type", "source_split", "source_image_id"])
    op.create_index("ix_qa_cases_source_type", "qa_cases", ["source_type"])
    op.create_index("ix_qa_cases_sync_status", "qa_cases", ["sync_status"])
    op.create_index("ix_qa_cases_cvat_job_frame", "qa_cases", ["cvat_job_id", "cvat_frame_id"])
    op.create_index("ix_qa_cases_cvat_job_id", "qa_cases", ["cvat_job_id"])
    op.create_index("ix_qa_cases_cvat_project_id", "qa_cases", ["cvat_project_id"])
    op.create_index("ix_qa_cases_cvat_task_id", "qa_cases", ["cvat_task_id"])

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
    for column in (
        "dataset_id",
        "source_split",
        "source_image_id",
        "cvat_project_id",
        "cvat_task_id",
        "cvat_job_id",
    ):
        op.create_index(
            f"ix_cvat_dataset_image_mappings_{column}",
            "cvat_dataset_image_mappings",
            [column],
        )

    op.drop_index("ix_annotation_revisions_image_version", table_name="annotation_revisions")
    op.drop_index("ix_annotation_revisions_created_at", table_name="annotation_revisions")
    op.drop_index("ix_annotation_revisions_image_id", table_name="annotation_revisions")
    op.drop_index("ix_annotation_revisions_split", table_name="annotation_revisions")
    op.drop_index("ix_annotation_revisions_dataset_id", table_name="annotation_revisions")
    op.drop_table("annotation_revisions")
