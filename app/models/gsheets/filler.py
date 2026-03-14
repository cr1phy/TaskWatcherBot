import asyncio
from datetime import date
from functools import partial
from typing import Any, Callable

from gspread import Spreadsheet, Worksheet

from ..cloudtext.models import Group, Journal, Student, primary_to_secondary
from .helpers import retry_api


def col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


class SpreadsheetFiller:
    async def _run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def add_dated_sheet(
        self, spreadsheet: Spreadsheet, group: Group, journal: Journal
    ) -> None:
        title = date.today().strftime("%d.%m.%Y")

        # Удалить существующий лист с такой датой
        for ws in await self._run(spreadsheet.worksheets):
            if ws.title == title:
                await self._run(
                    retry_api,
                    spreadsheet.batch_update,
                    {"requests": [{"deleteSheet": {"sheetId": ws.id}}]},
                )
                break

        worksheet = await self._run(
            retry_api,
            spreadsheet.add_worksheet,
            title=title,
            rows=200,
            cols=200,
        )
        await self._run(self._delete_default_sheet, spreadsheet)
        await self._run(self._fill, spreadsheet, worksheet, group, journal)
        await self._run(self._reorder_sheets, spreadsheet)

    def _delete_default_sheet(self, spreadsheet: Spreadsheet) -> None:
        for ws in spreadsheet.worksheets():
            if ws.title in ("Sheet1", "Лист1", "Лист 1"):
                retry_api(
                    spreadsheet.batch_update,
                    {"requests": [{"deleteSheet": {"sheetId": ws.id}}]},
                )
                break

    def _reorder_sheets(self, spreadsheet: Spreadsheet) -> None:
        sheets = spreadsheet.worksheets()

        def parse_date(title: str) -> date:
            try:
                parts = title.split(".")
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
            except (ValueError, IndexError):
                return date.min

        sorted_sheets = sorted(
            sheets, key=lambda ws: parse_date(ws.title), reverse=True
        )
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "index": i},
                    "fields": "index",
                }
            }
            for i, ws in enumerate(sorted_sheets)
        ]
        if requests:
            retry_api(spreadsheet.batch_update, {"requests": requests})

    def _fill(
        self,
        spreadsheet: Spreadsheet,
        worksheet: Worksheet,
        group: Group,
        journal: Journal,
    ) -> None:
        # All unique students from group
        seen: set[str] = set()
        student_names: list[str] = []
        for s in group.students:
            if s.full_name not in seen:
                seen.add(s.full_name)
                student_names.append(s.full_name)

        num_students = len(student_names)
        homeworks = journal.homeworks
        probes = journal.probes
        num_hw = len(homeworks)
        num_probes = len(probes)

        # Journal data mapped by name
        journal_map: dict[str, Student] = {}
        for s in journal.students:
            if s.name not in journal_map:
                journal_map[s.name] = s

        # ── Row layout ──
        hw_name_row = 1
        hw_maxball_row = 2
        hw_headers_row = 3
        hw_students_start = 4
        hw_students_end = hw_students_start + num_students - 1

        probe_name_row = hw_students_end + 2
        probe_headers_row = probe_name_row + 1
        probe_students_start = probe_headers_row + 1
        probe_students_end = probe_students_start + num_students - 1

        stats_header_row = probe_students_end + 2
        stats_students_start = stats_header_row + 1

        hw_start_col = 2

        updates: list[dict[str, Any]] = []

        # ══════════════════════════════════════
        # HW SECTION
        # ══════════════════════════════════════

        updates.append(
            {
                "range": f"A{hw_maxball_row}",
                "values": [["Максимальный балл за ДЗ 👉"]],
            }
        )

        for i, task in enumerate(homeworks):
            score_col = hw_start_col + i * 2
            pct_col = score_col + 1
            sc = col_letter(score_col)
            pc = col_letter(pct_col)

            updates.append(
                {"range": f"{sc}{hw_name_row}", "values": [[task.homework_name]]}
            )
            updates.append(
                {"range": f"{sc}{hw_maxball_row}", "values": [[task.maximum_score]]}
            )
            updates.append(
                {"range": f"{sc}{hw_headers_row}", "values": [["Балл за ДЗ"]]}
            )
            updates.append(
                {"range": f"{pc}{hw_headers_row}", "values": [["В процентах"]]}
            )

            for j, name in enumerate(student_names):
                row = hw_students_start + j
                student = journal_map.get(name)
                work = student.works.get(task.id) if student else None

                updates.append(
                    {
                        "range": f"{sc}{row}",
                        "values": [[work.score if work else ""]],
                    }
                )

                if work and task.maximum_score:
                    pct = round(work.score / task.maximum_score * 100)
                    updates.append({"range": f"{pc}{row}", "values": [[f"{pct}%"]]})
                else:
                    updates.append({"range": f"{pc}{row}", "values": [[""]]})

        for j, name in enumerate(student_names):
            row = hw_students_start + j
            updates.append({"range": f"A{row}", "values": [[name]]})

        # ══════════════════════════════════════
        # PROBE SECTION
        # ══════════════════════════════════════

        for i, task in enumerate(probes):
            pri_col = hw_start_col + i * 2
            sec_col = pri_col + 1
            pr = col_letter(pri_col)
            se = col_letter(sec_col)

            updates.append(
                {"range": f"{pr}{probe_name_row}", "values": [[task.probe_name]]}
            )
            updates.append(
                {"range": f"{pr}{probe_headers_row}", "values": [["Первичный балл"]]}
            )
            updates.append(
                {"range": f"{se}{probe_headers_row}", "values": [["Вторичный балл"]]}
            )

            for j, name in enumerate(student_names):
                row = probe_students_start + j
                student = journal_map.get(name)
                work = student.works.get(task.id) if student else None

                primary = work.score if work else ""
                secondary = primary_to_secondary(work.score) if work else ""

                updates.append({"range": f"{pr}{row}", "values": [[primary]]})
                updates.append({"range": f"{se}{row}", "values": [[secondary]]})

        for j, name in enumerate(student_names):
            row = probe_students_start + j
            updates.append({"range": f"A{row}", "values": [[name]]})

        # ══════════════════════════════════════
        # STATS SECTION (only HW, not probes)
        # ══════════════════════════════════════

        updates.append(
            {"range": f"A{stats_header_row}", "values": [["Общая статистика"]]}
        )
        updates.append(
            {"range": f"B{stats_header_row}", "values": [["Кол-во невыполненных ДЗ"]]}
        )
        updates.append(
            {"range": f"D{stats_header_row}", "values": [["Всего ДЗ было выдано"]]}
        )
        updates.append(
            {"range": f"F{stats_header_row}", "values": [["Не выполнено в процентах"]]}
        )

        for j, name in enumerate(student_names):
            stats_row = stats_students_start + j
            student = journal_map.get(name)

            # Count only HW, not probes
            done_hw = (
                sum(1 for t in homeworks if student and student.works.get(t.id))
                if student
                else 0
            )
            not_done = num_hw - done_hw
            percent = round(not_done / num_hw * 100) if num_hw else 0

            updates.append({"range": f"A{stats_row}", "values": [[name]]})
            updates.append({"range": f"B{stats_row}", "values": [[not_done]]})
            updates.append({"range": f"D{stats_row}", "values": [[num_hw]]})
            updates.append({"range": f"F{stats_row}", "values": [[f"{percent}%"]]})

        retry_api(worksheet.batch_update, updates)

        self._apply_styles(
            spreadsheet,
            worksheet,
            num_hw,
            num_probes,
            num_students,
            hw_name_row,
            hw_maxball_row,
            hw_headers_row,
            hw_students_start,
            probe_name_row,
            probe_headers_row,
            probe_students_start,
            stats_header_row,
            stats_students_start,
        )

    def _apply_styles(
        self,
        spreadsheet: Spreadsheet,
        worksheet: Worksheet,
        num_hw: int,
        num_probes: int,
        num_students: int,
        hw_name_row: int,
        hw_maxball_row: int,
        hw_headers_row: int,
        hw_students_start: int,
        probe_name_row: int,
        probe_headers_row: int,
        probe_students_start: int,
        stats_header_row: int,
        stats_students_start: int,
    ) -> None:
        sheet_id = worksheet.id
        hw_end_col = 2 + num_hw * 2
        probe_end_col = 2 + num_probes * 2

        green = {"red": 0.576, "green": 0.769, "blue": 0.490}
        blue = {"red": 0.235, "green": 0.471, "blue": 0.847}
        yellow = {"red": 0.98, "green": 0.95, "blue": 0.7}
        white = {"red": 1, "green": 1, "blue": 1}

        def fmt(
            r1: int,
            r2: int,
            c1: int,
            c2: int,
            bg: dict[str, Any] | None = None,
            bold: bool = False,
            center: bool = False,
        ) -> dict[str, Any]:
            cell: dict[str, Any] = {"userEnteredFormat": {}}
            fields = []
            if bg:
                cell["userEnteredFormat"]["backgroundColor"] = bg
                fields.append("userEnteredFormat.backgroundColor")
            if bold:
                cell["userEnteredFormat"]["textFormat"] = {"bold": True}
                fields.append("userEnteredFormat.textFormat.bold")
            if center:
                cell["userEnteredFormat"]["horizontalAlignment"] = "CENTER"
                fields.append("userEnteredFormat.horizontalAlignment")
            return {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": r1 - 1,
                        "endRowIndex": r2,
                        "startColumnIndex": c1 - 1,
                        "endColumnIndex": c2,
                    },
                    "cell": cell,
                    "fields": ",".join(fields),
                }
            }

        def merge(r1: int, r2: int, c1: int, c2: int) -> dict[str, Any]:
            return {
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": r1 - 1,
                        "endRowIndex": r2,
                        "startColumnIndex": c1 - 1,
                        "endColumnIndex": c2,
                    },
                    "mergeType": "MERGE_ALL",
                }
            }

        requests: list[dict[str, Any]] = []

        # ── HW ──
        requests.append(
            fmt(
                hw_name_row,
                hw_name_row,
                1,
                hw_end_col,
                bg=green,
                bold=True,
                center=True,
            )
        )
        requests.append(
            fmt(hw_maxball_row, hw_maxball_row, 2, hw_end_col, bg=white, center=True)
        )
        requests.append(
            fmt(hw_headers_row, hw_headers_row, 2, hw_end_col, bg=white, center=True)
        )
        requests.append(
            fmt(
                hw_students_start,
                hw_students_start + num_students - 1,
                2,
                hw_end_col,
                bg=white,
                center=True,
            )
        )
        for i in range(num_hw):
            col = 2 + i * 2
            requests.append(merge(hw_name_row, hw_name_row, col, col + 1))
            requests.append(merge(hw_maxball_row, hw_maxball_row, col, col + 1))

        # ── Probe ──
        requests.append(
            fmt(
                probe_name_row,
                probe_name_row,
                1,
                probe_end_col,
                bg=blue,
                bold=True,
                center=True,
            )
        )
        requests.append(
            fmt(
                probe_headers_row,
                probe_headers_row,
                2,
                probe_end_col,
                bg=white,
                center=True,
            )
        )
        requests.append(
            fmt(
                probe_students_start,
                probe_students_start + num_students - 1,
                2,
                probe_end_col,
                bg=white,
                center=True,
            )
        )
        for i in range(num_probes):
            col = 2 + i * 2
            requests.append(merge(probe_name_row, probe_name_row, col, col + 1))

        # ── Stats ──
        requests.append(
            fmt(
                stats_header_row,
                stats_header_row,
                1,
                7,
                bg=yellow,
                bold=True,
                center=True,
            )
        )
        requests.append(merge(stats_header_row, stats_header_row, 2, 3))
        requests.append(merge(stats_header_row, stats_header_row, 4, 5))
        requests.append(merge(stats_header_row, stats_header_row, 6, 7))
        for j in range(num_students):
            row = stats_students_start + j
            requests.append(merge(row, row, 2, 3))
            requests.append(merge(row, row, 4, 5))
            requests.append(merge(row, row, 6, 7))
            requests.append(fmt(row, row, 2, 7, center=True))

        # Conditional: red if > 50%
        for j in range(num_students):
            row = stats_students_start + j
            requests.append(
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": sheet_id,
                                    "startRowIndex": row - 1,
                                    "endRowIndex": row,
                                    "startColumnIndex": 5,
                                    "endColumnIndex": 7,
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "%"}],
                                },
                                "format": {},
                            },
                        },
                        "index": 0,
                    }
                }
            )

        # Column A width
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 280},
                    "fields": "pixelSize",
                }
            }
        )

        # Auto-resize data columns
        max_col = max(hw_end_col, probe_end_col, 7)
        requests.append(
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": max_col,
                    }
                }
            }
        )

        # Row heights
        for start, count in [
            (hw_students_start, num_students),
            (probe_students_start, num_students),
            (stats_students_start, num_students),
        ]:
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": start - 1,
                            "endIndex": start - 1 + count,
                        },
                        "properties": {"pixelSize": 24},
                        "fields": "pixelSize",
                    }
                }
            )

        retry_api(spreadsheet.batch_update, {"requests": requests})
