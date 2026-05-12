import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database import db

# Импортируем наши "кусочки" логики
from handlers.user import router as user_router
from handlers.catalog import router as catalog_router
from handlers.cart import router as cart_router
from handlers.admin import router as admin_router


async def main():
    # Настраиваем логирование
    logging.basicConfig(level=logging.INFO)

    # Инициализируем бота и диспетчер
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем все маршруты к диспетчеру
    dp.include_router(user_router)
    dp.include_router(catalog_router)
    dp.include_router(cart_router)
    dp.include_router(admin_router)

    # Подключаемся к базе данных
    await db.connect()

    try:
        logging.info("Бот запущен и структура успешно собрана!")
        # Запускаем поллинг
        await dp.start_polling(bot)
    finally:
        # Корректно закрываем соединения при отключении
        await db.disconnect()
        logging.info("Пул соединений с БД закрыт.")


if __name__ == "__main__":
    asyncio.run(main())