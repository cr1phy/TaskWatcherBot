from aiogram import Bot, Router
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import (
    IS_MEMBER,
    IS_NOT_MEMBER,
    Command,
    CommandStart,
    ChatMemberUpdatedFilter,
)

from app._config import OWNER_TGID
from app.middleware import OwnerMiddleware

user_router = Router()
owner_router = Router()

owner_router.update.outer_middleware(OwnerMiddleware(OWNER_TGID))


@user_router.message(CommandStart())
async def on_start(msg: Message) -> None:
    await msg.answer("Hello!")


@owner_router.message(CommandStart())
async def on_owner_start(msg: Message) -> None:
    await msg.answer("ALO!!!")


@owner_router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_inviting_to_group(event: ChatMemberUpdated, bot: Bot) -> None:
    pass
