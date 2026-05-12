import asyncpg
from config import DB_DSN

class Database:
    """Обертка для удобного доступа к пулу БД из любого файла."""
    pool = None

    @classmethod
    async def connect(cls):
        cls.pool = await asyncpg.create_pool(dsn=DB_DSN)

    @classmethod
    async def disconnect(cls):
        if cls.pool:
            await cls.pool.close()

db = Database()