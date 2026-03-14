from os import getenv

from dotenv import load_dotenv


def get_required_envvar(key: str) -> str:
    if value := getenv(key):
        return value
    raise Exception(f"{key} не найден в .env!")


load_dotenv()

BOT_TOKEN = get_required_envvar("BOT_TOKEN")
OWNER_TGID = int(get_required_envvar("OWNER_TGID"))

CLOUDTEXT_BASE_URL = get_required_envvar("CLOUDTEXT_BASE_URL")
CLOUDTEXT_EMAIL = get_required_envvar("CLOUDTEXT_EMAIL")
CLOUDTEXT_PASSWORD = get_required_envvar("CLOUDTEXT_PASSWORD")

DB_URL = get_required_envvar("DB_URL")
REDIS_URL = get_required_envvar("REDIS_URL")

TG_API_ID = int(get_required_envvar("TG_API_ID"))
TG_API_HASH = get_required_envvar("TG_API_HASH")
TG_SESSION = get_required_envvar("TG_SESSION")

GSPRE
