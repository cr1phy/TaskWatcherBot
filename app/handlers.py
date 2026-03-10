from aiogram import Bot, Router
from aiogram.types import Message, ChatMember
from aiogram.filters import IS_MEMBER, IS_NOT_MEMBER, CommandStart, ChatMemberUpdatedFilter


router = Router()


@router.message(CommandStart())
async def on_start(msg: Message) -> None:
    await msg.answer("Hello!")


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_inviting_to_group(member: ChatMember, bot: Bot) -> None:
    