import os
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db
from config import DEFAULT_COVER_PATH
from keyboards.user_kb import get_catalog_categories_keyboard, get_buy_keyboard

router = Router()


@router.message(F.text == "💽 Каталог винила")
@router.message(Command("catalog"))
@router.callback_query(F.data == "catalog")
async def show_catalog_root(event: types.Message | types.CallbackQuery):
    text = "Выберите, как вы хотите искать пластинки:"
    keyboard = get_catalog_categories_keyboard()

    # Проверяем, откуда пришел запрос: от кнопки или от команды
    if isinstance(event, types.CallbackQuery):
        try:
            # Пытаемся плавно заменить текст
            await event.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            # Если до этого была картинка, удаляем и шлем заново
            await event.message.delete()
            await event.message.answer(text, reply_markup=keyboard)
        await event.answer() # Гасим часики загрузки
    else:
        # Если это просто команда /catalog
        await event.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "nav_artists")
async def show_artists(callback: types.CallbackQuery):
    query = "SELECT DISTINCT a.id, a.name FROM artists a JOIN releases r ON a.id = r.artist_id JOIN vinyl_records v ON r.id = v.release_id WHERE v.stock_quantity > 0 ORDER BY a.name;"
    async with db.pool.acquire() as conn:
        artists = await conn.fetch(query)

    if not artists:
        await callback.message.edit_text("Сейчас нет доступных исполнителей.",
                                         reply_markup=get_catalog_categories_keyboard())
        return

    builder = InlineKeyboardBuilder()
    for artist in artists:
        builder.button(text=artist['name'], callback_data=f"artist_{artist['id']}")
    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="nav_back_root"))
    await callback.message.edit_text("🎸 **Выберите исполнителя:**", parse_mode="Markdown",
                                     reply_markup=builder.as_markup())


@router.callback_query(F.data == "nav_genres")
async def show_genres(callback: types.CallbackQuery):
    query = "SELECT DISTINCT g.id, g.name FROM genres g JOIN release_genres rg ON g.id = rg.genre_id JOIN vinyl_records v ON rg.release_id = v.release_id WHERE v.stock_quantity > 0 ORDER BY g.name;"
    async with db.pool.acquire() as conn:
        genres = await conn.fetch(query)

    builder = InlineKeyboardBuilder()
    for genre in genres:
        builder.button(text=genre['name'], callback_data=f"genre_{genre['id']}")
    builder.adjust(2)
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="nav_back_root"))
    await callback.message.edit_text("🎧 **Выберите жанр:**", parse_mode="Markdown", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("artist_"))
async def show_artist_portfolio(callback: types.CallbackQuery):
    # Извлекаем ID артиста из callback_data (например, "artist_1")
    artist_id = int(callback.data.split("_")[1])

    async with db.pool.acquire() as conn:
        # 1. Получаем профиль исполнителя (имя, страна, описание)
        artist = await conn.fetchrow(
            "SELECT name, country, description FROM artists WHERE id = $1;",
            artist_id
        )

        # 2. Получаем все релизы этого артиста (сортируем по году выпуска)
        releases = await conn.fetch(
            "SELECT id, title, release_year FROM releases WHERE artist_id = $1 ORDER BY release_year;",
            artist_id
        )

    if not artist:
        await callback.answer("Информация об исполнителе не найдена.", show_alert=True)
        return

    # Формируем текст сводки
    text = (
        f"🎤 **{artist['name']}** 🌍 _{artist['country']}_\n\n"
        f"📖 {artist['description']}\n\n"
        f"👇 **Выберите альбом для просмотра изданий:**"
    )

    # Динамически собираем клавиатуру из альбомов
    builder = InlineKeyboardBuilder()

    if releases:
        for r in releases:
            builder.button(
                text=f"💿 {r['title']} ({r['release_year']})",
                callback_data=f"release_{r['id']}"
            )
    else:
        text += "\n\n_(К сожалению, альбомов этого исполнителя сейчас нет в каталоге)_"

    # Добавляем кнопку возврата на предыдущий уровень (например, к списку артистов или жанров)
    builder.button(text="🔙 Назад", callback_data="back_to_catalog_root")

    # Выстраиваем кнопки в один столбец для удобства чтения на телефоне
    builder.adjust(1)

    # Обновляем сообщение
    try:
        # Если до этого была картинка, edit_text может выдать ошибку,
        # поэтому надежнее удалить старое сообщение и прислать новое,
        # либо использовать edit_caption, если картинку оставляем.
        # Для простоты текстового меню:
        await callback.message.delete()
        await callback.message.answer(
            text=text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )
    except Exception:
        # Резервный вариант, если удаление не сработало
        await callback.message.edit_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )

    await callback.answer()


@router.callback_query(F.data == "back_to_catalog_root")
async def show_all_artists(callback: types.CallbackQuery):
    # Получаем список всех артистов из БД, сортируем по алфавиту
    async with db.pool.acquire() as conn:
        artists = await conn.fetch("SELECT id, name FROM artists ORDER BY name;")

    if not artists:
        await callback.answer("Каталог исполнителей пока пуст.", show_alert=True)
        return

    text = "🎸 **Каталог исполнителей:**\nВыберите группу, чтобы посмотреть альбомы:"

    builder = InlineKeyboardBuilder()

    # Генерируем кнопки для каждого артиста
    for artist in artists:
        builder.button(
            text=f"{artist['name']}",
            callback_data=f"artist_{artist['id']}"
        )

    # Выстраиваем кнопки исполнителей по 2 в ряд
    builder.adjust(2)

    # --- ДОБАВЛЕНО: Кнопка выхода ---
    # Метод row() принудительно создает новую строку на всю ширину сообщения
    builder.row(types.InlineKeyboardButton(text="🏠 На главную", callback_data="main_menu"))

    try:
        await callback.message.edit_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            text=text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )

    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    text = "🏠 **Главное меню**\nДобро пожаловать в магазин винила! Выберите нужное действие:"

    # Создаем кнопки главного меню
    builder = InlineKeyboardBuilder()
    # В хэндлере главного меню:
    builder.button(text="💿 Открыть каталог", callback_data="catalog")
    # Если у вас есть корзина или другие разделы, раскомментируйте и добавьте их сюда:
    # builder.button(text="🛒 Моя корзина", callback_data="cart_view")
    # builder.button(text="📦 Мои заказы", callback_data="my_orders")

    builder.adjust(1)  # Кнопки друг под другом

    try:
        # Если меню вызывается из текстового сообщения, плавно меняем текст
        await callback.message.edit_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )
    except Exception:
        # Если мы возвращаемся из карточки с фото, плавно изменить не получится.
        # Удаляем старое сообщение с картинкой и шлем новое текстовое.
        await callback.message.delete()
        await callback.message.answer(
            text=text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )

    # Обязательно "гасим" часики загрузки на нажатой кнопке
    await callback.answer()


@router.callback_query(F.data.startswith("artist_") | F.data.startswith("genre_"))
async def show_releases(callback: types.CallbackQuery):
    action, item_id = callback.data.split("_")
    item_id = int(item_id)

    if action == "artist":
        query = "SELECT DISTINCT r.id, r.title, r.release_year, a.name AS artist_name FROM releases r JOIN artists a ON r.artist_id = a.id JOIN vinyl_records v ON r.id = v.release_id WHERE r.artist_id = $1 AND v.stock_quantity > 0 ORDER BY r.release_year DESC;"
        back_btn = "nav_artists"
    else:
        query = "SELECT DISTINCT r.id, r.title, r.release_year, a.name AS artist_name FROM releases r JOIN release_genres rg ON r.id = rg.release_id JOIN artists a ON r.artist_id = a.id JOIN vinyl_records v ON r.id = v.release_id WHERE rg.genre_id = $1 AND v.stock_quantity > 0 ORDER BY a.name, r.release_year DESC;"
        back_btn = "nav_genres"

    async with db.pool.acquire() as conn:
        releases = await conn.fetch(query, item_id)

    builder = InlineKeyboardBuilder()
    for release in releases:
        btn_text = f"{release['artist_name']} - {release['title']} ({release['release_year']})"
        builder.button(text=btn_text, callback_data=f"release_{release['id']}")
    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data=back_btn))
    await callback.message.edit_text("📀 **Выберите релиз:**", parse_mode="Markdown", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("release_"))
async def show_release_formats(callback: types.CallbackQuery):
    release_id = int(callback.data.split("_")[1])
    query = "SELECT v.sku, v.format, v.color, v.condition_media, v.price, a.name AS artist_name, r.title AS album_title FROM vinyl_records v JOIN releases r ON v.release_id = r.id JOIN artists a ON r.artist_id = a.id WHERE v.release_id = $1 AND v.stock_quantity > 0 ORDER BY v.price ASC;"

    async with db.pool.acquire() as conn:
        records = await conn.fetch(query, release_id)

    if not records:
        await callback.answer("К сожалению, все издания этого альбома распроданы.", show_alert=True)
        return

    artist = records[0]['artist_name']
    album = records[0]['album_title']
    builder = InlineKeyboardBuilder()
    for rec in records:
        btn_text = f"{rec['format']} | {rec['color']} ({rec['condition_media']}) - {rec['price']}₽"
        builder.button(text=btn_text, callback_data=f"item_{rec['sku']}")
    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 В меню каталога", callback_data="nav_back_root"))

    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(f"🎸 **{artist} — {album}**\n\nВыберите подходящее издание:", parse_mode="Markdown",
                                  reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("item_"))
async def show_single_product_card(callback: types.CallbackQuery):
    sku = callback.data.split("_")[1]

    query = """
            SELECT sku, \
                   artist_name, \
                   album_title, \
                   album_description, \
                   format,
                   color, \
                   condition_media, \
                   price, \
                   cover_image_url, \
                   release_id
            FROM view_vinyl_catalog
            WHERE sku = $1 \
              AND stock_quantity > 0; \
            """

    async with db.pool.acquire() as conn:
        record = await conn.fetchrow(query, sku)

    if not record:
        await callback.answer("Эта пластинка только что была распродана!", show_alert=True)
        return

    text = (
        f"🎸 **{record['artist_name']} — {record['album_title']}**\n\n"
        f"📖 _{record['album_description']}_\n\n"
        f"▫️ **Формат:** {record['format']} ({record['color']})\n"
        f"▫️ **Состояние:** {record['condition_media']}\n"
        f"▫️ **Артикул:** `{record['sku']}`\n\n"
        f"💰 **Цена:** {record['price']} руб."
    )

    kb = [
        [types.InlineKeyboardButton(text="➕ В корзину", callback_data=f"buy_{sku}")],
        [types.InlineKeyboardButton(text="🔙 К списку изданий", callback_data=f"release_{record['release_id']}")]
    ]
    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=kb)

    image_path = record['cover_image_url']
    photo_to_send = None

    if image_path:
        if image_path.startswith("http"):
            photo_to_send = URLInputFile(image_path)
        elif os.path.exists(image_path):
            photo_to_send = FSInputFile(image_path)

    if not photo_to_send and os.path.exists(DEFAULT_COVER_PATH):
        photo_to_send = FSInputFile(DEFAULT_COVER_PATH)

    try:
        await callback.message.delete()
    except Exception:
        pass

    try:
        if photo_to_send:
            await callback.message.answer_photo(
                photo=photo_to_send,
                caption=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await callback.message.answer(
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    except Exception as e:
        # Улучшено логирование: теперь видно, на каком артикуле произошла ошибка
        logging.warning(f"Ошибка загрузки фото для артикула {sku}: {e}")
        await callback.message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    await callback.answer()


@router.callback_query(F.data == "nav_back_root")
async def nav_back_root(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите, как вы хотите искать пластинки:",
                                     reply_markup=get_catalog_categories_keyboard())