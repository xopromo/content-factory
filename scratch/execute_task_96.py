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
    reply_to = 353
    task_id = 96
    
    text = (
        "🤖 <b>Локальная архитектура Jarvis (без интернета):</b>\n\n"
        "Для работы в полностью офлайн-режиме используются следующие локальные нейросети и движки:\n\n"
        "1️⃣ <b>Распознавание речи (STT):</b>\n"
        "• <b>Faster-Whisper</b> (оптимизированная версия OpenAI Whisper на C++). Она запускается локально на процессоре или видеокарте и за доли секунды переводит ваш голос в текст.\n\n"
        "2️⃣ <b>Диалоговый движок (Brain):</b>\n"
        "• <b>Ollama</b> — локальная платформа, которая запускает языковые модели прямо на вашем ПК.\n"
        "• В качестве «мозга» используются легковесные, но умные локальные модели: <b>Mistral-7B</b>, <b>Llama-3-8B</b> или <b>Phi-3</b>. Они общаются с вами, хранят контекст и вызывают инструменты.\n\n"
        "3️⃣ <b>Синтез речи (TTS):</b>\n"
        "• <b>Sillero TTS</b> — отличный русскоязычный движок синтеза речи. Он работает полностью офлайн, не требует GPU и выдает качественный голос (например, Светланы/Ксении) с естественными интонациями.\n\n"
        "Вся эта цепочка (Голос ➡️ Faster-Whisper ➡️ Ollama/Llama ➡️ Sillero TTS ➡️ Голос) работает на вашем компьютере автономно."
    )
    
    print("Sending Telegram reply...")
    msg_id = send_telegram_reply(reply_to, text)
    if msg_id:
        print(f"Telegram reply sent. Message ID: {msg_id}")
        print("Marking task completed in git...")
        complete_task(task_id, msg_id, "ИИ-агент ответил на вопрос о локальной архитектуре и движках Jarvis.")
    else:
        print("Failed to send telegram reply.")

if __name__ == "__main__":
    main()
