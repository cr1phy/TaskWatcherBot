import qrcode  # type: ignore
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from yoyo import get_backend, read_migrations  # type: ignore

from .config import BOT_TOKEN, DB_URL
from .container import Container
from .handlers import router
from .jobs.notify import notify_students
from .jobs.sheets import update_sheets
from .middleware import LoggingMiddleware


def apply_migrations() -> None:
    backend = get_backend(DB_URL)
    migrations = read_migrations("migrations/")
    with backend.lock():
        backend.apply_one(migrations)


async def main() -> None:
    apply_migrations()

    c = await Container.create()
    scheduler = AsyncIOScheduler()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.update.outer_middleware(LoggingMiddleware())
    dp.include_router(router)

    @dp.startup()
    async def on_startup() -> None:
        await c.cloudtext.start()

        await c.tg_client.connect()
        if not await c.tg_client.is_user_authorized():
            qr_login = await c.tg_client.qr_login()
            qr = qrcode.QRCode()
            qr.add_data(qr_login.url)
            qr.make()
            qr.print_ascii()
            print(
                "Сканируй QR в Telegram → Настройки → Устройства → Подключить устройство"
            )
            await qr_login.wait()
            print("Авторизация прошла успешно!")

        c.gsheets.start()

        scheduler.add_job(
            notify_students,
            CronTrigger(day_of_week="mon", hour=10),
            kwargs={**c.as_kwargs(), "bot": bot},
        )
        scheduler.add_job(
            update_sheets,
            CronTrigger(day_of_week="sun", hour=3),
            kwargs=c.as_kwargs(),
        )
        scheduler.start()

    @dp.shutdown()
    async def on_shutdown() -> None:
        scheduler.shutdown()
        await c.close()

    await dp.start_polling(bot, **c.as_kwargs())
