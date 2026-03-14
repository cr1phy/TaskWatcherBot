from typing import Any

from app.models.cloudtext.models import Journal
from app.models.cloudtext.parsing import (
    apply_max_balls,
    parse_groups,
    parse_journal,
    parse_task_max_ball,
    parse_works,
)

GROUPS_RESPONSE = [
    {
        "id": 1,
        "name": "Группа 1",
        "students": {
            "data": [
                {
                    "id": 10,
                    "first_name": "Иван",
                    "last_name": "Иванов",
                    "middle_name": None,
                },
                {
                    "id": 11,
                    "first_name": "Мария",
                    "last_name": "Петрова",
                    "middle_name": "Сергеевна",
                },
            ]
        },
    },
    {
        "id": 2,
        "name": "Индивидуальные",
        "students": {"data": []},
    },
]

JOURNAL_RESPONSE = {
    "journal": {
        "group": {"id": 1, "name": "Группа 1"},
        "tasks": [
            {"id": 100, "name": "1 задание (Алгоритмы)", "max_ball": 10},
            {"id": 101, "name": "Пробник №1", "max_ball": 29},
        ],
        "data": [
            {
                "id": 10,
                "name": "Иванов Иван",
                "count": 2,
                "avg": 75,
                "works": [
                    {"task_id": 100, "ball": 8, "max_ball": 10, "status": 4},
                    {"task_id": 100, "ball": 6, "max_ball": 10, "status": 4},
                ],
            },
            {
                "id": 11,
                "name": "Петрова Мария",
                "count": 0,
                "avg": 0,
                "works": [],
            },
        ],
    }
}


class TestParseGroups:
    def test_filters_non_groups(self) -> None:
        groups = parse_groups(GROUPS_RESPONSE)
        assert len(groups) == 1
        assert groups[0].name == "Группа 1"

    def test_parses_students(self) -> None:
        groups = parse_groups(GROUPS_RESPONSE)
        assert len(groups[0].students) == 2

    def test_student_middle_name(self) -> None:
        groups = parse_groups(GROUPS_RESPONSE)
        petrov = next(s for s in groups[0].students if s.id == 11)
        assert petrov.middle_name == "Сергеевна"

    def test_student_no_middle_name(self) -> None:
        groups = parse_groups(GROUPS_RESPONSE)
        ivanov = next(s for s in groups[0].students if s.id == 10)
        assert ivanov.middle_name is None


class TestParseWorks:
    def test_best_work_selected(self) -> None:
        works_data = [
            {"task_id": 100, "ball": 6, "max_ball": 10, "status": 4},
            {"task_id": 100, "ball": 8, "max_ball": 10, "status": 4},
        ]
        works = parse_works(works_data)
        assert works[100].score == 8

    def test_none_ball_treated_as_zero(self) -> None:
        works_data = [
            {"task_id": 100, "ball": None, "max_ball": 10, "status": 1},
        ]
        works = parse_works(works_data)
        assert works[100].score == 0

    def test_dict_format(self) -> None:
        works_data = {"100": [{"task_id": 100, "ball": 5, "max_ball": 10, "status": 4}]}
        works = parse_works(works_data)
        assert 100 in works
        assert works[100].score == 5

    def test_empty_dict_value_skipped(self) -> None:
        works_data: list[dict[str, Any]] | dict[str, list] = {"100": []}
        works = parse_works(works_data)
        assert 100 not in works


class TestParseJournal:
    def test_parses_group(self) -> None:
        j = parse_journal(JOURNAL_RESPONSE)
        assert j.id == 1
        assert j.name == "Группа 1"

    def test_parses_tasks(self) -> None:
        j = parse_journal(JOURNAL_RESPONSE)
        assert len(j.tasks) == 2

    def test_active_students_only(self) -> None:
        j = parse_journal(JOURNAL_RESPONSE)
        assert len(j.students) == 1
        assert j.students[0].id == 10

    def test_best_work_in_journal(self) -> None:
        j = parse_journal(JOURNAL_RESPONSE)
        assert j.students[0].works[100].score == 8


class TestApplyMaxBalls:
    def _make_journal(self) -> Journal:
        return parse_journal(JOURNAL_RESPONSE)

    def test_api_map_takes_priority(self) -> None:
        j = self._make_journal()
        apply_max_balls(j, {100: 15})
        task = next(t for t in j.tasks if t.id == 100)
        assert task.maximum_score == 15

    def test_student_max_used_when_no_api(self) -> None:
        j = self._make_journal()
        apply_max_balls(j, {})
        task = next(t for t in j.tasks if t.id == 100)
        assert task.maximum_score == 10

    def test_zero_when_no_data(self) -> None:
        j = self._make_journal()
        apply_max_balls(j, {})
        task = next(t for t in j.tasks if t.id == 101)
        assert task.maximum_score == 0


class TestParseTaskMaxBall:
    def test_empty_returns_zero(self) -> None:
        assert parse_task_max_ball({}) == 0

    def test_fields_max_ball_sum(self) -> None:
        detail = {
            "task": {
                "fields": [
                    {"max_ball": 3, "type": 1},
                    {"max_ball": 5, "type": 1},
                ]
            }
        }
        assert parse_task_max_ball(detail) == 8

    def test_criteria_fallback(self) -> None:
        detail = {
            "task": {
                "fields": [
                    {
                        "max_ball": None,
                        "type": 1,
                        "criteria": [
                            {"max_ball": 2},
                            {"max_ball": 3},
                        ],
                    }
                ]
            }
        }
        assert parse_task_max_ball(detail) == 5

    def test_question_count_fallback(self) -> None:
        detail = {
            "task": {
                "fields": [
                    {"type": 1},
                    {"type": 2},
                    {"type": 0},
                ]
            }
        }
        assert parse_task_max_ball(detail) == 2
