"""Application profile and role for an externally authenticated user."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ApplicationUser(Base):
    __tablename__ = "application_users"
    __table_args__ = (
        CheckConstraint("role IN ('annotator', 'reviewer', 'admin')", name="role_values"),
        Index("ix_application_users_role_disabled", "role", "disabled"),
    )

    # Supabase Auth's `sub` claim is a UUID today, but a string identifier keeps
    # the application portable to another OIDC provider without a data migration.
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    # The unique constraint already owns a b-tree index; a second non-unique
    # email index only adds write/storage overhead.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="annotator", index=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
