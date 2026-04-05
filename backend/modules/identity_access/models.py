from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"


class MembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    memberships: Mapped[list["TenantUser"]] = relationship(back_populates="user")
    refresh_sessions: Mapped[list["RefreshSession"]] = relationship(back_populates="user")


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (Index("ix_tenants_slug", "slug", unique=True),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        String(32), default=TenantStatus.TRIAL.value, nullable=False
    )
    plan_tier: Mapped[str] = mapped_column(String(64), default="starter", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    settings: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)

    memberships: Mapped[list["TenantUser"]] = relationship(back_populates="tenant")


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_roles_tenant_id_slug"),
        Index("ix_roles_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permission_codes: Mapped[list[str]] = mapped_column(default=list, nullable=False)


class Permission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (Index("ix_permissions_code", "code", unique=True),)

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")


class TenantUser(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tenant_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_users_tenant_id_user_id"),
        Index("ix_tenant_users_user_id", "user_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    membership_status: Mapped[MembershipStatus] = mapped_column(
        String(32), default=MembershipStatus.ACTIVE.value, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")
    role: Mapped["Role | None"] = relationship()


class RefreshSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (Index("ix_refresh_sessions_token_hash", "token_hash", unique=True),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    user: Mapped["User"] = relationship(back_populates="refresh_sessions")
