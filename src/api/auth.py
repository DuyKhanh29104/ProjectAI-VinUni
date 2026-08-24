from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_db_session, require_roles
from src.models.application_user import ApplicationUser
from src.models.auth_schemas import (
    ApplicationUserList,
    ApplicationUserProfileUpdate,
    ApplicationUserRoleUpdate,
    AuthenticatedUser,
)
from src.services.auth_service import ApplicationUserService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=AuthenticatedUser)
async def get_my_profile(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    return current_user


@router.put("/me", response_model=AuthenticatedUser)
async def update_my_profile(
    payload: ApplicationUserProfileUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUser:
    profile = await session.get(ApplicationUser, current_user.id)
    if profile is None:
        # Authentication-disabled local development uses an ephemeral admin.
        return cast(
            AuthenticatedUser,
            current_user.model_copy(update={"display_name": payload.display_name.strip()}),
        )
    profile.display_name = payload.display_name.strip()
    profile.updated_at = datetime.now(UTC)
    await session.commit()
    return ApplicationUserService.to_response(profile)


@router.get("/users", response_model=ApplicationUserList)
async def list_application_users(
    _admin: Annotated[AuthenticatedUser, Depends(require_roles("admin"))],
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> ApplicationUserList:
    count = int((await session.execute(select(func.count()).select_from(ApplicationUser))).scalar_one())
    profiles = (
        await session.scalars(
            select(ApplicationUser).order_by(ApplicationUser.created_at, ApplicationUser.id).limit(limit).offset(offset)
        )
    ).all()
    return ApplicationUserList(
        count=count,
        results=[ApplicationUserService.to_response(profile) for profile in profiles],
    )


@router.patch("/users/{user_id}/role", response_model=AuthenticatedUser)
async def update_application_user_role(
    user_id: str,
    payload: ApplicationUserRoleUpdate,
    admin: Annotated[AuthenticatedUser, Depends(require_roles("admin"))],
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUser:
    profile = await session.get(ApplicationUser, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Application user was not found.")
    if profile.id == admin.id and payload.role != "admin":
        admin_count = int(
            (
                await session.execute(
                    select(func.count()).select_from(ApplicationUser).where(
                        ApplicationUser.role == "admin",
                        ApplicationUser.disabled.is_(False),
                    )
                )
            ).scalar_one()
        )
        if admin_count <= 1:
            raise HTTPException(status_code=409, detail="The last active administrator cannot remove their own role.")
    profile.role = payload.role
    profile.updated_at = datetime.now(UTC)
    await session.commit()
    return ApplicationUserService.to_response(profile)
