from aiogram.fsm.state import State, StatesGroup

class CheckoutState(StatesGroup):
    """Шаги оформления заказа"""
    email = State()
    phone = State()
    delivery_method = State()
    address = State()