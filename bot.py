# bot.py
BOT_TOKEN = "8293227144:AAHyO0mIOa_-D-_cPhBDyQMwp7ZjJMFX5ew"

import asyncio
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

# ---------- GOOGLE SHEETS ----------
def add_to_sheet(liga, genre, username, link):
    creds = Credentials.from_service_account_file(
        "credentials.json",
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    client = gspread.authorize(creds)
    sheet = client.open("yourtunes contest").sheet1
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        liga,
        genre,
        username,
        link
    ])

# ---------- FSM ----------
class SubmitForm(StatesGroup):
    choose_league = State()
    choose_genre = State()
    wait_link = State()

# ---------- Keyboards ----------
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

START_TEXT = (
    "yourtunēs CONTEST\n"
    "Онлайн музыкальный конкурс.\n"
    "Нажми кнопку, чтобы подать трек."
)

ASK_LINK_TEXT = (
    "Отправь ссылку на релиз одним сообщением.\n\n"
    "⚠️ Внимание: принимаются только треки,\n"
    "официально выпущенные через сервис дистрибуции yourtunēs."
)

# ---------- Handlers ----------
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

    data = await state.get_data()
    league = data.get("league", "—")
    genre = data.get("genre") or "—"
    username = f"@{message.from_user.username}" if message.from_user.username else "—"

    # записываем в Google Sheets
    add_to_sheet(league, genre, username, message.text)

    await message.answer("Заявка принята. Спасибо за участие в yourtunēs CONTEST.")
    await state.clear()

# ---------- Run ----------
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # команды
    dp.message.register(cmd_start, CommandStart())
    # кнопки
    dp.callback_query.register(submit_track, F.data == "submit_track")
    dp.callback_query.register(choose_league, F.data.startswith("league:"), SubmitForm.choose_league)
    dp.callback_query.register(choose_genre, F.data.startswith("genre:"), SubmitForm.choose_genre)
    # ссылка
    dp.message.register(receive_link, SubmitForm.wait_link, F.text.exists())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
