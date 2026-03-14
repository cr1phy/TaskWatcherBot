import re

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.filters import IS_MEMBER, IS_NOT_MEMBER, ChatMemberUpdatedFilter, Command
from aiogram.types import (
    ChatMemberUpdated,
    InlineKeyboardButton,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon import TelegramClient  # type: ignore

from ..config import OWNER_TGID
from ..middleware import OwnerMiddleware
from ..models.cloudtext import CloudTextClient, apply_max_balls
from ..models.gsheets import GSheetsClient
from ..services.groups import GroupRegistry
from ..services.user import UserService


def init_owner_router() -> Router:
    r = Router()
    r.message.outer_middleware(OwnerMiddleware(OWNER_TGID))
    r.my_chat_member.outer_middleware(OwnerMiddleware(OWNER_TGID))
    return r


router = init_owner_router()


@router.message(Command("links"))
async def on_links(msg: Message, cloudtext: CloudTextClient, bot: Bot) -> None:
    me = await bot.get_me()
    groups = await cloudtext.get_groups()
    lines = ["<b>Ссылки для учеников:</b>\n"]
    for g in groups:
        lines.append(f"Группа {g.number}: https://t.me/{me.username}?start={g.number}")
    await msg.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("create_sheets"))
async def on_create_sheets(
    msg: Message,
    cloudtext: CloudTextClient,
    gsheets: GSheetsClient,
) -> None:
    await msg.answer("Создаю таблицы...")
    ct_groups = await cloudtext.get_groups()

    for ct_group in ct_groups:
        try:
            journal = await cloudtext.get_journal(ct_group.id)
            max_balls = await cloudtext.get_max_balls()
            apply_max_balls(journal, max_balls)
            await gsheets.get_or_create_sheet(ct_group.number, ct_group, journal)
            await msg.answer(f"Группа {ct_group.number}: готово")
        except Exception as e:
            await msg.answer(f"Группа {ct_group.number}: ошибка — {e}")

    await msg.answer("✅ Все таблицы созданы.")


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_joining(
    member: ChatMemberUpdated,
    bot: Bot,
    groups: GroupRegistry,
    cloudtext: CloudTextClient,
) -> None:
    title = member.chat.title or ""
    m = re.search(r"Группа\s*(\d+)", title)

    if not m:
        # Самокик + DM владельцу
        await bot.send_message(
            OWNER_TGID,
            f"⚠️ Бот добавлен в чат «{title}» — название не соответствует формату 'Группа N'. Вышел.",
        )
        await bot.leave_chat(member.chat.id)
        return

    group_n = int(m.group(1))
    await groups.register(group_n, member.chat.id)

    me = await bot.get_me()
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text="📎 Привязаться",
            url=f"https://t.me/{me.username}?start={group_n}",
        )
    )

    await bot.send_message(
        member.chat.id,
        f"✅ Группа {group_n} привязана.\n\n"
        f"Ученики, нажмите кнопку ниже, чтобы привязать свой аккаунт:",
        reply_markup=builder.as_markup(),
    )

    await bot.send_message(
        OWNER_TGID,
        f"✅ Бот добавлен в чат «{title}» (Группа {group_n})",
    )


@router.my_chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_bot_leaving(
    member: ChatMemberUpdated, bot: Bot, groups: GroupRegistry
) -> None:
    title = member.chat.title or ""
    m = re.search(r"Группа\s*(\d+)", title)

    if m:
        group_n = int(m.group(1))
        await groups.unregister(group_n)

    await bot.send_message(
        OWNER_TGID,
        f"🚪 Бот удалён из чата «{title}»"
        + (f" (Группа {m.group(1)} отвязана)" if m else ""),
    )


@router.message(Command("parse_users"))
async def on_parse_users(
    msg: Message,
    bot: Bot,
    tg_client: TelegramClient,
    groups: GroupRegistry,
    users: UserService,
) -> None:
    await msg.answer("Начинаю парсинг...")
    await bot.send_chat_action(msg.chat.id, ChatAction.TYPING)

    all_groups = await groups.get_all()
    if not all_groups:
        await msg.answer("Нет привязанных групп.")
        return

    await bot.get_me()
    lines = []
    for group_n, chat_id in all_groups.items():
        participants = await tg_client.get_participants(chat_id)
        total = 0
        linked = 0
        for p in participants:
            if p.bot:
                continue
            if p.id == OWNER_TGID:
                continue
            total += 1
            if await users.exists(p.id):
                linked += 1
        lines.append(f"Группа {group_n}: {linked}/{total} привязано")

    await msg.answer("\n".join(lines))
