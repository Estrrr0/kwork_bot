# -*- coding: utf-8 -*-
"""Одноразовый запуск монитора: вызывается GitHub Actions по расписанию.
Не использует aiogram — только requests (отправка через Telegram Bot API).
"""
import html
import json
import os
import sys
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import kwork
import responder

STATE_FILE = os.path.join(BASE, "state.json")
TOKEN = os.environ.get("BOT_TOKEN", "")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"chat_id": None, "categories": [], "seen": [], "sent_count": 0}


def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    resp = requests.post(url, data=data, timeout=30)
    resp.raise_for_status()


def main():
    st = load_state()
    chat_id = st.get("chat_id")
    cats = st.get("categories") or [None]

    found = []
    for cat in cats:
        try:
            found.extend(kwork.fetch_wants(cat))
        except Exception as e:
            print(f"[warn] загрузка кат {cat}: {e}")

    seen = set(st.get("seen", []))
    new_wants = []
    for w in found:
        wid = w.get("id")
        if wid and wid not in seen:
            seen.add(wid)
            new_wants.append(w)
    st["seen"] = list(seen)

    if new_wants and chat_id and TOKEN:
        for w in new_wants:
            link = f"https://kwork.ru/projects/{w.get('id')}"
            text = responder.want_to_text(w) + f"🔗 <a href='{link}'>Открыть заказ</a>"
            kb = {"inline_keyboard": [[{"text": "Открыть заказ на KWORK", "url": link}]]}
            try:
                send_message(chat_id, text, kb)
                time.sleep(1)
                resp_text = responder.build_response(w)
                send_message(chat_id, f"📝 <b>Готовый отклик:</b>\n\n<code>{html.escape(resp_text)}</code>")
            except Exception as e:
                print(f"[warn] отправка заказа {w.get('id')}: {e}")
            time.sleep(1)
        st["sent_count"] = st.get("sent_count", 0) + len(new_wants)

    save_state(st)
    print(f"ok: найдено={len(found)} новых={len(new_wants)} отправлено_всего={st['sent_count']}")


if __name__ == "__main__":
    main()
