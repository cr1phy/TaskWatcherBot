from aiogram import F, Bot, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import OWNER_TGID
from ..models.cloudtext import CloudTextClient
from ..services.user import UserService
from ..states import LinkingState

router = Router()


def normalize(name: str) -> str:
    return " ".join(name.lower().split())


def match(tg_name: str, cloudtext_name: str) -> bool:
    tg = normalize(tg_name)
    ct = normalize(cloudtext_name)
    return tg in ct or ct in tg


@router.message(CommandStart())
async def on_start(msg: Message, command: CommandObject, state: FSMContext) -> None:
    if not msg.from_user:
        return

    if msg.from_user.id == OWNER_TGID:
        await msg.answer(
            "<b>Панель владельца</b>\n\n"
            "/links — ссылки для учеников\n"
            "/create_sheets — создать таблицы\n"
            "/parse_users — статистика привязок",
            parse_mode="HTML",
        )
        return

    if not command.args:
        await msg.answer(
            "Привет! Чтобы привязаться, попроси преподавателя дать ссылку-приглашение."
        )
        return

    group_n = command.args
    await msg.answer(
        f"Привет, ученик из группы {group_n}! Для того, чтобы в группе работала "
        f"статистика, мне нужно твоё ФИО или ФИ. "
        f"<b>Важно, чтобы оно совпадало с ФИО в CloudText!</b>",
        parse_mode="HTML",
    )
    await state.set_state(LinkingState.GettingName)
    await state.update_data({"group_n": group_n})


@router.message(
    StateFilter(LinkingState.GettingName), Command("stats", "help", "unlink")
)
async def on_command_in_state(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Привязка отменена.")


@router.message(StateFilter(LinkingState.GettingName))
async def on_getting_name(
    msg: Message,
    bot: Bot,
    state: FSMContext,
    cloudtext: CloudTextClient,
    users: UserService,
) -> None:
    if not msg.text or not msg.from_user:
        return

    waiting_msg = await msg.answer("Окей! Сейчас посмотрю...")
    await bot.send_chat_action(msg.chat.id, ChatAction.TYPING)

    group_n = await state.get_value("group_n")
    if not group_n:
        await waiting_msg.edit_text("Группа не найдена.")
        await state.clear()
        return

    groups = await cloudtext.get_groups()
    group = next((g for g in groups if g.number == int(group_n)), None)
    if not group:
        await waiting_msg.edit_text("Группа не найдена.")
        await state.clear()
        return

    students = [s for s in group.students if match(msg.text, s.full_name)]

    if not students:
        await waiting_msg.edit_text("Не нашёл тебя. Проверь ФИО и попробуй ещё раз.")
        return

    if len(students) == 1:
        student = students[0]
        if await users.exists(msg.from_user.id):
            await waiting_msg.edit_text("Ты уже привязан!")
        else:
            await users.link(msg.from_user.id, student.id, int(group_n))
            await waiting_msg.edit_text("Готово! Ты привязан.")
        await state.clear()
        return

    journal = await cloudtext.get_journal(group.id)

    builder = InlineKeyboardBuilder()
    for s in students:
        student_in_journal = next(
            (js for js in journal.students if js.name == s.full_name), None
        )
        if student_in_journal:
            done = sum(
                1 for t in journal.homeworks if student_in_journal.works.get(t.id)
            )
            total = len(journal.homeworks)
            avg = student_in_journal.avg
            label = f"{s.full_name} — {done}/{total} ДЗ, ср. {avg}%"
        else:
            label = s.full_name

        builder.add(InlineKeyboardButton(text=label, callback_data=f"link:{s.id}"))

    await waiting_msg.edit_text(
        "Нашёл несколько совпадений, выбери себя.",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(LinkingState.ChoosingStudent)


@router.callback_query(
    StateFilter(LinkingState.ChoosingStudent), F.data.startswith("link:")
)
async def on_student_chosen(
    callback: CallbackQuery,
    state: FSMContext,
    users: UserService,
) -> None:
    if not callback.data or not callback.message:
        return
    student_id = int(callback.data.split(":")[1])
    group_n = (await state.get_data())["group_n"]
    await users.link(callback.from_user.id, student_id, int(group_n))
    if callback.message:
        await callback.message.edit_text("Готово! Ты привязан.")  # type: ignore
    await state.clear()


@router.message(Command("unlink"))
async def on_unlink(msg: Message, users: UserService) -> None:
    if not msg.from_user:
        return
    if not await users.exists(msg.from_user.id):
        await msg.answer("Ты и так не привязан.")
        return
    await users.unlink(msg.from_user.id)
    await msg.answer("Отвязано. Можешь привязаться заново.")


@router.message(Command("help"))
async def on_help(msg: Message) -> None:
    if (user := msg.from_user) and user.id == OWNER_TGID:
        await msg.answer(
            "<b>Доступные команды:</b>\n"
            "/start — начало привязки (через ссылку)\n"
            "/stats — твоя статистика по ДЗ\n"
            "/unlink — отвязаться\n"
            "/help — эта справка"
        )
