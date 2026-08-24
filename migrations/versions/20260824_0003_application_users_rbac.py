"""add application user profiles and RBAC

Revision ID: 20260824_0003
Revises: 20260822_0002
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0003"
down_revision: str | None = "20260822_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_users",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('annotator', 'reviewer', 'admin')",
            name=op.f("ck_application_users_role_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_users")),
        sa.UniqueConstraint("email", name=op.f("uq_application_users_email")),
    )
    op.create_index("ix_application_users_email", "application_users", ["email"])
    op.create_index("ix_application_users_role", "application_users", ["role"])
    op.create_index("ix_application_users_disabled", "application_users", ["disabled"])
    op.create_index(
        "ix_application_users_role_disabled",
        "application_users",
        ["role", "disabled"],
    )
    # Supabase exposes tables in the public schema through its Data API. With
    # RLS enabled and no public policy, only the direct backend database role
    # (the table owner/BYPASSRLS role) can read or modify application roles.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE application_users ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_application_users_role_disabled", table_name="application_users")
    op.drop_index("ix_application_users_disabled", table_name="application_users")
    op.drop_index("ix_application_users_role", table_name="application_users")
    op.drop_index("ix_application_users_email", table_name="application_users")
    op.drop_table("application_users")
