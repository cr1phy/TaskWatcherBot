-- depends:

CREATE TABLE IF NOT EXISTS users (
    tg_id BIGINT PRIMARY KEY,
    student_id INTEGER NOT NULL,
    group_number INTEGER NOT NULL
);