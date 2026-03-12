from aiogram import Bot, Dispatcher

from ._config import (
    BOT_TOKEN,
    CLOUDTEXT_BASE_URL,
    CLOUDTEXT_EMAIL,
    CLOUDTEXT_PASSWORD,
)
from .models.cloudtext import CloudTextClient


async def main() -> None:
    ct_client = CloudTextClient(CLOUDTEXT_EMAIL, CLOUDTEXT_PASSWORD, CLOUDTEXT_BASE_URL)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router=global_router)
    await dp.start_polling(bot, cloudtext=ct_client)  # type: ignore
