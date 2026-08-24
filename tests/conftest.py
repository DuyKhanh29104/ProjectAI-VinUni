import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from src import models as _models  # noqa: F401  # Ensure every mapped table is registered.
from src.config import Settings
from src.db.base import Base
from src.db.session import (
    create_database_engine,
    create_session_factory,
    normalize_async_database_url,
    normalize_sync_database_url,
)
from src.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_LOCK_NAMESPACE = 127991
_DATABASE_OVERRIDE_QUERY_KEYS = {"database", "dbname"}


@dataclass(frozen=True)
class PostgresTestDatabase:
    async_url: str
    sync_url: str


def _truncate_application_tables(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            quote = connection.dialect.identifier_preparer.quote
            table_names = ", ".join(quote(table.name) for table in Base.metadata.sorted_tables)
            connection.exec_driver_sql(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def postgres_test_database() -> Iterator[PostgresTestDatabase]:
    """Return guarded async and sync URLs for the dedicated PostgreSQL test database."""
    if os.getenv("PYTEST_XDIST_WORKER"):
        raise pytest.UsageError(
            "PostgreSQL tests cannot share one TEST_DATABASE_URL across pytest-xdist workers; "
            "run without xdist or provision one test database per worker."
        )
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        raise pytest.UsageError(
            "Database-backed tests require TEST_DATABASE_URL pointing to a dedicated PostgreSQL database "
            "whose name ends with '_test'."
        )
    normalized_raw_url = raw_url.strip()
    if normalized_raw_url.startswith("postgres://"):
        normalized_raw_url = f"postgresql://{normalized_raw_url.removeprefix('postgres://')}"
    try:
        parsed_url = make_url(normalized_raw_url)
    except ArgumentError as error:
        raise pytest.UsageError("TEST_DATABASE_URL is not a valid SQLAlchemy database URL.") from error
    if parsed_url.get_backend_name() != "postgresql":
        raise pytest.UsageError("TEST_DATABASE_URL must use PostgreSQL.")
    override_keys = _DATABASE_OVERRIDE_QUERY_KEYS.intersection(key.lower() for key in parsed_url.query)
    if override_keys:
        keys = ", ".join(sorted(override_keys))
        raise pytest.UsageError(f"TEST_DATABASE_URL must not override the database through query parameter(s): {keys}")
    database_name = parsed_url.database or ""
    if not database_name.lower().endswith("_test"):
        raise pytest.UsageError("Refusing to reset TEST_DATABASE_URL: its database name must end with '_test'.")
    driver_neutral_url = str(parsed_url.set(drivername="postgresql").render_as_string(hide_password=False))
    database = PostgresTestDatabase(
        async_url=normalize_async_database_url(driver_neutral_url),
        sync_url=normalize_sync_database_url(driver_neutral_url),
    )
    lock_engine = create_engine(database.sync_url, pool_pre_ping=True)
    try:
        with lock_engine.connect() as connection:
            current_database = connection.scalar(text("SELECT current_database()"))
            if not isinstance(current_database, str) or not current_database.lower().endswith("_test"):
                raise pytest.UsageError(
                    "Refusing to reset PostgreSQL: the connected database must have a name ending in '_test'."
                )
            lock_acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(:namespace, hashtext(current_database()))"),
                {"namespace": _LOCK_NAMESPACE},
            )
            connection.commit()
            if not lock_acquired:
                raise pytest.UsageError(
                    f"TEST_DATABASE_URL database {current_database!r} is already in use by another test run."
                )
            try:
                yield database
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:namespace, hashtext(current_database()))"),
                    {"namespace": _LOCK_NAMESPACE},
                )
                connection.commit()
    finally:
        lock_engine.dispose()


@pytest.fixture(scope="session")
def migrated_postgres_database(postgres_test_database: PostgresTestDatabase) -> PostgresTestDatabase:
    """Apply the committed Alembic history once before database-backed tests run."""
    config = Config(PROJECT_ROOT / "alembic.ini")
    with patch.dict(os.environ, {"DATABASE_URL": postgres_test_database.async_url}):
        command.upgrade(config, "head")
    return postgres_test_database


@pytest.fixture
def clean_postgres_database(migrated_postgres_database: PostgresTestDatabase) -> Iterator[PostgresTestDatabase]:
    """Reset application rows around a test while preserving Alembic's revision table."""
    _truncate_application_tables(migrated_postgres_database.sync_url)
    try:
        yield migrated_postgres_database
    finally:
        _truncate_application_tables(migrated_postgres_database.sync_url)


@pytest_asyncio.fixture
async def postgres_async_session_factory(
    clean_postgres_database: PostgresTestDatabase,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_database_engine(clean_postgres_database.async_url)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


@pytest.fixture
def postgres_sync_session_factory(
    clean_postgres_database: PostgresTestDatabase,
) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(clean_postgres_database.sync_url, pool_pre_ping=True)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


@pytest_asyncio.fixture
async def client(
    postgres_async_session_factory: async_sessionmaker[AsyncSession],
    postgres_test_database: PostgresTestDatabase,
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client backed by the dedicated PostgreSQL test database."""
    settings = Settings(app_env="test", database_url=postgres_test_database.async_url, _env_file=None)
    application = create_app(settings=settings, db_session_factory=postgres_async_session_factory)
    transport = ASGITransport(app=application)

    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=transport, base_url="http://test") as api_client:
            yield api_client


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
