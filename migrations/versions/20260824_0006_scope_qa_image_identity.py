"""scope QA image identity by dataset release

Revision ID: 20260824_0006
Revises: 20260824_0005
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260824_0006"
down_revision: str | None = "20260824_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_qa_images_filename", "qa_images", type_="unique")
    op.drop_index("ix_qa_images_source_image_id", table_name="qa_images")
    op.create_index("ix_qa_images_source_image_id", "qa_images", ["source_image_id"])
    op.create_index("ix_qa_images_filename", "qa_images", ["filename"])
    op.create_index("ix_qa_images_dataset_release", "qa_images", ["dataset", "release"])
    op.create_unique_constraint(
        "uq_qa_image_dataset_release_source",
        "qa_images",
        ["dataset", "release", "source_image_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_qa_image_dataset_release_source", "qa_images", type_="unique")
    op.drop_index("ix_qa_images_dataset_release", table_name="qa_images")
    op.drop_index("ix_qa_images_filename", table_name="qa_images")
    op.drop_index("ix_qa_images_source_image_id", table_name="qa_images")
    op.create_index("ix_qa_images_source_image_id", "qa_images", ["source_image_id"], unique=True)
    op.create_unique_constraint("uq_qa_images_filename", "qa_images", ["filename"])
