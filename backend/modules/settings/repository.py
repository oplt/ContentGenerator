from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.settings.models import AppSetting


class SettingsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> list[AppSetting]:
        result = await self.db.execute(select(AppSetting).order_by(AppSetting.key.asc()))
        return list(result.scalars().all())

    async def list_by_prefix(self, prefix: str) -> list[AppSetting]:
        result = await self.db.execute(
            select(AppSetting)
            .where(AppSetting.key.like(f"{prefix}%"))
            .order_by(AppSetting.key.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, setting_id: str) -> AppSetting | None:
        result = await self.db.execute(select(AppSetting).where(AppSetting.id == setting_id))
        return result.scalar_one_or_none()

    async def get_by_key(self, key: str) -> AppSetting | None:
        result = await self.db.execute(select(AppSetting).where(AppSetting.key == key))
        return result.scalar_one_or_none()

    async def create(self, key: str, value: str, description: str | None) -> AppSetting:
        setting = AppSetting(key=key, value=value, description=description)
        self.db.add(setting)
        await self.db.flush()
        return setting

    async def delete(self, setting: AppSetting) -> None:
        await self.db.delete(setting)
        await self.db.flush()
