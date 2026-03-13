from aiogram import F, Bot, Router
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncpg
from redis import asyncio as aioredis

from ..dao.user import UserDAO
from ..models.cloudtext import CloudTextClient
from ..states import LinkingState


router = Router()


def normalize(name: str) -> str:
    return " ".join(name.lower().split())


def match(tg_name: str, cloudtext_name: str) -> bool:
    tg = normalize(tg_name)
    ct = normalize(cloudtext_name)
    return tg in ct or ct in tg


@router.message(CommandStart(deep_link=True))
async def on_start(msg: Message, state: FSMContext) -> None:
    if msg.text and len(splitted_msg := msg.text.split()) == 2:
        group_n = splitted_msg[1]
        await msg.answer(
            f"Привет, ученик из группы {group_n}! Для того, чтобы в группе работала статистика необходимо мне получить от тебя ФИО или ФИ. <b>Важно, чтобы оно совпадало с ФИО в CloudText!</b>"
        )
        await state.set_state(LinkingState.GettingName)
        await state.update_data({"group_n": group_n})
        return
    await msg.answer("Я ожидаю номер группы для привязки.")


@router.message(StateFilter(LinkingState.GettingName))
async def on_getting_name(
    msg: Message,
    bot: Bot,
    state: FSMContext,
    cloudtext: CloudTextClient,
    pool: asyncpg.Pool,
) -> None:
    if not msg.text or not msg.from_user:
        await msg.delete()
        return

    waiting_msg = await msg.answer("Окей! Сейчас посмотрю...")
    await bot.send_chat_action(msg.chat.id, ChatAction.TYPING)

    groups = await cloudtext.get_groups()
    group_n = await state.get_value("group_n")
    if not group_n:
        await waiting_msg.edit_text("Группа не найдена.")
        await state.clear()
        return
    group = next((g for g in groups if g.number == int(group_n)), None)
    if not group:
        await waiting_msg.edit_text("Группа не найдена.")
        await state.clear()
        return

    students = [
        s for s in group.students if normalize(s.full_name) == normalize(msg.text)
    ]

    if not students:
        await waiting_msg.edit_text("Не нашёл тебя. Проверь ФИО и попробуй ещё раз.")
        return

    if len(students) == 1:
        student = students[0]
        group_n = (await state.get_data())["group_n"]
        dao = UserDAO(pool)
        if await dao.exists(msg.from_user.id):
            await waiting_msg.edit_text("Ты уже привязан!")
        else:
            await dao.create(msg.from_user.id, student.id, int(group_n))
            await waiting_msg.edit_text("Готово! Ты привязан.")
        await state.clear()
        return

    builder = InlineKeyboardBuilder()
    for s in students:
        builder.add(
            InlineKeyboardButton(
                text=f"{s.full_name} (#{s.id})", callback_data=f"link:{s.id}"
            )
        )

    await waiting_msg.edit_text(
        "Нашёл несколько совпадений, выбери себя.",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(LinkingState.ChoosingStudent)


@router.callback_query(
    StateFilter(LinkingState.ChoosingStudent), F.data.startswith("link:")
)
async def on_student_chosen(
    callback: CallbackQuery, state: FSMContext, pool: asyncpg.Pool
) -> None:
    if not callback.message:
        return
    student_id = int(callback.data.split(":")[1])
    group_n = (await state.get_data())["group_n"]
    dao = UserDAO(pool)
    await dao.create(callback.from_user.id, student_id, int(group_n))
    await callback.message.edit_text("Готово! Ты привязан.")
    await state.clear()
