from redis import asyncio as aioredis


class GroupRegistry:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def register(self, group_number: int, chat_id: int) -> None:
        await self._redis.set(f"group_{group_number}", chat_id)

    async def unregister(self, group_number: int) -> None:
        await self._redis.delete(f"group_{group_number}")

    async def get_chat_id(self, group_number: int) -> int | None:
        value = await self._redis.get(f"group_{group_number}")
        return int(value) if value else None

    async def get_all(self) -> dict[int, int]:
        keys = await self._redis.keys("group_*")  # type: ignore
        result: dict[int, int] = {}
        for key in keys:
            group_n = int(key.decode().split("_")[1])
            chat_id = int(await self._redis.get(key))
            result[group_n] = chat_id
        return result
