import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId
import datetime as dt
import logging
import aiohttp

# Настройка логирования для диагностики
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

API_TOKEN = "7898171758:AAGodbxpbofXC568XzgJ7VPLiJ-flt8YokU"
ADMIN_ID = 349177382
CHANNEL_ID = "@vacancy228"


# API_TOKEN = "7652183042:AAHkGYirAKyb8iww0OAjQciL0MRHzbrtICQ"
# ADMIN_ID = 685600785
# CHANNEL_ID = "@rabota_minsk"

# Подключение к MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["vacancy"]
vacancies_collection = db["vacancies"]
settings_collection = db["settings"]

# Инициализация инструкций
if not settings_collection.find_one({"key": "payment_instructions"}):
    settings_collection.insert_one({
        "key": "payment_instructions",
        "value": (
            "<b>Оплатите 5 BYN через ЕРИП:</b>\n"
            "📱 Платежи → ЕРИП → Банковские/Финансовые услуги → Банки/НКФО → Альфа-Банк → Пополнение счета\n"
            "В поле <b>№ телефона или № тек. счета</b> введите: <code>375447825825</code> → Далее\n"
            "В поле <b>Сумма платежа, BYN</b> введите: <code>5</code> → Далее\n"
            "Проверьте все данные → Оплатить\n\n"
            "Администратор в рабочее время проверит платеж и одобрит вашу вакансию\n"
            "По всем вопросам: @saskovets"
        )
    })

if not settings_collection.find_one({"key": "channel_instruction"}):
    settings_collection.insert_one({
        "key": "channel_instruction",
        "value": (
            "📌 Как разместить вакансию в канале\n"
            "💬 Чтобы опубликовать вакансию, перейдите в нашего Telegram-бота и заполните анкету.\n"
            "🤖 https://t.me/rabota_minsk_bot\n\n"
            "Укажите следующую информацию:\n\n"
            "1️⃣ Название вакансии\n"
            "Краткое и понятное — чтобы сразу было видно, кого вы ищете.\n"
            "2️⃣ Описание вакансии\n"
            "Опишите, чем предстоит заниматься, какие нужны навыки и опыт.\n"
            "3️⃣ Заработная плата\n"
            "Укажите сумму в BYN — за день, месяц или смену.\n"
            "4️⃣ Тип занятости\n"
            "Например: подработка, полный день, график 2/2 и т.д.\n"
            "5️⃣ Контакт для связи\n"
            "Оставьте номер телефона или ник в Telegram (например, @username).\n\n"
            "❗️ После заполнения анкеты бот предложит два варианта публикации:\n\n"
            "🕟 Бесплатно — вакансия публикуется в порядке живой очереди. Ожидание может занять до 12 часов.\n"
            "💵 Платно — вакансия будет опубликована максимально быстро. Стоимость размещения — 5 BYN.\n\n"
            "🔎 Обратите внимание:\n"
            "Каждая вакансия проходит предварительную модерацию. Сомнительные или подозрительные объявления будут отклонены."
        ),
        "button_text": "Перейти к боту",
        "message_id": None
    })

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

class VacancyForm(StatesGroup):
    title = State()
    description = State()
    salary = State()
    employment = State()
    link = State()
    review = State()
    priority = State()
    payment_check = State()
    edit_payment = State()
    edit_channel_instruction = State()
    edit_channel_button = State()

VACANCIES_PER_PAGE = 5
MAX_MESSAGES_TO_DELETE = 50  # Ограничение на количество сообщений для удаления за раз

async def send_and_log(chat_id, text, state, is_vacancy=False, **kwargs):
    try:
        msg = await bot.send_message(chat_id, text, **kwargs)
        data = await state.get_data()
        messages = data.get("messages_to_delete", [])
        vacancy_messages = data.get("vacancy_messages", [])
        if is_vacancy:
            vacancy_messages.append(msg.message_id)
        else:
            messages.append({"bot_msg_id": msg.message_id})
        await state.update_data(messages_to_delete=messages, vacancy_messages=vacancy_messages)
        logger.info(f"Сообщение отправлено в чат {chat_id}: {msg.message_id}")
        return msg
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")
        raise

async def get_payment_instructions():
    setting = settings_collection.find_one({"key": "payment_instructions"})
    return setting["value"] if setting else "Инструкции по оплате не найдены."

async def get_channel_instruction():
    setting = settings_collection.find_one({"key": "channel_instruction"})
    if setting:
        return setting["value"], setting.get("button_text", "Перейти к боту"), setting.get("message_id")
    return (
        "📌 Как разместить вакансию в канале\n"
        "💬 Чтобы опубликовать вакансию, перейдите в нашего Telegram-бота и заполните анкету.\n"
        "🤖 https://t.me/rabota_minsk_bot\n\n"
        "Укажите следующую информацию:\n\n"
        "1️⃣ Название вакансии\n"
        "Краткое и понятное — чтобы сразу было видно, кого вы ищете.\n"
        "2️⃣ Описание вакансии\n"
        "Опишите, чем предстоит заниматься, какие нужны навыки и опыт.\n"
        "3️⃣ Заработная плата\n"
        "Укажите сумму в BYN — за день, месяц или смену.\n"
        "4️⃣ Тип занятости\n"
        "Например: подработка, полный день, график 2/2 и т.д.\n"
        "5️⃣ Контакт для связи\n"
        "Оставьте номер телефона или ник в Telegram (например, @username).\n\n"
        "❗️ После заполнения анкеты бот предложит два варианта публикации:\n\n"
        "🕟 Бесплатно — вакансия публикуется в порядке живой очереди. Ожидание может занять до 12 часов.\n"
        "💵 Платно — вакансия будет опубликована максимально быстро. Стоимость размещения — 5 BYN.\n\n"
        "🔎 Обратите внимание:\n"
        "Каждая вакансия проходит предварительную модерацию. Сомнительные или подозрительные объявления будут отклонены."
    ), "Перейти к боту", None

async def delete_messages(chat_id, messages, welcome_id, vacancy_messages):
    messages_to_delete = messages.copy()
    for msg in messages_to_delete:
        bot_msg_id = msg.get("bot_msg_id") if isinstance(msg, dict) else None
        user_msg_id = msg.get("user_msg_id") if isinstance(msg, dict) else None

        if not bot_msg_id and isinstance(msg, int):
            bot_msg_id = msg

        if bot_msg_id and bot_msg_id != welcome_id:
            try:
                await bot.delete_message(chat_id, bot_msg_id)
                logger.info(f"Удалено сообщение {bot_msg_id} из чата {chat_id}")
                if user_msg_id:
                    await bot.delete_message(chat_id, user_msg_id)
                    logger.info(f"Удалено пользовательское сообщение {user_msg_id} из чата {chat_id}")
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение {bot_msg_id}: {e}")
            finally:
                if msg in messages:
                    messages.remove(msg)

@dp.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Платежные инструкции", callback_data="view_payment")],
            [InlineKeyboardButton(text="✏️ Изменить платежные инструкции", callback_data="edit_payment")],
            [InlineKeyboardButton(text="📝 Инструкция в канале", callback_data="view_channel_instruction")],
            [InlineKeyboardButton(text="📬 Опубликовать инструкцию в канале", callback_data="post_channel_instruction")],
            [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
            [InlineKeyboardButton(text="📋 Все вакансии", callback_data="admin_view_vacancies|0")]
        ])
        welcome_msg = await send_and_log(
            message.chat.id,
            "🌟 <b>Добро пожаловать, Администратор!</b> 🌟\n\n"
            "Вы в панели управления вакансиями. Выберите действие:",
            state,
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
            [InlineKeyboardButton(text="📜 Мои вакансии", callback_data="view_my_vacancies|0")]
        ])
        welcome_msg = await send_and_log(
            message.chat.id,
            "🌟 <b>Привет!</b> 🌟\n\n"
            "Я — бот для публикации вакансий по работе и подработке.\n\n"
            "Если хочешь разместить вакансию, просто следуй инструкциям — я задам 5 коротких вопросов которые помогут сформировать пост.\n\n"
            "После этого вакансия попадёт на модерацию, и вскоре будет опубликована в канале.\n\n"
            "Хочешь ускорить публикацию и обойти очередь? Доступна платная публикация вне очереди — скажу, как это сделать в конце.\n\n"
            "Нажми <b>Создать вакансию</b>, и поехали!",
            state,
            reply_markup=keyboard
        )
    await state.update_data(welcome_message_id=welcome_msg.message_id)

@dp.message(F.text == "/admin", F.from_user.id == ADMIN_ID)
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Платежные инструкции", callback_data="view_payment")],
        [InlineKeyboardButton(text="✏️ Изменить платежные инструкции", callback_data="edit_payment")],
        [InlineKeyboardButton(text="📝 Инструкция в канале", callback_data="view_channel_instruction")],
        [InlineKeyboardButton(text="📬 Опубликовать инструкцию в канале", callback_data="post_channel_instruction")],
        [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
        [InlineKeyboardButton(text="📋 Все вакансии", callback_data="admin_view_vacancies|0")]
    ])
    welcome_msg = await send_and_log(
        message.chat.id,
        "🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
        state,
        reply_markup=keyboard
    )
    await state.update_data(welcome_message_id=welcome_msg.message_id)

@dp.message(F.text == "/my_vacancies")
async def cmd_my_vacancies(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await send_and_log(
            message.chat.id,
            "Эта команда для пользователей. Используйте /admin.",
            state
        )
        return
    
    vacancies = list(vacancies_collection.find({"user_id": message.from_user.id}))
    await display_vacancies(message.chat.id, vacancies, state, page=0)

@dp.callback_query(F.data.startswith("view_my_vacancies"))
async def view_my_vacancies(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("|")[1])
    vacancies = list(vacancies_collection.find({"user_id": callback.from_user.id}))
    await display_vacancies(callback.message.chat.id, vacancies, state, page)
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass

@dp.callback_query(F.data.startswith("admin_view_vacancies"))
async def admin_view_vacancies(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ только для администратора.")
        return
    
    page = int(callback.data.split("|")[1])
    vacancies = list(vacancies_collection.find())
    await display_all_vacancies(callback.message.chat.id, vacancies, state, page)
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass

async def display_vacancies(chat_id, vacancies, state, page=0):
    if not vacancies:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
        ])
        await send_and_log(chat_id, "📭 У вас пока нет вакансий.", state, reply_markup=keyboard)
        return
    
    approved = [v for v in vacancies if v.get("status") == "Одобрена"]
    declined = [v for v in vacancies if v.get("status") == "Отклонена"]
    pending = [v for v in vacancies if v.get("status") == "На модерации"]
    
    all_vacancies = (
        [(v, "Одобренные") for v in approved] +
        [(v, "Отклоненные") for v in declined] +
        [(v, "На модерации") for v in pending]
    )
    
    total_pages = (len(all_vacancies) + VACANCIES_PER_PAGE - 1) // VACANCIES_PER_PAGE
    start_idx = page * VACANCIES_PER_PAGE
    end_idx = min(start_idx + VACANCIES_PER_PAGE, len(all_vacancies))
    page_vacancies = all_vacancies[start_idx:end_idx]
    
    vacancy_text = f"📜 <b>Ваши вакансии (стр. {page + 1}/{total_pages}):</b>\n\n"
    for i, (vacancy, category) in enumerate(page_vacancies, start_idx + 1):
        vacancy_text += (
            f"{i}. <b>{vacancy.get('title', 'Не указано')}</b> ({category})\n"
            f"   🆔 ID: {vacancy['_id']}\n"
            f"   📄 Описание: {vacancy.get('description', 'Не указано')}\n"
            f"   💰 З/П: {vacancy.get('salary', 'Не указано')}\n"
            f"   🕒 Тип занятости: {vacancy.get('employment', 'Не указано')}\n"
            f"   ☎️ Контакт для связи: {vacancy.get('link', 'Не указано')}\n\n"
        )
    
    keyboard = InlineKeyboardBuilder()
    if page > 0:
        keyboard.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"view_my_vacancies|{page - 1}"))
    if page < total_pages - 1:
        keyboard.add(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"view_my_vacancies|{page + 1}"))
    keyboard.row(InlineKeyboardButton(text="📤 Новая вакансия", callback_data="start_form"))
    keyboard.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start"))
    
    await send_and_log(chat_id, vacancy_text, state, reply_markup=keyboard.as_markup())

async def display_all_vacancies(chat_id, vacancies, state, page=0):
    if not vacancies:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
        ])
        await send_and_log(chat_id, "📭 Вакансий пока нет.", state, reply_markup=keyboard)
        return
    
    total_pages = (len(vacancies) + VACANCIES_PER_PAGE - 1) // VACANCIES_PER_PAGE
    start_idx = page * VACANCIES_PER_PAGE
    end_idx = min(start_idx + VACANCIES_PER_PAGE, len(vacancies))
    page_vacancies = vacancies[start_idx:end_idx]
    
    vacancy_text = f"📋 <b>Все вакансии (стр. {page + 1}/{total_pages}):</b>\n\n"
    for i, vacancy in enumerate(page_vacancies, start_idx + 1):
        vacancy_text += (
            f"{i}. <b>{vacancy.get('title', 'Не указано')}</b> ({vacancy.get('status', 'Не указано')})\n"
            f"   🆔 ID: {vacancy['_id']}\n"
            f"   👤 Пользователь: @{vacancy.get('username', vacancy.get('user_id'))}\n"
            f"   📄 Описание: {vacancy.get('description', 'Не указано')}\n"
            f"   💰 З/П: {vacancy.get('salary', 'Не указано')}\n"
            f"   🕒 Тип занятости: {vacancy.get('employment', 'Не указано')}\n"
            f"   ☎️ Контакт для связи: {vacancy.get('link', 'Не указано')}\n\n"
        )
    
    keyboard = InlineKeyboardBuilder()
    if page > 0:
        keyboard.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_view_vacancies|{page - 1}"))
    if page < total_pages - 1:
        keyboard.add(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin_view_vacancies|{page + 1}"))
    for vacancy in page_vacancies:
        keyboard.row(InlineKeyboardButton(text=f"🗑 Удалить {vacancy['_id']}", callback_data=f"delete_vacancy|{vacancy['_id']}"))
    keyboard.row(InlineKeyboardButton(text="📤 Новая вакансия", callback_data="start_form"))
    keyboard.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start"))
    
    await send_and_log(chat_id, vacancy_text, state, reply_markup=keyboard.as_markup())

@dp.callback_query(F.data == "view_payment", F.from_user.id == ADMIN_ID)
async def view_payment_instructions(callback: CallbackQuery, state: FSMContext):
    instructions = await get_payment_instructions()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_payment")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    # Редактируем текущее сообщение, но добавим его в messages_to_delete перед редактированием
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    messages.append({"bot_msg_id": callback.message.message_id})
    await state.update_data(messages_to_delete=messages)
    
    await callback.message.edit_text(
        f"💸 <b>Текущие инструкции по оплате:</b>\n\n{instructions}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "view_channel_instruction", F.from_user.id == ADMIN_ID)
async def view_channel_instruction(callback: CallbackQuery, state: FSMContext):
    instruction, button_text, message_id = await get_channel_instruction()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="edit_channel_instruction")],
        [InlineKeyboardButton(text="🔗 Изменить кнопку", callback_data="edit_channel_button")],
        [InlineKeyboardButton(text="📬 Опубликовать/Обновить", callback_data="post_channel_instruction")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    # Редактируем текущее сообщение, но добавим его в messages_to_delete перед редактированием
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    messages.append({"bot_msg_id": callback.message.message_id})
    await state.update_data(messages_to_delete=messages)
    
    await callback.message.edit_text(
        f"📢 <b>Инструкция для канала:</b>\n\n{instruction}\n\n"
        f"🔗 <b>Текст кнопки:</b> {button_text}\n"
        f"🆔 ID сообщения в канале: {message_id if message_id else 'Не опубликовано'}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "edit_payment", F.from_user.id == ADMIN_ID)
async def start_edit_payment(callback: CallbackQuery, state: FSMContext):
    instructions = await get_payment_instructions()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    # Редактируем текущее сообщение, но добавим его в messages_to_delete перед редактированием
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    messages.append({"bot_msg_id": callback.message.message_id})
    await state.update_data(messages_to_delete=messages)
    
    await callback.message.edit_text(
        "✏️ Отредактируйте текст инструкций по оплате (кнопка \"✅ Я оплатил\" будет добавлена автоматически):\n\n"
        f"{instructions}",
        reply_markup=keyboard
    )
    await state.set_state(VacancyForm.edit_payment)
    await callback.answer()

@dp.callback_query(F.data == "edit_channel_instruction", F.from_user.id == ADMIN_ID)
async def start_edit_channel_instruction(callback: CallbackQuery, state: FSMContext):
    instruction, _, _ = await get_channel_instruction()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    # Редактируем текущее сообщение, но добавим его в messages_to_delete перед редактированием
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    messages.append({"bot_msg_id": callback.message.message_id})
    await state.update_data(messages_to_delete=messages)
    
    await callback.message.edit_text(
        "✏️ Отредактируйте текст инструкции для канала (кнопка будет добавлена автоматически):\n\n"
        f"{instruction}",
        reply_markup=keyboard
    )
    await state.set_state(VacancyForm.edit_channel_instruction)
    await callback.answer()

@dp.callback_query(F.data == "edit_channel_button", F.from_user.id == ADMIN_ID)
async def start_edit_channel_button(callback: CallbackQuery, state: FSMContext):
    _, button_text, _ = await get_channel_instruction()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    # Редактируем текущее сообщение, но добавим его в messages_to_delete перед редактированием
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    messages.append({"bot_msg_id": callback.message.message_id})
    await state.update_data(messages_to_delete=messages)
    
    await callback.message.edit_text(
        f"🔗 Отредактируйте текст для кнопки в инструкции канала:\n\n{button_text}",
        reply_markup=keyboard
    )
    await state.set_state(VacancyForm.edit_channel_button)
    await callback.answer()

@dp.message(VacancyForm.edit_payment, F.from_user.id == ADMIN_ID)
async def process_new_payment_instructions(message: Message, state: FSMContext):
    settings_collection.update_one(
        {"key": "payment_instructions"},
        {"$set": {"value": message.text}},
        upsert=True
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотреть", callback_data="view_payment")],
        [InlineKeyboardButton(text="✏️ Изменить еще раз", callback_data="edit_payment")],
        [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(
        message.chat.id,
        f"💸 <b>Инструкции обновлены:</b>\n\n{message.text}\n\nОни будут показаны пользователям при выборе платной публикации.",
        state,
        reply_markup=keyboard
    )
    await state.clear()

@dp.message(VacancyForm.edit_channel_instruction, F.from_user.id == ADMIN_ID)
async def process_new_channel_instruction(message: Message, state: FSMContext):
    settings_collection.update_one(
        {"key": "channel_instruction"},
        {"$set": {"value": message.text}},
        upsert=True
    )
    # Получаем данные состояния
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    vacancy_messages = data.get("vacancy_messages", [])
    welcome_id = data.get("welcome_message_id")

    # Удаляем все сообщения, кроме welcome_id
    messages_to_delete = messages.copy()
    messages_to_delete.append({"bot_msg_id": message.message_id})  # Добавляем сообщение пользователя
    await delete_messages(message.chat.id, messages_to_delete, welcome_id, vacancy_messages)

    # Очищаем состояние
    await state.clear()
    await state.update_data(messages_to_delete=[{"bot_msg_id": welcome_id}] if welcome_id else [])

    # Отображаем главное меню админа
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Платежные инструкции", callback_data="view_payment")],
        [InlineKeyboardButton(text="✏️ Изменить платежные инструкции", callback_data="edit_payment")],
        [InlineKeyboardButton(text="📝 Инструкция в канале", callback_data="view_channel_instruction")],
        [InlineKeyboardButton(text="📬 Опубликовать инструкцию в канале", callback_data="post_channel_instruction")],
        [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
        [InlineKeyboardButton(text="📋 Все вакансии", callback_data="admin_view_vacancies|0")]
    ])
    if welcome_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=welcome_id,
                text="🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение {welcome_id}: {e}")
            welcome_msg = await send_and_log(
                message.chat.id,
                "🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
                state,
                reply_markup=keyboard
            )
            await state.update_data(welcome_message_id=welcome_msg.message_id)
    else:
        welcome_msg = await send_and_log(
            message.chat.id,
            "🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
            state,
            reply_markup=keyboard
        )
        await state.update_data(welcome_message_id=welcome_msg.message_id)

@dp.message(VacancyForm.edit_channel_button, F.from_user.id == ADMIN_ID)
async def process_new_channel_button(message: Message, state: FSMContext):
    settings_collection.update_one(
        {"key": "channel_instruction"},
        {"$set": {"button_text": message.text}},
        upsert=True
    )
    # Получаем данные состояния
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    vacancy_messages = data.get("vacancy_messages", [])
    welcome_id = data.get("welcome_message_id")

    # Удаляем все сообщения, кроме welcome_id
    messages_to_delete = messages.copy()
    messages_to_delete.append({"bot_msg_id": message.message_id})  # Добавляем сообщение пользователя
    await delete_messages(message.chat.id, messages_to_delete, welcome_id, vacancy_messages)

    # Очищаем состояние
    await state.clear()
    await state.update_data(messages_to_delete=[{"bot_msg_id": welcome_id}] if welcome_id else [])

    # Отображаем главное меню админа
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Платежные инструкции", callback_data="view_payment")],
        [InlineKeyboardButton(text="✏️ Изменить платежные инструкции", callback_data="edit_payment")],
        [InlineKeyboardButton(text="📝 Инструкция в канале", callback_data="view_channel_instruction")],
        [InlineKeyboardButton(text="📬 Опубликовать инструкцию в канале", callback_data="post_channel_instruction")],
        [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
        [InlineKeyboardButton(text="📋 Все вакансии", callback_data="admin_view_vacancies|0")]
    ])
    if welcome_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=welcome_id,
                text="🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение {welcome_id}: {e}")
            welcome_msg = await send_and_log(
                message.chat.id,
                "🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
                state,
                reply_markup=keyboard
            )
            await state.update_data(welcome_message_id=welcome_msg.message_id)
    else:
        welcome_msg = await send_and_log(
            message.chat.id,
            "🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
            state,
            reply_markup=keyboard
        )
        await state.update_data(welcome_message_id=welcome_msg.message_id)

async def check_channel_message():
    _, _, message_id = await get_channel_instruction()
    if not message_id:
        logger.info("Сообщение не найдено в базе данных, требуется публикация нового сообщения.")
        return None  # Возвращаем None, если сообщения нет

    try:
        # Проверяем, существует ли канал и есть ли у бота права
        chat = await bot.get_chat(CHANNEL_ID)
        if chat.type not in ["channel", "supergroup"]:
            logger.error(f"CHANNEL_ID {CHANNEL_ID} не является каналом или супергруппой.")
            return None

        chat_member = await bot.get_chat_member(CHANNEL_ID, (await bot.get_me()).id)
        if chat_member.status not in ["administrator", "creator"]:
            logger.error("Бот не имеет прав администратора в канале. Требуются права для чтения, редактирования и закрепления сообщений.")
            return None

        # Проверяем, существует ли сообщение
        try:
            message = await bot.get_chat(CHANNEL_ID)  # Проверяем доступ к чату
            # Проверяем, закреплено ли сообщение
            if chat.pinned_message and chat.pinned_message.message_id == message_id:
                logger.info(f"Закреплённое сообщение {message_id} всё ещё существует в канале.")
                return message_id  # Сообщение существует и закреплено
            else:
                logger.warning(f"Сообщение {message_id} не является закреплённым в канале.")
                return None  # Сообщение не закреплено
        except Exception as e:
            logger.warning(f"Сообщение {message_id} не найдено в канале или недоступно: {e}")
            return None  # Сообщение недоступно
    except Exception as e:
        logger.warning(f"Ошибка при проверке канала {CHANNEL_ID}: {e}")
        return None

async def post_channel_instruction(auto=False, chat_id=None, state=None):
    instruction, button_text, message_id = await get_channel_instruction()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, url="https://t.me/rabota_minsk_bot")]
    ])
    try:
        # Проверяем, существует ли уже закреплённое сообщение
        existing_message_id = await check_channel_message()
        if existing_message_id:
            # Если сообщение существует и закреплено, редактируем его
            try:
                await bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=existing_message_id,
                    text=instruction,
                    reply_markup=keyboard
                )
                logger.info(f"{'Автоматически' if auto else ''} отредактировано сообщение с инструкцией в канале: {existing_message_id}")
                return existing_message_id
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение {existing_message_id}: {e}")
                # Если не удалось отредактировать, попробуем удалить и открепить
                try:
                    await bot.delete_message(CHANNEL_ID, existing_message_id)
                    logger.info(f"Удалено старое сообщение {existing_message_id} из канала")
                except Exception as e:
                    logger.warning(f"Не удалось удалить сообщение {existing_message_id}: {e}")
                try:
                    await bot.unpin_chat_message(CHANNEL_ID, existing_message_id)
                    logger.info(f"Откреплено старое сообщение {existing_message_id}")
                except Exception as e:
                    logger.warning(f"Не удалось открепить сообщение {existing_message_id}: {e}")

        # Очищаем message_id в базе, так как старое сообщение либо отредактировано, либо удалено
        settings_collection.update_one(
            {"key": "channel_instruction"},
            {"$set": {"message_id": None}},
            upsert=True
        )

        # Публикуем новое сообщение
        msg = await bot.send_message(CHANNEL_ID, instruction, reply_markup=keyboard)
        settings_collection.update_one(
            {"key": "channel_instruction"},
            {"$set": {"message_id": msg.message_id}},
            upsert=True
        )
        await bot.pin_chat_message(CHANNEL_ID, msg.message_id, disable_notification=True)
        logger.info(f"{'Автоматически' if auto else ''} опубликован и закреплён новый пост с инструкцией в канале: {msg.message_id}")
        
        # Отправляем уведомление админу только при ручном вызове
        if chat_id and state and not auto:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👀 Просмотреть", callback_data="view_channel_instruction")],
                [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="edit_channel_instruction")],
                [InlineKeyboardButton(text="🔗 Изменить кнопку", callback_data="edit_channel_button")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
            ])
            await send_and_log(
                chat_id,
                "✅ <b>Инструкция успешно опубликована/обновлена и закреплена в канале!</b>",
                state,
                reply_markup=keyboard
            )
        return msg.message_id
    except Exception as e:
        logger.error(f"Ошибка при {'авто' if auto else ''}публикации инструкции в канале: {e}")
        if chat_id and state and not auto:
            await send_and_log(
                chat_id,
                "❌ Ошибка при публикации/обновлении инструкции. Проверьте права бота в канале.",
                state,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
                ])
            )
        return None

@dp.callback_query(F.data == "post_channel_instruction", F.from_user.id == ADMIN_ID)
async def post_channel_instruction_manual(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    welcome_id = data.get("welcome_message_id")
    vacancy_messages = data.get("vacancy_messages", [])

    messages_to_delete = messages.copy()
    messages_to_delete.append({"bot_msg_id": callback.message.message_id})
    await delete_messages(callback.message.chat.id, messages_to_delete, welcome_id, vacancy_messages)
    await state.update_data(messages_to_delete=messages_to_delete)

    await post_channel_instruction(auto=False, chat_id=callback.message.chat.id, state=state)
    await callback.answer()

async def monitor_channel_instruction():
    while True:
        if not await check_channel_message():
            await post_channel_instruction(auto=True)
        await asyncio.sleep(3600)

@dp.callback_query(F.data == "start_form")
async def begin_form(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    welcome_id = data.get("welcome_message_id")
    messages = data.get("messages_to_delete", [])
    vacancy_messages = data.get("vacancy_messages", [])
    
    messages_to_delete = messages.copy()
    messages_to_delete.append({"bot_msg_id": callback.message.message_id})
    await delete_messages(callback.message.chat.id, messages_to_delete, welcome_id, vacancy_messages)
    await state.update_data(messages_to_delete=[{"bot_msg_id": welcome_id}] if welcome_id else [])
    
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await send_and_log(callback.message.chat.id, "📝 <b>Шаг 1/5:</b> Укажите название вакансии. Это будет заголовок поста по которому соискатель сможет быстро понять суть вакансии:", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.title)

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Начало обработки back_to_start для пользователя {callback.from_user.id}")
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    vacancy_messages = data.get("vacancy_messages", [])
    welcome_id = data.get("welcome_message_id")

    messages_to_delete = messages.copy()
    messages_to_delete.append({"bot_msg_id": callback.message.message_id})
    for msg in messages_to_delete:
        bot_msg_id = msg.get("bot_msg_id") if isinstance(msg, dict) else None
        user_msg_id = msg.get("user_msg_id") if isinstance(msg, dict) else None

        if bot_msg_id and bot_msg_id != welcome_id:
            try:
                await bot.delete_message(callback.message.chat.id, bot_msg_id)
                logger.info(f"Удалено сообщение {bot_msg_id} из чата {callback.message.chat.id}")
                if user_msg_id:
                    await bot.delete_message(callback.message.chat.id, user_msg_id)
                    logger.info(f"Удалено пользовательское сообщение {user_msg_id} из чата {callback.message.chat.id}")
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение {bot_msg_id}: {e}")
            finally:
                if msg in messages:
                    messages.remove(msg)

    vacancy_messages_to_delete = vacancy_messages.copy()
    for msg_id in vacancy_messages_to_delete:
        if msg_id != welcome_id:
            try:
                await bot.delete_message(callback.message.chat.id, msg_id)
                logger.info(f"Удалено сообщение вакансии {msg_id} из чата {callback.message.chat.id}")
                vacancy_messages.remove(msg_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение вакансии {msg_id}: {e}")

    await state.update_data(messages_to_delete=messages, vacancy_messages=vacancy_messages)
    
    if callback.from_user.id == ADMIN_ID:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Платежные инструкции", callback_data="view_payment")],
            [InlineKeyboardButton(text="✏️ Изменить платежные инструкции", callback_data="edit_payment")],
            [InlineKeyboardButton(text="📝 Инструкция в канале", callback_data="view_channel_instruction")],
            [InlineKeyboardButton(text="📬 Опубликовать инструкцию в канале", callback_data="post_channel_instruction")],
            [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
            [InlineKeyboardButton(text="📋 Все вакансии", callback_data="admin_view_vacancies|0")]
        ])
        if welcome_id:
            try:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=welcome_id,
                    text="🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение {welcome_id}: {e}")
                welcome_msg = await send_and_log(
                    callback.message.chat.id,
                    "🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
                    state,
                    reply_markup=keyboard
                )
                await state.update_data(welcome_message_id=welcome_msg.message_id)
        else:
            welcome_msg = await send_and_log(
                callback.message.chat.id,
                "🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:",
                state,
                reply_markup=keyboard
            )
            await state.update_data(welcome_message_id=welcome_msg.message_id)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
            [InlineKeyboardButton(text="📜 Мои вакансии", callback_data="view_my_vacancies|0")]
        ])
        if welcome_id:
            try:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=welcome_id,
                    text="🌟 <b>Вернулись в главное меню</b> 🌟\n\nЧто хотите сделать?",
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение {welcome_id}: {e}")
                welcome_msg = await send_and_log(
                    callback.message.chat.id,
                    "🌟 <b>Вернулись в главное меню</b> 🌟\n\nЧто хотите сделать?",
                    state,
                    reply_markup=keyboard
                )
                await state.update_data(welcome_message_id=welcome_msg.message_id)
        else:
            welcome_msg = await send_and_log(
                callback.message.chat.id,
                "🌟 <b>Вернулись в главное меню</b> 🌟\n\nЧто хотите сделать?",
                state,
                reply_markup=keyboard
            )
            await state.update_data(welcome_message_id=welcome_msg.message_id)
    
    await state.clear()
    logger.info(f"Завершена обработка back_to_start для пользователя {callback.from_user.id}")

@dp.message(VacancyForm.title)
async def process_title(message: Message, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        messages[-1]["user_msg_id"] = message.message_id
    await state.update_data(messages_to_delete=messages, title=message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_title")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(message.chat.id, "📝 <b>Шаг 2/5:</b> Укажите описание вакансии:", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.description)

@dp.callback_query(F.data == "back_to_title")
async def back_to_title(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        last_entry = messages.pop()
        try:
            await bot.delete_message(callback.message.chat.id, last_entry["bot_msg_id"])
            if "user_msg_id" in last_entry:
                await bot.delete_message(callback.message.chat.id, last_entry["user_msg_id"])
        except:
            pass
    await state.update_data(messages_to_delete=messages, description=None)
    
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await send_and_log(callback.message.chat.id, "📝 <b>Шаг 1/5:</b> Укажите название вакансии. Это будет заголовок поста по которому соискатель сможет быстро понять суть вакансии:", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.title)

@dp.message(VacancyForm.description)
async def process_description(message: Message, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        messages[-1]["user_msg_id"] = message.message_id
    await state.update_data(messages_to_delete=messages, description=message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_description")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(message.chat.id, "📝 <b>Шаг 3/5:</b> Укажите заработную плату:", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.salary)

@dp.callback_query(F.data == "back_to_description")
async def back_to_description(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        last_entry = messages.pop()
        try:
            await bot.delete_message(callback.message.chat.id, last_entry["bot_msg_id"])
            if "user_msg_id" in last_entry:
                await bot.delete_message(callback.message.chat.id, last_entry["user_msg_id"])
        except:
            pass
    await state.update_data(messages_to_delete=messages, salary=None)
    
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_title")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(callback.message.chat.id, "📝 <b>Шаг 2/5:</b> Укажите описание вакансии:", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.description)

@dp.message(VacancyForm.salary)
async def process_salary(message: Message, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        messages[-1]["user_msg_id"] = message.message_id
    await state.update_data(messages_to_delete=messages, salary=message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_salary")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(message.chat.id, "📝 <b>Шаг 4/5:</b> Укажите тип занятости (Например: полный рабочий день, подработка, удаленка, гибкий график, 2/2 и т.д):", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.employment)

@dp.callback_query(F.data == "back_to_salary")
async def back_to_salary(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        last_entry = messages.pop()
        try:
            await bot.delete_message(callback.message.chat.id, last_entry["bot_msg_id"])
            if "user_msg_id" in last_entry:
                await bot.delete_message(callback.message.chat.id, last_entry["user_msg_id"])
        except:
            pass
    await state.update_data(messages_to_delete=messages, employment=None)
    
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_description")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(callback.message.chat.id, "📝 <b>Шаг 3/5:</b> Укажите заработную плату:", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.salary)

@dp.message(VacancyForm.employment)
async def process_employment(message: Message, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        messages[-1]["user_msg_id"] = message.message_id
    await state.update_data(messages_to_delete=messages, employment=message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_employment")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(message.chat.id, "📝 <b>Шаг 5/5:</b> Укажите вид контактной связи с работодателем (Номер телефона или username в Telegram):", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.link)

@dp.callback_query(F.data == "back_to_employment")
async def back_to_employment(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        last_entry = messages.pop()
        try:
            await bot.delete_message(callback.message.chat.id, last_entry["bot_msg_id"])
            if "user_msg_id" in last_entry:
                await bot.delete_message(callback.message.chat.id, last_entry["user_msg_id"])
        except:
            pass
    await state.update_data(messages_to_delete=messages, link=None)
    
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_salary")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(callback.message.chat.id, "📝 <b>Шаг 4/5:</b> Укажите тип занятости (Например: полный рабочий день, подработка, удаленка, гибкий график, 2/2 и т.д):", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.employment)

@dp.message(VacancyForm.link)
async def process_link(message: Message, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        messages[-1]["user_msg_id"] = message.message_id
    await state.update_data(messages_to_delete=messages, link=message.text)
    
    review_text = (
        "📋 <b>Ваша вакансия:</b>\n\n"
        f"💼 <b>Название:</b> {data.get('title', 'Не указано')}\n"
        f"📄 <b>Описание:</b> {data.get('description', 'Не указано')}\n"
        f"💰 <b>Зарплата:</b> {data.get('salary', 'Не указано')}\n"
        f"🕒 <b>Тип занятости:</b> {data.get('employment', 'Не указано')}\n"
        f"☎️ <b>Контакт для связи:</b> {message.text}\n\n"
        "Проверьте данные перед отправкой:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_link"), InlineKeyboardButton(text="▶️ Далее", callback_data="proceed_to_priority")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(message.chat.id, review_text, state, reply_markup=keyboard)
    await state.set_state(VacancyForm.review)

@dp.callback_query(F.data == "back_to_link")
async def back_to_link(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        last_entry = messages.pop()
        try:
            await bot.delete_message(callback.message.chat.id, last_entry["bot_msg_id"])
            if "user_msg_id" in last_entry:
                await bot.delete_message(callback.message.chat.id, last_entry["user_msg_id"])
        except:
            pass
    await state.update_data(messages_to_delete=messages)
    
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_employment")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(callback.message.chat.id, "📝 <b>Шаг 5/5:</b> Укажите вид контактной связи с работодателем (Номер телефона или username в Telegram):", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.link)

@dp.callback_query(F.data == "proceed_to_priority")
async def proceed_to_priority(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    if messages:
        last_entry = messages.pop()
        try:
            await bot.delete_message(callback.message.chat.id, last_entry["bot_msg_id"])
        except:
            pass
    await state.update_data(messages_to_delete=messages)
    
    try:
        await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except:
        pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Вне очереди", callback_data="priority_paid"), InlineKeyboardButton(text="🕓 Очередь", callback_data="priority_free")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await send_and_log(callback.message.chat.id, "📤 <b>Выберите способ размещения:</b>\n\n🕔 <b>Очередь</b> - Бесплатная публикация вакансии в порядке живой очереди. Модерация может занимать до 12 часов.\n\n🚀 <b>Вне очереди</b> - Платное продвижение вакансии. Публикация происходит крайне быстро. Можно публиковать вакансию несколько раз в течении 24 часов.", state, reply_markup=keyboard)
    await state.set_state(VacancyForm.priority)

@dp.callback_query(VacancyForm.priority, F.data == "priority_free")
async def process_free_priority(callback: CallbackQuery, state: FSMContext):
    await state.update_data(priority="🕓 Ожидание очереди")
    await send_to_admin(callback, state)

@dp.callback_query(VacancyForm.priority, F.data == "priority_paid")
async def process_paid_priority(callback: CallbackQuery, state: FSMContext):
    await state.update_data(priority="🚀 Сразу в публикацию (оплачено вручную)")
    instructions = await get_payment_instructions()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="check_payment"), InlineKeyboardButton(text="❌ В очередь", callback_data="send_as_free")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    full_text = f"💸 <b>Оплата публикации:</b>\n\n{instructions}\n\nПосле оплаты нажмите \"✅ Я оплатил\":"
    await send_and_log(callback.message.chat.id, full_text, state, reply_markup=keyboard)
    await state.set_state(VacancyForm.payment_check)

@dp.callback_query(VacancyForm.payment_check, F.data == "check_payment")
async def check_payment(callback: CallbackQuery, state: FSMContext):
    await send_to_admin(callback, state)

@dp.callback_query(VacancyForm.payment_check, F.data == "send_as_free")
async def send_as_free(callback: CallbackQuery, state: FSMContext):
    await state.update_data(priority="🕓 Ожидание очереди")
    await send_to_admin(callback, state)

async def send_to_admin(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    admin_vacancy_text = (
        f"<b>{data.get('priority', 'Не указано')}</b>\n\n"
        f"<b>💼 Вакансия:</b> {data.get('title', 'Не указано')}\n"
        f"<b>💰 Зарплата:</b> {data.get('salary', 'Не указано')}\n"
        f"<b>📄 Описание:</b> {data.get('description', 'Не указано')}\n"
        f"<b>🕒 Тип занятости:</b> {data.get('employment', 'Не указано')}\n"
        f"<b>☎️ Контакт для связи:</b> {data.get('link', 'Не указано')}"
    )
    
    vacancy = {
        "user_id": callback.from_user.id,
        "username": callback.from_user.username,
        "title": data.get('title', 'Не указано'),
        "salary": data.get('salary', 'Не указано'),
        "description": data.get('description', 'Не указано'),
        "employment": data.get('employment', 'Не указано'),
        "link": data.get('link', 'Не указано'),
        "priority": data.get('priority', 'Не указано'),
        "status": "На модерации",
        "created_at": datetime.now(dt.UTC),
        "channel_message_id": None
    }
    vacancy_id = vacancies_collection.insert_one(vacancy).inserted_id
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve|{vacancy_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline|{vacancy_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_vacancy|{vacancy_id}")
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start"))

    await send_and_log(ADMIN_ID, f"📥 <b>Новая вакансия от @{callback.from_user.username or callback.from_user.id}:</b>\n\n{admin_vacancy_text}", state, is_vacancy=True, reply_markup=builder.as_markup())
    await callback.message.edit_reply_markup(reply_markup=None)
    
    data = await state.get_data()
    welcome_id = data.get("welcome_message_id")
    messages = data.get("messages_to_delete", [])
    vacancy_messages = data.get("vacancy_messages", [])
    await delete_messages(callback.message.chat.id, messages, welcome_id, vacancy_messages)
    await state.update_data(messages_to_delete=[{"bot_msg_id": welcome_id}] if welcome_id else [])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Новая вакансия", callback_data="start_form")],
        [InlineKeyboardButton(text="📜 Мои вакансии", callback_data="view_my_vacancies|0")]
    ])
    await send_and_log(callback.message.chat.id, "✅ <b>Ваша вакансия отправлена на модерацию!</b>", state, reply_markup=keyboard)
    await state.clear()

@dp.callback_query(F.data.startswith("approve"))
async def approve_vacancy(callback: CallbackQuery, state: FSMContext):
    vacancy_id = callback.data.split("|")[1]
    vacancy_data = vacancies_collection.find_one({"_id": ObjectId(vacancy_id)})
    
    if not vacancy_data:
        await send_and_log(
            callback.message.chat.id,
            "❌ Ошибка: вакансия не найдена.",
            state
        )
        return
    
    user_id = vacancy_data.get("user_id")
    channel_message_id = vacancy_data.get("channel_message_id")
    
    if not user_id:
        await send_and_log(
            callback.message.chat.id,
            "❌ Ошибка: пользователь не найден.",
            state
        )
        return
    
    channel_vacancy_text = (
        f"💼 <b>Вакансия:</b> {vacancy_data.get('title', 'Не указано')}\n"
        f"📄 <b>Описание:</b> {vacancy_data.get('description', 'Не указано')}\n"
        f"💰 <b>З/П:</b> {vacancy_data.get('salary', 'Не указано')}\n"
        f"🕒 <b>Тип занятости:</b> {vacancy_data.get('employment', 'Не указано')}\n"
        f"☎️ <b>Контакт для связи:</b> {vacancy_data.get('link', 'Не указано')}"
    )
    
    channel_msg = await bot.send_message(CHANNEL_ID, channel_vacancy_text)
    vacancies_collection.update_one(
        {"_id": ObjectId(vacancy_id)},
        {"$set": {"status": "Одобрена", "updated_at": datetime.now(dt.UTC), "channel_message_id": channel_msg.message_id}}
    )
    
    user_state = FSMContext(dp.storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Новая вакансия", callback_data="start_form")],
        [InlineKeyboardButton(text="📜 Мои вакансии", callback_data="view_my_vacancies|0")]
    ])
    await send_and_log(user_id, f"✅ <b>Ваша вакансия \"{vacancy_data.get('title')}\" одобрена и опубликована!</b>", user_state, reply_markup=keyboard)
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.callback_query(F.data.startswith("decline"))
async def decline_vacancy(callback: CallbackQuery, state: FSMContext):
    vacancy_id = callback.data.split("|")[1]
    vacancy_data = vacancies_collection.find_one({"_id": ObjectId(vacancy_id)})
    
    if not vacancy_data:
        await send_and_log(
            callback.message.chat.id,
            "❌ Ошибка: вакансия не найдена.",
            state
        )
        return
    
    user_id = vacancy_data.get("user_id")
    if not user_id:
        await send_and_log(
            callback.message.chat.id,
            "❌ Ошибка: пользователь не найден.",
            state
        )
        return
    
    vacancies_collection.update_one(
        {"_id": ObjectId(vacancy_id)},
        {"$set": {"status": "Отклонена", "updated_at": datetime.now(dt.UTC)}}
    )
    
    user_state = FSMContext(dp.storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Новая вакансия", callback_data="start_form")],
        [InlineKeyboardButton(text="📜 Мои вакансии", callback_data="view_my_vacancies|0")]
    ])
    await send_and_log(user_id, f"❌ <b>Ваша вакансия \"{vacancy_data.get('title')}\" отклонена.</b>", user_state, reply_markup=keyboard)
    await callback.message.edit_reply_markup(reply_markup=None)
    await send_and_log(
        callback.message.chat.id,
        "✅ Вакансия отклонена.",
        state
    )

@dp.callback_query(F.data.startswith("delete_vacancy"))
async def delete_vacancy(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ только для администратора.")
        return
    
    vacancy_id = callback.data.split("|")[1]
    vacancy_data = vacancies_collection.find_one({"_id": ObjectId(vacancy_id)})
    
    if not vacancy_data:
        await send_and_log(
            callback.message.chat.id,
            "❌ Ошибка: вакансия не найдена.",
            state
        )
        return
    
    user_id = vacancy_data.get("user_id")
    channel_message_id = vacancy_data.get("channel_message_id")
    
    if channel_message_id:
        try:
            await bot.delete_message(CHANNEL_ID, channel_message_id)
        except:
            pass
    
    if user_id:
        user_state = FSMContext(dp.storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Новая вакансия", callback_data="start_form")],
            [InlineKeyboardButton(text="📜 Мои вакансии", callback_data="view_my_vacancies|0")]
        ])
        await send_and_log(user_id, f"🗑 <b>Ваша вакансия \"{vacancy_data.get('title')}\" удалена администратором.</b>", user_state, reply_markup=keyboard)
    
    vacancies_collection.delete_one({"_id": ObjectId(vacancy_id)})
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await send_and_log(
        callback.message.chat.id,
        "🗑 Вакансия успешно удалена.",
        state
    )

async def main():
    asyncio.create_task(monitor_channel_instruction())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())