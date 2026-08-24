from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import jwt
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.models.application_user import ApplicationUser
from src.models.auth_schemas import ApplicationRole, AuthenticatedUser


class AuthenticationError(ValueError):
    """Raised when a bearer token cannot establish a trusted identity."""


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    email: str
    display_name: str


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> VerifiedIdentity: ...


class SupabaseJwtVerifier:
    _ALLOWED_ALGORITHMS = {"ES256", "RS256", "HS256"}

    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_url:
            raise ValueError("SUPABASE_URL is required to verify access tokens.")
        self._issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
        self._audience = settings.supabase_jwt_audience
        self._secret = (
            settings.supabase_jwt_secret.get_secret_value()
            if settings.supabase_jwt_secret is not None
            else None
        )
        jwks_url = settings.supabase_jwks_url or f"{self._issuer}/.well-known/jwks.json"
        self._jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)

    async def verify(self, token: str) -> VerifiedIdentity:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = str(header.get("alg", ""))
            if algorithm not in self._ALLOWED_ALGORITHMS:
                raise AuthenticationError("The access token uses an unsupported signing algorithm.")
            if algorithm == "HS256":
                if not self._secret:
                    raise AuthenticationError(
                        "SUPABASE_JWT_SECRET is required for legacy HS256 access tokens."
                    )
                signing_key: Any = self._secret
            else:
                signing_key = await asyncio.to_thread(
                    lambda: self._jwks_client.get_signing_key_from_jwt(token).key
                )
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except AuthenticationError:
            raise
        except jwt.PyJWTError as error:
            raise AuthenticationError("The access token is invalid or expired.") from error
        except Exception as error:
            raise AuthenticationError("The access token signing key could not be verified.") from error

        subject = claims.get("sub")
        email = claims.get("email")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError("The access token does not identify a user.")
        if not isinstance(email, str) or not email.strip():
            raise AuthenticationError("Label Guardian requires an email-authenticated user.")
        metadata = claims.get("user_metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        display_name = metadata.get("full_name") or metadata.get("name") or email.split("@", 1)[0]
        return VerifiedIdentity(
            subject=subject,
            email=email.strip().lower(),
            display_name=str(display_name).strip() or email.split("@", 1)[0],
        )


class ApplicationUserService:
    @staticmethod
    async def ensure_profile(
        session: AsyncSession,
        identity: VerifiedIdentity,
        settings: Settings,
    ) -> ApplicationUser:
        existing = await session.get(ApplicationUser, identity.subject)
        if existing is not None:
            changed = False
            if existing.email != identity.email:
                existing.email = identity.email
                existing.updated_at = datetime.now(UTC)
                changed = True
            # Bootstrap configuration remains a last-resort recovery mechanism
            # if the env var was added after the initial profile was created.
            # Once any admin exists, a deliberately demoted bootstrap account
            # must not silently grant itself admin again on the next request.
            if identity.email in settings.auth_bootstrap_admin_email_values and existing.role != "admin":
                admin_id = await session.scalar(
                    select(ApplicationUser.id).where(ApplicationUser.role == "admin").limit(1)
                )
                if admin_id is None:
                    existing.role = "admin"
                    existing.updated_at = datetime.now(UTC)
                    changed = True
            if changed:
                await session.commit()
            return cast(ApplicationUser, existing)

        now = datetime.now(UTC)
        role = "admin" if identity.email in settings.auth_bootstrap_admin_email_values else "annotator"
        profile = ApplicationUser(
            id=identity.subject,
            email=identity.email,
            display_name=identity.display_name,
            role=role,
            disabled=False,
            created_at=now,
            updated_at=now,
        )
        session.add(profile)
        try:
            await session.commit()
        except IntegrityError:
            # Two first requests from the same new session can race. Re-read the
            # profile created by the winner instead of returning a 500.
            await session.rollback()
            profile = await session.scalar(
                select(ApplicationUser).where(ApplicationUser.id == identity.subject)
            )
            if profile is None:
                raise
        return cast(ApplicationUser, profile)

    @staticmethod
    def to_response(profile: ApplicationUser) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=profile.id,
            email=profile.email,
            display_name=profile.display_name,
            role=cast(ApplicationRole, profile.role),
            disabled=profile.disabled,
        )
