"""Validate the Alembic lifecycle on a dedicated PostgreSQL test database."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from src.db.session import normalize_async_database_url

_LOCK_NAMESPACE = 127991
_DATABASE_OVERRIDE_QUERY_KEYS = {"database", "dbname"}


def _run_lifecycle(config: Config, database_url: str) -> None:
    with patch.dict(os.environ, {"DATABASE_URL": database_url}):
        command.upgrade(config, "head")
        command.check(config)
        command.downgrade(config, "base")
        command.upgrade(config, "head")


async def _run_guarded_lifecycle(config: Config, database_url: str) -> str:
    """Verify and exclusively lock the live database before destructive DDL."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            current_database = await connection.scalar(text("SELECT current_database()"))
            if not isinstance(current_database, str) or not current_database.lower().endswith("_test"):
                raise RuntimeError(
                    "Refusing destructive migration check: the connected PostgreSQL database "
                    "must have a name ending in '_test'"
                )
            lock_acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:namespace, hashtext(current_database()))"),
                {"namespace": _LOCK_NAMESPACE},
            )
            await connection.commit()
            if not lock_acquired:
                raise RuntimeError(
                    f"Refusing destructive migration check: {current_database} is already in use by another test run"
                )
            try:
                await asyncio.to_thread(_run_lifecycle, config, database_url)
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:namespace, hashtext(current_database()))"),
                    {"namespace": _LOCK_NAMESPACE},
                )
                await connection.commit()
    finally:
        await engine.dispose()
    return current_database


def main() -> None:
    """Check for one head, schema drift, and reversible migrations."""
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    config = Config(project_root / "alembic.ini")
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected exactly one migration head, found: {heads}")

    configured_url = os.getenv("TEST_DATABASE_URL")
    if not configured_url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required; point it at a disposable PostgreSQL database whose name ends in '_test'"
        )
    database_url = normalize_async_database_url(configured_url)
    parsed_url = make_url(database_url)
    override_keys = _DATABASE_OVERRIDE_QUERY_KEYS.intersection(key.lower() for key in parsed_url.query)
    if override_keys:
        keys = ", ".join(sorted(override_keys))
        raise RuntimeError(f"TEST_DATABASE_URL must not override the database through query parameter(s): {keys}")
    database_name = parsed_url.database or ""
    if not database_name.lower().endswith("_test"):
        raise RuntimeError("Refusing destructive migration check: TEST_DATABASE_URL database name must end in '_test'")

    verified_database_name = asyncio.run(_run_guarded_lifecycle(config, database_url))

    print(f"PostgreSQL migration check passed for {verified_database_name} at head {heads[0]}")


if __name__ == "__main__":
    main()
