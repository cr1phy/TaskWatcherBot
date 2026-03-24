import structlog
from aiogram import Bot

from ..models.cloudtext import CloudTextClient, Journal, apply_max_balls
from ..models.cloudtext.models import Student
from ..services.groups import GroupRegistry
from ..services.user import UserService

logger = structlog.get_logger()


def _is_hw_done(student: Student, task_id: int) -> bool:
    work = student.works.get(task_id)
    return work is not None and work.score > 0


async def notify_students(
    bot: Bot,
    users: UserService,
    groups: GroupRegistry,
    cloudtext: CloudTextClient,
) -> None:
    ct_groups = await cloudtext.get_groups()
    group_id_map: dict[int, int] = {g.number: g.id for g in ct_groups}

    student_names: dict[int, str] = {}
    for g in ct_groups:
        for s in g.students:
            student_names[s.id] = s.full_name

    registered = await groups.get_all()
    all_users = await users.get_all()
    journals: dict[int, Journal] = {}
    for group_number, ct_id in {
        n: group_id_map[n] for n in registered if n in group_id_map
    }.items():
        try:
            journal = await cloudtext.get_journal(ct_id)
            max_balls = await cloudtext.get_max_balls()
            apply_max_balls(journal, max_balls)
            journals[group_number] = journal
        except Exception as e:
            await logger.aerror(
                "journal_fetch_failed", group_number=group_number, error=str(e)
            )

    for group_number, chat_id in registered.items():
        maybe_journal: Journal | None = journals.get(group_number)
        if not maybe_journal:
            continue
        await _notify_group(bot, chat_id, maybe_journal)

    for user in all_users:
        maybe_journal: Journal | None = journals.get(user.group_number)
        if not maybe_journal:
            continue
        journal = maybe_journal
        name = student_names.get(user.student_id)
        if not name:
            continue

        matches = [s for s in journal.students if s.name == name]
        if len(matches) != 1:
            await logger.awarning(
                "ambiguous_student",
                name=name,
                matches=len(matches),
                group=user.group_number,
            )
            continue

        await _notify_personal(bot, user.tg_id, matches[0], journal)


async def _notify_group(bot: Bot, chat_id: int, journal: Journal) -> None:
    lines = [f"<b>📊 Статистика по домашним заданиям — {journal.name}</b>\n"]

    total_hw = len(journal.homeworks)
    for student in journal.active_students:
        done = sum(1 for t in journal.homeworks if _is_hw_done(student, t.id))
        if done < total_hw:
            lines.append(f"— {student.name}: сдано {done}/{total_hw}")
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
    not_done = [t for t in journal.homeworks if not _is_hw_done(student, t.id)]
    if not not_done:
        return

    lines = ["<b>Привет! Напоминаю о невыполненных заданиях:</b>\n"]
    for task in not_done:
        lines.append(f"— {task.homework_name}")

    try:
        await bot.send_message(tg_id, "\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await logger.aerror("personal_notify_failed", tg_id=tg_id, error=str(e))
