import http
import re
from typing import Any, cast
from urllib.parse import unquote

from aiohttp import ClientSession
from pydantic import BaseModel, Field, computed_field, field_validator
from yarl import URL


class CloudtextClient:
    def __init__(self, email: str, password: str, base_url: str) -> None:
        self._email = email
        self._password = password
        self._base_url = base_url
        self._session: ClientSession | None = None

    async def start(self) -> None:
        session = ClientSession(base_url=self._base_url)

        await session.get("/login")
        xsrf = session.cookie_jar.filter_cookies(URL(self._base_url)).get("xsrf-token")
        headers = {
            "X-XSRF-TOKEN": unquote(xsrf.value),
            "Accept": "application/json",
        }

        async with session.post(
            "/login",
            headers=headers,
            json={"email": self._email, "password": self._password, "stage": 1},
        ) as response:
            if response.status != http.HTTPStatus.ACCEPTED:
                await session.close()
                raise Exception("Something went wrong with log")

        self._session = session

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()

    async def get_students(self) -> None:
        if not self._session:
            return
        await self._session.get("/api/students")


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


class GroupStudent(BaseModel):
    id: int
    first_name: str
    last_name: str
    middle_name: str | None

    @computed_field
    @property
    def full_name(self) -> str:
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(parts)


class Group(BaseModel):
    id: int
    name: str
    students: list[GroupStudent] = []

    @computed_field
    @property
    def number(self) -> int:
        match = re.search(r"Группа\s*(\d+)", self.name)
        return int(match.group(1)) if match else self.id


class Task(BaseModel):
    id: int
    name: str
    maximum_score: int = Field()

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
        return any(m in self.name.lower() for m in MONTHS)


class Work(BaseModel):
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


class Student(BaseModel):
    id: int
    name: str
    works: dict[int, Work] = {}
    count: int = 0
    avg: int = 0


class GroupStudents(BaseModel):
    id: int
    group_name: str
    students: list[Student] = []
    tasks: list[Task] = []

    @property
    def homeworks(self) -> list[Task]:
        return [t for t in self.tasks if not t.is_probe and t.name != "_Шаблон"]

    @property
    def probes(self) -> list[Task]:
        return sorted(
            [t for t in self.tasks if t.is_probe],
            key=lambda t: (t.has_month, t.name),
        )

    @field_validator("students", mode="wrap")
    @classmethod
    def active_students(
        cls,
        value: Any,
    ) -> list[Student]:
        if students := cast(list[Student], value):
            seen: set[str] = set()
            result: list[Student] = []
            for s in students:
                if s.name not in seen and (s.count > 0 or s.works):
                    seen.add(s.name)
                    result.append(s)
            return result
        raise ValueError("Value isn't a list of students")
