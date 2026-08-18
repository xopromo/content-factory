# -*- coding: utf-8 -*-
import sys
import os
from pathlib import Path

# Add project root to path
ROOT = Path("c:/Users/асус/Desktop/клод/антигравити, всякое/content-factory")
sys.path.append(str(ROOT))
sys.path.append(os.path.abspath("C:/Users/асус/.gemini/antigravity/brain/53b913fe-94c5-41ad-ad76-72fde5331225"))

from scripts.task_listener import send_telegram_reply
from scratch.complete_vscode_task import complete_task

def main():
    reply_to = 364
    task_id = 98
    
    text = (
        "💡 <b>Зачем в схеме нужен Git и можно ли слушать Telegram локально?</b>\n\n"
        "Использование Git в качестве посредника решает три важные проблемы:\n\n"
        "1️⃣ <b>Проблема «серого» IP и NAT:</b>\n"
        "Ваш домашний ПК находится за роутером и не имеет публичного IP-адреса. Telegram не может отправить Webhook (уведомление о новом сообщении) напрямую на ваш компьютер. Git выступает как безопасный облачный буфер (брокер сообщений).\n\n"
        "2️⃣ <b>Постоянное хранилище (Persistence):</b>\n"
        "Бот хостится на бесплатном сервере Render. У бесплатного Render нет постоянного диска (при перезапуске сервера все локальные файлы стираются). Git используется как надёжная бесплатная база данных для хранения списка задач (<code>tasks.json</code>).\n\n"
        "3️⃣ <b>Автономность:</b>\n"
        "Если ваш ПК выключен, бот на Render всё равно примет ваше сообщение и запишет в Git. Задача не потеряется. Как только вы включите ПК, листенер заберёт её и выполнит.\n\n"
        "---\n\n"
        "🔌 <b>Можно ли слушать Telegram полностью локально?</b>\n"
        "<b>Да, можно.</b> Для этого есть два пути:\n\n"
        "• <b>Вариант А (Long Polling):</b> Мы запускаем бота <code>voice_bot.py</code> прямо на вашем ПК. Вместо вебхуков он сам постоянно опрашивает сервера Telegram. Но тогда ваш ПК должен быть включен 24/7, и скрипту постоянно нужны рабочие прокси для обхода блокировок Telegram API в РФ.\n"
        "• <b>Вариант Б (Telethon / Userbot):</b> Локальный скрипт авторизуется под вашим личным аккаунтом Telegram и слушает сообщения в канале напрямую. Это работает быстро, но требует держать сессию активной и также уязвимо к блокировкам IP-адресов Telegram со стороны провайдеров.\n\n"
        "Текущая схема с Git была выбрана как <i>наиболее отказоустойчивая</i>, так как она разделяет приём сообщений (всегда онлайн в облаке) и их выполнение (локально на ПК по мере его включения)."
    )
    
    print("Sending Telegram reply...")
    msg_id = send_telegram_reply(reply_to, text)
    if msg_id:
        print(f"Telegram reply sent. Message ID: {msg_id}")
        print("Marking task completed in git...")
        complete_task(task_id, msg_id, "ИИ-агент объяснил архитектурную роль Git в проекте и варианты локального прослушивания Telegram.")
    else:
        print("Failed to send telegram reply.")

if __name__ == "__main__":
    main()
