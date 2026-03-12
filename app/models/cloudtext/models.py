from __future__ import annotations

import re

from pydantic import (
    AliasChoices,
    ConfigDict,
)


from pydantic import BaseModel, Field, computed_field, field_validator


MONTHS = [
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
]

EGE_SCALE = {
    1: 7,
    2: 14,
    3: 20,
    4: 27,
    5: 34,
    6: 40,
    7: 43,
    8: 46,
    9: 48,
    10: 51,
    11: 54,
    12: 56,
    13: 59,
    14: 62,
    15: 64,
    16: 67,
    17: 70,
    18: 72,
    19: 75,
    20: 78,
    21: 80,
    22: 83,
    23: 85,
    24: 88,
    25: 90,
    26: 93,
    27: 95,
    28: 98,
    29: 100,
}


def primary_to_secondary(primary: int) -> int:
    if primary <= 0:
        return 0
    if primary >= 29:
        return 100
    return EGE_SCALE.get(primary, 0)


class AppModel(BaseModel):
    model_config = ConfigDict(
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )


class IdModel(AppModel):
    id: int


class GroupBase(IdModel):
    name: str

    @computed_field
    @property
    def number(self) -> int:
        match = re.search(r"Группа\s*(\d+)", self.name)
        return int(match.group(1)) if match else self.id


class GroupStudent(IdModel):
    first_name: str
    last_name: str
    middle_name: str | None = None

    @computed_field
    @property
    def full_name(self) -> str:
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(parts)

    @property
    def name(self) -> str:
        # удобное внутреннее имя, в JSON не сериализуется
        return self.full_name


class Task(IdModel):
    name: str
    maximum_score: int

    @computed_field
    @property
    def is_probe(self) -> bool:
        return self.maximum_score == 29 or "Пробник" in self.name

    @property
    def homework_name(self) -> str:
        num_match = re.search(r"(\d+)\s*задание", self.name)
        num = int(num_match.group(1)) if num_match else 0

        topic_match = re.search(r"\((.+)\)", self.name)
        topic = topic_match.group(1) if topic_match else self.name

        return f"Задание №{num}. {topic}" if num else topic

    @property
    def probe_name(self) -> str:
        match = re.search(r"(Пробник\s*№?\s*\d+)", self.name)
        return match.group(1) if match else self.name

    @property
    def has_month(self) -> bool:
        lower_name = self.name.lower()
        return any(month in lower_name for month in MONTHS)


class Work(AppModel):
    task_id: int
    score: int
    maximum_score: int
    status: int

    @property
    def is_done(self) -> bool:
        return self.status == 4

    @computed_field
    @property
    def percent(self) -> int:
        return round(self.score / self.maximum_score * 100) if self.maximum_score else 0


class Student(IdModel):
    name: str
    works: dict[int, Work] = Field(default_factory=lambda: {})
    count: int = 0
    avg: int = 0


class Group(GroupBase):
    students: list[GroupStudent] = Field(default_factory=lambda: [])


class Journal(GroupBase):
    name: str = Field(
        validation_alias=AliasChoices("group_name", "name"),
        serialization_alias="group_name",
    )
    students: list[Student] = Field(default_factory=lambda: [])
    tasks: list[Task] = Field(default_factory=lambda: [])

    @property
    def group_name(self) -> str:
        return self.name

    @property
    def homeworks(self) -> list[Task]:
        return [t for t in self.tasks if not t.is_probe and t.name != "_Шаблон"]

    @property
    def probes(self) -> list[Task]:
        return sorted(
            (t for t in self.tasks if t.is_probe),
            key=lambda t: (t.has_month, t.name),
        )

    @field_validator("students", mode="after")
    @classmethod
    def active_students(cls, students: list[Student]) -> list[Student]:
        seen: set[int] = set()
        result: list[Student] = []

        for student in students:
            if student.id not in seen and (student.count > 0 or student.works):
                seen.add(student.id)
                result.append(student)

        return result
