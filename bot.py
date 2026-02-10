import asyncio
import os
import json
import re
from urllib.parse import urlparse
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties


# =========================
# ENV
# =========================
BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_NAME = os.environ.get("SHEET_NAME", "yourtunes contest")
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]


# =========================
# Link validation
# =========================
ALLOWED_DOMAINS = {
    "yourtunes.net",
    "www.yourtunes.net",
}

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def extract_first_url(text: str):
    m = URL_RE.search(text or "")
    return m.group(0) if m else None


def is_allowed_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
        return host in ALLOWED_DOMAINS
    except Exception:
        return False


# =========================
# Google Sheets
# =========================
def add_to_sheet(liga: str, genre: str, username: str, link: str):
    creds_dict = json.loads(GOOGLE_CREDENTIALS)

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1

    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        liga,
        genre,
        username,
        link,
    ])


# =========================
# FSM
# =========================
class SubmitForm(StatesGroup):
    choose_league = State()
    choose_genre = State()
    wait_link = State()


# =========================
# Keyboards
# =========================
def kb_start():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подать трек", callback_data="submit_track")]
    ])


def kb_league():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ЛИГА ЖАНРОВ", callback_data="league:GENRES")],
        [InlineKeyboardButton(text="AI ЛИГА", callback_data="league:AI")]
    ])


def kb_genre():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Рэп", callback_data="genre:Рэп")],
        [InlineKeyboardButton(text="Рок", callback_data="genre:Рок")],
        [InlineKeyboardButton(text="Поп", callback_data="genre:Поп")],
        [InlineKeyboardButton(text="Электронная", callback_data="genre:Электронная")]
    ])


# =========================
# Texts (HTML)
# =========================
START_TEXT = (
    "<b>yourtunēs CONTEST</b>\n"
    "<i>Музыкальный онлайн конкурс.</i>\n"
    "Нажми кнопку, чтобы подать трек."
)

ASK_LINK_TEXT = (
    "Отправь мультссылку на релиз одним сообщением.\n\n"
    "⚠️ Внимание: принимаются только треки,\n"
    "официально выпущенные через сервис дистрибуции yourtunēs и мультиссылки на релиз, созданные в личном кабинете.\n\n"
    "Подробнее о том, как создать мультиссылку:\n"
    '<a href="https://yourtunes.net/news/kak-sdelat-multissylku-reliza-na-servise-yourtunes">FAQ</a>'
)

OK_TEXT = (
    "<b>✅ Заявка принята.</b>\n\n"
    "Релиз будет проверен на соответствие условиям конкурса. "
    "Результаты отбора будут объявлены 2 марта.\n\n"
    "Актуальную информацию о ходе конкурса читайте в канале @YOURTUNES1\n\n"
    "<i>Чтобы начать заново, напишите /start</i>"
)

NOT_OK_TEXT = (
    "⚠️ <b>Эта ссылка не подходит.</b>\n\n"
    "Принимаются только мультиссылки на релизы,\n"
    "созданные через личный кабинет yourtunēs.\n\n"
    "Подробнее о том, как её создать, читайте по ссылке: "
    '<a href="https://yourtunes.net/news/kak-sdelat-multissylku-reliza-na-servise-yourtunes">FAQ</a>\n\n'
    "<i>Чтобы начать заново, нажмите /start</i>"
)


# =========================
# Handlers
# =========================
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(START_TEXT, reply_markup=kb_start())


async def submit_track(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await state.set_state(SubmitForm.choose_league)
    await call.message.answer("Выбери лигу", reply_markup=kb_league())


async def choose_league(call: CallbackQuery, state: FSMContext):
    await call.answer()
    league = call.data.split(":")[1]

    if league == "GENRES":
        await state.update_data(league="ЛИГА ЖАНРОВ", genre=None)
        await state.set_state(SubmitForm.choose_genre)
        await call.message.answer("Выбери жанр", reply_markup=kb_genre())
    else:
        await state.update_data(league="AI ЛИГА", genre=None)
        await state.set_state(SubmitForm.wait_link)
        await call.message.answer(ASK_LINK_TEXT)


async def choose_genre(call: CallbackQuery, state: FSMContext):
    await call.answer()
    genre = call.data.split(":")[1]
    await state.update_data(genre=genre)
    await state.set_state(SubmitForm.wait_link)
    await call.message.answer(ASK_LINK_TEXT)


async def receive_link(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправь ссылку текстом одним сообщением.")
        return

    url = extract_first_url(message.text)
    if not url:
        await message.answer("Пришли ссылку одним сообщением (полный URL, начиная с http/https).")
        return

    if not is_allowed_url(url):
        await message.answer(NOT_OK_TEXT)
        return

    data = await state.get_data()
    league = data.get("league", "—")
    genre = data.get("genre") or "—"
    username = f"@{message.from_user.username}" if message.from_user.username else "—"

    try:
        add_to_sheet(league, genre, username, url)
        await message.answer(OK_TEXT)
    except Exception as e:
        await message.answer(f"Ошибка записи в таблицу. Сообщи администратору.\n\nТехнически: {e}")

    await state.clear()


# =========================
# Run
# =========================
async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(submit_track, F.data == "submit_track")
    dp.callback_query.register(choose_league, F.data.startswith("league:"), SubmitForm.choose_league)
    dp.callback_query.register(choose_genre, F.data.startswith("genre:"), SubmitForm.choose_genre)
    dp.message.register(receive_link, SubmitForm.wait_link)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
