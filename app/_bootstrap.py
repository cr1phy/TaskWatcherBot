from aiogram import Bot, Dispatcher

from _config import (
    BOT_TOKEN,
    CLOUDTEXT_BASE_URL,
    CLOUDTEXT_EMAIL,
    CLOUDTEXT_PASSWORD,
)
from models.cloudtext import CloudtextClient


async def main() -> None:
    ct_client = CloudtextClient(CLOUDTEXT_EMAIL, CLOUDTEXT_PASSWORD, CLOUDTEXT_BASE_URL)
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    await dp.start_polling(bot, cloudtext=ct_client)  # type: ignore
