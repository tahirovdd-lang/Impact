import asyncio
import logging
import json
import os
import time

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton
)

logging.basicConfig(level=logging.INFO)

# ====== НАСТРОЙКИ ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден. Добавь переменную окружения BOT_TOKEN.")

# ✅ IMPACT (все данные переименованы)
BOT_USERNAME = os.getenv("BOT_USERNAME", "impact_webapp_bot").replace("@", "").strip().lower()
ADMIN_ID = int(os.getenv("ADMIN_ID", "6013591658"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@IMPACT_PRINT").strip()


def normalize_webapp_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url

    # ✅ нормализация GitHub Pages ссылок
    if "github.io" in url:
        # отделяем query
        if "?" in url:
            base, q = url.split("?", 1)
            q = "?" + q
        else:
            base, q = url, ""

        base = base.rstrip("/")

        # если нет .html — добавим /index.html
        if not base.lower().endswith(".html"):
            base = base + "/index.html"

        return base + q

    return url


# ✅ FIX: GitHub Pages чувствителен к регистру пути.
# Было: .../impact/index.html (часто 404)
# Стало: .../Impact/ (часто правильный путь)
DEFAULT_WEBAPP = "https://tahirovdd-lang.github.io/Impact/?v=1"

# ✅ IMPACT WebApp (можно переопределить переменной окружения WEBAPP_URL)
WEBAPP_URL = normalize_webapp_url(os.getenv("WEBAPP_URL", DEFAULT_WEBAPP))

logging.info(f"WEBAPP_URL (effective) = {WEBAPP_URL}")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ====== АНТИ-ДУБЛЬ START ======
_last_start: dict[int, float] = {}


def allow_start(user_id: int, ttl: float = 2.0) -> bool:
    now = time.time()
    prev = _last_start.get(user_id, 0.0)
    if now - prev < ttl:
        return False
    _last_start[user_id] = now
    return True


# ====== КНОПКИ ======
BTN_OPEN_MULTI = "IMPACT • Открыть • Ochish • Open"


def kb_webapp_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_OPEN_MULTI, web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True
    )


def kb_channel_url() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BTN_OPEN_MULTI, url=WEBAPP_URL)]]
    )


# ====== ТЕКСТ ======
def welcome_text() -> str:
    return (
        "🇷🇺 Добро пожаловать в <b>IMPACT</b> 🖨️📣\n"
        "Выберите услугу и оформите заявку — нажмите «Открыть» ниже.\n\n"
        "🇺🇿 <b>IMPACT</b> 🖨️📣 ga xush kelibsiz!\n"
        "Xizmatni tanlang va ariza yuboring — pastdagi «Ochish» tugmasini bosing.\n\n"
        "🇬🇧 Welcome to <b>IMPACT</b> 🖨️📣\n"
        "Choose a service and send a request — tap “Open” below."
    )


@dp.message(CommandStart())
async def start(message: types.Message):
    if not allow_start(message.from_user.id):
        return
    await message.answer(welcome_text(), reply_markup=kb_webapp_reply())


@dp.message(Command("startapp"))
async def startapp(message: types.Message):
    if not allow_start(message.from_user.id):
        return
    await message.answer(welcome_text(), reply_markup=kb_webapp_reply())


@dp.message(Command("debug_url"))
async def debug_url(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"WEBAPP_URL = <code>{WEBAPP_URL}</code>")


@dp.message(Command("post_shop"))
async def post_shop(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔️ Нет доступа.")

    text = (
        "🇷🇺 <b>IMPACT</b> 🖨️📣\nНажмите кнопку ниже, чтобы открыть каталог услуг.\n\n"
        "🇺🇿 <b>IMPACT</b> 🖨️📣\nPastdagi tugma orqali xizmatlar katalogini oching.\n\n"
        "🇬🇧 <b>IMPACT</b> 🖨️📣\nTap the button below to open the services catalog."
    )

    try:
        sent = await bot.send_message(CHANNEL_ID, text, reply_markup=kb_channel_url())
        try:
            await bot.pin_chat_message(CHANNEL_ID, sent.message_id, disable_notification=True)
            await message.answer("✅ Пост отправлен в канал и закреплён.")
        except Exception:
            await message.answer(
                "✅ Пост отправлен в канал.\n"
                "⚠️ Не удалось закрепить — дай боту право «Закреплять сообщения»."
            )
    except Exception as e:
        logging.exception("CHANNEL POST ERROR")
        await message.answer(f"❌ Ошибка отправки в канал: <code>{e}</code>")


# ====== ВСПОМОГАТЕЛЬНЫЕ ======
def fmt_sum(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        n = 0
    return f"{n:,}".replace(",", " ")


def tg_label(u: types.User) -> str:
    return f"@{u.username}" if u.username else u.full_name


def clean_str(v) -> str:
    return ("" if v is None else str(v)).strip()


def safe_int(v, default=0) -> int:
    try:
        if v is None or isinstance(v, bool):
            return default
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).strip().replace(" ", "")
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def build_order_lines(data: dict) -> list[str]:
    raw_items = data.get("items")
    lines: list[str] = []

    if isinstance(raw_items, list):
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            name = clean_str(it.get("name")) or clean_str(it.get("id")) or "—"
            qty = safe_int(it.get("qty"), 0)
            if qty <= 0:
                continue
            price = safe_int(it.get("price"), 0)
            if price > 0:
                lines.append(f"• {name} × {qty} = {fmt_sum(price * qty)} сум")
            else:
                lines.append(f"• {name} × {qty}")

    return lines


def is_consultation_payload(data: dict) -> bool:
    action = clean_str(data.get("action")).lower()
    text = clean_str(data.get("text"))
    items = data.get("items")

    if action in ("consultation", "consult", "message", "support"):
        return True
    # ✅ даже если action сломался — если есть text и нет items → это консультация
    if text and not items:
        return True
    return False


def is_order_payload(data: dict) -> bool:
    action = clean_str(data.get("action")).lower()
    items = data.get("items")

    if action == "order":
        return True
    # ✅ если action сломался — но есть items списком → это заказ
    if isinstance(items, list) and len(items) > 0:
        return True
    return False


# ====== ДАННЫЕ ИЗ WEBAPP ======
@dp.message(F.web_app_data)
async def webapp_data(message: types.Message):
    raw = message.web_app_data.data

    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    # ✅ 1) КОНСУЛЬТАЦИЯ (строго текст клиента + ник)
    if is_consultation_payload(data):
        text = clean_str(data.get("text"))
        if not text:
            return await message.answer("⚠️ Пустое сообщение. Напишите текст обращения.")

        admin_text = (
            "💬 <b>НОВАЯ КОНСУЛЬТАЦИЯ IMPACT</b>\n\n"
            f"📝 <b>Текст:</b> {text}\n\n"
            f"👤 <b>Telegram:</b> {tg_label(message.from_user)}"
        )
        await bot.send_message(ADMIN_ID, admin_text)
        return await message.answer("✅ <b>Сообщение отправлено!</b>\nМы скоро ответим.")

    # ✅ 2) ЗАКАЗ / ЗАЯВКА
    if is_order_payload(data):
        lines = build_order_lines(data)
        if not lines:
            return await message.answer("⚠️ Корзина пустая. Добавьте услуги и повторите.")

        total_str = clean_str(data.get("total")) or clean_str(data.get("total_items")) or "0"
        payment = clean_str(data.get("payment")) or "—"
        order_type = clean_str(data.get("type")) or clean_str(data.get("order_type")) or "—"
        address = clean_str(data.get("address")) or clean_str(data.get("branch_address")) or "—"
        comment = clean_str(data.get("comment"))
        order_id = clean_str(data.get("order_id")) or "—"

        admin_text = (
            "🚨 <b>НОВАЯ ЗАЯВКА IMPACT</b>\n"
            f"🆔 <b>{order_id}</b>\n\n"
            + "\n".join(lines) +
            f"\n\n💰 <b>Сумма:</b> {total_str} сум"
            f"\n🚚 <b>Тип:</b> {order_type}"
            f"\n💳 <b>Оплата:</b> {payment}"
            f"\n📍 <b>Адрес:</b> {address}"
            f"\n👤 <b>Telegram:</b> {tg_label(message.from_user)}"
        )
        if comment:
            admin_text += f"\n💬 <b>Комментарий:</b> {comment}"

        await bot.send_message(ADMIN_ID, admin_text)
        return await message.answer("✅ <b>Ваша заявка принята!</b>\n🙏 Спасибо! Мы скоро свяжемся с вами.")

    # ✅ 3) если пришло непонятно что — не шлём админу мусор
    await message.answer("⚠️ Данные не распознаны. Откройте каталог и попробуйте снова.")


# ====== ЗАПУСК ======
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
