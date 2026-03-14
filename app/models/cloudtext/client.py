import asyncio
import time
from datetime import datetime
from typing import Any
from urllib.parse import unquote
import redis.asyncio as aioredis
import aiohttp
import structlog
from aiohttp import ClientSession
from yarl import URL

from .models import Group, Journal
from .parsing import parse_groups, parse_journal, parse_task_max_ball


class CloudTextError(Exception):
    pass


class AuthError(CloudTextError):
    pass


class RateLimitError(CloudTextError):
    pass


class CloudTextClient:
    def __init__(
        self, email: str, password: str, base_url: str, redis: aioredis.Redis
    ) -> None:
        self._logger = structlog.get_logger()
        self._email = email
        self._password = password
        self._base_url = base_url
        self._session: ClientSession | None = None
        self._semaphore = asyncio.Semaphore(1)
        self._max_balls: dict[int, int] = {}
        self._max_balls_updated: float = 0
        self._max_balls_lock = asyncio.Lock()
        self._redis = redis
        self.busy: bool = False

    async def start(self) -> None:
        session = ClientSession(base_url=self._base_url)

        await session.get("/login")
        xsrf = session.cookie_jar.filter_cookies(URL(self._base_url)).get("XSRF-TOKEN")
        if xsrf is None:
            await session.close()
            raise AuthError("XSRF-TOKEN cookie not found during authentication")

        headers = {
            "X-XSRF-TOKEN": unquote(xsrf.value),
            "Accept": "application/json",
        }

        async with session.post(
            "/login",
            headers=headers,
            json={"email": self._email, "password": self._password, "stage": 1},
        ) as response:
            if response.status != 200:
                await session.close()
                raise AuthError(f"Login failed with status {response.status}")

        self._session = session
        await self._logger.ainfo("cloudtext_authenticated", email=self._email)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
        self._session = None
        await self._logger.ainfo("cloudtext_session_closed")

    async def _get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 5,
    ) -> Any:
        if not self._session:
            raise CloudTextError("Client is not started")

        async with self._semaphore:
            for attempt in range(max_retries):
                async with self._session.get(path, params=params) as resp:
                    if resp.status == 401:
                        raise AuthError("Session expired")
                    if resp.status == 429:
                        wait = min(30 * (attempt + 1), 180)
                        await self._logger.awarning("rate_limit", path=path, wait=wait)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status != 200:
                        await self._logger.aerror(
                            "http_error", path=path, status=resp.status
                        )
                        return None
                    try:
                        return await resp.json()
                    except (aiohttp.ContentTypeError, ValueError):
                        await self._logger.aerror("invalid_json", path=path)
                        return None

        raise RateLimitError(f"Rate limit after {max_retries} retries: {path}")

    async def get_max_balls(self, ttl: int = 86400) -> dict[int, int]:
        async with self._max_balls_lock:
            if time.time() - self._max_balls_updated < ttl:
                return self._max_balls

            if self._redis:
                cached = await self._redis.get("ct:max_balls")
                if cached:
                    import json

                    self._max_balls = {int(k): v for k, v in json.loads(cached).items()}
                    self._max_balls_updated = time.time()
                    await self._logger.ainfo(
                        "max_balls_from_cache", count=len(self._max_balls)
                    )
                    return self._max_balls

            self._max_balls = await self.build_max_ball_map()
            self._max_balls_updated = time.time()

            if self._redis:
                import json

                await self._redis.set(
                    "ct:max_balls", json.dumps(self._max_balls), ex=ttl
                )

            return self._max_balls

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
            raise CloudTextError(f"Failed to get journal for group {group_id}")
        return parse_journal(data)

    async def get_all_tasks(self) -> list[dict[str, Any]]:
        all_tasks: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._get_json("/api/tasks", params={"page": page})
            if not data:
                break
            all_tasks.extend(data["data"])
            await self._logger.ainfo(
                "tasks_page",
                page=page,
                total=data["last_page"],
                count=len(data["data"]),
            )
            if page >= data["last_page"]:
                break
            page += 1
            await asyncio.sleep(0.5)
        return all_tasks

    async def get_task_detail(self, task_id: int) -> dict[str, Any]:
        data = await self._get_json(f"/api/tasks/{task_id}/edit")
        return data or {}

    async def get_task_max_ball(self, task_id: int) -> int:
        detail = await self.get_task_detail(task_id)
        return parse_task_max_ball(detail)

    async def build_max_ball_map(self) -> dict[int, int]:
        tasks = await self.get_all_tasks()
        max_balls: dict[int, int] = {}
        for _i, t in enumerate(tasks):
            task_id = t["id"]
            try:
                mb = await self.get_task_max_ball(task_id)
                max_balls[task_id] = mb
            except Exception as e:
                await self._logger.aerror(
                    "task_max_ball_failed", task=t["name"], error=str(e)
                )
                max_balls[task_id] = 0
            await asyncio.sleep(1.5)
        return max_balls
