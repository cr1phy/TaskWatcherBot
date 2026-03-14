import asyncpg

from ..models.db.spreadsheet import SpreadsheetRecord


class SpreadsheetDAO:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, group_number: int) -> SpreadsheetRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM spreadsheets WHERE group_number = $1", group_number
            )
            return SpreadsheetRecord.model_validate(dict(row)) if row else None

    async def get_all(self) -> list[SpreadsheetRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM spreadsheets WHERE group_number != -1"
            )
            return [SpreadsheetRecord.model_validate(dict(row)) for row in rows]

    async def save(self, group_number: int, spreadsheet_id: str, url: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO spreadsheets (group_number, spreadsheet_id, url)
                VALUES ($1, $2, $3)
                ON CONFLICT (group_number) DO UPDATE
                SET spreadsheet_id = $2, url = $3
                """,
                group_number,
                spreadsheet_id,
                url,
            )
