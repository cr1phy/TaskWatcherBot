import asyncio
from datetime import datetime
import time
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from aiohttp import ClientSession
import aiohttp
import structlog
from yarl import URL

from .models import Group, Journal
from .parsing import parse_groups, parse_journal


class CloudTextError(Exception):
    pass


class AuthError(CloudTextError):
    pass


class RateLimitError(CloudTextError):
    pass


class CloudTextClient:
    def __init__(self, email: str, password: str, base_url: str) -> None:
        self._logger = structlog.get_logger()
        self._email = email
        self._password = password
        self._base_url = base_url
        self._session: ClientSession | None = None

    async def start(self) -> None:
        session = ClientSession(base_url=self._base_url)

        await session.get("/login")
        xsrf = session.cookie_jar.filter_cookies(URL(self._base_url)).get("xsrf-token")
        headers = {
            "X-XSRF-TOKEN": unquote(xsrf.value),
            "Accept": "application/json",
        }

        async with session.post(
            "/login",
            headers=headers,
            json={"email": self._email, "password": self._password, "stage": 1},
        ) as response:
            if response.status != HTTPStatus.ACCEPTED:
                await session.close()
                raise AuthError("Something went wrong with logging in")

        self._session = session

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
        self._session = None

    async def _get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 5,
    ) -> Any:
        if not self._session:
            raise CloudTextError("client isn't working")

        for attempt in range(max_retries):
            async with self._session.get(path, params=params) as resp:
                if resp.status == 401:
                    raise AuthError("Куки протухли, требуется повторная авторизация")
                if resp.status == 429:
                    wait = min(30 * (attempt + 1), 180)
                    await self._logger.awarning(
                        "Rate limit на %s, ожидание %d сек...", path, wait
                    )
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    await self._logger.aerror("%s вернул %d", path, resp.status)
                    return None
                try:
                    return await resp.json()
                except (aiohttp.ContentTypeError, ValueError):
                    await self._logger.aerror("%s вернул невалидный JSON", path)
                    return None

        raise RateLimitError(
            f"Rate limit не прошёл после {max_retries} попыток: {path}"
        )

    async def get_groups(self) -> list[Group]:
        data = await self._get_json("/api/students")
        if not data:
            return []
        return parse_groups(data)

    async def get_journal(self, group_id: int) -> Journal:
        now = int(time.time())
        data = await self._get_json(
            "/api/journal",
            params={
                "group_id": f"-{group_id}",
                "date_start": int(datetime(2025, 9, 1).timestamp()),
                "date_end": now,
                "_": now,
            },
        )
        if not data:
            raise CloudTextError(f"Ошибка получения журнала для группы {group_id}")
        return parse_journal(data)
