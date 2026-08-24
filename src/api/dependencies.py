from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.models.auth_schemas import ApplicationRole, AuthenticatedUser
from src.services.auth_service import ApplicationUserService, AuthenticationError, TokenVerifier
from src.services.real_dataset_service import RealDatasetService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise RuntimeError("Database session factory is unavailable outside the application lifespan")
    async with session_factory() as session:
        yield session


def get_real_dataset_service(request: Request) -> RealDatasetService:
    service = getattr(request.app.state, "real_dataset_service", None)
    if service is None:
        raise RuntimeError("Real dataset service is unavailable")
    return cast(RealDatasetService, service)


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> AuthenticatedUser:
    settings = cast(Settings, request.app.state.settings)
    if not settings.auth_enabled:
        return AuthenticatedUser(
            id=settings.auth_dev_user_id,
            email=settings.auth_dev_user_email,
            display_name=settings.auth_dev_user_name,
            role="admin",
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Supabase access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    verifier = cast(TokenVerifier | None, getattr(request.app.state, "auth_verifier", None))
    if verifier is None:
        raise RuntimeError("Authentication verifier is unavailable")
    try:
        identity = await verifier.verify(credentials.credentials)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    profile = await ApplicationUserService.ensure_profile(session, identity, settings)
    if profile.disabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This user account is disabled.")
    return ApplicationUserService.to_response(profile)


def require_roles(*roles: ApplicationRole) -> Callable[..., Awaitable[AuthenticatedUser]]:
    allowed = frozenset(roles)

    async def dependency(
        current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(sorted(allowed))}.",
            )
        return current_user

    return dependency
