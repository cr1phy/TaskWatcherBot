from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    Message,
    TelegramObject,
    User,
)

logger = structlog.get_logger()


class PrivateOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.chat.type != "private":
            return
        if (
            isinstance(event, CallbackQuery)
            and event.message
            and event.message.chat.type != "private"
        ):
            return
        return await handler(event, data)


class OwnerMiddleware(BaseMiddleware):
    def __init__(self, owner_id: int) -> None:
        self.owner_id = owner_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user and user.id == self.owner_id:
            return await handler(event, data)
        return


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        uid = user.id if user else None
        uname = user.username or user.full_name if user else None

        match event:
            case Message(text=text, chat=chat):
                await logger.ainfo(
                    "message",
                    user_id=uid,
                    username=uname,
                    chat_id=chat.id,
                    text=text,
                )
            case CallbackQuery(data=cb_data):
                await logger.ainfo(
                    "callback",
                    user_id=uid,
                    username=uname,
                    data=cb_data,
                )
            case ChatMemberUpdated(chat=chat, new_chat_member=new_member):
                await logger.ainfo(
                    "chat_member_updated",
                    chat_id=chat.id,
                    chat_title=chat.title,
                    new_status=new_member.status,
                )
            case _:
                await logger.adebug(
                    "update",
                    type=type(event).__name__,
                    user_id=uid,
                )

        return await handler(event, data)
