import time
from typing import Any, Callable

from gspread.exceptions import APIError


def copy_block_right(
    sheet_id: int, src_col: int, start_row: int, end_row: int, dest_col: int
) -> dict[str, Any]:
    return {
        "copyPaste": {
            "source": {
                "sheetId": sheet_id,
                "startRowIndex": start_row - 1,
                "endRowIndex": end_row,
                "startColumnIndex": src_col - 1,
                "endColumnIndex": src_col + 1,
            },
            "destination": {
                "sheetId": sheet_id,
                "startRowIndex": start_row - 1,
                "endRowIndex": end_row,
                "startColumnIndex": dest_col - 1,
                "endColumnIndex": dest_col + 1,
            },
            "pasteType": "PASTE_NORMAL",
        }
    }


def delete_rows(sheet_id: int, start_row: int, count: int) -> dict[str, Any]:
    return {
        "deleteDimension": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": start_row - 1,
                "endIndex": start_row - 1 + count,
            }
        }
    }


def retry_api(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 10,
    **kwargs: dict[str, Any],
) -> Any:
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if e.response.status_code in (429, 503):
                wait = min(60 * (attempt + 1), 300)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"API не отвечает после {max_retries} попыток")
