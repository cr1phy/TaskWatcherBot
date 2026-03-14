from dataclasses import dataclass, fields
from typing import Any

import asyncpg
from redis import asyncio as aioredis
from telethon import TelegramClient  # type: ignore

from .config import (
    CLOUDTEXT_BASE_URL,
    CLOUDTEXT_EMAIL,
    CLOUDTEXT_PASSWORD,
    DB_URL,
    GSHEETS_CREDS_FILE,
    REDIS_URL,
    SPREADSHEETS_FOLDER_ID,
    TG_API_HASH,
    TG_API_ID,
    TG_SESSION,
)
from .models.cloudtext import CloudTextClient
from .models.gsheets import GSheetsClient
from .services.groups import GroupRegistry
from .services.user import UserService


@dataclass
class Container:
    users: UserService
    groups: GroupRegistry
    cloudtext: CloudTextClient
    gsheets: GSheetsClient
    tg_client: TelegramClient

    @classmethod
    async def create(cls) -> "Container":
        pool = await asyncpg.create_pool(DB_URL)
        redis = aioredis.from_url(REDIS_URL)

        return cls(
            users=UserService(pool),
            groups=GroupRegistry(redis),
            cloudtext=CloudTextClient(
                CLOUDTEXT_EMAIL,
                CLOUDTEXT_PASSWORD,
                CLOUDTEXT_BASE_URL,
                redis=redis,
            ),
            gsheets=GSheetsClient(
                GSHEETS_CREDS_FILE, SPREADSHEETS_FOLDER_ID, pool, redis
            ),
            tg_client=TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH),
        )

    def as_kwargs(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    async def close(self) -> None:
        await self.cloudtext.close()
        await self.tg_client.disconnect()
