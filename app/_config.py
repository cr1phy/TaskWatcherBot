from os import getenv
from dotenv import load_dotenv


def get_required_envvar(key: str) -> str:
    if value := getenv(key):
        return value
    raise Exception(f"{key} isn't found in .env!")


load_dotenv()

BOT_TOKEN = get_required_envvar("BOT_TOKEN")
OWNER_TGID = get_required_envvar("OWNER_TGID")

CLOUDTEXT_BASE_URL = get_required_envvar("CLOUDTEXT_BASE_URL")
CLOUDTEXT_EMAIL = get_required_envvar("CLOUDTEXT_EMAIL")
CLOUDTEXT_PASSWORD = get_required_envvar("CLOUDTEXT_PASSWORD")
