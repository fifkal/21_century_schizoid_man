import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Предполагаемые импорты из вашего проекта
from database import db
from filters import IsAdmin
from keyboards.admin_kb import get_admin_main_keyboard, get_admin_order_actions_keyboard

router = Router()

# Подключаем фильтр IsAdmin ко всем сообщениям и коллбэкам в этом роутере
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("admin"))
async def cmd_admin_panel(message: types.Message):
    text = "🛠 <b>Панель управления магазином</b>\n\nЗдесь вы можете управлять заказами и статусами доставок."
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_main_keyboard())


@router.callback_query(F.data == "admin_main_menu")
async def back_to_admin_main(callback: types.CallbackQuery):
    text = "🛠 <b>Панель управления магазином</b>\n\nЗдесь вы можете управлять заказами и статусами доставок."
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_main_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_active_orders")
async def show_active_orders(callback: types.CallbackQuery):
    query = """
            SELECT order_id AS id, status, total_amount, created_at, username
            FROM view_order_summary
            WHERE status NOT IN ('Выполнен', 'Отменен')
            ORDER BY created_at ASC; \
            """
    async with db.pool.acquire() as conn:
        orders = await conn.fetch(query)

    if not orders:
        await callback.message.edit_text(
            "🎉 Сейчас нет активных заказов. Все отправлено!",
            parse_mode="HTML",
            reply_markup=get_admin_main_keyboard()
        )
        return

    builder = InlineKeyboardBuilder()
    for order in orders:
        # Формируем текст кнопки (напр. "#12 | ivan_vinyl | 4500₽ | Оплачен")
        btn_text = f"#{order['id']} | @{order['username']} | {order['total_amount']}₽ | {order['status']}"
        builder.button(text=btn_text, callback_data=f"admorder_{order['id']}")

    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 В главное админ-меню", callback_data="admin_main_menu"))

    await callback.message.edit_text("📋 <b>Активные заказы:</b>", parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admorder_"))
async def show_order_details(callback: types.CallbackQuery):
    # Безопасное извлечение ID
    try:
        order_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        return await callback.answer("Ошибка: неверный ID заказа.", show_alert=True)

    # Добавлен алиас "o.id AS order_id", чтобы избежать KeyError
    query_order = """
                  SELECT o.id AS order_id, \
                         o.status, \
                         o.total_amount, \
                         o.delivery_method, \
                         o.shipping_address,
                         c.username, \
                         c.phone, \
                         c.email
                  FROM orders o
                           JOIN customers c ON o.customer_id = c.id
                  WHERE o.id = $1; \
                  """
    query_items = """
                  SELECT artist_name AS artist, album_title AS title, sku, quantity, price_at_purchase
                  FROM view_order_items_detail
                  WHERE order_id = $1; \
                  """

    async with db.pool.acquire() as conn:
        order = await conn.fetchrow(query_order, order_id)
        if not order:
            return await callback.answer("Заказ не найден в базе данных.", show_alert=True)

        items = await conn.fetch(query_items, order_id)

    # Переведено на HTML, убраны конфликтующие теги Markdown (**)
    text = (
        f"📦 <b>Заказ #{order['order_id']}</b>\n"
        f"👤 <b>От:</b> @{order['username']}\n"
    )

    if order['phone']:
        text += f"📞 <b>Телефон:</b> {order['phone']}\n"
    if order['email']:
        text += f"📧 <b>Email:</b> {order['email']}\n"

    text += f"💰 <b>Сумма:</b> {order['total_amount']} руб.\n"

    if order['shipping_address']:
        text += f"📍 <b>Адрес:</b> {order['shipping_address']}\n"

    text += "\n🛒 <b>Товары:</b>\n"

    for idx, item in enumerate(items, start=1):
        text += (
            f"{idx}. {item['artist']} - {item['title']}\n"
            f"   └ {item['quantity']} шт. x {item['price_at_purchase']}₽ "
            f"(SKU: <code>{item['sku']}</code>)\n"
        )

    text += f"\n💰 <b>ИТОГО:</b> {order['total_amount']} руб."

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_admin_order_actions_keyboard(order_id, order['status'])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admstatus_"))
async def change_order_status(callback: types.CallbackQuery):
    """Обновляет статус заказа. При отмене использует хранимую процедуру для возврата товаров."""

    # maxsplit=2 гарантирует безопасное разделение, даже если статус состоит из нескольких слов
    parts = callback.data.split("_", maxsplit=2)
    if len(parts) != 3:
        return await callback.answer("Некорректные данные для смены статуса", show_alert=True)

    _, order_id_str, new_status = parts
    order_id = int(order_id_str)

    try:
        async with db.pool.acquire() as conn:
            if new_status == 'Отменен':
                await conn.execute("CALL cancel_order_and_restock($1)", order_id)
                await callback.answer(f"✅ Заказ #{order_id} отменен. Товары возвращены на склад!", show_alert=True)
            else:
                await conn.execute("UPDATE orders SET status = $1 WHERE id = $2;", new_status, order_id)
                await callback.answer(f"✅ Статус изменен на '{new_status}'", show_alert=True)
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса заказа #{order_id}: {e}")
        return await callback.answer("Произошла ошибка при обновлении статуса.", show_alert=True)

    # Возвращаем админа к обновленному списку активных заказов
    await show_active_orders(callback)


@router.callback_query(F.data == "admin_history_orders")
async def show_history_orders(callback: types.CallbackQuery):
    query = """
            SELECT o.id, o.status, o.total_amount, o.created_at, c.username
            FROM orders o
                     JOIN customers c ON o.customer_id = c.id
            WHERE o.status IN ('Выполнен', 'Отменен')
            ORDER BY o.created_at DESC LIMIT 50; \
            """
    async with db.pool.acquire() as conn:
        orders = await conn.fetch(query)

    if not orders:
        return await callback.answer("🗄 История пуста. Завершенных заказов пока нет.", show_alert=True)

    builder = InlineKeyboardBuilder()
    for order in orders:
        icon = "✅" if order['status'] == 'Выполнен' else "❌"
        btn_text = f"{icon} #{order['id']} | @{order['username']} | {order['total_amount']}₽"
        builder.button(text=btn_text, callback_data=f"admorder_{order['id']}")

    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 В главное админ-меню", callback_data="admin_main_menu"))

    text = "🗄 <b>История заказов:</b>\nПоследние 50 завершенных и отмененных покупок."
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()