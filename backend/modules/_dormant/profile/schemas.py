from pydantic import BaseModel


class ProfileResponse(BaseModel):
    user_id: str
    bio: str | None
    avatar_url: str | None
    location: str | None
    website: str | None


class ProfileUpdate(BaseModel):
    bio: str | None = None
    location: str | None = None
    website: str | None = None
