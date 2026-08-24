"""secure backend-only Supabase tables

Revision ID: 20260824_0004
Revises: 20260824_0003
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260824_0004"
down_revision: str | None = "20260824_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKEND_ONLY_TABLES = (
    "annotation_revisions",
    "audit_logs",
    "ingestion_assets",
    "ingestion_job_events",
    "ingestion_jobs",
    "qa_cases",
    "qa_evaluations",
    "qa_images",
    "qa_object_provenance",
    "qa_objects",
)


def upgrade() -> None:
    # Supabase exposes `public` through its Data API. These tables are consumed
    # only by FastAPI/worker direct PostgreSQL connections, so browser roles get
    # neither grants nor policies. RLS is a second line of defense.
    if op.get_bind().dialect.name == "postgresql":
        for table_name in _BACKEND_ONLY_TABLES:
            op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')

        all_tables = ", ".join(f'"{name}"' for name in (*_BACKEND_ONLY_TABLES, "application_users"))
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE {all_tables} FROM anon';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon';
                    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL PRIVILEGES ON TABLES FROM anon';
                    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon';
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE {all_tables} FROM authenticated';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM authenticated';
                    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL PRIVILEGES ON TABLES FROM authenticated';
                    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL PRIVILEGES ON SEQUENCES FROM authenticated';
                END IF;
            END
            $$
            """
        )

    op.drop_index("ix_application_users_email", table_name="application_users")


def downgrade() -> None:
    op.create_index("ix_application_users_email", "application_users", ["email"])
    if op.get_bind().dialect.name == "postgresql":
        for table_name in _BACKEND_ONLY_TABLES:
            op.execute(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY')
    # Deliberately do not restore broad browser grants. A code rollback must not
    # silently reopen application data through the Supabase Data API.
