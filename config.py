# -*- coding: utf-8 -*-
import os

# Токен бота.
# 1) На GitHub Actions задаётся секретом BOT_TOKEN (переменная окружения).
# 2) Локально — берётся из файла local_token.txt (он не попадает в репозиторий).
def _read_local_token():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_token.txt")
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


BOT_TOKEN = os.environ.get("BOT_TOKEN", "") or _read_local_token()
