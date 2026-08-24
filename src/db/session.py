from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _rename_query_parameter(database_url: URL, source: str, target: str) -> URL:
    query = dict(database_url.query)
    if source not in query:
        return database_url
    if target in query:
        raise ValueError(f"Database URL must not set both '{source}' and '{target}'")
    query[target] = query.pop(source)
    return database_url.set(query=query)


def normalize_async_database_url(database_url: str) -> str:
    """Return a PostgreSQL URL suitable for the async application engine.

    Hosting dashboards (including Supabase) commonly provide ``postgresql://``.
    SQLAlchemy interprets that as the synchronous psycopg2 dialect, which cannot
    be used by the application's async database layer. Default it to the installed
    asyncpg dialect. Label Guardian no longer supports SQLite or other database
    backends.
    """
    normalized_url = database_url.strip()
    if normalized_url.startswith("postgres://"):
        normalized_url = f"postgresql://{normalized_url.removeprefix('postgres://')}"

    parsed_url = make_url(normalized_url)
    if parsed_url.get_backend_name() != "postgresql":
        raise ValueError("Label Guardian requires a PostgreSQL DATABASE_URL")
    if parsed_url.drivername not in {"postgresql", "postgresql+asyncpg"}:
        raise ValueError("Label Guardian DATABASE_URL must use the asyncpg PostgreSQL driver")
    parsed_url = _rename_query_parameter(parsed_url, "sslmode", "ssl")
    return str(parsed_url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False))


def normalize_sync_database_url(database_url: str) -> str:
    """Return a PostgreSQL URL suitable for the synchronous ingestion worker."""
    normalized_url = database_url.strip()
    if normalized_url.startswith("postgres://"):
        normalized_url = f"postgresql://{normalized_url.removeprefix('postgres://')}"

    parsed_url = make_url(normalized_url)
    if parsed_url.get_backend_name() != "postgresql":
        raise ValueError("Label Guardian ingestion requires a PostgreSQL database URL")
    if parsed_url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("Label Guardian ingestion database URL must use the psycopg PostgreSQL driver")
    parsed_url = _rename_query_parameter(parsed_url, "ssl", "sslmode")
    return str(parsed_url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False))


def create_database_engine(database_url: str) -> AsyncEngine:
    """Create the application's async database engine."""
    return create_async_engine(
        normalize_async_database_url(database_url),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
