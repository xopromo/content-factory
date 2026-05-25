#!/usr/bin/env python3
"""
Voice Bot — голосовые заметки в базу знаний.

Принимает голосовые сообщения в Telegram, транскрибирует через Groq Whisper,
форматирует в Markdown и сохраняет в knowledge/voice/.

Запуск: python3 scripts/voice_bot.py
Требует: TG_BOT_TOKEN, GROQ_KEY в переменных окружения
"""

import os
import re
import sys
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from groq import Groq
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)

# ── Конфиг ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
VOICE_DIR = ROOT / "knowledge" / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# Категории для разметки заметок
CATEGORIES = [
    "💼 Кейс",
    "💡 Инсайт",
    "📋 Гайд/инструкция",
    "🎯 Стратегия",
    "❓ Вопрос/гипотеза",
    "📝 Просто мысль",
]

# Состояния диалога
WAIT_CATEGORY = 1

# ── Groq транскрипция ─────────────────────────────────────────────────────────

def transcribe(audio_path: Path) -> str:
    client = Groq(api_key=os.environ["GROQ_KEY"])
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(audio_path.name, f),
            model="whisper-large-v3-turbo",
            language="ru",
            response_format="text",
        )
    return result.strip()


# ── Форматирование и сохранение ───────────────────────────────────────────────

def save_note(text: str, category: str, duration_sec: int = 0) -> Path:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M")
    slug = re.sub(r"[^\w\-]", "", category.split()[-1].lower())[:20]

    filename = f"{date_str}_{time_str}_{slug}.md"
    path = VOICE_DIR / filename

    duration_note = f" ({duration_sec}с)" if duration_sec else ""
    content = f"""# {category} — {now.strftime("%d.%m.%Y %H:%M")}

> *Голосовая заметка{duration_note}*

{text}

---
*Источник: voice_bot | {now.isoformat()}*
"""
    path.write_text(content, encoding="utf-8")
    log.info("Saved: %s", path)
    return path


# ── Хэндлеры ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я записываю голосовые заметки в базу знаний.\n\n"
        "Просто отправь голосовое сообщение — я транскрибирую и сохраню.\n\n"
        "Команды:\n"
        "/list — последние 5 заметок\n"
        "/help — справка"
    )


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    files = sorted(VOICE_DIR.glob("*.md"), reverse=True)[:5]
    if not files:
        await update.message.reply_text("Заметок пока нет.")
        return
    lines = ["Последние заметки:\n"]
    for f in files:
        lines.append(f"• `{f.name}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает голосовое, транскрибирует, спрашивает категорию."""
    voice = update.message.voice or update.message.audio
    if not voice:
        return ConversationHandler.END

    await update.message.reply_text("Транскрибирую...")

    # Скачиваем аудио
    file = await ctx.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    await file.download_to_drive(tmp_path)

    # Транскрибируем
    try:
        text = transcribe(tmp_path)
    except Exception as e:
        log.error("Transcription failed: %s", e)
        await update.message.reply_text(f"Ошибка транскрипции: {e}")
        tmp_path.unlink(missing_ok=True)
        return ConversationHandler.END
    finally:
        tmp_path.unlink(missing_ok=True)

    # Сохраняем текст во временный контекст
    ctx.user_data["text"] = text
    ctx.user_data["duration"] = getattr(voice, "duration", 0)

    # Показываем транскрипт
    preview = text[:400] + ("..." if len(text) > 400 else "")
    await update.message.reply_text(f"📝 *Транскрипт:*\n\n{preview}", parse_mode="Markdown")

    # Спрашиваем категорию
    keyboard = [[cat] for cat in CATEGORIES]
    await update.message.reply_text(
        "Выбери категорию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return WAIT_CATEGORY


async def handle_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает категорию, сохраняет заметку."""
    category = update.message.text.strip()
    text = ctx.user_data.get("text", "")
    duration = ctx.user_data.get("duration", 0)

    if not text:
        await update.message.reply_text("Что-то пошло не так, попробуй ещё раз.")
        return ConversationHandler.END

    path = save_note(text, category, duration)

    await update.message.reply_text(
        f"✅ Сохранено в `{path.relative_to(ROOT)}`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )

    # Предлагаем добавить тег
    await update.message.reply_text(
        "Можешь добавить тему одним словом (для поиска) или отправь /skip:"
    )
    return ConversationHandler.END


async def handle_text_tag(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Если пользователь прислал тег текстом после сохранения."""
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    # Дописываем тег в последний файл
    files = sorted(VOICE_DIR.glob("*.md"), reverse=True)
    if files:
        content = files[0].read_text(encoding="utf-8")
        content = content.replace(
            "---\n*Источник:",
            f"**Тема:** {text}\n\n---\n*Источник:",
        )
        files[0].write_text(content, encoding="utf-8")
        await update.message.reply_text(f"Тема «{text}» добавлена.")


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── Запуск ────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.getenv("TG_BOT_TOKEN")
    groq_key = os.getenv("GROQ_KEY")

    if not token:
        sys.exit("Нет TG_BOT_TOKEN в переменных окружения")
    if not groq_key:
        sys.exit("Нет GROQ_KEY в переменных окружения")

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
        ],
        states={
            WAIT_CATEGORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_tag))

    print(f"Бот запущен. Файлы сохраняются в: {VOICE_DIR}")
    print("Остановить: Ctrl+C")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
