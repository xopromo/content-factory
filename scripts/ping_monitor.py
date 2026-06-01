#!/usr/bin/env python3
import time
import urllib.request
import urllib.error
import sys

URL = "https://voice-bot-ohfb.onrender.com/"
FAIL_LIMIT = 3
fail_count = 0

print("Starting ping monitor for Render bot...")

while True:
    try:
        req = urllib.request.Request(URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        status = 999  # Сетевая ошибка или тайм-аут

    if status in (200, 404):
        # Бот жив, сбрасываем счетчик ошибок
        fail_count = 0
    else:
        fail_count += 1
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Пинг провален (статус: {status}). Попытка {fail_count}/{FAIL_LIMIT}")

    if fail_count >= FAIL_LIMIT:
        print("Бот на Render официально упал! Завершаю работу с ошибкой.")
        sys.exit(1)

    time.sleep(15)
