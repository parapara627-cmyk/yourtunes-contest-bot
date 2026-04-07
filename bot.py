import asyncio
import os
import json
import re
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

CONTEST_CLOSED = os.environ.get("CONTEST_CLOSED", "true").lower() == "true"
CURRENT_ROUND = int(os.environ.get("CURRENT_ROUND", "1"))

CONTEST_CHANNEL = "@contest_by_yourtunes"
APPLICATIONS_SHEET = "Заявки"


# =========================
# Link extraction
# =========================
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def extract_first_url(text: str):
    m = URL_RE.search(text or "")
    return m.group(0) if m else None


# =========================
# Google Sheets
# =========================
def get_worksheet(sheet_title: str):
    creds_dict = json.loads(GOOGLE_CREDENTIALS)

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    client = gspread.authorize(creds)
    spreadsheet = client.open(SHEET_NAME)
    worksheet = spreadsheet.worksheet(sheet_title)
    return worksheet


def add_to_applications_sheet(liga: str, genre: str, user, link: str, round_number: int):
    sheet = get_worksheet(APPLICATIONS_SHEET)

    username = f"@{user.username}" if user.username else "—"
    full_name = user.full_name or "—"

    status = "submitted" if round_number == 1 else "submitted_r2"

    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),  # date
        liga,                                       # league
        genre,                                      # genre
        username,                                   # username
        link,                                       # link
        str(user.id),                               # user_id
        str(user.id),                               # chat_id
        full_name,                                  # full_name
        str(round_number),                          # round
        status,                                     # status
        "",                                         # comment
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
    "<i>Музыкальный онлайн-конкурс.</i>\n\n"
    "Приём треков открыт с 7 по 20 апреля.\n"
    "Результаты отбора будут объявлены 27 апреля.\n\n"
    f"Все обновления публикуются в канале {CONTEST_CHANNEL}.\n\n"
    "Нажми кнопку ниже, чтобы подать трек."
)

ASK_LINK_TEXT = (
    "Отправь мультиссылку на релиз одним сообщением.\n\n"
    "Важно:\n"
    "— принимаются только мультиссылки на релиз\n"
    "— все заявки проходят модерацию перед отбором\n\n"
    "Если ссылка не соответствует условиям конкурса, заявка не будет допущена."
)

OK_TEXT = (
    "<b>✅ Заявка принята.</b>\n\n"
    "Трек отправлен на модерацию.\n"
    "Результаты отбора будут опубликованы 27 апреля.\n\n"
    f"Следите за обновлениями в канале {CONTEST_CHANNEL}.\n\n"
    "<i>Чтобы начать заново, напишите /start</i>"
)

NOT_OK_TEXT = (
    "⚠️ <b>Не удалось распознать ссылку.</b>\n\n"
    "Пожалуйста, отправь мультиссылку на релиз одним сообщением.\n\n"
    "<i>Чтобы начать заново, нажми /start</i>"
)

CONTEST_CLOSED_TEXT = (
    "<b>Приём треков завершён.</b>\n\n"
    "Спасибо всем, кто подал заявки в yourtunēs CONTEST.\n\n"
    "Результаты отбора будут объявлены 27 апреля.\n"
    f"Актуальная информация публикуется в канале {CONTEST_CHANNEL}."
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

    if CONTEST_CLOSED:
        await call.message.answer(CONTEST_CLOSED_TEXT)
        return

    await state.set_state(SubmitForm.choose_league)
    await call.message.answer("Выбери лигу", reply_markup=kb_league())


async def choose_league(call: CallbackQuery, state: FSMContext):
    await call.answer()
    league_code = call.data.split(":")[1]

    if league_code == "GENRES":
        await state.update_data(league="ЛИГА ЖАНРОВ", genre="—")
        await state.set_state(SubmitForm.choose_genre)
        await call.message.answer("Выбери жанр", reply_markup=kb_genre())
    else:
        await state.update_data(league="AI ЛИГА", genre="—")
        await state.set_state(SubmitForm.wait_link)
        await call.message.answer(ASK_LINK_TEXT)


async def choose_genre(call: CallbackQuery, state: FSMContext):
    await call.answer()
    genre = call.data.split(":")[1]
    await state.update_data(genre=genre)
    await state.set_state(SubmitForm.wait_link)
    await call.message.answer(ASK_LINK_TEXT)


async def receive_link(message: Message, state: FSMContext):
    if CONTEST_CLOSED:
        await message.answer(CONTEST_CLOSED_TEXT)
        await state.clear()
        return

    if not message.text:
        await message.answer(NOT_OK_TEXT)
        return

    url = extract_first_url(message.text)
    if not url:
        await message.answer(NOT_OK_TEXT)
        return

    data = await state.get_data()
    league = data.get("league", "—")
    genre = data.get("genre", "—")

    try:
        add_to_applications_sheet(
            liga=league,
            genre=genre,
            user=message.from_user,
            link=url,
            round_number=CURRENT_ROUND,
        )
        await message.answer(OK_TEXT)
    except Exception as e:
        print(f"[ERROR] Failed to write application to sheet: {e}")
        await message.answer(
            "Не удалось записать заявку в таблицу. "
            "Попробуй ещё раз чуть позже или сообщи администратору."
        )

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
    dp.callback_query.register(
        choose_league,
        F.data.startswith("league:"),
        SubmitForm.choose_league,
    )
    dp.callback_query.register(
        choose_genre,
        F.data.startswith("genre:"),
        SubmitForm.choose_genre,
    )
    dp.message.register(receive_link, SubmitForm.wait_link)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
