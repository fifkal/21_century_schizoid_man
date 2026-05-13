import os
import logging
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
    # Используем username вместо first_name (если username не установлен, обращаемся как "друг")
    username = message.from_user.username or "друг"

    text = (
        f"Привет, @{username}! 🎵\n\n"
        "Добро пожаловать в магазин винила. Воспользуйтесь меню ниже."
    )

    if os.path.exists(WELCOME_IMAGE_PATH):
        await message.answer_photo(
            photo=FSInputFile(WELCOME_IMAGE_PATH),
            caption=text,
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(text, reply_markup=get_main_keyboard())


@router.message(F.text == "📦 Мои заказы")
async def show_my_orders(message: types.Message):
    user_id = message.from_user.id

    query_orders = """
                   SELECT o.id, o.status, o.total_amount, o.created_at
                   FROM orders o
                            JOIN customers c ON o.customer_id = c.id
                   WHERE c.telegram_id = $1
                   ORDER BY o.created_at DESC; \
                   """
    query_total_spent = "SELECT get_customer_total_spent($1);"

    try:
        async with db.pool.acquire() as conn:
            orders = await conn.fetch(query_orders, user_id)
            total_spent = await conn.fetchval(query_total_spent, user_id)

        # Защита от NULL, если у пользователя еще нет выполненных заказов
        total_spent = total_spent or 0

        if not orders:
            await message.answer("📭 У вас пока нет заказов.\nПерейдите в каталог, чтобы выбрать свою первую пластинку!")
            return

        builder = InlineKeyboardBuilder()
        for order in orders:
            date_str = order['created_at'].strftime("%d.%m.%Y")
            btn_text = f"#{order['id']} ({date_str}) — {order['status']}"
            builder.button(text=btn_text, callback_data=f"myorder_{order['id']}")

        builder.adjust(1)

        # Перешли на HTML
        text = (
            f"📦 <b>Ваша история заказов</b>\n"
            f"💎 <b>Выкуплено на сумму:</b> {total_spent} руб.\n\n"
            f"Нажмите на заказ для просмотра деталей."
        )

        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())

    except Exception as e:
        logging.error(f"Ошибка при загрузке истории заказов: {e}")
        await message.answer("Произошла ошибка при загрузке ваших заказов.")


@router.callback_query(F.data.startswith("myorder_"))
async def show_my_order_details(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    query_order = """
                  SELECT o.id, o.status, o.total_amount, o.delivery_method, o.shipping_address, o.created_at
                  FROM orders o
                           JOIN customers c ON o.customer_id = c.id
                  WHERE o.id = $1 \
                    AND c.telegram_id = $2; \
                  """

    query_items = """
                  SELECT artist_name AS artist, \
                         album_title AS title,
                         sku, \
                         quantity, \
                         price_at_purchase
                  FROM view_order_items_detail
                  WHERE order_id = $1; \
                  """

    try:
        async with db.pool.acquire() as conn:
            order = await conn.fetchrow(query_order, order_id, user_id)
            if not order:
                return await callback.answer("❌ Заказ не найден или у вас нет к нему доступа.", show_alert=True)
            items = await conn.fetch(query_items, order_id)

        date_str = order['created_at'].strftime("%d.%m.%Y %H:%M")

        # Разметка переведена на HTML
        text = (
            f"🧾 <b>Детали заказа #{order['id']}</b>\n"
            f"📅 <b>Дата:</b> {date_str}\n"
            f"📌 <b>Статус:</b> <code>{order['status']}</code>\n\n"
            f"🚚 <b>Доставка:</b> {order['delivery_method']}\n"
        )

        if order['shipping_address']:
            text += f"📍 <b>Адрес:</b> {order['shipping_address']}\n"

        text += "\n🛒 <b>Состав заказа:</b>\n"

        for idx, item in enumerate(items, start=1):
            # Убраны format и color, так как SQL-запрос их не извлекает
            text += (
                f"{idx}. {item['artist']} — {item['title']}\n"
                f"   └ {item['quantity']} шт. x {item['price_at_purchase']} руб. (SKU: <code>{item['sku']}</code>)\n"
            )

        text += f"\n💰 <b>Итого:</b> {order['total_amount']} руб."

        kb = [[types.InlineKeyboardButton(text="🔙 К списку заказов", callback_data="back_to_my_orders")]]
        reply_markup = types.InlineKeyboardMarkup(inline_keyboard=kb)

        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)

    except Exception as e:
        logging.error(f"Ошибка при загрузке деталей заказа #{order_id}: {e}")
        await callback.answer("Не удалось загрузить детали заказа.", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "back_to_my_orders")
async def back_to_my_orders_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    query = """
            SELECT o.id, o.status, o.total_amount, o.created_at
            FROM orders o
                     JOIN customers c ON o.customer_id = c.id
            WHERE c.telegram_id = $1
            ORDER BY o.created_at DESC; \
            """

    try:
        async with db.pool.acquire() as conn:
            orders = await conn.fetch(query, user_id)

        if not orders:
            return await callback.message.edit_text("📭 У вас пока нет заказов.")

        builder = InlineKeyboardBuilder()
        for order in orders:
            date_str = order['created_at'].strftime("%d.%m.%Y")
            btn_text = f"#{order['id']} ({date_str}) — {order['status']}"
            builder.button(text=btn_text, callback_data=f"myorder_{order['id']}")

        builder.adjust(1)

        await callback.message.edit_text(
            "📦 <b>Ваша история заказов:</b>\nНажмите на заказ для просмотра деталей.",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logging.error(f"Ошибка при возврате к списку заказов: {e}")

    await callback.answer()