import pytest

from src.db.session import create_database_engine, normalize_async_database_url, normalize_sync_database_url


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        (
            "postgresql://user:p%40ss@db.example.test:5432/label_guardian?ssl=require",
            "postgresql+asyncpg://user:p%40ss@db.example.test:5432/label_guardian?ssl=require",
        ),
        (
            "postgresql://user:password@db.example.test:5432/label_guardian?sslmode=require",
            "postgresql+asyncpg://user:password@db.example.test:5432/label_guardian?ssl=require",
        ),
        (
            "postgres://user:password@db.example.test:5432/label_guardian",
            "postgresql+asyncpg://user:password@db.example.test:5432/label_guardian",
        ),
        (
            "postgresql+asyncpg://user:password@db.example.test:5432/label_guardian",
            "postgresql+asyncpg://user:password@db.example.test:5432/label_guardian",
        ),
    ],
)
def test_normalize_async_database_url(database_url: str, expected: str) -> None:
    assert normalize_async_database_url(database_url) == expected


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        (
            "postgresql://user:p%40ss@db.example.test:5432/label_guardian?sslmode=require",
            "postgresql+psycopg://user:p%40ss@db.example.test:5432/label_guardian?sslmode=require",
        ),
        (
            "postgresql://user:password@db.example.test:5432/label_guardian?ssl=require",
            "postgresql+psycopg://user:password@db.example.test:5432/label_guardian?sslmode=require",
        ),
        (
            "postgres://user:password@db.example.test:5432/label_guardian",
            "postgresql+psycopg://user:password@db.example.test:5432/label_guardian",
        ),
        (
            "postgresql+psycopg://user:password@db.example.test:5432/label_guardian",
            "postgresql+psycopg://user:password@db.example.test:5432/label_guardian",
        ),
    ],
)
def test_normalize_sync_database_url(database_url: str, expected: str) -> None:
    assert normalize_sync_database_url(database_url) == expected


@pytest.mark.parametrize("normalizer", [normalize_async_database_url, normalize_sync_database_url])
def test_database_url_normalizers_reject_sqlite(normalizer) -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        normalizer("sqlite:///./label_guardian.db")


@pytest.mark.parametrize(
    ("normalizer", "database_url", "expected_driver"),
    [
        (
            normalize_async_database_url,
            "postgresql+psycopg://user:password@db.example.test/label_guardian?sslmode=require",
            "asyncpg",
        ),
        (
            normalize_sync_database_url,
            "postgresql+asyncpg://user:password@db.example.test/label_guardian?ssl=require",
            "psycopg",
        ),
    ],
)
def test_database_url_normalizers_reject_mismatched_driver(normalizer, database_url: str, expected_driver: str) -> None:
    with pytest.raises(ValueError, match=expected_driver):
        normalizer(database_url)


@pytest.mark.parametrize("normalizer", [normalize_async_database_url, normalize_sync_database_url])
def test_database_url_normalizers_reject_conflicting_tls_parameters(normalizer) -> None:
    with pytest.raises(ValueError, match="must not set both"):
        normalizer("postgresql://user:password@db.example.test/label_guardian?ssl=require&sslmode=require")


def test_conventional_postgres_url_uses_asyncpg_driver() -> None:
    engine = create_database_engine("postgresql://user:password@db.example.test:5432/label_guardian")

    assert engine.url.drivername == "postgresql+asyncpg"
    engine.sync_engine.dispose()


def test_database_engine_uses_configured_pool_limits() -> None:
    engine = create_database_engine(
        "postgresql://user:password@db.example.test:5432/label_guardian",
        pool_size=3,
        max_overflow=0,
    )

    assert engine.sync_engine.pool.size() == 3
    assert engine.sync_engine.pool._max_overflow == 0
    engine.sync_engine.dispose()
