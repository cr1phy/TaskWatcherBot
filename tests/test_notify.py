from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.notify import _notify_group, _notify_personal
from app.models.cloudtext.models import Journal, Student, Task, Work


def _make_journal(
    group_name: str, students: list[Student], tasks: list[Task]
) -> Journal:
    return Journal(id=1, name=group_name, students=students, tasks=tasks)


def _make_student(sid: int, name: str, works: dict[int, Work] | None = None) -> Student:
    return Student(id=sid, name=name, works=works or {}, count=1, avg=0)


def _make_task(tid: int, name: str) -> Task:
    return Task(id=tid, name=name, maximum_score=10)


class TestNotifyGroup:
    @pytest.mark.asyncio
    async def test_sends_message_to_chat(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock()

        task = _make_task(1, "1 задание (Тема)")
        work = Work(task_id=1, score=8, maximum_score=10, status=4)
        student = _make_student(1, "Иванов Иван", {1: work})
        journal = _make_journal("Группа 1", [student], [task])

        await _notify_group(bot, 123, journal)
        bot.send_message.assert_awaited_once()
        call_args = bot.send_message.call_args
        assert call_args[0][0] == 123
        assert "всё сдано ✅" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_shows_not_done_count(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock()

        tasks = [_make_task(1, "1 задание (А)"), _make_task(2, "2 задание (Б)")]
        student = _make_student(1, "Иванов Иван", {})
        journal = _make_journal("Группа 1", [student], tasks)

        await _notify_group(bot, 123, journal)
        text = bot.send_message.call_args[0][1]
        assert "сдано 0/2" in text

    @pytest.mark.asyncio
    async def test_silently_handles_send_error(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock(side_effect=Exception("forbidden"))

        journal = _make_journal("Группа 1", [], [])
        await _notify_group(bot, 123, journal)


class TestNotifyPersonal:
    @pytest.mark.asyncio
    async def test_sends_not_done_tasks(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock()

        task = _make_task(1, "1 задание (Тема)")
        student = _make_student(1, "Иванов Иван", {})
        journal = _make_journal("Группа 1", [student], [task])

        await _notify_personal(bot, 42, student, journal)
        bot.send_message.assert_awaited_once()
        text = bot.send_message.call_args[0][1]
        assert "Задание №1" in text

    @pytest.mark.asyncio
    async def test_no_message_when_all_done(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock()

        task = _make_task(1, "1 задание (Тема)")
        work = Work(task_id=1, score=8, maximum_score=10, status=4)
        student = _make_student(1, "Иванов Иван", {1: work})
        journal = _make_journal("Группа 1", [student], [task])

        await _notify_personal(bot, 42, student, journal)
        bot.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_silently_handles_send_error(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock(side_effect=Exception("blocked"))

        task = _make_task(1, "1 задание (Тема)")
        student = _make_student(1, "Иванов Иван", {})
        journal = _make_journal("Группа 1", [student], [task])

        await _notify_personal(bot, 42, student, journal)
