import asyncio
from functools import partial
from typing import Any, Callable

import asyncpg
import structlog
from gspread import Client, Spreadsheet, oauth
from redis import asyncio as aioredis

from ...dao.spreadsheet import SpreadsheetDAO
from ...models.cloudtext import Journal
from .filler import SpreadsheetFiller
from .helpers import retry_api


class GSheetsClient:
    _logger = structlog.get_logger()

    def __init__(
        self,
        creds_file: str,
        folder_id: str,
        pool: asyncpg.Pool,
        redis: aioredis.Redis,
    ) -> None:
        self._creds_file = creds_file
        self._folder_id = folder_id
        self._dao = SpreadsheetDAO(pool)
        self._redis = redis
        self._filler = SpreadsheetFiller()
        self._account: Client | None = None

    def start(self) -> None:
        self._account = oauth(credentials_filename=self._creds_file)

    async def get_or_create_sheet(self, group_number: int, journal: Journal) -> str:
        cache_key = f"spreadsheet:{group_number}"

        if cached := await self._redis.get(cache_key):
            return cached.decode()

        if row := await self._dao.get(group_number):
            await self._redis.set(cache_key, row.spreadsheet_id)
            return row.spreadsheet_id

        spreadsheet = await self._create_spreadsheet(
            f"Статистика по ДЗ и пробникам (Группа №{group_number})"
        )
        await self._filler.add_dated_sheet(spreadsheet, journal)
        await self._dao.save(group_number, spreadsheet.id, spreadsheet.url)
        await self._redis.set(cache_key, spreadsheet.id)
        await self._logger.ainfo("sheet_created", group_number=group_number)
        return spreadsheet.id

    async def update_all_sheets(self, journals: dict[int, Any]) -> None:
        rows = await self._dao.get_all()
        for row in rows:
            if journal := journals.get(row.group_number):
                try:
                    spreadsheet = await self._open(row.spreadsheet_id)
                    await self._filler.add_dated_sheet(spreadsheet, journal)
                    await self._logger.ainfo(
                        "sheet_updated", group_number=row.group_number
                    )
                except Exception as e:
                    await self._logger.aerror(
                        "sheet_update_failed",
                        group_number=row.group_number,
                        error=str(e),
                    )

    async def _run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def _create_spreadsheet(self, title: str) -> Spreadsheet:
        assert self._account
        return await self._run(
            self._account.create,
            title,
            folder_id=self._folder_id,
        )

    async def _open(self, spreadsheet_id: str) -> Spreadsheet:
        assert self._account
        return await self._run(retry_api, self._account.open_by_key, spreadsheet_id)
