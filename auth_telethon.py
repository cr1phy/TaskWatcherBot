import asyncio
import sys

import qrcode  # type: ignore
from telethon import TelegramClient  # type: ignore
from telethon.errors import SessionPasswordNeededError  # type: ignore

from app.config import TG_API_HASH, TG_API_ID, TG_SESSION


async def auth() -> None:
    client = TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        print("Уже авторизован!")
        await client.disconnect()
        return

    qr_login = await client.qr_login()

    qr = qrcode.QRCode()
    qr.add_data(qr_login.url)
    qr.make()
    qr.print_ascii()

    print("Сканируй QR в Telegram → Настройки → Устройства → Подключить устройство")

    try:
        await qr_login.wait()
    except SessionPasswordNeededError:
        password = input("Введи пароль 2FA: ")
        await client.sign_in(password=password)

    print("Авторизация прошла успешно!")
    await client.disconnect()


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(auth())
