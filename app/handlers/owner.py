import re

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.types import ChatMemberUpdated, Message
from aiogram.filters import IS_MEMBER, IS_NOT_MEMBER, ChatMemberUpdatedFilter, Command
import asyncpg
from redis import asyncio as aioredis
from telethon import TelegramClient  # type: ignore
from telethon.tl.types import TotalList

from ..config import OWNER_TGID
from ..dao.user import UserDAO
from ..middleware import OwnerMiddleware


def init_owner_router() -> Router:
    middleware = OwnerMiddleware(OWNER_TGID)
    r = Router()
    for _, observer in r.observers.items():
        observer.middleware(middleware)
    return r


router = init_owner_router()


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_joining(
    member: ChatMemberUpdated, bot: Bot, redis: aioredis.Redis
) -> None:
    if (title := member.chat.title) and (match := re.search(r"Группа\s*(\d+)", title)):
        group_n = match.group(1)
        await redis.set(f"group_{group_n}", member.chat.id)
    else:
        await bot.send_message(
            chat_id=member.from_user.id,
            text="Название чата должно быть в формате 'Группа N'.",
        )


@router.message(Command("parse_users"))
async def on_parse_users(
    msg: Message,
    bot: Bot,
    tg_client: TelegramClient,
    redis: aioredis.Redis,
    pool: asyncpg.Pool,
) -> None:
    await msg.answer("Начинаю парсинг...")
    await bot.send_chat_action(msg.chat.id, ChatAction.TYPING)

    keys: list[str] = await redis.keys("group_*")
    if not keys:
        await msg.answer("Нет привязанных групп.")
        return

    dao = UserDAO(pool)
    linked = 0
    for key in keys:
        group_n = key.decode().split("_")[1]
        chat_id = int(await redis.get(key))
        participants: TotalList = await tg_client.get_participants(chat_id)

        for p in participants:
            if p.bot or not p.username:
                continue
            tg_id = p.id
            if not await dao.exists(tg_id):
                continue
            linked += 1

    await msg.answer(f"Готово. Привязано: {linked}")
