from pydantic import BaseModel, EmailStr, Field


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    admin_invite_code: str | None = None


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class AuthUserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None
    is_verified: bool
    is_admin: bool = False
    mfa_enabled: bool = False


class AuthTokensResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


# Email verification
class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


# Password reset
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


# MFA
class MfaEnableResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaDisableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
