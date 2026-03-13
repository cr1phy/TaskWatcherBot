import asyncpg
import qrcode

from aiogram import Bot, Dispatcher
from redis import asyncio as aioredis
from telethon import TelegramClient  # type: ignore
from yoyo import get_backend, read_migrations  # type: ignore
from handlers import router

from .models.cloudtext import CloudTextClient

from .config import (
    BOT_TOKEN,
    CLOUDTEXT_BASE_URL,
    CLOUDTEXT_EMAIL,
    CLOUDTEXT_PASSWORD,
    DB_URL,
    REDIS_URL,
    TG_API_HASH,
    TG_API_ID,
    TG_SESSION,
)


def apply_migrations(db_url: str) -> None:
    backend = get_backend(db_url)
    migrations = read_migrations("migrations/")
    with backend.lock():
        backend.apply_one(migrations)


async def main() -> None:
    apply_migrations(DB_URL)

    pool = await asyncpg.create_pool(DB_URL)
    redis = aioredis.from_url(REDIS_URL)
    ct_client = CloudTextClient(CLOUDTEXT_EMAIL, CLOUDTEXT_PASSWORD, CLOUDTEXT_BASE_URL)
    tg_client = TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    async def on_startup() -> None:
        await ct_client.start()
        await tg_client.connect()

        if not await tg_client.is_user_authorized():
            qr_login = await tg_client.qr_login()

            qr = qrcode.QRCode()
            qr.add_data(qr_login.url)
            qr.make()
            qr.print_ascii()

            print(
                "Сканируй QR в Telegram → Настройки → Устройства → Подключить устройство"
            )
            await qr_login.wait()
            print("Авторизация прошла успешно!")

    dp.startup.register(on_startup)

    async def on_shutdown() -> None:
        await ct_client.close()
        await tg_client.disconnect()
        await redis.aclose()
        await pool.close()

    dp.shutdown.register(on_shutdown)

    await dp.start_polling(  # type: ignore
        bot,
        pool=pool,
        redis=redis,
        cloudtext=ct_client,
        tg_client=tg_client,
    )
