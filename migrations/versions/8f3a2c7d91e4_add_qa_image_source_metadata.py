"""add QA image source metadata

Revision ID: 8f3a2c7d91e4
Revises: 4a7b8c9d0e1f
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f3a2c7d91e4"
down_revision: str | None = "4a7b8c9d0e1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("qa_images") as batch_op:
        batch_op.add_column(sa.Column("provider", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("dataset", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("release", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("modality", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("asset_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("data_format", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("storage_key", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("qa_images") as batch_op:
        batch_op.drop_column("storage_key")
        batch_op.drop_column("data_format")
        batch_op.drop_column("asset_type")
        batch_op.drop_column("modality")
        batch_op.drop_column("release")
        batch_op.drop_column("dataset")
        batch_op.drop_column("provider")
