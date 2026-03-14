from pydantic import BaseModel


class User(BaseModel):
    tg_id: int
    student_id: int
    group_number: int
