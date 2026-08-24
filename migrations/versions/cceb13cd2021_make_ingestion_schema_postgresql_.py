"""Make the ingestion schema PostgreSQL compatible.

Revision ID: cceb13cd2021
Revises: 8f3a2c7d91e4
Create Date: 2026-08-19 11:25:12.152493
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cceb13cd2021"
down_revision: str | None = "8f3a2c7d91e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMESTAMP_COLUMNS = (
    ("ingestion_assets", "created_at", False),
    ("ingestion_job_events", "created_at", False),
    ("ingestion_jobs", "created_at", False),
    ("ingestion_jobs", "started_at", True),
    ("ingestion_jobs", "finished_at", True),
    ("qa_images", "created_at", False),
)
_BBOX_TABLES = ("qa_objects", "qa_object_provenance")
_BBOX_COORDINATES = ("xmin", "ymin", "xmax", "ymax")


def _rename_sqlite_bbox_columns(*, add_prefix: bool) -> None:
    for table_name in _BBOX_TABLES:
        for coordinate in _BBOX_COORDINATES:
            source = coordinate if add_prefix else f"bbox_{coordinate}"
            target = f"bbox_{coordinate}" if add_prefix else coordinate
            op.execute(f'ALTER TABLE "{table_name}" RENAME COLUMN "{source}" TO "{target}"')


def upgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        _rename_sqlite_bbox_columns(add_prefix=True)
        return
    if dialect_name != "postgresql":
        return

    # Existing values were written as UTC-aware datetimes into naive columns.
    # Interpret them as UTC while converting to TIMESTAMP WITH TIME ZONE.
    op.execute("SET LOCAL TIME ZONE 'UTC'")
    for table_name, column_name, nullable in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=False),
            type_=sa.DateTime(timezone=True),
            existing_nullable=nullable,
        )


def downgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        _rename_sqlite_bbox_columns(add_prefix=False)
        return
    if dialect_name != "postgresql":
        return

    op.execute("SET LOCAL TIME ZONE 'UTC'")
    for table_name, column_name, nullable in reversed(_TIMESTAMP_COLUMNS):
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(timezone=False),
            existing_nullable=nullable,
        )
