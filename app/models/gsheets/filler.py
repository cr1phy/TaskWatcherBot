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


def pct_color(pct: int) -> dict[str, float]:
    if pct <= 0:
        return {"red": 0.85, "green": 0.85, "blue": 0.85}
    elif pct <= 30:
        return {"red": 0.87, "green": 0.36, "blue": 0.34}
    elif pct <= 50:
        return {"red": 0.92, "green": 0.6, "blue": 0.6}
    elif pct <= 70:
        return {"red": 0.95, "green": 0.76, "blue": 0.46}
    elif pct <= 90:
        return {"red": 0.72, "green": 0.88, "blue": 0.53}
    else:
        return {"red": 0.42, "green": 0.76, "blue": 0.44}


def stats_color(pct: int) -> dict[str, float]:
    if pct <= 10:
        return {"red": 0.42, "green": 0.76, "blue": 0.44}
    elif pct <= 30:
        return {"red": 0.72, "green": 0.88, "blue": 0.53}
    elif pct <= 50:
        return {"red": 0.95, "green": 0.76, "blue": 0.46}
    elif pct <= 70:
        return {"red": 0.92, "green": 0.6, "blue": 0.6}
    else:
        return {"red": 0.87, "green": 0.36, "blue": 0.34}


def is_done(work: Any) -> bool:
    return work is not None and work.score > 0


class SpreadsheetFiller:
    async def _run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def add_dated_sheet(
        self, spreadsheet: Spreadsheet, group: Group, journal: Journal
    ) -> None:
        title = date.today().strftime("%d.%m.%Y")

        worksheet = await self._run(
            retry_api,
            spreadsheet.add_worksheet,
            title="_tmp",
            rows=200,
            cols=200,
        )

        for ws in await self._run(spreadsheet.worksheets):
            if ws.id == worksheet.id:
                continue
            if ws.title == title or ws.title in ("Sheet1", "Лист1", "Лист 1"):
                await self._run(
                    retry_api,
                    spreadsheet.batch_update,
                    {"requests": [{"deleteSheet": {"sheetId": ws.id}}]},
                )

        await self._run(
            retry_api,
            spreadsheet.batch_update,
            {
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": worksheet.id, "title": title},
                            "fields": "title",
                        }
                    }
                ]
            },
        )
        worksheet._properties["title"] = title

        await self._run(self._fill, spreadsheet, worksheet, group, journal)
        await self._run(self._reorder_sheets, spreadsheet)

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
        sheet_id = worksheet.id

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

        journal_map: dict[str, Student] = {}
        for s in journal.students:
            if s.name not in journal_map:
                journal_map[s.name] = s

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
        hw_end_col = 2 + num_hw * 2
        probe_end_col = 2 + num_probes * 2

        updates: list[dict[str, Any]] = []

        updates.append(
            {"range": f"A{hw_maxball_row}", "values": [["Максимальный балл за ДЗ 👉"]]}
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

                if is_done(work):
                    pct = (
                        round(work.score / task.maximum_score * 100)
                        if task.maximum_score
                        else 0
                    )
                    updates.append({"range": f"{sc}{row}", "values": [[work.score]]})
                    updates.append({"range": f"{pc}{row}", "values": [[f"{pct}%"]]})
                else:
                    updates.append({"range": f"{sc}{row}", "values": [[0]]})
                    updates.append({"range": f"{pc}{row}", "values": [["0%"]]})

        for j, name in enumerate(student_names):
            row = hw_students_start + j
            updates.append({"range": f"A{row}", "values": [[name]]})

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

                if is_done(work):
                    updates.append({"range": f"{pr}{row}", "values": [[work.score]]})
                    updates.append(
                        {
                            "range": f"{se}{row}",
                            "values": [[primary_to_secondary(work.score)]],
                        }
                    )
                else:
                    updates.append({"range": f"{pr}{row}", "values": [[0]]})
                    updates.append({"range": f"{se}{row}", "values": [[0]]})

        for j, name in enumerate(student_names):
            row = probe_students_start + j
            updates.append({"range": f"A{row}", "values": [[name]]})

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

            done_hw = 0
            if student:
                for t in homeworks:
                    work = student.works.get(t.id)
                    if is_done(work):
                        done_hw += 1

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
            sheet_id,
            num_hw,
            num_probes,
            num_students,
            hw_name_row,
            hw_maxball_row,
            hw_headers_row,
            hw_students_start,
            hw_students_end,
            hw_end_col,
            probe_name_row,
            probe_headers_row,
            probe_students_start,
            probe_students_end,
            probe_end_col,
            stats_header_row,
            stats_students_start,
        )

        color_requests: list[dict[str, Any]] = []

        def set_range_color(
            row: int, c1: int, c2: int, color: dict[str, float]
        ) -> dict[str, Any]:
            return {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": c1 - 1,
                        "endColumnIndex": c2,
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": color}},
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }

        for j, name in enumerate(student_names):
            row = hw_students_start + j
            student = journal_map.get(name)
            for i, task in enumerate(homeworks):
                score_col = hw_start_col + i * 2
                pct_col = score_col + 1
                work = student.works.get(task.id) if student else None
                if is_done(work) and task.maximum_score:
                    pct = round(work.score / task.maximum_score * 100)
                else:
                    pct = 0
                color = pct_color(pct)
                color_requests.append(
                    set_range_color(row, score_col, pct_col + 1, color)
                )

        for j, name in enumerate(student_names):
            row = probe_students_start + j
            student = journal_map.get(name)
            for i, task in enumerate(probes):
                pri_col = hw_start_col + i * 2
                sec_col = pri_col + 1
                work = student.works.get(task.id) if student else None
                if is_done(work):
                    pct = round(work.score / 29 * 100)
                else:
                    pct = 0
                color = pct_color(pct)
                color_requests.append(set_range_color(row, pri_col, sec_col + 1, color))

        for j, name in enumerate(student_names):
            stats_row = stats_students_start + j
            student = journal_map.get(name)
            done_hw = 0
            if student:
                for t in homeworks:
                    work = student.works.get(t.id)
                    if is_done(work):
                        done_hw += 1
            not_done = num_hw - done_hw
            percent = round(not_done / num_hw * 100) if num_hw else 0
            color = stats_color(percent)
            color_requests.append(set_range_color(stats_row, 2, 7, color))

        if color_requests:
            retry_api(spreadsheet.batch_update, {"requests": color_requests})

    def _apply_styles(
        self,
        spreadsheet: Spreadsheet,
        worksheet: Worksheet,
        sheet_id: int,
        num_hw: int,
        num_probes: int,
        num_students: int,
        hw_name_row: int,
        hw_maxball_row: int,
        hw_headers_row: int,
        hw_students_start: int,
        hw_students_end: int,
        hw_end_col: int,
        probe_name_row: int,
        probe_headers_row: int,
        probe_students_start: int,
        probe_students_end: int,
        probe_end_col: int,
        stats_header_row: int,
        stats_students_start: int,
    ) -> None:
        green = {"red": 0.576, "green": 0.769, "blue": 0.490}
        blue = {"red": 0.235, "green": 0.471, "blue": 0.847}
        yellow = {"red": 0.98, "green": 0.95, "blue": 0.7}
        white = {"red": 1, "green": 1, "blue": 1}
        black = {"red": 0, "green": 0, "blue": 0}

        def fmt(
            r1: int,
            r2: int,
            c1: int,
            c2: int,
            bg: dict[str, Any] | None = None,
            bold: bool = False,
            italic: bool = False,
            center: bool = False,
            vcenter: bool = False,
            font_size: int | None = None,
        ) -> dict[str, Any]:
            cell: dict[str, Any] = {"userEnteredFormat": {}}
            fields: list[str] = []
            if bg:
                cell["userEnteredFormat"]["backgroundColor"] = bg
                fields.append("userEnteredFormat.backgroundColor")
            text_fmt: dict[str, Any] = {}
            if bold:
                text_fmt["bold"] = True
            if italic:
                text_fmt["italic"] = True
            if font_size:
                text_fmt["fontSize"] = font_size
            if text_fmt:
                cell["userEnteredFormat"]["textFormat"] = text_fmt
                fields.append("userEnteredFormat.textFormat")
            if center:
                cell["userEnteredFormat"]["horizontalAlignment"] = "CENTER"
                fields.append("userEnteredFormat.horizontalAlignment")
            if vcenter:
                cell["userEnteredFormat"]["verticalAlignment"] = "MIDDLE"
                fields.append("userEnteredFormat.verticalAlignment")
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

        def outer_border(r1: int, r2: int, c1: int, c2: int) -> dict[str, Any]:
            border = {"style": "SOLID", "colorStyle": {"rgbColor": black}}
            return {
                "updateBorders": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": r1 - 1,
                        "endRowIndex": r2,
                        "startColumnIndex": c1 - 1,
                        "endColumnIndex": c2,
                    },
                    "top": border,
                    "bottom": border,
                    "left": border,
                    "right": border,
                }
            }

        requests: list[dict[str, Any]] = []

        max_data_col = max(hw_end_col, probe_end_col, 7)

        requests.append(
            fmt(
                1,
                stats_students_start + num_students,
                1,
                max_data_col,
                center=True,
                vcenter=True,
            )
        )

        requests.append(
            fmt(
                hw_name_row,
                hw_name_row,
                2,
                hw_end_col,
                bg=green,
                bold=True,
                center=True,
            )
        )
        requests.append(
            fmt(
                hw_maxball_row,
                hw_maxball_row,
                2,
                hw_end_col,
                bg=white,
                bold=True,
                center=True,
            )
        )
        requests.append(
            fmt(
                hw_headers_row,
                hw_headers_row,
                2,
                hw_end_col,
                bg=white,
                bold=True,
                italic=True,
                center=True,
            )
        )

        requests.append(fmt(hw_students_start, hw_students_end, 1, 1, font_size=12))
        requests.append(
            fmt(probe_students_start, probe_students_end, 1, 1, font_size=12)
        )
        requests.append(
            fmt(
                stats_students_start,
                stats_students_start + num_students - 1,
                1,
                1,
                font_size=12,
            )
        )

        for i in range(num_hw):
            col = 2 + i * 2
            requests.append(merge(hw_name_row, hw_name_row, col, col + 1))
            requests.append(merge(hw_maxball_row, hw_maxball_row, col, col + 1))

        for i in range(num_hw):
            col = 2 + i * 2
            requests.append(outer_border(hw_name_row, hw_students_end, col, col + 1))

        requests.append(
            fmt(
                probe_name_row,
                probe_name_row,
                2,
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
                bold=True,
                italic=True,
                center=True,
            )
        )

        for i in range(num_probes):
            col = 2 + i * 2
            requests.append(merge(probe_name_row, probe_name_row, col, col + 1))

        for i in range(num_probes):
            col = 2 + i * 2
            requests.append(
                outer_border(probe_name_row, probe_students_end, col, col + 1)
            )

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

        requests.append(
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": max_data_col,
                    }
                }
            }
        )

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
                        "properties": {"pixelSize": 32},
                        "fields": "pixelSize",
                    }
                }
            )

        for row in [
            hw_name_row,
            hw_maxball_row,
            hw_headers_row,
            probe_name_row,
            probe_headers_row,
            stats_header_row,
        ]:
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row - 1,
                            "endIndex": row,
                        },
                        "properties": {"pixelSize": 28},
                        "fields": "pixelSize",
                    }
                }
            )

        retry_api(spreadsheet.batch_update, {"requests": requests})
