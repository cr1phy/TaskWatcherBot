-- depends: 0001_create_users

CREATE TABLE IF NOT EXISTS spreadsheets (
    group_number INTEGER PRIMARY KEY,
    spreadsheet_id TEXT NOT NULL,
    url TEXT NOT NULL
);