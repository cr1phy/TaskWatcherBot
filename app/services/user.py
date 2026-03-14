import asyncpg

from ..dao.user import UserDAO
from ..models.db.user import User


class UserService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._dao = UserDAO(pool)

    async def get(self, tg_id: int) -> User | None:
        row = await self._dao.get_by_tg_id(tg_id)
        return User.model_validate(dict(row)) if row else None

    async def get_all(self) -> list[User]:
        rows = await self._dao.get_all()
        return [User.model_validate(dict(row)) for row in rows]

    async def exists(self, tg_id: int) -> bool:
        return await self._dao.exists(tg_id)

    async def link(self, tg_id: int, student_id: int, group_number: int) -> None:
        await self._dao.create(tg_id, student_id, group_number)
