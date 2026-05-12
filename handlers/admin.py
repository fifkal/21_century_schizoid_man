from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db
from filters import IsAdmin
from keyboards.admin_kb import get_admin_main_keyboard, get_admin_order_actions_keyboard

router = Router()
# Подключаем фильтр IsAdmin ко всем сообщениям и коллбэкам в этом роутере
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

@router.message(Command("admin"))
async def cmd_admin_panel(message: types.Message):
    await message.answer("🛠 **Панель управления магазином**\n\nЗдесь вы можете управлять заказами и статусами доставок.", parse_mode="Markdown", reply_markup=get_admin_main_keyboard())

@router.callback_query(F.data == "admin_active_orders")
async def show_active_orders(callback: types.CallbackQuery):
    query = ("SELECT order_id AS id, status, total_amount, "
             "created_at, first_name FROM view_order_summary WHERE status NOT IN ('Выполнен', 'Отменен') ORDER BY created_at ASC;")
    async with db.pool.acquire() as conn:
        orders = await conn.fetch(query)

    if not orders:
        await callback.message.edit_text("🎉 Сейчас нет активных заказов. Все отправлено!", reply_markup=get_admin_main_keyboard())
        return

    builder = InlineKeyboardBuilder()
    for order in orders:
        date_str = order['created_at'].strftime("%d.%m")
        btn_text = f"#{order['id']} | {order['first_name']} | {order['total_amount']}₽ | {order['status']}"
        builder.button(text=btn_text, callback_data=f"admorder_{order['id']}")

    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 В главное админ-меню", callback_data="admin_main_menu"))
    await callback.message.edit_text("📋 **Активные заказы:**", parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("admorder_"))
async def show_order_details(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    query_order = ("SELECT o.id, o.status, o.total_amount, o.delivery_method, o.shipping_address, "
                   "c.first_name, c.last_name, c.phone, c.email FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id = $1;")
    query_items = ("SELECT artist_name AS artist, album_title AS title, "
                   "sku, quantity, price_at_purchase FROM view_order_items_detail WHERE order_id = $1;")

    async with db.pool.acquire() as conn:
        order = await conn.fetchrow(query_order, order_id)
        items = await conn.fetch(query_items, order_id)

    text = (f"🧾 **ЗАКАЗ #{order['id']}**\n📌 **Статус:** {order['status']}\n\n👤 **Покупатель:** {order['first_name']} {order['last_name']}\n📞 **Телефон:** `{order['phone']}`\n📧 **Email:** {order['email']}\n🚚 **Доставка:** {order['delivery_method']}\n")
    if order['shipping_address']: text += f"📍 **Адрес:** {order['shipping_address']}\n"
    text += "\n🛒 **Товары:**\n"
    for idx, item in enumerate(items, start=1):
        text += f"{idx}. {item['artist']} - {item['title']}\n   └ {item['quantity']} шт. x {item['price_at_purchase']}₽ (SKU: `{item['sku']}`)\n"
    text += f"\n💰 **ИТОГО:** {order['total_amount']} руб."

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_order_actions_keyboard(order_id, order['status']))

@router.callback_query(F.data.startswith("admstatus_"))
async def change_order_status(callback: types.CallbackQuery):
    """Обновляет статус заказа. При отмене использует хранимую процедуру для возврата товаров."""
    _, order_id, new_status = callback.data.split("_")
    order_id = int(order_id)

    async with db.pool.acquire() as conn:
        if new_status == 'Отменен':
            # Вызываем нашу хранимую SQL-процедуру!
            # Она сама изменит статус и добавит +N к stock_quantity каждой пластинки в чеке
            await conn.execute("CALL cancel_order_and_restock($1)", order_id)
            await callback.answer(f"✅ Заказ #{order_id} отменен. Товары возвращены на склад!", show_alert=True)
        else:
            # Для других статусов (Отправлен, Выполнен) используем обычный UPDATE
            await conn.execute("UPDATE orders SET status = $1 WHERE id = $2;", new_status, order_id)
            await callback.answer(f"✅ Статус изменен на '{new_status}'", show_alert=True)

    # Возвращаем админа к обновленному списку
    await show_active_orders(callback)

@router.callback_query(F.data == "admin_history_orders")
async def show_history_orders(callback: types.CallbackQuery):
    query = "SELECT o.id, o.status, o.total_amount, o.created_at, c.first_name FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.status IN ('Выполнен', 'Отменен') ORDER BY o.created_at DESC LIMIT 50;"
    async with db.pool.acquire() as conn:
        orders = await conn.fetch(query)

    if not orders: return await callback.answer("🗄 История пуста. Завершенных заказов пока нет.", show_alert=True)

    builder = InlineKeyboardBuilder()
    for order in orders:
        icon = "✅" if order['status'] == 'Выполнен' else "❌"
        btn_text = f"{icon} #{order['id']} | {order['first_name']} | {order['total_amount']}₽"
        builder.button(text=btn_text, callback_data=f"admorder_{order['id']}")
    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 В главное админ-меню", callback_data="admin_main_menu"))
    await callback.message.edit_text("🗄 **История заказов:**\nПоследние 50 завершенных и отмененных покупок.", parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_main_menu")
async def back_to_admin_main(callback: types.CallbackQuery):
    await callback.message.edit_text("🛠 **Панель управления магазином**", parse_mode="Markdown", reply_markup=get_admin_main_keyboard())