from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from src.config import Settings
from src.services.auth_service import AuthenticationError, SupabaseJwtVerifier


@pytest.mark.asyncio
async def test_legacy_supabase_token_is_verified_with_all_identity_claims() -> None:
    settings = Settings(
        app_env="test",
        auth_enabled=True,
        supabase_url="https://project.supabase.co",
        supabase_jwt_secret="test-secret-that-never-leaves-this-unit-test",
        _env_file=None,
    )
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "user-123",
            "email": "Reviewer@Example.com",
            "user_metadata": {"full_name": "QA Reviewer"},
            "aud": "authenticated",
            "iss": "https://project.supabase.co/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.supabase_jwt_secret.get_secret_value(),  # type: ignore[union-attr]
        algorithm="HS256",
    )

    identity = await SupabaseJwtVerifier(settings).verify(token)

    assert identity.subject == "user-123"
    assert identity.email == "reviewer@example.com"
    assert identity.display_name == "QA Reviewer"


@pytest.mark.asyncio
async def test_supabase_token_with_wrong_audience_is_rejected() -> None:
    secret = "test-secret-that-never-leaves-this-unit-test"
    settings = Settings(
        app_env="test",
        auth_enabled=True,
        supabase_url="https://project.supabase.co",
        supabase_jwt_secret=secret,
        _env_file=None,
    )
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "user-123",
            "email": "reviewer@example.com",
            "aud": "not-this-api",
            "iss": "https://project.supabase.co/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError, match="invalid or expired"):
        await SupabaseJwtVerifier(settings).verify(token)


def test_production_requires_authentication() -> None:
    with pytest.raises(ValidationError, match="AUTH_ENABLED must be true"):
        Settings(app_env="production", auth_enabled=False, _env_file=None)


def test_production_rejects_local_cors_origin() -> None:
    with pytest.raises(ValidationError, match="local origins"):
        Settings(
            app_env="production",
            auth_enabled=True,
            supabase_url="https://project.supabase.co",
            dataset_backend="database",
            dataset_id="nuscenes",
            dataset_version="v1.0-mini",
            database_url="postgresql+asyncpg://user:password@db.example.com/postgres",
            cors_origins="http://localhost:5173",
            _env_file=None,
        )


def test_production_configuration_accepts_explicit_remote_services() -> None:
    settings = Settings(
        app_env="production",
        auth_enabled=True,
        supabase_url="https://project.supabase.co",
        dataset_backend="database",
        dataset_id="nuscenes",
        dataset_version="v1.0-mini",
        database_url="postgresql+asyncpg://user:password@db.example.com/postgres",
        cors_origins="https://label-guardian.example.com",
        auth_bootstrap_admin_emails="admin@example.com",
        _env_file=None,
    )

    assert settings.cors_origin_values == ["https://label-guardian.example.com"]


def test_production_requires_a_recovery_administrator() -> None:
    with pytest.raises(ValidationError, match="AUTH_BOOTSTRAP_ADMIN_EMAILS"):
        Settings(
            app_env="production",
            auth_enabled=True,
            supabase_url="https://project.supabase.co",
            dataset_backend="database",
            dataset_id="nuscenes",
            dataset_version="v1.0-mini",
            database_url="postgresql+asyncpg://user:password@db.example.com/postgres",
            cors_origins="https://label-guardian.example.com",
            _env_file=None,
        )


def test_production_rejects_cors_origin_with_a_path() -> None:
    with pytest.raises(ValidationError, match="without paths"):
        Settings(
            app_env="production",
            auth_enabled=True,
            supabase_url="https://project.supabase.co",
            dataset_backend="database",
            dataset_id="nuscenes",
            dataset_version="v1.0-mini",
            database_url="postgresql+asyncpg://user:password@db.example.com/postgres",
            cors_origins="https://label-guardian.example.com/app",
            auth_bootstrap_admin_emails="admin@example.com",
            _env_file=None,
        )
