import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_DSN = os.getenv("DB_DSN")

# Парсим ID админов из строки в список чисел
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

WELCOME_IMAGE_PATH = "static/hello.jpg"
DEFAULT_COVER_PATH = "static/default_cover.jpg"