from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules._dormant.profile.models import UserProfile
from backend.modules._dormant.profile.repository import ProfileRepository


class ProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProfileRepository(db)

    async def get_profile(self, user_id: str) -> UserProfile:
        return await self.repo.get_or_create(user_id)

    async def update_profile(
        self,
        user_id: str,
        bio: str | None,
        location: str | None,
        website: str | None,
    ) -> UserProfile:
        profile = await self.repo.get_or_create(user_id)
        await self.repo.update(profile, bio=bio, location=location, website=website)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def set_avatar_url(self, user_id: str, url: str | None) -> UserProfile:
        profile = await self.repo.get_or_create(user_id)
        profile.avatar_url = url
        if url is None:
            profile.avatar_storage_key = None
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def replace_avatar(
        self,
        user_id: str,
        avatar_url: str,
        storage_key: str,
    ) -> tuple[UserProfile, str | None]:
        profile = await self.repo.get_or_create(user_id)
        previous_key = profile.avatar_storage_key
        profile.avatar_url = avatar_url
        profile.avatar_storage_key = storage_key
        await self.db.commit()
        await self.db.refresh(profile)
        return profile, previous_key

    async def clear_avatar(self, user_id: str) -> str | None:
        profile = await self.repo.get_or_create(user_id)
        previous_key = profile.avatar_storage_key
        profile.avatar_url = None
        profile.avatar_storage_key = None
        await self.db.commit()
        await self.db.refresh(profile)
        return previous_key
