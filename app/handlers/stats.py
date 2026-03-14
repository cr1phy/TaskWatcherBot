import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..models.cloudtext import CloudTextClient, apply_max_balls
from ..services.user import UserService

router = Router()


@router.message(Command("stats"))
async def on_stats(
    msg: Message,
    users: UserService,
    cloudtext: CloudTextClient,
) -> None:
    if not msg.from_user:
        return
    user = await users.get(msg.from_user.id)

    if not user:
        await msg.answer(
            "Ты не привязан. Используй ссылку-приглашение от преподавателя."
        )
        return

    groups = await cloudtext.get_groups()
    ct_group = next((g for g in groups if g.number == user.group_number), None)
    if not ct_group:
        await msg.answer("Группа не найдена в CloudText.")
        return

    ct_student = next((s for s in ct_group.students if s.id == user.student_id), None)
    if not ct_student:
        await msg.answer("Не нашёл тебя в группе.")
        return

    try:
        journal = await asyncio.wait_for(cloudtext.get_journal(ct_group.id), timeout=10)
    except asyncio.TimeoutError:
        await msg.answer("⏳ Бот сейчас занят, попробуй через пару минут.")
        return
    max_balls = await cloudtext.get_max_balls()
    apply_max_balls(journal, max_balls)

    matches = [s for s in journal.students if s.name == ct_student.full_name]
    if not matches:
        await msg.answer("Не нашёл тебя в журнале.")
        return
    if len(matches) > 1:
        await msg.answer(
            "В журнале несколько учеников с таким именем. Обратись к преподавателю."
        )
        return
    student = matches[0]

    lines = [f"<b>Статистика {student.name}</b>\n"]

    if journal.homeworks:
        lines.append("<b>Домашние задания:</b>")
        for task in journal.homeworks:
            work = student.works.get(task.id)
            if work:
                lines.append(
                    f"{task.homework_name}: {work.score}/{task.maximum_score} ({work.percent}%)"
                )
            else:
                lines.append(f"{task.homework_name}: не сдано")

    if journal.probes:
        lines.append("\n<b>Пробники:</b>")
        for task in journal.probes:
            work = student.works.get(task.id)
            if work:
                lines.append(f"{task.probe_name}: {work.score}/29")
            else:
                lines.append(f"{task.probe_name}: не сдан")

    await msg.answer("\n".join(lines), parse_mode="HTML")
