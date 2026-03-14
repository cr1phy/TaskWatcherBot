import asyncio
from datetime import date
from functools import partial
from typing import Any, Callable

from gspread import Spreadsheet, Worksheet
from gspread.utils import rowcol_to_a1

from ..cloudtext.models import Journal, primary_to_secondary
from .helpers import copy_block_right, retry_api

LAYOUT = {
    "hw": {
        "start_row": 1,
        "end_row": 11,
        "start_col": 2,
        "col_width": 2,
        "name_row": 1,
        "max_ball_row": 2,
        "students_row": 4,
    },
    "probe": {
        "start_row": 12,
        "end_row": 21,
        "start_col": 2,
        "col_width": 2,
        "name_row": 12,
        "students_row": 14,
    },
    "stats": {"students_row": 23},
}

MAX_STUDENTS = 10


class SpreadsheetFiller:
    async def _run(self, func: Callable[..., Any], *args: Any, **kwargs: Any):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def add_dated_sheet(self, spreadsheet: Spreadsheet, journal: Journal) -> None:
        title = date.today().strftime("%d.%m.%Y")
        worksheet = await self._run(
            retry_api,
            spreadsheet.add_worksheet,
            title=title,
            rows=100,
            cols=200,
        )
        await self._run(self._fill, spreadsheet, worksheet, journal)

    def _fill(
        self,
        spreadsheet: Spreadsheet,
        worksheet: Worksheet,
        journal: Journal,
    ) -> None:
        sheet_id = worksheet.id
        hw = LAYOUT["hw"]
        probe = LAYOUT["probe"]
        stats = LAYOUT["stats"]

        students = journal.students
        num_students = len(students)
        rows_deleted = max(0, MAX_STUDENTS - num_students)

        actual_hw_end = hw["end_row"] - rows_deleted
        actual_probe_start = probe["start_row"] - rows_deleted
        actual_probe_end = probe["end_row"] - rows_deleted * 2
        actual_probe_students = probe["students_row"] - rows_deleted
        actual_stats_students = stats["students_row"] - rows_deleted * 2

        if rows_deleted > 0:
            hw_end = hw["students_row"] + MAX_STUDENTS - 1
            probe_end = probe["students_row"] + MAX_STUDENTS - 1
            stats_end = stats["students_row"] + MAX_STUDENTS - 1
            retry_api(worksheet.delete_rows, hw_end - rows_deleted + 1, hw_end)
            retry_api(worksheet.delete_rows, probe_end - rows_deleted + 1, probe_end)
            retry_api(worksheet.delete_rows, stats_end - rows_deleted + 1, stats_end)

        copy_requests = [
            copy_block_right(
                sheet_id,
                hw["start_col"],
                hw["start_row"],
                actual_hw_end,
                hw["start_col"] + i * hw["col_width"],
            )
            for i in range(1, len(journal.homeworks))
        ] + [
            copy_block_right(
                sheet_id,
                probe["start_col"],
                actual_probe_start,
                actual_probe_end,
                probe["start_col"] + i * probe["col_width"],
            )
            for i in range(1, len(journal.probes))
        ]
        if copy_requests:
            retry_api(spreadsheet.batch_update, {"requests": copy_requests})

        updates: list[dict[str, Any]] = []

        for i, task in enumerate(journal.homeworks):
            col = hw["start_col"] + i * hw["col_width"]
            updates.append(
                {
                    "range": rowcol_to_a1(hw["name_row"], col),
                    "values": [[task.homework_name]],
                }
            )
            updates.append(
                {
                    "range": rowcol_to_a1(hw["max_ball_row"], col),
                    "values": [[task.maximum_score]],
                }
            )

        for i, task in enumerate(journal.probes):
            col = probe["start_col"] + i * probe["col_width"]
            updates.append(
                {
                    "range": rowcol_to_a1(actual_probe_start, col),
                    "values": [[task.probe_name]],
                }
            )

        for j, student in enumerate(students):
            hw_row = hw["students_row"] + j
            probe_row = actual_probe_students + j
            stats_row = actual_stats_students + j

            for row in (hw_row, probe_row, stats_row):
                updates.append(
                    {"range": rowcol_to_a1(row, 1), "values": [[student.name]]}
                )

            for i, task in enumerate(journal.homeworks):
                col = hw["start_col"] + i * hw["col_width"]
                work = student.works.get(task.id)
                updates.append(
                    {
                        "range": rowcol_to_a1(hw_row, col),
                        "values": [[work.score if work else 0]],
                    }
                )

            for i, task in enumerate(journal.probes):
                col = probe["start_col"] + i * probe["col_width"]
                work = student.works.get(task.id)
                primary = work.score if work else 0
                updates.append(
                    {"range": rowcol_to_a1(probe_row, col), "values": [[primary]]}
                )
                updates.append(
                    {
                        "range": rowcol_to_a1(probe_row, col + 1),
                        "values": [[primary_to_secondary(primary)]],
                    }
                )

            not_done = sum(1 for t in journal.homeworks if not student.works.get(t.id))
            total_hw = len(journal.homeworks)
            percent = round(not_done / total_hw * 100) if total_hw else 0
            updates.append(
                {"range": rowcol_to_a1(stats_row, 2), "values": [[not_done]]}
            )
            updates.append(
                {"range": rowcol_to_a1(stats_row, 4), "values": [[total_hw]]}
            )
            updates.append(
                {"range": rowcol_to_a1(stats_row, 6), "values": [[f"{percent}%"]]}
            )

        retry_api(worksheet.batch_update, updates)
        self._apply_styles(
            spreadsheet,
            worksheet,
            journal,
            actual_probe_start,
            actual_stats_students,
            num_students,
        )

    def _apply_styles(
        self,
        spreadsheet: Spreadsheet,
        worksheet: Worksheet,
        journal: Journal,
        probe_start: int,
        stats_start: int,
        num_students: int,
    ) -> None:
        hw = LAYOUT["hw"]
        probe = LAYOUT["probe"]
        sheet_id = worksheet.id

        hw_end_col = hw["start_col"] + len(journal.homeworks) * hw["col_width"]
        probe_end_col = probe["start_col"] + len(journal.probes) * probe["col_width"]

        def header_range(
            start_row: int,
            end_row: int,
            start_col: int,
            end_col: int,
            color: dict[str, Any],
        ) -> dict[str, Any]:
            return {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row - 1,
                        "endRowIndex": end_row,
                        "startColumnIndex": start_col - 1,
                        "endColumnIndex": end_col,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color,
                            "textFormat": {"bold": True},
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat",
                }
            }

        blue = {"red": 0.2, "green": 0.6, "blue": 0.9}
        green = {"red": 0.4, "green": 0.7, "blue": 0.4}
        yellow = {"red": 0.95, "green": 0.95, "blue": 0.6}
        red_light = {"red": 1.0, "green": 0.8, "blue": 0.8}

        format_requests = [
            header_range(
                hw["name_row"], hw["name_row"], hw["start_col"], hw_end_col, blue
            ),
            header_range(
                probe_start, probe_start, probe["start_col"], probe_end_col, green
            ),
            header_range(stats_start, stats_start, 1, 7, yellow),
        ]

        for j in range(num_students):
            stats_row = stats_start + j
            format_requests.append(
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": sheet_id,
                                    "startRowIndex": stats_row - 1,
                                    "endRowIndex": stats_row,
                                    "startColumnIndex": 5,
                                    "endColumnIndex": 6,
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "NUMBER_GREATER",
                                    "values": [{"userEnteredValue": "50"}],
                                },
                                "format": {"backgroundColor": red_light},
                            },
                        },
                        "index": 0,
                    }
                }
            )

        retry_api(spreadsheet.batch_update, {"requests": format_requests})
