import os
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WELCOME_IMAGE_PATH
from database import db
from keyboards.user_kb import get_main_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    text = (
        f"Привет, {message.from_user.first_name}! 🎵\n\n"
        "Добро пожаловать в магазин винила. Воспользуйтесь меню ниже."
    )
    if os.path.exists(WELCOME_IMAGE_PATH):
        await message.answer_photo(photo=FSInputFile(WELCOME_IMAGE_PATH), caption=text,
                                   reply_markup=get_main_keyboard())
    else:
        await message.answer(text, reply_markup=get_main_keyboard())


@router.message(F.text == "📦 Мои заказы")
async def show_my_orders(message: types.Message):
    user_id = message.from_user.id

    # Делаем два запроса: первый для истории, второй - вызывает нашу функцию подсчета трат
    query_orders = """
                   SELECT o.id, o.status, o.total_amount, o.created_at
                   FROM orders o
                            JOIN customers c ON o.customer_id = c.id
                   WHERE c.telegram_id = $1
                   ORDER BY o.created_at DESC; \
                   """
    # Вызов нашей SQL-функции
    query_total_spent = "SELECT get_customer_total_spent($1);"

    async with db.pool.acquire() as conn:
        orders = await conn.fetch(query_orders, user_id)
        # Получаем LTV клиента (функция возвращает одно число)
        total_spent = await conn.fetchval(query_total_spent, user_id)

    if not orders:
        await message.answer("📭 У вас пока нет заказов.\nПерейдите в каталог, чтобы выбрать свою первую пластинку!")
        return

    builder = InlineKeyboardBuilder()
    for order in orders:
        date_str = order['created_at'].strftime("%d.%m.%Y")
        btn_text = f"#{order['id']} ({date_str}) — {order['status']}"
        builder.button(text=btn_text, callback_data=f"myorder_{order['id']}")

    builder.adjust(1)

    # Формируем красивое сообщение с использованием данных из SQL-функции
    text = (
        f"📦 **Ваша история заказов**\n"
        f"💎 **Выкуплено на сумму:** {total_spent} руб.\n\n"
        f"Нажмите на заказ для просмотра деталей."
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("myorder_"))
async def show_my_order_details(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    query_order = """
                  SELECT o.id, o.status, o.total_amount, o.delivery_method, o.shipping_address, o.created_at
                  FROM orders o \
                           JOIN customers c ON o.customer_id = c.id
                  WHERE o.id = $1 \
                    AND c.telegram_id = $2;
                  """
    query_items = """SELECT artist_name AS artist, album_title AS title, 
                            sku, quantity, price_at_purchase FROM view_order_items_detail WHERE order_id = $1;"""
    async with db.pool.acquire() as conn:
        order = await conn.fetchrow(query_order, order_id, user_id)
        if not order:
            await callback.answer("❌ Заказ не найден или у вас нет к нему доступа.", show_alert=True)
            return
        items = await conn.fetch(query_items, order_id)

    date_str = order['created_at'].strftime("%d.%m.%Y %H:%M")
    text = (
        f"🧾 **Детали заказа #{order['id']}**\n📅 **Дата:** {date_str}\n📌 **Статус:** `{order['status']}`\n\n🚚 **Доставка:** {order['delivery_method']}\n")
    if order['shipping_address']:
        text += f"📍 **Адрес:** {order['shipping_address']}\n"
    text += "\n🛒 **Состав заказа:**\n"

    for idx, item in enumerate(items, start=1):
        text += f"{idx}. {item['artist']} — {item['title']} ({item['format']}, {item['color']})\n   └ {item['quantity']} шт. x {item['price_at_purchase']} руб.\n"
    text += f"\n💰 **Итого:** {order['total_amount']} руб."

    kb = [[types.InlineKeyboardButton(text="🔙 К списку заказов", callback_data="back_to_my_orders")]]
    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=kb)

    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=reply_markup)


@router.callback_query(F.data == "back_to_my_orders")
async def back_to_my_orders_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    query = """
            SELECT o.id, o.status, o.total_amount, o.created_at
            FROM orders o \
                     JOIN customers c ON o.customer_id = c.id
            WHERE c.telegram_id = $1 \
            ORDER BY o.created_at DESC;
            """
    async with db.pool.acquire() as conn:
        orders = await conn.fetch(query, user_id)

    if not orders:
        await callback.message.edit_text("📭 У вас пока нет заказов.")
        return

    builder = InlineKeyboardBuilder()
    for order in orders:
        date_str = order['created_at'].strftime("%d.%m.%Y")
        btn_text = f"#{order['id']} ({date_str}) — {order['status']}"
        builder.button(text=btn_text, callback_data=f"myorder_{order['id']}")
    builder.adjust(1)
    await callback.message.edit_text("📦 **Ваша история заказов:**\nНажмите на заказ для просмотра деталей.",
                                     parse_mode="Markdown", reply_markup=builder.as_markup())