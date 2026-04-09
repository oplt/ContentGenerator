from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    admin_invite_code: str | None = None


class SignInRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)

    @field_validator("mfa_code", mode="before")
    @classmethod
    def normalize_mfa_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class MembershipRoleResponse(BaseModel):
    id: UUID | None = None
    name: str | None = None
    slug: str | None = None
    permission_codes: list[str] = []


class MembershipResponse(BaseModel):
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    role: MembershipRoleResponse | None = None
    status: str


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str | None
    is_verified: bool
    is_admin: bool = False
    mfa_enabled: bool = False
    default_tenant_id: UUID | None = None
    memberships: list[MembershipResponse] = []
    rbac_mode: str = "role_based_placeholder"


class AuthSessionResponse(BaseModel):
    user: AuthUserResponse | None = None
    requires_email_verification: bool = False
    message: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class MfaEnableResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaDisableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TenantSwitchResponse(BaseModel):
    tenant_id: UUID
