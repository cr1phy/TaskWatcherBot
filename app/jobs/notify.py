import structlog
from aiogram import Bot

from ..models.cloudtext import CloudTextClient, Journal
from ..models.cloudtext.models import Student
from ..services.groups import GroupRegistry
from ..services.user import UserService

logger = structlog.get_logger()


async def notify_students(
    bot: Bot,
    users: UserService,
    groups: GroupRegistry,
    cloudtext: CloudTextClient,
) -> None:
    ct_groups = await cloudtext.get_groups()
    group_id_map: dict[int, int] = {g.number: g.id for g in ct_groups}

    registered = await groups.get_all()
    all_users = await users.get_all()

    journals: dict[int, Journal] = {}
    for group_number, ct_id in {
        n: group_id_map[n] for n in registered if n in group_id_map
    }.items():
        try:
            journals[group_number] = await cloudtext.get_journal(ct_id)
        except Exception as e:
            await logger.aerror(
                "journal_fetch_failed", group_number=group_number, error=str(e)
            )

    for group_number, chat_id in registered.items():
        journal = journals.get(group_number)
        if not journal:
            continue
        await _notify_group(bot, chat_id, journal)

    for user in all_users:
        journal = journals.get(user.group_number)
        if not journal:
            continue
        student = next((s for s in journal.students if s.id == user.student_id), None)
        if not student:
            continue
        await _notify_personal(bot, user.tg_id, student, journal)


async def _notify_group(bot: Bot, chat_id: int, journal: Journal) -> None:
    lines = [f"<b>📊 Статистика по домашним заданиям — {journal.name}</b>\n"]

    total_hw = len(journal.homeworks)
    for student in journal.students:
        done = sum(1 for t in journal.homeworks if student.works.get(t.id))
        not_done = total_hw - done
        if not_done:
            lines.append(f"— {student.name}: не сдано {not_done}/{total_hw}")
        else:
            lines.append(f"— {student.name}: всё сдано ✅")

    try:
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await logger.aerror("group_notify_failed", chat_id=chat_id, error=str(e))


async def _notify_personal(
    bot: Bot,
    tg_id: int,
    student: Student,
    journal: Journal,
) -> None:
    not_done = [t for t in journal.homeworks if not student.works.get(t.id)]
    if not not_done:
        return

    lines = ["<b>Привет! Напоминаю о невыполненных заданиях:</b>\n"]
    for task in not_done:
        lines.append(f"— {task.homework_name}")

    try:
        await bot.send_message(tg_id, "\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await logger.aerror("personal_notify_failed", tg_id=tg_id, error=str(e))
