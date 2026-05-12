from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_admin_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="📋 Активные заказы", callback_data="admin_active_orders")],
        [InlineKeyboardButton(text="🗄 История (Выполненные)", callback_data="admin_history_orders")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_admin_order_actions_keyboard(order_id: int, current_status: str):
    if current_status in ('Выполнен', 'Отменен'):
        kb = [[InlineKeyboardButton(text="🔙 К истории заказов", callback_data="admin_history_orders")]]
    else:
        kb = [
            [
                InlineKeyboardButton(text="📦 Отправлен", callback_data=f"admstatus_{order_id}_Отправлен"),
                InlineKeyboardButton(text="✅ Выполнен", callback_data=f"admstatus_{order_id}_Выполнен")
            ],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"admstatus_{order_id}_Отменен")],
            [InlineKeyboardButton(text="🔙 К активным заказам", callback_data="admin_active_orders")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=kb)