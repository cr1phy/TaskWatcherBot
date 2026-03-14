import re

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.filters import IS_MEMBER, IS_NOT_MEMBER, ChatMemberUpdatedFilter, Command
from aiogram.types import ChatMemberUpdated, Message
from telethon import TelegramClient  # type: ignore

from ..config import OWNER_TGID
from ..middleware import OwnerMiddleware
from ..services.groups import GroupRegistry
from ..services.user import UserService


def init_owner_router() -> Router:
    r = Router()
    r.message.outer_middleware(OwnerMiddleware(OWNER_TGID))
    r.my_chat_member.outer_middleware(OwnerMiddleware(OWNER_TGID))
    return r


router = init_owner_router()


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_joining(
    member: ChatMemberUpdated, bot: Bot, groups: GroupRegistry
) -> None:
    if (title := member.chat.title) and (m := re.search(r"Группа\s*(\d+)", title)):
        await groups.register(int(m.group(1)), member.chat.id)
        return
    await bot.send_message(
        member.chat.id,
        "Название чата должно быть в формате 'Группа N'.",
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

    lines = []
    for group_n, chat_id in all_groups.items():
        participants = await tg_client.get_participants(chat_id)
        total = sum(1 for p in participants if not p.bot)
        linked = sum(1 for p in participants if not p.bot and await users.exists(p.id))
        lines.append(f"Группа {group_n}: {linked}/{total} привязано")

    await msg.answer("\n".join(lines))
