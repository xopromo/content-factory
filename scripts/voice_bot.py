#!/usr/bin/env python3
"""
Voice Bot — голосовые заметки + распаковка эксперта + заполнение бизнеса.

Режимы:
  🎤 Голосовая заметка  — транскрипция → категория → knowledge/voice/
  💡 Экспертиза         — AI-вопросы для распаковки опыта → knowledge/voice/
  💼 Бизнес             — AI-вопросы про продукты/услуги → business/products.md
  🎯 Аудитория          — серия вопросов → AI-профиль ЦА → business/audience.md
  📰 Новости ниши       — свежие новости VK-рекламы → комментарий эксперта → knowledge/voice/

Переменные окружения:
  TG_BOT_TOKEN, GROQ_KEY
  GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH  (опционально, для облачного режима)
"""

import os, re, sys, base64, logging, tempfile, urllib.request, urllib.parse, json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from groq import Groq
from ddgs import DDGS
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ── Состояния разговора ────────────────────────────────────────────────────────
WAIT_CATEGORY     = 1
WAIT_EXPERT_PICK  = 2
WAIT_EXPERT_VOICE = 3
WAIT_BIZ_PICK     = 4
WAIT_BIZ_VOICE    = 5
WAIT_AUD_ANSWER   = 6
WAIT_AUD_CONFIRM  = 7
WAIT_NEWS_PICK    = 8
WAIT_NEWS_VOICE   = 9

# ── Константы ─────────────────────────────────────────────────────────────────
CATEGORIES = ["💼 Кейс", "💡 Инсайт", "📋 Гайд", "🎯 Стратегия", "❓ Гипотеза", "📝 Мысль"]

AUDIENCE_QUESTIONS = [
    "Кто твой типичный клиент? Чем занимается, сколько лет, что за бизнес или проект?",
    "Какую главную боль он приходит к тебе решать? Как он сам её формулирует своими словами?",
    "Что он уже пробовал до тебя? Почему это не сработало или сработало не так?",
    "Откуда клиент узнаёт о тебе? Где проводит время онлайн, что читает, на кого подписан?",
    "Что останавливает от покупки? Главные возражения или страхи?",
    "Какой конкретный результат он хочет получить через месяц работы с тобой?",
]

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🎤 Голосовая заметка"],
        ["💡 Экспертиза", "💼 Бизнес"],
        ["🎯 Аудитория", "📋 Заметки"],
        ["📰 Новости ниши"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

NEWS_QUERY = "ВКонтакте реклама таргет 2026"

NAV_KEYBOARD = ReplyKeyboardMarkup(
    [["🏠 Главное меню"]],
    resize_keyboard=True,
)

NUMS = {"1️⃣": 0, "2️⃣": 1, "3️⃣": 2}

# ── Работа с файлами (GitHub API или локальный диск) ──────────────────────────

def _gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def gh_read(path: str) -> str:
    if not os.environ.get("GITHUB_TOKEN"):
        p = Path(__file__).parent.parent / path
        return p.read_text("utf-8") if p.exists() else ""
    repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
    branch = os.environ.get("GITHUB_BRANCH", "claude/vigilant-einstein-hPa8u")
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={branch}"
    try:
        req = urllib.request.Request(url, headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            return base64.b64decode(d["content"].replace("\n", "")).decode("utf-8")
    except Exception:
        return ""

def gh_write(path: str, content: str, message: str) -> str:
    if not os.environ.get("GITHUB_TOKEN"):
        p = Path(__file__).parent.parent / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")
        return str(p)
    repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
    branch = os.environ.get("GITHUB_BRANCH", "claude/vigilant-einstein-hPa8u")
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    sha = None
    try:
        req = urllib.request.Request(url + f"?ref={branch}", headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read()).get("sha")
    except Exception:
        pass
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={**_gh_headers(), "Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.loads(r.read())
        return result.get("content", {}).get("html_url", path)

def gh_list(path: str) -> list[str]:
    if not os.environ.get("GITHUB_TOKEN"):
        p = Path(__file__).parent.parent / path
        return sorted([f.name for f in p.glob("*.md")], reverse=True) if p.exists() else []
    repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
    branch = os.environ.get("GITHUB_BRANCH", "claude/vigilant-einstein-hPa8u")
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={branch}"
    try:
        req = urllib.request.Request(url, headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            files = json.loads(r.read())
            return sorted([f["name"] for f in files if f["name"].endswith(".md")], reverse=True)
    except Exception:
        return []

# ── Groq ──────────────────────────────────────────────────────────────────────

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

def llm_chat(prompt: str, system: str = "") -> str:
    client = Groq(api_key=os.environ["GROQ_KEY"])
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=800,
        temperature=0.85,
    )
    return resp.choices[0].message.content.strip()

# ── Генерация вопросов ────────────────────────────────────────────────────────

def gen_expert_questions(context: str) -> list[str]:
    existing = f"Уже есть в базе знаний:\n{context}" if context.strip() else "База знаний пока пуста."
    result = llm_chat(
        f"""{existing}

Придумай ровно 3 вопроса для распаковки экспертизы таргетолога ВКонтакте.
Требования:
- Спрашивай про конкретные ситуации, провалы, неочевидные паттерны, инсайты из практики
- НЕ спрашивай «какие у тебя достижения» — это скучно, человек не будет отвечать
- Вопросы должны провоцировать истории, а не общие ответы
- Пример хорошего вопроса: «Расскажи про клиента, которому ты отказал — почему?»
- Только 3 вопроса, каждый на отдельной строке, без нумерации и маркеров""",
        "Ты помогаешь эксперту распаковать знания для наполнения контент-базы.",
    )
    questions = [q.strip() for q in result.splitlines() if q.strip() and not q.strip().startswith("#")]
    return questions[:3]

def gen_business_questions(existing: str) -> list[str]:
    context = f"Уже описано:\n{existing[:1500]}" if existing.strip() and existing.strip() != "# Продукты и услуги" else "Описания пока нет."
    result = llm_chat(
        f"""{context}

Придумай ровно 3 вопроса для описания продуктов и услуг.
Спрашивай то, чего ещё нет выше: конкретные офферы, цены, результаты клиентов, УТП, гарантии.
Только 3 вопроса, каждый на отдельной строке, без нумерации.""",
        "Ты помогаешь заполнить описание бизнеса для системы контент-маркетинга.",
    )
    questions = [q.strip() for q in result.splitlines() if q.strip() and not q.strip().startswith("#")]
    return questions[:3]

def gen_audience_profile(answers: list[tuple[str, str]]) -> str:
    qa_text = "\n\n".join(f"Вопрос: {q}\nОтвет: {a}" for q, a in answers)
    return llm_chat(
        f"""На основе ответов эксперта составь профиль целевой аудитории в Markdown:

{qa_text}

Структура профиля:
## Демография
## Главная боль и запрос
## Что пробовал раньше
## Где находится онлайн
## Ключевые возражения
## Желаемый результат
## Поисковые запросы (5–7 фраз)""",
        "Ты маркетолог, составляешь профиль ЦА для контент-стратегии эксперта.",
    )

# ── Вспомогательные ───────────────────────────────────────────────────────────

def format_voice_note(text: str, category: str, duration: int = 0) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^\w]", "", category.split()[-1].lower())[:15]
    filename = f"{now.strftime('%Y-%m-%d_%H-%M')}_{slug}.md"
    dur = f" ({duration}с)" if duration else ""
    content = (
        f"# {category} — {now.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"> *Голосовая заметка{dur} | UTC*\n\n"
        f"{text}\n\n"
        f"---\n*Источник: voice_bot | {now.isoformat()}*\n"
    )
    return filename, content

def questions_keyboard(questions: list[str]) -> ReplyKeyboardMarkup:
    """Показывает вопросы в сообщении, кнопки — номера + навигация."""
    return ReplyKeyboardMarkup(
        [["1️⃣", "2️⃣", "3️⃣"],
         ["🔄 Новые вопросы"],
         ["🏠 Главное меню"]],
        resize_keyboard=True,
    )

def fmt_questions(questions: list[str]) -> str:
    lines = []
    for i, q in enumerate(questions, 1):
        emoji = ["1️⃣", "2️⃣", "3️⃣"][i - 1]
        lines.append(f"{emoji} {q}")
    return "\n\n".join(lines)

async def _transcribe_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    voice = update.message.voice or update.message.audio
    if not voice:
        return None
    await update.message.reply_text("Транскрибирую...")
    file = await ctx.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    await file.download_to_drive(tmp_path)
    try:
        return transcribe(tmp_path)
    except Exception as e:
        log.error("Transcription error: %s", e)
        await update.message.reply_text(f"Ошибка транскрипции: {e}", reply_markup=MAIN_KEYBOARD)
        return None
    finally:
        tmp_path.unlink(missing_ok=True)

# ── Команды ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Выбери режим или просто отправь голосовое.",
        reply_markup=MAIN_KEYBOARD,
    )

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END

async def go_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    await update.message.reply_text("Главное меню:", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END

# ── Режим: обычная голосовая заметка ─────────────────────────────────────────

async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _transcribe_voice(update, ctx)
    if text is None:
        return ConversationHandler.END

    ctx.user_data["text"] = text
    ctx.user_data["duration"] = getattr(update.message.voice or update.message.audio, "duration", 0)

    preview = text[:500] + ("..." if len(text) > 500 else "")
    await update.message.reply_text(f"📝 *Транскрипт:*\n\n{preview}", parse_mode="Markdown")

    keyboard = [[cat] for cat in CATEGORIES] + [["🏠 Главное меню"]]
    await update.message.reply_text(
        "Выбери категорию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return WAIT_CATEGORY

async def handle_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    category = update.message.text.strip()
    note_text = ctx.user_data.get("text", "")
    duration = ctx.user_data.get("duration", 0)

    if not note_text:
        await update.message.reply_text("Что-то пошло не так, попробуй ещё раз.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    await update.message.reply_text("Сохраняю...", reply_markup=ReplyKeyboardRemove())
    try:
        filename, content = format_voice_note(note_text, category, duration)
        gh_write(f"knowledge/voice/{filename}", content, f"voice: {filename}")
        await update.message.reply_text(f"✅ Сохранено: `{filename}`", parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    return ConversationHandler.END

# ── Режим: Экспертиза ─────────────────────────────────────────────────────────

async def menu_expert(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("⏳ Читаю базу знаний и генерирую вопросы...")
    files = gh_list("knowledge/voice")[:5]
    context_parts = [gh_read(f"knowledge/voice/{f}")[:400] for f in files if f]
    context = "\n---\n".join(context_parts)
    questions = gen_expert_questions(context)
    ctx.user_data["expert_questions"] = questions
    await update.message.reply_text(
        f"💡 *Выбери тему для записи:*\n\n{fmt_questions(questions)}",
        parse_mode="Markdown",
        reply_markup=questions_keyboard(questions),
    )
    return WAIT_EXPERT_PICK

async def expert_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    questions = ctx.user_data.get("expert_questions", [])

    if text == "🔄 Новые вопросы":
        return await menu_expert(update, ctx)

    idx = NUMS.get(text)
    if idx is not None and idx < len(questions):
        ctx.user_data["expert_question"] = questions[idx]
        await update.message.reply_text(
            f"🎙 *{questions[idx]}*\n\nОтправь голосовое:",
            parse_mode="Markdown",
            reply_markup=NAV_KEYBOARD,
        )
        return WAIT_EXPERT_VOICE

    return WAIT_EXPERT_PICK

async def expert_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _transcribe_voice(update, ctx)
    if text is None:
        return WAIT_EXPERT_VOICE

    question = ctx.user_data.get("expert_question", "")
    full_text = f"**Вопрос:** {question}\n\n**Ответ:** {text}" if question else text

    ctx.user_data["text"] = full_text
    ctx.user_data["duration"] = getattr(update.message.voice or update.message.audio, "duration", 0)

    preview = text[:500] + ("..." if len(text) > 500 else "")
    await update.message.reply_text(f"📝 *Транскрипт:*\n\n{preview}", parse_mode="Markdown")

    keyboard = [[cat] for cat in CATEGORIES] + [["🏠 Главное меню"]]
    await update.message.reply_text(
        "Выбери категорию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return WAIT_CATEGORY

# ── Режим: Бизнес ─────────────────────────────────────────────────────────────

async def menu_business(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("⏳ Смотрю что уже есть и генерирую вопросы...")
    existing = gh_read("business/products.md")
    questions = gen_business_questions(existing)
    ctx.user_data["biz_questions"] = questions
    await update.message.reply_text(
        f"💼 *Вопросы про бизнес:*\n\n{fmt_questions(questions)}",
        parse_mode="Markdown",
        reply_markup=questions_keyboard(questions),
    )
    return WAIT_BIZ_PICK

async def biz_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    questions = ctx.user_data.get("biz_questions", [])

    if text == "🔄 Новые вопросы":
        return await menu_business(update, ctx)

    idx = NUMS.get(text)
    if idx is not None and idx < len(questions):
        ctx.user_data["biz_question"] = questions[idx]
        await update.message.reply_text(
            f"🎙 *{questions[idx]}*\n\nОтправь голосовое:",
            parse_mode="Markdown",
            reply_markup=NAV_KEYBOARD,
        )
        return WAIT_BIZ_VOICE

    return WAIT_BIZ_PICK

async def biz_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _transcribe_voice(update, ctx)
    if text is None:
        return WAIT_BIZ_VOICE

    question = ctx.user_data.get("biz_question", "")
    now = datetime.now(timezone.utc)

    await update.message.reply_text(f"📝 *Транскрипт:*\n\n{text[:500]}", parse_mode="Markdown")

    existing = gh_read("business/products.md")
    entry = f"\n\n## {now.strftime('%d.%m.%Y')} — {question}\n\n{text}\n"
    if not existing.strip() or existing.strip() == "# Продукты и услуги":
        new_content = f"# Продукты и услуги\n{entry}"
    else:
        new_content = existing.rstrip() + entry

    try:
        gh_write("business/products.md", new_content, f"business: {now.strftime('%Y-%m-%d')}")
        await update.message.reply_text("✅ Добавлено в business/products.md", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    return ConversationHandler.END

# ── Режим: Аудитория ──────────────────────────────────────────────────────────

async def menu_audience(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["aud_answers"] = []
    ctx.user_data["aud_index"] = 0
    total = len(AUDIENCE_QUESTIONS)
    await update.message.reply_text(
        f"🎯 *Распаковка аудитории* (вопрос 1 из {total})\n\n{AUDIENCE_QUESTIONS[0]}\n\n_Отвечай голосовым_",
        parse_mode="Markdown",
        reply_markup=NAV_KEYBOARD,
    )
    return WAIT_AUD_ANSWER

async def audience_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _transcribe_voice(update, ctx)
    if text is None:
        return WAIT_AUD_ANSWER

    idx = ctx.user_data.get("aud_index", 0)
    answers: list = ctx.user_data.get("aud_answers", [])
    answers.append((AUDIENCE_QUESTIONS[idx], text))
    ctx.user_data["aud_answers"] = answers
    ctx.user_data["aud_index"] = idx + 1

    total = len(AUDIENCE_QUESTIONS)
    if idx + 1 < total:
        next_q = AUDIENCE_QUESTIONS[idx + 1]
        await update.message.reply_text(
            f"✓ Записал!\n\n🎯 *Вопрос {idx + 2} из {total}:*\n\n{next_q}\n\n_Отвечай голосовым_",
            parse_mode="Markdown",
        )
        return WAIT_AUD_ANSWER

    await update.message.reply_text("⏳ Все ответы собраны. Генерирую профиль ЦА...")
    profile = gen_audience_profile(answers)
    ctx.user_data["aud_profile"] = profile

    await update.message.reply_text(
        f"📊 *Профиль целевой аудитории:*\n\n{profile}",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["✅ Сохранить"], ["🔄 Уточнить"], ["🏠 Главное меню"]],
            resize_keyboard=True,
        ),
    )
    return WAIT_AUD_CONFIRM

async def audience_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == "✅ Сохранить":
        profile = ctx.user_data.get("aud_profile", "")
        now = datetime.now(timezone.utc)
        content = (
            f"# Профиль целевой аудитории\n\n"
            f"> Сгенерирован {now.strftime('%d.%m.%Y')} на основе ответов автора.\n\n"
            f"{profile}\n"
        )
        try:
            gh_write("business/audience.md", content, f"audience: профиль ЦА {now.strftime('%Y-%m-%d')}")
            await update.message.reply_text("✅ Профиль ЦА сохранён в business/audience.md", reply_markup=MAIN_KEYBOARD)
        except Exception as e:
            await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)
        ctx.user_data.clear()
        return ConversationHandler.END

    if text == "🔄 Уточнить":
        await update.message.reply_text(
            "Что нужно уточнить? Ответь голосовым, добавлю в профиль:",
            reply_markup=NAV_KEYBOARD,
        )
        # Добавляем уточняющий вопрос и собираем ещё один ответ
        idx = ctx.user_data.get("aud_index", len(AUDIENCE_QUESTIONS))
        AUDIENCE_QUESTIONS_EXTRA = "Что хочешь уточнить или добавить к профилю аудитории?"
        ctx.user_data["aud_extra"] = True
        return WAIT_AUD_ANSWER

    return WAIT_AUD_CONFIRM

# ── Режим: Новости ниши ───────────────────────────────────────────────────────

def fetch_news(query: str, max_results: int = 3) -> list[dict]:
    """Ищет свежие новости через DuckDuckGo, возвращает list[{title, url, body}]."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results, region="ru-ru"))
        return results
    except Exception as e:
        log.warning("News fetch error: %s", e)
        return []

async def menu_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("⏳ Ищу свежие новости по VK-рекламе...")
    items = fetch_news(NEWS_QUERY)

    if not items:
        await update.message.reply_text(
            "Не удалось найти новости. Попробуй позже.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    ctx.user_data["news_items"] = items
    lines = []
    for i, item in enumerate(items, 1):
        emoji = ["1️⃣", "2️⃣", "3️⃣"][i - 1]
        lines.append(f"{emoji} *{item.get('title', '—')}*\n_{item.get('source', '')}_ • {item.get('date', '')[:10]}")
        if item.get("body"):
            lines.append(f"↳ {item['body'][:120]}…")
        lines.append("")

    await update.message.reply_text(
        "📰 *Свежие новости по VK-рекламе:*\n\n" + "\n".join(lines).strip()
        + "\n\nВыбери новость и запиши свой комментарий эксперта:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["1️⃣", "2️⃣", "3️⃣"],
             ["🔄 Новые новости"],
             ["🏠 Главное меню"]],
            resize_keyboard=True,
        ),
    )
    return WAIT_NEWS_PICK

async def news_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    items = ctx.user_data.get("news_items", [])

    if text == "🔄 Новые новости":
        return await menu_news(update, ctx)

    idx = NUMS.get(text)
    if idx is not None and idx < len(items):
        item = items[idx]
        ctx.user_data["news_item"] = item
        title = item.get("title", "")
        url = item.get("url", "")
        await update.message.reply_text(
            f"🎙 *{title}*\n\nЗапиши свой комментарий: что думаешь, согласен или нет, как это работает на практике?",
            parse_mode="Markdown",
            reply_markup=NAV_KEYBOARD,
        )
        return WAIT_NEWS_VOICE

    return WAIT_NEWS_PICK

async def news_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _transcribe_voice(update, ctx)
    if text is None:
        return WAIT_NEWS_VOICE

    item = ctx.user_data.get("news_item", {})
    title = item.get("title", "Новость")
    url = item.get("url", "")
    now = datetime.now(timezone.utc)

    preview = text[:500] + ("..." if len(text) > 500 else "")
    await update.message.reply_text(f"📝 *Транскрипт:*\n\n{preview}", parse_mode="Markdown")

    filename = f"{now.strftime('%Y-%m-%d_%H-%M')}_новость.md"
    content = (
        f"# 💡 Комментарий к новости — {now.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"> *Голосовой комментарий эксперта | UTC*\n\n"
        f"**Новость:** [{title}]({url})\n\n"
        f"**Мой комментарий:**\n\n{text}\n\n"
        f"---\n*Источник: voice_bot | {now.isoformat()}*\n"
    )
    try:
        gh_write(f"knowledge/voice/{filename}", content, f"voice: комментарий к новости {now.strftime('%Y-%m-%d')}")
        await update.message.reply_text(f"✅ Сохранено: `{filename}`", parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    return ConversationHandler.END

# ── Список заметок ────────────────────────────────────────────────────────────

async def menu_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    files = gh_list("knowledge/voice")[:5]
    if files:
        await update.message.reply_text(
            "Последние заметки:\n\n" + "\n".join(f"• {n}" for n in files),
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.message.reply_text("Заметок пока нет.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END

# ── Запуск ────────────────────────────────────────────────────────────────────

def main() -> None:
    if not (token := os.getenv("TG_BOT_TOKEN")):
        sys.exit("Нет TG_BOT_TOKEN")
    if not os.getenv("GROQ_KEY"):
        sys.exit("Нет GROQ_KEY")

    mode = "GitHub API" if os.getenv("GITHUB_TOKEN") else "локальный диск"
    print(f"Бот запущен | Сохранение: {mode}")

    app = Application.builder().token(token).build()

    home_filter = filters.Regex("^🏠 Главное меню$")

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
            MessageHandler(filters.Regex("^💡 Экспертиза$"), menu_expert),
            MessageHandler(filters.Regex("^💼 Бизнес$"), menu_business),
            MessageHandler(filters.Regex("^🎯 Аудитория$"), menu_audience),
            MessageHandler(filters.Regex("^📋 Заметки$"), menu_list),
            MessageHandler(filters.Regex("^📰 Новости ниши$"), menu_news),
        ],
        states={
            WAIT_CATEGORY: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category),
            ],
            WAIT_EXPERT_PICK: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expert_pick),
            ],
            WAIT_EXPERT_VOICE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, expert_voice),
            ],
            WAIT_BIZ_PICK: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, biz_pick),
            ],
            WAIT_BIZ_VOICE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, biz_voice),
            ],
            WAIT_AUD_ANSWER: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, audience_answer),
            ],
            WAIT_AUD_CONFIRM: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, audience_confirm),
            ],
            WAIT_NEWS_PICK: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, news_pick),
            ],
            WAIT_NEWS_VOICE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, news_voice),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
