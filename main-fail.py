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

# Настройка логирования для диагностики
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

API_TOKEN = "токен_бота"
ADMIN_ID = "айди_юзера"
CHANNEL_ID = "ник_канала"

# Подключение к MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["vacancy_bot"]
vacancies_collection = db["vacancies"]
settings_collection = db["settings"]

# Удаление старой коллекции vacancies при запуске
vacancies_collection.drop()
settings_collection.drop()
logger.info("Старая коллекция 'vacancies' удалена. Начинаем с чистой базы.")

# Инициализация инструкции по оплате в базе, если её нет
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

VACANCIES_PER_PAGE = 5

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

@dp.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Платежные инструкции", callback_data="view_payment")],
            [InlineKeyboardButton(text="✏️ Изменить инструкции", callback_data="edit_payment")],
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
        [InlineKeyboardButton(text="✏️ Изменить инструкции", callback_data="edit_payment")],
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
        await message.answer("Эта команда для пользователей. Используйте /admin.")
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
    await callback.message.edit_text(
        f"💸 <b>Текущие инструкции по оплате:</b>\n\n{instructions}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "edit_payment", F.from_user.id == ADMIN_ID)
async def start_edit_payment(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_start")]
    ])
    await callback.message.edit_text(
        "✏️ Введите новый текст инструкций по оплате (кнопка \"✅ Я оплатил\" будет добавлена автоматически):",
        reply_markup=keyboard
    )
    await state.set_state(VacancyForm.edit_payment)
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
    await message.answer(
        f"💸 <b>Инструкции обновлены:</b>\n\n{message.text}\n\nОни будут показаны пользователям при выборе платной публикации.",
        reply_markup=keyboard
    )
    await state.clear()

@dp.callback_query(F.data == "start_form")
async def begin_form(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    welcome_id = data.get("welcome_message_id")
    
    for msg in data.get("messages_to_delete", []):
        if msg["bot_msg_id"] != welcome_id:
            try:
                await bot.delete_message(callback.message.chat.id, msg["bot_msg_id"])
                if "user_msg_id" in msg:
                    await bot.delete_message(callback.message.chat.id, msg["user_msg_id"])
            except:
                pass
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
    
    # Удаляем только невакансионные сообщения
    for msg in messages[:]:
        if "bot_msg_id" in msg and msg["bot_msg_id"] != welcome_id and msg["bot_msg_id"] not in vacancy_messages:
            try:
                await bot.delete_message(callback.message.chat.id, msg["bot_msg_id"])
                logger.info(f"Удалено сообщение {msg['bot_msg_id']} из чата {callback.message.chat.id}")
                if "user_msg_id" in msg:
                    await bot.delete_message(callback.message.chat.id, msg["user_msg_id"])
                    logger.info(f"Удалено пользовательское сообщение {msg['user_msg_id']} из чата {callback.message.chat.id}")
                messages.remove(msg)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение {msg['bot_msg_id']}: {e}")
    
    await state.update_data(messages_to_delete=messages)
    
    if callback.from_user.id == ADMIN_ID:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Платежные инструкции", callback_data="view_payment")],
            [InlineKeyboardButton(text="✏️ Изменить инструкции", callback_data="edit_payment")],
            [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
            [InlineKeyboardButton(text="📋 Все вакансии", callback_data="admin_view_vacancies|0")]
        ])
        await send_and_log(callback.message.chat.id, "🌟 <b>Панель администратора</b> 🌟\n\nВыберите действие:", state, reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Создать вакансию", callback_data="start_form")],
            [InlineKeyboardButton(text="📜 Мои вакансии", callback_data="view_my_vacancies|0")]
        ])
        await send_and_log(callback.message.chat.id, "🌟 <b>Вернулись в главное меню</b> 🌟\n\nЧто хотите сделать?", state, reply_markup=keyboard)
    
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
    await send_and_log(message.chat.id, "📝 <b>Шаг 5/5:</b>  Укажите вид контактной связи с работодателем (Номер телефона или username в Telegram):", state, reply_markup=keyboard)
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
    for msg in data.get("messages_to_delete", []):
        if msg["bot_msg_id"] != welcome_id:
            try:
                await bot.delete_message(callback.message.chat.id, msg["bot_msg_id"])
                if "user_msg_id" in msg:
                    await bot.delete_message(callback.message.chat.id, msg["user_msg_id"])
            except:
                pass
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
        await callback.message.answer("❌ Ошибка: вакансия не найдена.")
        return
    
    user_id = vacancy_data.get("user_id")
    channel_message_id = vacancy_data.get("channel_message_id")
    
    if not user_id:
        await callback.message.answer("❌ Ошибка: пользователь не найден.")
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
        await callback.message.answer("❌ Ошибка: вакансия не найдена.")
        return
    
    user_id = vacancy_data.get("user_id")
    if not user_id:
        await callback.message.answer("❌ Ошибка: пользователь не найден.")
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
    await callback.message.answer("✅ Вакансия отклонена.")

@dp.callback_query(F.data.startswith("delete_vacancy"))
async def delete_vacancy(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ только для администратора.")
        return
    
    vacancy_id = callback.data.split("|")[1]
    vacancy_data = vacancies_collection.find_one({"_id": ObjectId(vacancy_id)})
    
    if not vacancy_data:
        await callback.message.answer("❌ Ошибка: вакансия не найдена.")
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
    await callback.message.answer("🗑 Вакансия успешно удалена.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())