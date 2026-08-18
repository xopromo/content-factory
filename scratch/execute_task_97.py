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
    reply_to = 356
    task_id = 97
    
    text = (
        "🎙 <b>Как доставлять голосовые с телефона на компьютер (в один шаг, находясь далеко от ПК):</b>\n\n"
        "Для этого у нас уже есть работающая схема, и её можно сделать ещё более автономной:\n\n"
        "1️⃣ <b>Текущая схема (быстрая, полу-локальная):</b>\n"
        "• Вы записываете голосовое в Телеграм-бот с телефона, будучи где угодно.\n"
        "• Бот на сервере Render мгновенно переводит его в текст с помощью <b>Groq Whisper API</b> (это бесплатно и занимает 1 секунду) и записывает текст в <code>tasks.json</code> на GitHub.\n"
        "• Локальный компьютер (листенер) забирает эту задачу через Git и выполняет её. Всё происходит автоматически в один шаг для вас.\n\n"
        "2️⃣ <b>Полностью локальная схема (без облачных API расшифровки):</b>\n"
        "Если вы хотите, чтобы расшифровка голоса происходила строго локально на вашем ПК (например, через локальный Whisper):\n"
        "• Бот в Телеграме при получении голосового сообщения сохраняет его исходный аудиофайл (формат <code>.ogg</code>) и загружает его в Git-репозиторий в специальную папку (например, <code>docs/voice/</code>).\n"
        "• Ваш домашний компьютер через листенер делает <code>git pull</code>, обнаруживает новые файлы <code>.ogg</code> в папке.\n"
        "• На компьютере автоматически запускается локальный <b>Faster-Whisper</b>, расшифровывает файл прямо на вашем процессоре/видеокарте и передаёт готовый текст агенту на выполнение.\n"
        "• Ответ возвращается обратно в Телеграм.\n\n"
        "<b>Что мы можем сделать прямо сейчас:</b>\n"
        "Мы можем доработать бота на Render и локальный листенер, чтобы они обменивались именно исходными аудиофайлами <code>.ogg</code> через репозиторий, а ваш ПК расшифровывал их локально. Это полностью освободит нас от внешних API распознавания!"
    )
    
    print("Sending Telegram reply...")
    msg_id = send_telegram_reply(reply_to, text)
    if msg_id:
        print(f"Telegram reply sent. Message ID: {msg_id}")
        print("Marking task completed in git...")
        complete_task(task_id, msg_id, "ИИ-агент предложил варианты доставки и локальной расшифровки голосовых сообщений.")
    else:
        print("Failed to send telegram reply.")

if __name__ == "__main__":
    main()
