-- depends: 0001_create_users

CREATE TABLE spreadsheets (
    group_number INTEGER PRIMARY KEY,
    spreadsheet_id TEXT NOT NULL,
    url TEXT NOT NULL
);