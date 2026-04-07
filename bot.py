import asyncio
import os
import json
import re
from datetime import datetime
from urllib.parse import urlparse

import gspread
from google.oauth2.service_account import Credentials

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
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
FINAL_CHAT_LINK = os.environ.get("FINAL_CHAT_LINK", "")

ADMIN_IDS_RAW = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = {
    int(x.strip())
    for x in ADMIN_IDS_RAW.split(",")
    if x.strip().isdigit()
}

APPLICATIONS_SHEET = "Заявки"
ROUND2_INVITES_SHEET = "round2_invites"
ROUND2_APPLICATIONS_SHEET = "Заявки_2"
ROUND3_INVITES_SHEET = "round3_invites"


# =========================
# Link validation
# =========================
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

ROUND1_ALLOWED_DOMAINS = {
    "yourtunes.net",
    "www.yourtunes.net",
    "band.link",
    "www.band.link",
    "bandlink.to",
    "www.bandlink.to",
    "lnk.to",
    "www.lnk.to",
    "zvonko.link",
    "www.zvonko.link",
}

ROUND2_ALLOWED_DOMAINS = {
    "yourtunes.net",
    "www.yourtunes.net",
}


def extract_first_url(text: str):
    m = URL_RE.search(text or "")
    return m.group(0) if m else None


def get_host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def is_allowed_url_for_round(url: str, round_number: int) -> bool:
    host = get_host(url)
    if not host:
        return False

    if round_number == 2:
        return host in ROUND2_ALLOWED_DOMAINS

    return host in ROUND1_ALLOWED_DOMAINS


# =========================
# Google Sheets
# =========================
def get_gspread_client():
    creds_dict = json.loads(GOOGLE_CREDENTIALS)

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    return gspread.authorize(creds)


def get_worksheet(sheet_title: str):
    client = get_gspread_client()
    spreadsheet = client.open(SHEET_NAME)
    return spreadsheet.worksheet(sheet_title)


def add_application_row(
    sheet_title: str,
    liga: str,
    genre: str,
    user,
    link: str,
    round_number: int,
):
    sheet = get_worksheet(sheet_title)

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


def get_application_sheet_for_round(round_number: int) -> str:
    if round_number == 2:
        return ROUND2_APPLICATIONS_SHEET
    return APPLICATIONS_SHEET


def find_invite_by_user_id(sheet_title: str, user_id: int):
    """
    Универсально для round2_invites и round3_invites:
    date | league | genre | username | link | user_id | chat_id | full_name | round | status | comment | notify_status | notify_error
    """
    sheet = get_worksheet(sheet_title)
    rows = sheet.get_all_values()

    if len(rows) < 2:
        return None

    for row_index, row in enumerate(rows[1:], start=2):
        row_user_id = row[5].strip() if len(row) > 5 else ""
        if row_user_id == str(user_id):
            return {
                "row_index": row_index,
                "date": row[0] if len(row) > 0 else "",
                "league": row[1] if len(row) > 1 else "—",
                "genre": row[2] if len(row) > 2 else "—",
                "username": row[3] if len(row) > 3 else "",
                "link": row[4] if len(row) > 4 else "",
                "user_id": row[5] if len(row) > 5 else "",
                "chat_id": row[6] if len(row) > 6 else "",
                "full_name": row[7] if len(row) > 7 else "",
                "round": row[8] if len(row) > 8 else "",
                "status": row[9] if len(row) > 9 else "",
                "comment": row[10] if len(row) > 10 else "",
                "notify_status": row[11] if len(row) > 11 else "",
                "notify_error": row[12] if len(row) > 12 else "",
            }

    return None


def get_invite_rows(sheet_title: str):
    sheet = get_worksheet(sheet_title)
    rows = sheet.get_all_values()

    if len(rows) < 2:
        return []

    result = []
    for row_index, row in enumerate(rows[1:], start=2):
        result.append({
            "row_index": row_index,
            "date": row[0].strip() if len(row) > 0 else "",
            "league": row[1].strip() if len(row) > 1 else "—",
            "genre": row[2].strip() if len(row) > 2 else "—",
            "username": row[3].strip() if len(row) > 3 else "",
            "link": row[4].strip() if len(row) > 4 else "",
            "user_id": row[5].strip() if len(row) > 5 else "",
            "chat_id": row[6].strip() if len(row) > 6 else "",
            "full_name": row[7].strip() if len(row) > 7 else "",
            "round": row[8].strip() if len(row) > 8 else "",
            "status": row[9].strip() if len(row) > 9 else "",
            "comment": row[10].strip() if len(row) > 10 else "",
            "notify_status": row[11].strip() if len(row) > 11 else "",
            "notify_error": row[12].strip() if len(row) > 12 else "",
        })

    return result


def update_notify_result(sheet_title: str, row_index: int, status: str, error_text: str = ""):
    """
    notify_status = колонка L (12)
    notify_error  = колонка M (13)
    """
    sheet = get_worksheet(sheet_title)
    sheet.update_cell(row_index, 12, status)
    sheet.update_cell(row_index, 13, error_text)


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
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подать трек", callback_data="submit_track")]
        ]
    )


def kb_league():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ЛИГА ЖАНРОВ", callback_data="league:GENRES")],
            [InlineKeyboardButton(text="AI ЛИГА", callback_data="league:AI")],
        ]
    )


def kb_genre():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Рэп", callback_data="genre:Рэп")],
            [InlineKeyboardButton(text="Рок", callback_data="genre:Рок")],
            [InlineKeyboardButton(text="Поп", callback_data="genre:Поп")],
            [InlineKeyboardButton(text="Электронная", callback_data="genre:Электронная")],
        ]
    )


def kb_round2():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подать трек во 2-й раунд", callback_data="submit_round2")]
        ]
    )


def kb_final_chat():
    final_url = FINAL_CHAT_LINK.strip()

    if not final_url:
        raise ValueError("FINAL_CHAT_LINK is empty")

    if not final_url.startswith("https://t.me/"):
        raise ValueError("FINAL_CHAT_LINK must start with https://t.me/")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Вступить в чат финалистов",
                url=final_url
            )]
        ]
    )


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

ROUND2_ASK_LINK_TEXT = (
    "Для участия во втором этапе отправь мультиссылку на релиз, "
    "созданную в личном кабинете yourtunēs.\n\n"
    "Подробнее о том, как создать мультиссылку, читайте "
    '<a href="https://yourtunes.net/news/kak-sdelat-multissylku-reliza-na-servise-yourtunes">здесь</a>.'
)

OK_TEXT = (
    "<b>✅ Заявка принята.</b>\n\n"
    "Трек отправлен на модерацию.\n"
    "Результаты отбора будут опубликованы 27 апреля.\n\n"
    f"Следите за обновлениями в канале {CONTEST_CHANNEL}."
)

ROUND2_OK_TEXT = (
    "<b>✅ Заявка принята.</b>\n\n"
    "Трек отправлен на модерацию.\n"
    "Результаты второго этапа будут опубликованы 13 мая.\n\n"
    f"Следите за обновлениями в канале {CONTEST_CHANNEL}."
)

NOT_OK_TEXT = (
    "⚠️ <b>Эта ссылка не подходит.</b>\n\n"
    "Для участия нужно отправить мультиссылку на релиз.\n\n"
    "Если ты отправил ссылку на отдельную площадку или другой тип страницы, заявка не будет принята.\n\n"
    "<i>Попробуй ещё раз или нажми /start</i>"
)

ROUND2_NOT_OK_TEXT = (
    "⚠️ <b>Эта ссылка не подходит.</b>\n\n"
    "Для второго этапа нужно отправить мультиссылку на релиз, "
    "созданную в личном кабинете yourtunēs.\n\n"
    "Подробнее о том, как создать мультиссылку, читайте "
    '<a href="https://yourtunes.net/news/kak-sdelat-multissylku-reliza-na-servise-yourtunes">здесь</a>.'
)

CONTEST_CLOSED_TEXT = (
    "<b>Приём треков завершён.</b>\n\n"
    "Спасибо всем, кто подал заявки в yourtunēs CONTEST.\n\n"
    "Результаты отбора будут объявлены 27 апреля.\n"
    f"Актуальная информация публикуется в канале {CONTEST_CHANNEL}."
)

ROUND2_TEXT = (
    "<b>Поздравляем! Ты прошёл во второй этап yourtunēs CONTEST.</b>\n\n"
    "Второй этап — конкурсный.\n"
    f'Тема раунда уже опубликована в канале <a href="https://t.me/contest_by_yourtunes">{CONTEST_CHANNEL}</a>.\n\n'
    "У тебя есть 8 дней, чтобы записать и выпустить новый трек через сервис дистрибуции "
    '<a href="https://yourtunes.net">yourtunēs</a>.\n\n'
    "<b>Важно!</b> Трек должен выйти на стриминговых площадках до 6 мая включительно."
)

ROUND2_DENIED_TEXT = (
    "Доступ ко второму раунду для этого аккаунта не найден.\n\n"
    "Если ты уверен, что прошёл дальше, напиши организаторам конкурса."
)

FINAL_TEXT = (
    "<b>Поздравляем! Ты прошёл в финал yourtunēs CONTEST.</b>\n\n"
    "Вся информация будет публиковаться в специальном чате для финалистов.\n\n"
    "Нажми кнопку ниже, чтобы вступить в чат."
)

ADMIN_ONLY_TEXT = "Эта команда доступна только администратору."

ROUND2_SEND_DONE_TEMPLATE = (
    "Рассылка второго раунда завершена.\n\n"
    "Отправлено: {sent}\n"
    "Ошибок: {failed}\n"
    "Пропущено (уже отправляли): {skipped}"
)

FINAL_SEND_DONE_TEMPLATE = (
    "Рассылка финалистам завершена.\n\n"
    "Отправлено: {sent}\n"
    "Ошибок: {failed}\n"
    "Пропущено (уже отправляли): {skipped}"
)


# =========================
# Helpers
# =========================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


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

    await state.update_data(round=1)
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


async def submit_round2(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()

    invite = find_invite_by_user_id(ROUND2_INVITES_SHEET, call.from_user.id)
    if not invite:
        await call.message.answer(ROUND2_DENIED_TEXT)
        return

    await state.update_data(
        round=2,
        league=invite["league"] or "—",
        genre=invite["genre"] or "—",
    )
    await state.set_state(SubmitForm.wait_link)
    await call.message.answer(ROUND2_ASK_LINK_TEXT)


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
    round_number = int(data.get("round", CURRENT_ROUND))

    if not is_allowed_url_for_round(url, round_number):
        if round_number == 2:
            await message.answer(ROUND2_NOT_OK_TEXT)
        else:
            await message.answer(NOT_OK_TEXT)
        return

    target_sheet = get_application_sheet_for_round(round_number)

    try:
        add_application_row(
            sheet_title=target_sheet,
            liga=league,
            genre=genre,
            user=message.from_user,
            link=url,
            round_number=round_number,
        )

        if round_number == 2:
            await message.answer(ROUND2_OK_TEXT)
        else:
            await message.answer(OK_TEXT)

    except Exception as e:
        print(f"[ERROR] Failed to write application to sheet '{target_sheet}': {e}")
        await message.answer(
            "Не удалось записать заявку в таблицу. "
            "Попробуй ещё раз чуть позже или сообщи администратору."
        )

    await state.clear()


async def send_round2(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(ADMIN_ONLY_TEXT)
        return

    try:
        invites = get_invite_rows(ROUND2_INVITES_SHEET)
    except Exception as e:
        await message.answer(f"Не удалось прочитать лист {ROUND2_INVITES_SHEET}: {e}")
        return

    if not invites:
        await message.answer("Лист round2_invites пуст.")
        return

    sent = 0
    failed = 0
    skipped = 0

    for row in invites:
        row_index = row["row_index"]
        chat_id_raw = row["chat_id"]
        notify_status = row["notify_status"]

        if notify_status:
            skipped += 1
            continue

        if not chat_id_raw.isdigit():
            failed += 1
            update_notify_result(
                sheet_title=ROUND2_INVITES_SHEET,
                row_index=row_index,
                status="failed",
                error_text="invalid chat_id",
            )
            continue

        chat_id = int(chat_id_raw)

        try:
            await message.bot.send_message(
                chat_id=chat_id,
                text=ROUND2_TEXT,
                reply_markup=kb_round2(),
            )
            update_notify_result(
                sheet_title=ROUND2_INVITES_SHEET,
                row_index=row_index,
                status="sent",
                error_text="",
            )
            sent += 1
        except Exception as e:
            update_notify_result(
                sheet_title=ROUND2_INVITES_SHEET,
                row_index=row_index,
                status="failed",
                error_text=str(e)[:500],
            )
            failed += 1

    await message.answer(
        ROUND2_SEND_DONE_TEMPLATE.format(
            sent=sent,
            failed=failed,
            skipped=skipped,
        )
    )


async def send_final(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(ADMIN_ONLY_TEXT)
        return

    try:
        invites = get_invite_rows(ROUND3_INVITES_SHEET)
    except Exception as e:
        await message.answer(f"Не удалось прочитать лист {ROUND3_INVITES_SHEET}: {e}")
        return

    if not invites:
        await message.answer("Лист round3_invites пуст.")
        return

    sent = 0
    failed = 0
    skipped = 0

    for row in invites:
        row_index = row["row_index"]
        chat_id_raw = row["chat_id"]
        notify_status = row["notify_status"]

        if notify_status:
            skipped += 1
            continue

        if not chat_id_raw.isdigit():
            failed += 1
            update_notify_result(
                sheet_title=ROUND3_INVITES_SHEET,
                row_index=row_index,
                status="failed",
                error_text="invalid chat_id",
            )
            continue

        chat_id = int(chat_id_raw)

        try:
            await message.bot.send_message(
                chat_id=chat_id,
                text=FINAL_TEXT,
                reply_markup=kb_final_chat(),
            )
            update_notify_result(
                sheet_title=ROUND3_INVITES_SHEET,
                row_index=row_index,
                status="sent",
                error_text="",
            )
            sent += 1
        except Exception as e:
            update_notify_result(
                sheet_title=ROUND3_INVITES_SHEET,
                row_index=row_index,
                status="failed",
                error_text=str(e)[:500],
            )
            failed += 1

    await message.answer(
        FINAL_SEND_DONE_TEMPLATE.format(
            sent=sent,
            failed=failed,
            skipped=skipped,
        )
    )


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
    dp.message.register(send_round2, Command("send_round2"))
    dp.message.register(send_final, Command("send_final"))

    dp.callback_query.register(submit_track, F.data == "submit_track")
    dp.callback_query.register(submit_round2, F.data == "submit_round2")
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
