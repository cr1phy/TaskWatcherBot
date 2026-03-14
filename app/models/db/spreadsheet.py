from pydantic import BaseModel


class SpreadsheetRecord(BaseModel):
    group_number: int
    spreadsheet_id: str
    url: str
