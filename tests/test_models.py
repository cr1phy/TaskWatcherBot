from app.models.cloudtext.models import (
    EGE_SCALE,
    Group,
    GroupStudent,
    Journal,
    Student,
    Task,
    Work,
    primary_to_secondary,
)


class TestPrimaryToSecondary:
    def test_zero_returns_zero(self) -> None:
        assert primary_to_secondary(0) == 0

    def test_negative_returns_zero(self) -> None:
        assert primary_to_secondary(-1) == 0

    def test_max_returns_100(self) -> None:
        assert primary_to_secondary(29) == 100

    def test_above_max_returns_100(self) -> None:
        assert primary_to_secondary(30) == 100

    def test_known_values(self) -> None:
        for primary, expected in EGE_SCALE.items():
            assert primary_to_secondary(primary) == expected


class TestGroupNumber:
    def test_extracts_number_from_name(self) -> None:
        g = Group(id=1, name="Группа 5")
        assert g.number == 5

    def test_extracts_number_with_spaces(self) -> None:
        g = Group(id=1, name="Группа  10")
        assert g.number == 10

    def test_fallback_to_id_when_no_match(self) -> None:
        g = Group(id=42, name="Индивидуальные")
        assert g.number == 42


class TestGroupStudent:
    def test_full_name_with_middle(self) -> None:
        s = GroupStudent(
            id=1, first_name="Иван", last_name="Иванов", middle_name="Иванович"
        )
        assert s.full_name == "Иванов Иван Иванович"

    def test_full_name_without_middle(self) -> None:
        s = GroupStudent(id=1, first_name="Иван", last_name="Иванов")
        assert s.full_name == "Иванов Иван"


class TestTask:
    def test_is_probe_by_score(self) -> None:
        t = Task(id=1, name="Что-то", maximum_score=29)
        assert t.is_probe is True

    def test_is_probe_by_name(self) -> None:
        t = Task(id=1, name="Пробник №1 (март)", maximum_score=10)
        assert t.is_probe is True

    def test_not_probe(self) -> None:
        t = Task(id=1, name="1 задание (Тема)", maximum_score=10)
        assert t.is_probe is False

    def test_homework_name_with_number(self) -> None:
        t = Task(id=1, name="1 задание (Алгоритмизация)", maximum_score=5)
        assert t.homework_name == "Задание №1. Алгоритмизация"

    def test_homework_name_without_number(self) -> None:
        t = Task(id=1, name="Просто тема", maximum_score=5)
        assert t.homework_name == "Просто тема"

    def test_probe_name(self) -> None:
        t = Task(id=1, name="Пробник №3 (апрель)", maximum_score=29)
        assert t.probe_name == "Пробник №3"

    def test_has_month_true(self) -> None:
        t = Task(id=1, name="Пробник №1 (март)", maximum_score=29)
        assert t.has_month is True

    def test_has_month_false(self) -> None:
        t = Task(id=1, name="Пробник №1", maximum_score=29)
        assert t.has_month is False


class TestWork:
    def test_is_done(self) -> None:
        w = Work(task_id=1, score=5, maximum_score=10, status=4)
        assert w.is_done is True

    def test_not_done(self) -> None:
        w = Work(task_id=1, score=5, maximum_score=10, status=2)
        assert w.is_done is False

    def test_percent(self) -> None:
        w = Work(task_id=1, score=7, maximum_score=10, status=4)
        assert w.percent == 70

    def test_percent_zero_max(self) -> None:
        w = Work(task_id=1, score=0, maximum_score=0, status=0)
        assert w.percent == 0

    def test_percent_rounds(self) -> None:
        w = Work(task_id=1, score=1, maximum_score=3, status=4)
        assert w.percent == 33


class TestJournal:
    def _make_journal(self, tasks: list[Task], students: list[Student]) -> Journal:
        return Journal(id=1, name="Группа 1", tasks=tasks, students=students)

    def test_homeworks_excludes_probes(self) -> None:
        tasks = [
            Task(id=1, name="1 задание (Тема)", maximum_score=10),
            Task(id=2, name="Пробник №1", maximum_score=29),
            Task(id=3, name="_Шаблон", maximum_score=0),
        ]
        j = self._make_journal(tasks, [])
        assert len(j.homeworks) == 1
        assert j.homeworks[0].id == 1

    def test_probes_only_probes(self) -> None:
        tasks = [
            Task(id=1, name="1 задание (Тема)", maximum_score=10),
            Task(id=2, name="Пробник №1", maximum_score=29),
        ]
        j = self._make_journal(tasks, [])
        assert len(j.probes) == 1
        assert j.probes[0].id == 2

    def test_active_students_filter_inactive(self) -> None:
        students = [
            Student(id=1, name="Активный", count=5),
            Student(id=2, name="Неактивный", count=0),
        ]
        j = self._make_journal([], students)
        assert len(j.active_students) == 1
        assert j.active_students[0].id == 1

    def test_active_students_deduplication(self) -> None:
        students = [
            Student(id=1, name="Ученик", count=5),
            Student(id=1, name="Ученик", count=3),
        ]
        j = self._make_journal([], students)
        assert len(j.active_students) == 1
