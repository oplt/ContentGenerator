from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import hash_password, verify_password
from backend.modules.identity_access.models import RefreshSession, User
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.users.repository import UsersRepository


class UsersService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UsersRepository(db)
        self.identity_repo = IdentityRepository(db)

    async def update_profile(self, user: User, full_name: str | None) -> User:
        updated = await self.repo.update_profile(user, full_name)
        await self.db.flush()
        await self.db.refresh(updated)
        return updated

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.password_hash = hash_password(new_password)
        await self.db.flush()

    async def list_sessions(self, user: User) -> list[RefreshSession]:
        return await self.identity_repo.list_active_sessions(user.id)

    async def revoke_session(self, user: User, session_id: str) -> None:
        session = await self.identity_repo.get_session_by_id(session_id)
        if not session or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Session not found")
        await self.identity_repo.revoke_refresh_session(session)
        await self.db.flush()

    async def list_directory(self) -> list[User]:
        return await self.repo.list_active_users()
