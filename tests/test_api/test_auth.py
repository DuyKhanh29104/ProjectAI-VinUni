from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import Settings
from src.main import create_app
from src.models.application_user import ApplicationUser
from src.services.auth_service import AuthenticationError, VerifiedIdentity


class FakeTokenVerifier:
    async def verify(self, token: str) -> VerifiedIdentity:
        identities = {
            "admin-token": VerifiedIdentity("admin-id", "admin@example.com", "Admin"),
            "annotator-token": VerifiedIdentity("annotator-id", "annotator@example.com", "Annotator"),
        }
        try:
            return identities[token]
        except KeyError as error:
            raise AuthenticationError("Invalid test token.") from error


@pytest_asyncio.fixture
async def authenticated_client(
    postgres_async_session_factory: async_sessionmaker[AsyncSession],
    postgres_test_database,
) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_env="test",
        database_url=postgres_test_database.async_url,
        auth_enabled=True,
        supabase_url="https://project.supabase.co",
        auth_bootstrap_admin_emails="admin@example.com",
        _env_file=None,
    )
    application = create_app(
        settings=settings,
        db_session_factory=postgres_async_session_factory,
        auth_verifier=FakeTokenVerifier(),
    )
    transport = ASGITransport(app=application)
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_protected_route_requires_bearer_token(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_first_verified_request_creates_default_annotator(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer annotator-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "annotator-id",
        "email": "annotator@example.com",
        "displayName": "Annotator",
        "role": "annotator",
        "disabled": False,
    }


@pytest.mark.asyncio
async def test_admin_can_assign_role_and_annotator_cannot(authenticated_client: AsyncClient) -> None:
    annotator_headers = {"Authorization": "Bearer annotator-token"}
    admin_headers = {"Authorization": "Bearer admin-token"}
    await authenticated_client.get("/api/v1/auth/me", headers=annotator_headers)
    await authenticated_client.get("/api/v1/auth/me", headers=admin_headers)

    forbidden = await authenticated_client.patch(
        "/api/v1/auth/users/admin-id/role",
        headers=annotator_headers,
        json={"role": "reviewer"},
    )
    updated = await authenticated_client.patch(
        "/api/v1/auth/users/annotator-id/role",
        headers=admin_headers,
        json={"role": "reviewer"},
    )

    assert forbidden.status_code == 403
    assert updated.status_code == 200
    assert updated.json()["role"] == "reviewer"


@pytest.mark.asyncio
async def test_annotator_cannot_run_agent(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        "/api/v1/dataset/images/smoke/example/evaluate",
        headers={"Authorization": "Bearer annotator-token"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_pipeline_status_requires_reviewer_or_admin(authenticated_client: AsyncClient) -> None:
    annotator = await authenticated_client.get(
        "/api/v1/ingestion/runs",
        headers={"Authorization": "Bearer annotator-token"},
    )
    admin = await authenticated_client.get(
        "/api/v1/ingestion/runs",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert annotator.status_code == 403
    assert admin.status_code == 200


@pytest.mark.asyncio
async def test_bootstrap_admin_email_recovers_an_existing_profile(
    authenticated_client: AsyncClient,
    postgres_async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = {"Authorization": "Bearer admin-token"}
    assert (await authenticated_client.get("/api/v1/auth/me", headers=headers)).json()["role"] == "admin"
    async with postgres_async_session_factory() as session:
        await session.execute(
            update(ApplicationUser).where(ApplicationUser.id == "admin-id").values(role="annotator")
        )
        await session.commit()

    recovered = await authenticated_client.get("/api/v1/auth/me", headers=headers)

    assert recovered.status_code == 200
    assert recovered.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_bootstrap_email_does_not_override_an_explicit_demotion(
    authenticated_client: AsyncClient,
    postgres_async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    bootstrap_headers = {"Authorization": "Bearer admin-token"}
    other_headers = {"Authorization": "Bearer annotator-token"}
    await authenticated_client.get("/api/v1/auth/me", headers=bootstrap_headers)
    await authenticated_client.get("/api/v1/auth/me", headers=other_headers)
    async with postgres_async_session_factory() as session:
        await session.execute(
            update(ApplicationUser).where(ApplicationUser.id == "annotator-id").values(role="admin")
        )
        await session.execute(
            update(ApplicationUser).where(ApplicationUser.id == "admin-id").values(role="annotator")
        )
        await session.commit()

    demoted = await authenticated_client.get("/api/v1/auth/me", headers=bootstrap_headers)

    assert demoted.status_code == 200
    assert demoted.json()["role"] == "annotator"
