import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from yoyo import get_backend, read_migrations  # type: ignore

from .config import BOT_TOKEN, DB_URL, OWNER_TGID
from .container import Container
from .handlers import router
from .jobs.notify import notify_students
from .jobs.sheets import update_sheets
from .middleware import LoggingMiddleware


def apply_migrations() -> None:
    backend = get_backend(DB_URL)
    migrations = read_migrations("migrations/")
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        if to_apply:
            backend.apply_migrations(to_apply)


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать привязку"),
            BotCommand(command="stats", description="Моя статистика по ДЗ"),
            BotCommand(command="unlink", description="Отвязаться"),
            BotCommand(command="help", description="Справка"),
        ],
        scope=BotCommandScopeDefault(),
    )

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Старт/помощь"),
            BotCommand(command="links", description="Ссылки для учеников"),
            BotCommand(command="create_sheets", description="Создать таблицы"),
            BotCommand(command="parse_users", description="Статистика привязок"),
        ],
        scope=BotCommandScopeChat(chat_id=OWNER_TGID),
    )


async def main() -> None:
    apply_migrations()

    c = await Container.create()
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.update.outer_middleware(LoggingMiddleware())
    dp.include_router(router)

    @dp.startup()
    async def on_startup() -> None:
        await c.cloudtext.start()

        await c.tg_client.connect()
        if not await c.tg_client.is_user_authorized():
            await c.tg_client.disconnect()
            raise RuntimeError(
                "Telethon не авторизован. Запусти: uv run scripts/auth_telethon.py"
            )

        c.gsheets.start()

        await set_bot_commands(bot)

        async def warmup() -> None:
            try:
                await c.cloudtext.get_max_balls()
                await bot.send_message(OWNER_TGID, "✅ Бот готов.")
            except Exception as e:
                await bot.send_message(OWNER_TGID, f"⚠️ Ошибка прогрева кэша: {e}")

        asyncio.create_task(warmup())

        scheduler.add_job(
            notify_students,
            CronTrigger(day_of_week="mon", hour=10),
            kwargs={
                "bot": bot,
                "users": c.users,
                "groups": c.groups,
                "cloudtext": c.cloudtext,
            },
        )
        scheduler.add_job(
            update_sheets,
            CronTrigger(day_of_week="sun", hour=3),
            kwargs={
                "groups": c.groups,
                "cloudtext": c.cloudtext,
                "gsheets": c.gsheets,
            },
        )
        scheduler.start()

    @dp.shutdown()
    async def on_shutdown() -> None:
        scheduler.shutdown()
        await c.close()

    await dp.start_polling(bot, **c.as_kwargs())
