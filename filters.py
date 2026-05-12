from aiogram.filters import BaseFilter
from aiogram import types
from config import ADMIN_IDS

class IsAdmin(BaseFilter):
    """Фильтр для проверки, является ли пользователь администратором."""
    async def __call__(self, message: types.Message | types.CallbackQuery) -> bool:
        return message.from_user.id in ADMIN_IDS