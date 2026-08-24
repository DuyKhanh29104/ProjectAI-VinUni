import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.routes import router
from src.config import IngestionSettings, Settings, get_settings
from src.db.session import create_database_engine, create_session_factory
from src.models.schemas import ServiceHealthResponse
from src.services.auth_service import SupabaseJwtVerifier, TokenVerifier
from src.services.google_cloud import create_gcs_storage_client
from src.services.real_dataset_service import RealDatasetService

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    db_session_factory: async_sessionmaker[AsyncSession] | None = None,
    real_dataset_service: RealDatasetService | None = None,
    auth_verifier: TokenVerifier | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    if app_settings.app_env == "production" and app_settings.dataset_backend == "database":
        # Validate required GCS configuration and credential material at boot.
        # Object permissions are verified by the post-deploy dataset smoke test;
        # `/ready` intentionally needs only PostgreSQL so least-privilege object
        # readers are not forced to hold bucket-list permissions.
        cloud_settings = IngestionSettings()
        _ = cloud_settings.bucket_name
        create_gcs_storage_client(cloud_settings)
    database_engine = None
    application_session_factory = db_session_factory
    if application_session_factory is None:
        database_engine = create_database_engine(app_settings.database_url)
        application_session_factory = create_session_factory(database_engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.db_session_factory = application_session_factory
        application.state.auth_verifier = auth_verifier or (
            SupabaseJwtVerifier(app_settings) if app_settings.auth_enabled else None
        )
        application.state.real_dataset_service = real_dataset_service or RealDatasetService(
            app_settings.dataset_root,
            dataset_backend=app_settings.dataset_backend,
            default_split=app_settings.dataset_default_split,
            dataset_id=app_settings.dataset_id,
            dataset_version=app_settings.dataset_version,
            model_name=app_settings.yolo_model_name,
            evaluation_cache_entries=app_settings.agent_evaluation_cache_entries,
        )
        logger.info("Starting %s in %s mode", app_settings.app_name, app_settings.app_env)
        try:
            yield
        finally:
            logger.info("Shutting down %s", app_settings.app_name)
            if database_engine is not None:
                await database_engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        description=app_settings.app_description,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_values,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.get(
        "/health",
        response_model=ServiceHealthResponse,
        tags=["System"],
    )
    @application.get(
        "/api/health",
        response_model=ServiceHealthResponse,
        tags=["System"],
        include_in_schema=False,
    )
    @application.get(
        "/api/v1/health",
        response_model=ServiceHealthResponse,
        tags=["System"],
    )
    async def health() -> ServiceHealthResponse:
        return ServiceHealthResponse(
            environment=app_settings.app_env,
            version=app_settings.app_version,
        )

    @application.get(
        "/ready",
        response_model=ServiceHealthResponse,
        tags=["System"],
    )
    async def readiness() -> ServiceHealthResponse:
        """Report ready after the application can reach PostgreSQL."""
        try:
            async with application_session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as error:
            logger.error("PostgreSQL readiness check failed: %s", error)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The service is not ready.",
            ) from error
        return ServiceHealthResponse(
            environment=app_settings.app_env,
            version=app_settings.app_version,
        )

    # `/api/v1` is the canonical public surface. Keep the unversioned routes as
    # compatibility aliases while clients migrate, but omit them from OpenAPI so
    # generated clients only discover the stable V1 contract.
    application.include_router(router, prefix="/api", include_in_schema=False)
    application.include_router(router, prefix="/api/v1")
    return application


app = create_app()
