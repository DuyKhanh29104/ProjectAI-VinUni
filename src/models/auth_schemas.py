from typing import Literal

from pydantic import Field

from src.models.base_schemas import ApiModel

ApplicationRole = Literal["annotator", "reviewer", "admin"]


class AuthenticatedUser(ApiModel):
    id: str
    email: str = Field(min_length=3, max_length=320)
    display_name: str
    role: ApplicationRole
    disabled: bool = False


class ApplicationUserList(ApiModel):
    count: int
    results: list[AuthenticatedUser]


class ApplicationUserRoleUpdate(ApiModel):
    role: ApplicationRole


class ApplicationUserProfileUpdate(ApiModel):
    display_name: str = Field(min_length=1, max_length=255)
