from redis import asyncio as aioredis


class GroupRegistry:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def register(self, group_number: int, chat_id: int) -> None:
        await self._redis.set(f"group_{group_number}", chat_id)

    async def get_all(self) -> dict[int, int]:
        keys = await self._redis.keys("group_*")
        result: dict[int, int] = {}
        for key in keys:
            group_n = int(key.decode().split("_")[1])
            chat_id = int(await self._redis.get(key))
            result[group_n] = chat_id
        return result
