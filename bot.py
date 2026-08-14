# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# В облаке api.telegram.org доступен напрямую. IP-обход нужен только в сетях с фильтрацией:
_TG_API_IP = os.environ.get("TG_API_IP", "")
if _TG_API_IP:
    import socket

    _real_getaddrinfo = socket.getaddrinfo

    def _pinned_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if isinstance(host, str) and host in ("api.telegram.org",):
            host = _TG_API_IP
        return _real_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _pinned_getaddrinfo

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web

import kwork
import responder

from config import BOT_TOKEN

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "bot.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("kwork-bot")

dp = Dispatcher()

DEFAULT_STATE = {
    "chat_id": None,
    "monitoring": False,
    "categories": [],          # пусто = все
    "interval": 60,            # секунды
    "seen": [],                # id заказов, о которых уже сообщили
    "sent_count": 0,
}


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                st = json.load(f)
            for k, v in DEFAULT_STATE.items():
                st.setdefault(k, v)
            return st
        except Exception:
            pass
    return dict(DEFAULT_STATE)


def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


state = load_state()
stop_event = asyncio.Event()


def cmd_help():
    return (
        "🤖 <b>Kwork-монитор</b>\n\n"
        "Слежу за новыми заказами и сразу присылаю ссылку + готовый отклик.\n\n"
        "Команды:\n"
        "• /monitor — включить мониторинг\n"
        "• /monitor off — выключить\n"
        "• /setcats 37 79 38 — только эти категории (пусто = все)\n"
        "• /listcats — список категорий\n"
        "• /interval 120 — проверять каждые 120 сек\n"
        "• /test — прислать свежие заказы сейчас\n"
        "• /status — текущие настройки\n\n"
        "💡 Подстройте подпись и «о себе» в файле kwork_bot/responder.py."
    )


def category_list_text():
    lines = ["Категории KWORK:\n"]
    for c in responder.CATEGORIES:
        lines.append(f"{c['id']} — {c['name']}")
    return "\n".join(lines)


def cat_names(ids):
    if not ids:
        return "все"
    return ", ".join(responder.NAME_BY_ID.get(i, i) for i in ids)


@dp.message(CommandStart())
async def on_start(message: types.Message):
    state["chat_id"] = message.chat.id
    save_state(state)
    await message.answer(
        f"Привет, {message.from_user.first_name}!\n\n" + cmd_help()
    )


@dp.message(Command("help"))
async def on_help(message: types.Message):
    await message.answer(cmd_help())


@dp.message(Command("monitor"))
async def on_monitor(message: types.Message):
    state["chat_id"] = message.chat.id
    args = message.text.split()
    if len(args) > 1 and args[1].lower() == "off":
        state["monitoring"] = False
        stop_event.set()
        save_state(state)
        await message.answer("⏸ Мониторинг остановлен.")
        return
    state["monitoring"] = True
    stop_event.clear()
    save_state(state)
    await message.answer(
        f"✅ Мониторинг включён.\nКатегории: {cat_names(state['categories'])}\n"
        f"Интервал: {state['interval']} сек.\nНовые заказы будут приходить сюда."
    )


@dp.message(Command("status"))
async def on_status(message: types.Message):
    await message.answer(
        f"📊 <b>Статус</b>\n"
        f"Мониторинг: {'включён' if state['monitoring'] else 'выключен'}\n"
        f"Категории: {cat_names(state['categories'])}\n"
        f"Интервал: {state['interval']} сек\n"
        f"Отправлено заказов: {state['sent_count']}"
    )


@dp.message(Command("setcats"))
async def on_setcats(message: types.Message):
    args = message.text.split()[1:]
    ids = [a for a in args if a in responder.NAME_BY_ID]
    if args and not ids:
        await message.answer("Не нашёл такие ID. Смотрите список: /listcats")
        return
    state["categories"] = ids
    save_state(state)
    await message.answer(f"📂 Категории: {cat_names(ids)}")


@dp.message(Command("listcats"))
async def on_listcats(message: types.Message):
    text = category_list_text()
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


@dp.message(Command("interval"))
async def on_interval(message: types.Message):
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("Формат: /interval 120 (секунды, минимум 30)")
        return
    val = max(30, int(args[1]))
    state["interval"] = val
    save_state(state)
    await message.answer(f"⏱ Интервал обновлён: {val} сек.")


@dp.message(Command("test"))
async def on_test(message: types.Message):
    await message.answer("Проверяю KWORK, секунду…")
    try:
        wants = await asyncio.to_thread(kwork.fetch_wants, None)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")
        return
    if not wants:
        await message.answer("Заказов не найдено.")
        return
    await message.answer(f"Найдено свежих заказов: {len(wants)}. Пример:")

    for want in wants[:2]:
        await send_want(message.bot, want)


async def send_want(bot: Bot, want):
    if not state.get("chat_id"):
        log.warning("Нет chat_id — пользователь ещё не нажал /start")
        return
    wid = want.get("id")
    link = f"https://kwork.ru/projects/{wid}"
    text = responder.want_to_text(want) + f"🔗 <a href='{link}'>Открыть заказ</a>"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть заказ на KWORK", url=link)]]
    )
    await bot.send_message(state["chat_id"], text, reply_markup=kb)
    response = responder.build_response(want)
    await bot.send_message(
        state["chat_id"],
        f"📝 <b>Готовый отклик:</b>\n\n<code>{response}</code>",
    )


async def monitor_loop():
    log.info("Мониторинг-цикл запущен")
    while True:
        if not state.get("monitoring") or stop_event.is_set():
            await asyncio.sleep(2)
            continue
        cats = state["categories"] or [None]
        found = []
        for cat in cats:
            try:
                wants = await asyncio.to_thread(kwork.fetch_wants, cat)
                found.extend(wants)
            except Exception as e:
                log.warning("Ошибка загрузки кат %s: %s", cat, e)

        seen_set = set(state["seen"])
        new_wants = []
        for w in found:
            wid = w.get("id")
            if wid and wid not in seen_set:
                seen_set.add(wid)
                new_wants.append(w)
        state["seen"] = list(seen_set)
        if new_wants:
            state["sent_count"] += len(new_wants)
            save_state(state)
            for w in new_wants:
                try:
                    await send_want(dp.bot, w)
                except Exception as e:
                    log.warning("Не удалось отправить заказ %s: %s", w.get("id"), e)
        await asyncio.sleep(state.get("interval", 60))


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp.bot = bot
    task = asyncio.create_task(monitor_loop())

    # Мини-веб-сервер: держит сервис «живым» на бесплатных хостингах (health-check + ping)
    app = web.Application()

    async def health(_request):
        return web.Response(text="ok")

    app.router.add_get("/", health)
    port = int(os.environ.get("PORT", 8000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
