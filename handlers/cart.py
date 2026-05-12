import re
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from states import CheckoutState

router = Router()
user_carts = {}  # Хранилище корзин в оперативной памяти


@router.callback_query(F.data.startswith("buy_"))
async def process_buy_callback(callback: types.CallbackQuery):
    sku = callback.data.split("_")[1]
    user_id = callback.from_user.id
    query = "SELECT stock_quantity FROM vinyl_records WHERE sku = $1"

    async with db.pool.acquire() as conn:
        record = await conn.fetchrow(query, sku)

    if not record or record['stock_quantity'] <= 0:
        await callback.answer("К сожалению, эта пластинка только что была полностью распродана! 😔", show_alert=True)
        return

    if user_id not in user_carts: user_carts[user_id] = {}
    current_qty = user_carts[user_id].get(sku, 0)

    if current_qty >= record['stock_quantity']:
        await callback.answer(f"Невозможно добавить! На складе доступно всего: {record['stock_quantity']} шт.",
                              show_alert=True)
        return

    user_carts[user_id][sku] = current_qty + 1
    await callback.answer("✅ Товар успешно добавлен в корзину!", show_alert=False)


@router.message(F.text == "🛒 Моя корзина")
async def show_cart(message: types.Message):
    user_id = message.from_user.id
    cart = user_carts.get(user_id, {})

    if not cart:
        await message.answer("Ваша корзина пуста 😔. Загляните в каталог!")
        return

    skus = list(cart.keys())
    query = ("SELECT sku, artist_name AS artist, "
             "album_title AS title, price FROM view_vinyl_catalog WHERE sku = ANY ($1::varchar[]);")
    async with db.pool.acquire() as conn:
        items = await conn.fetch(query, skus)

    text = "🛒 **Ваша корзина:**\n\n"
    total_amount = 0
    for item in items:
        qty = cart[item['sku']]
        line_total = item['price'] * qty
        total_amount += line_total
        text += f"▫️ {item['artist']} - {item['title']}\n   └ {qty} шт. x {item['price']} = {line_total} руб.\n"

    text += f"\n💰 **Итого к оплате:** {total_amount} руб."
    kb = [[InlineKeyboardButton(text="✅ Оформить заказ", callback_data="start_checkout")],
          [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")]]
    await message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    if callback.from_user.id in user_carts: del user_carts[callback.from_user.id]
    await callback.message.edit_text("🗑 Ваша корзина очищена.")


# --- Оформление заказа ---
@router.callback_query(F.data == "start_checkout")
async def checkout_start(callback: types.CallbackQuery, state: FSMContext):
    if not user_carts.get(callback.from_user.id): return await callback.answer("Ваша корзина пуста!", show_alert=True)
    await state.set_state(CheckoutState.email)
    await callback.message.answer("Начинаем оформление заказа! 🚀\n\nВведите ваш **Email**:")
    await callback.answer()


@router.message(CheckoutState.email)
async def checkout_email(message: types.Message, state: FSMContext):
    if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", message.text): return await message.answer(
        "Некорректный формат email. Попробуйте еще раз:")
    await state.update_data(email=message.text)
    await state.set_state(CheckoutState.phone)
    await message.answer("Отлично. Теперь введите ваш **Номер телефона** (в формате +7... или 8...):")


@router.message(CheckoutState.phone)
async def checkout_phone(message: types.Message, state: FSMContext):
    clean_phone = "".join(char for char in message.text if char.isdigit() or char == '+')
    if not re.match(r"^(\+7|8)[0-9]{10}$", clean_phone): return await message.answer(
        "Некорректный формат. Номер должен состоять из 11 цифр. Попробуйте еще раз:")
    await state.update_data(phone=clean_phone)
    await state.set_state(CheckoutState.delivery_method)
    kb = [[InlineKeyboardButton(text="🚚 Доставка", callback_data="delivery_Доставка"),
           InlineKeyboardButton(text="🏢 Самовывоз", callback_data="delivery_Самовывоз")]]
    await message.answer("Выберите способ получения заказа:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(CheckoutState.delivery_method, F.data.startswith("delivery_"))
async def checkout_delivery(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1]
    await state.update_data(delivery_method=method)
    if method == "Доставка":
        await state.set_state(CheckoutState.address)
        await callback.message.edit_text("Выбрана доставка. Введите полный **Адрес доставки**:")
    else:
        await callback.message.edit_text("Выбран самовывоз.")
        await state.update_data(address=None)
        await finalize_order(callback.message, state, callback.from_user)


@router.message(CheckoutState.address)
async def checkout_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    await finalize_order(message, state, message.from_user)


async def finalize_order(message: types.Message, state: FSMContext, user: types.User):
    data = await state.get_data()
    cart = user_carts.get(user.id, {})
    first_name, last_name = user.first_name or "Покупатель", user.last_name or ""

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            customer_id = await conn.fetchval("SELECT id FROM customers WHERE telegram_id = $1", user.id)
            if not customer_id:
                customer_id = await conn.fetchval(
                    "INSERT INTO customers (first_name, last_name, email, phone, telegram_id) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (email) DO UPDATE SET telegram_id = EXCLUDED.telegram_id RETURNING id",
                    first_name, last_name, data['email'], data['phone'], user.id
                )

            total_amount, order_items_data = 0, []
            for sku, qty in cart.items():
                record = await conn.fetchrow("SELECT id, price, stock_quantity FROM vinyl_records WHERE sku = $1", sku)
                if record['stock_quantity'] < qty:
                    await message.answer(f"❌ Ошибка: Товара {sku} нет в нужном количестве!")
                    return await state.clear()
                total_amount += record['price'] * qty
                order_items_data.append((record['id'], qty, record['price']))

            order_id = await conn.fetchval(
                "INSERT INTO orders (customer_id, total_amount, delivery_method, shipping_address) VALUES ($1, $2, $3, $4) RETURNING id",
                customer_id, total_amount, data['delivery_method'], data['address'])

            for r_id, qty, price in order_items_data:
                await conn.execute(
                    "INSERT INTO order_items (order_id, vinyl_record_id, quantity, price_at_purchase) VALUES ($1, $2, $3, $4)",
                    order_id, r_id, qty, price)
                await conn.execute("UPDATE vinyl_records SET stock_quantity = stock_quantity - $1 WHERE id = $2", qty,
                                   r_id)

    del user_carts[user.id]
    await state.clear()
    await message.answer(
        f"🎉 **Заказ #{order_id} успешно оформлен!**\nИтоговая сумма: {total_amount} руб.\nОжидайте, администратор скоро свяжется с вами.",
        parse_mode="Markdown")