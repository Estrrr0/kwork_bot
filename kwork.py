# -*- coding: utf-8 -*-
import json
import re
import time

import requests

BASE_URL = "https://kwork.ru/projects"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


def _extract_state(text):
    marker = "window.stateData="
    i = text.find(marker)
    if i < 0:
        raise ValueError("stateData не найден")
    start = text.find("{", i + len(marker))
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:j + 1])
    raise ValueError("JSON не закрыт")


def _request(url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            resp = _SESSION.get(url, timeout=25)
            if resp.status_code == 200:
                return resp.text
            last = f"HTTP {resp.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Не удалось загрузить {url}: {last}")


def fetch_wants(category_id=None):
    url = BASE_URL if category_id is None else f"{BASE_URL}?c={category_id}"
    text = _request(url)
    data = _extract_state(text)
    arr = data.get("wantsListData", {}).get("pagination", {}).get("data", [])
    return arr
