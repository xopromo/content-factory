#!/usr/bin/env python3
"""
Voice Bot — голосовые заметки в базу знаний с телефона.

Работает онлайн (Render.com), сохраняет транскрипты прямо в GitHub репозиторий
через GitHub API — никакого локального диска не нужно.

Запуск локально:  python3 scripts/voice_bot.py
Запуск онлайн:    Render.com web service (см. PROJECT_STATE.md)

Переменные окружения:
  TG_BOT_TOKEN   — от @BotFather
  GROQ_KEY       — от console.groq.com
  TG_CHAT_ID     — твой Telegram ID (от @userinfobot)
  GITHUB_TOKEN   — Personal Access Token с правом contents:write
  GITHUB_REPO    — xopromo/content-factory
  GITHUB_BRANCH  — claude/vigilant-einstein-hPa8u (или main после мерджа)
"""

import os
import re
import sys
import base64
import logging
import tempfile
import urllib.request
import urllib.parse
import json
from pathlib import Path
from datetime import datetime, timezone

from groq import Groq
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── Категории ─────────────────────────────────────────────────────────────────

CATEGORIES = [
    "💼 Кейс",
    "💡 Инсайт",
    "📋 Гайд",
    "🎯 Стратегия",
    "❓ Гипотеза",
    "📝 Мысль",
]

WAIT_CATEGORY = 1

# ── GitHub API — сохранение файла прямо в репо ────────────────────────────────

def push_to_github(filename: str, content: str) -> str:
    """Создаёт файл в knowledge/voice/ через GitHub API. Возвращает URL."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
    branch = os.environ.get("GITHUB_BRANCH", "claude/vigilant-einstein-hPa8u")

    if not token:
        # Локальный режим — сохраняем на диск
        local_dir = Path(__file__).parent.parent / "knowledge" / "voice"
        local_dir.mkdir(parents=True, exist_ok=True)
        path = local_dir / filename
        path.write_text(content, encoding="utf-8")
        log.info("Saved locally: %s", path)
        return str(path)

    path_in_repo = f"knowledge/voice/{filename}"
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path_in_repo)}"

    payload = json.dumps({
        "message": f"voice: {filename}",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
        html_url = result.get("content", {}).get("html_url", path_in_repo)
        log.info("Pushed to GitHub: %s", html_url)
        return html_url


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


# ── Форматирование заметки ────────────────────────────────────────────────────

def format_note(text: str, category: str, duration_sec: int = 0) -> tuple[str, str]:
    """Возвращает (filename, markdown_content)."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M")
    slug = re.sub(r"[^\w]", "", category.split()[-1].lower())[:15]
    filename = f"{date_str}_{time_str}_{slug}.md"

    duration_note = f" ({duration_sec}с)" if duration_sec else ""
    content = f"""# {category} — {now.strftime("%d.%m.%Y %H:%M")}

> *Голосовая заметка{duration_note} | UTC*

{text}

---
*Источник: voice_bot | {now.isoformat()}*
"""
    return filename, content


# ── Хэндлеры ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Отправь голосовое — я транскрибирую и сохраню в базу знаний.\n\n"
        "/list — последние заметки\n"
        "/cancel — отменить текущее действие"
    )


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
    branch = os.environ.get("GITHUB_BRANCH", "claude/vigilant-einstein-hPa8u")

    if token:
        url = f"https://api.github.com/repos/{repo}/contents/knowledge/voice?ref={branch}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                files = json.loads(resp.read())
                names = sorted([f["name"] for f in files if f["name"].endswith(".md")], reverse=True)[:5]
                if names:
                    await update.message.reply_text("Последние заметки:\n\n" + "\n".join(f"• {n}" for n in names))
                else:
                    await update.message.reply_text("Заметок пока нет.")
        except Exception as e:
            await update.message.reply_text(f"Ошибка получения списка: {e}")
    else:
        local_dir = Path(__file__).parent.parent / "knowledge" / "voice"
        files = sorted(local_dir.glob("*.md"), reverse=True)[:5] if local_dir.exists() else []
        if files:
            await update.message.reply_text("Последние заметки:\n\n" + "\n".join(f"• {f.name}" for f in files))
        else:
            await update.message.reply_text("Заметок пока нет.")


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    voice = update.message.voice or update.message.audio
    if not voice:
        return ConversationHandler.END

    await update.message.reply_text("Транскрибирую...")

    file = await ctx.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    await file.download_to_drive(tmp_path)

    try:
        text = transcribe(tmp_path)
    except Exception as e:
        log.error("Transcription failed: %s", e)
        await update.message.reply_text(f"Ошибка транскрипции: {e}")
        return ConversationHandler.END
    finally:
        tmp_path.unlink(missing_ok=True)

    ctx.user_data["text"] = text
    ctx.user_data["duration"] = getattr(voice, "duration", 0)

    preview = text[:500] + ("..." if len(text) > 500 else "")
    await update.message.reply_text(f"📝 *Транскрипт:*\n\n{preview}", parse_mode="Markdown")

    keyboard = [[cat] for cat in CATEGORIES]
    await update.message.reply_text(
        "Выбери категорию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return WAIT_CATEGORY


async def handle_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    category = update.message.text.strip()
    text = ctx.user_data.get("text", "")
    duration = ctx.user_data.get("duration", 0)

    if not text:
        await update.message.reply_text("Что-то пошло не так, попробуй ещё раз.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Сохраняю...",
        reply_markup=ReplyKeyboardRemove(),
    )

    try:
        filename, content = format_note(text, category, duration)
        location = push_to_github(filename, content)
        await update.message.reply_text(f"✅ Сохранено: `{filename}`", parse_mode="Markdown")
    except Exception as e:
        log.error("Save failed: %s", e)
        await update.message.reply_text(f"Ошибка сохранения: {e}")

    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── Запуск ────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.getenv("TG_BOT_TOKEN")
    if not token:
        sys.exit("Нет TG_BOT_TOKEN")
    if not os.getenv("GROQ_KEY"):
        sys.exit("Нет GROQ_KEY")

    mode = "GitHub API" if os.getenv("GITHUB_TOKEN") else "локальный диск"
    print(f"Бот запущен | Сохранение: {mode}")

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.VOICE | filters.AUDIO, handle_voice)],
        states={WAIT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(conv)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
