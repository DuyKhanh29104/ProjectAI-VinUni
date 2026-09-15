"""Scope persisted QA evaluations to the annotation revision.

Revision ID: 20260914_0009
Revises: 20260903_0008
"""

import sqlalchemy as sa
from alembic import op

revision = "20260914_0009"
down_revision = "20260903_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Imported historical tables are backend-only, like the existing QA tables.
    if op.get_bind().dialect.name == "postgresql":
        tables = (
            "projects",
            "project_memberships",
            "dataset_submissions",
            "submission_assets",
            "work_batches",
            "frame_tasks",
            "task_reviews",
            "workflow_events",
            "releases",
        )
        for table in tables:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        names = ", ".join(f'"{table}"' for table in tables)
        for role in ("anon", "authenticated"):
            op.execute(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL PRIVILEGES ON TABLE {names} FROM {role};
                END IF;
            END $$""")
    op.add_column("qa_evaluations", sa.Column("annotation_revision", sa.Integer(), nullable=False, server_default="0"))
    op.drop_constraint("uq_qa_evaluation_identity", "qa_evaluations", type_="unique")
    op.create_unique_constraint(
        "uq_qa_evaluation_identity",
        "qa_evaluations",
        ["dataset_id", "dataset_version", "split", "image_id", "model_name", "annotation_revision"],
    )


def downgrade() -> None:
    # Recreating the old constraint deliberately refuses a lossy downgrade when
    # multiple annotation revisions have already been evaluated.
    op.drop_constraint("uq_qa_evaluation_identity", "qa_evaluations", type_="unique")
    op.create_unique_constraint(
        "uq_qa_evaluation_identity",
        "qa_evaluations",
        ["dataset_id", "dataset_version", "split", "image_id", "model_name"],
    )
    op.drop_column("qa_evaluations", "annotation_revision")
