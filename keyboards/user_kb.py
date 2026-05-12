from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    kb = [
        [types.KeyboardButton(text="💽 Каталог винила")],
        [types.KeyboardButton(text="🛒 Моя корзина"), types.KeyboardButton(text="📦 Мои заказы")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_catalog_categories_keyboard():
    kb = [
        [InlineKeyboardButton(text="🎸 По исполнителям", callback_data="nav_artists")],
        [InlineKeyboardButton(text="🎧 По жанрам", callback_data="nav_genres")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_buy_keyboard(sku: str):
    kb = [[InlineKeyboardButton(text="➕ В корзину", callback_data=f"buy_{sku}")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)