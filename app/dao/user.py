import asyncpg


class UserDAO:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_tg_id(self, tg_id: int) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", tg_id)

    async def get_all(self) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM users")

    async def create(self, tg_id: int, student_id: int, group_number: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (tg_id, student_id, group_number) VALUES ($1, $2, $3)",
                tg_id,
                student_id,
                group_number,
            )

    async def exists(self, tg_id: int) -> bool:
        return await self.get_by_tg_id(tg_id) is not None
