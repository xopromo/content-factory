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

import os, re, sys, base64, logging, tempfile, urllib.request, urllib.parse, json, asyncio, time, subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from groq import Groq
from ddgs import DDGS
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
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
WAIT_CUSTOM_CATEGORY = 10
WAIT_NEWS_TOPIC    = 11
WAIT_NEWS_QUERY    = 12
WAIT_EXPERT_TOPIC  = 13
WAIT_EXPERT_QUERY  = 14
WAIT_BIZ_TOPIC     = 15
WAIT_BIZ_QUERY     = 16
WAIT_AUD_TOPIC     = 17
WAIT_AUD_QUERY     = 18
WAIT_ARTICLE_TOPIC = 19
WAIT_ARTICLE_CONFIRM = 20
WAIT_ARTICLE_MODE = 21
WAIT_FORWARD_ACTION = 22
WAIT_VOICE_NOTE = 23

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
        ["📰 Новости ниши", "🚀 Создать статью"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

NEWS_QUERY = "нейросети искусственный интеллект маркетинг 2026"

NEWS_TOPICS = {
    "🎯 VK-реклама": "VK-реклама таргетинг продвижение новости",
    "🤖 Нейросети и ИИ": "нейросети искусственный интеллект маркетинг 2026",
    "🪙 Криптовалюта": "криптовалюта биткоин трейдинг новости",
}

NAV_KEYBOARD = ReplyKeyboardMarkup(
    [["🏠"]],
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
    branch = os.environ.get("GITHUB_BRANCH", "main")
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
    branch = os.environ.get("GITHUB_BRANCH", "main")
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

def gh_write_bin(path: str, data: bytes, message: str) -> str:
    if not os.environ.get("GITHUB_TOKEN"):
        p = Path(__file__).parent.parent / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return str(p)
    repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
    branch = os.environ.get("GITHUB_BRANCH", "main")
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
        "content": base64.b64encode(data).decode(),
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
    branch = os.environ.get("GITHUB_BRANCH", "main")
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

def gen_expert_questions(topic: str, context: str) -> list[str]:
    existing = f"Уже есть в базе знаний по этой теме:\n{context}" if context.strip() else "База знаний пока пуста."
    result = llm_chat(
        f"""{existing}

Придумай ровно 3 глубоких вопроса для распаковки практического опыта эксперта в теме: «{topic}».
Требования:
- Спрашивай про конкретные ситуации, провалы, неочевидные паттерны, инсайты из практики
- НЕ спрашивай «какие у тебя достижения» — это скучно, человек не будет отвечать
- Вопросы должны провоцировать истории, а не общие ответы
- Пример хорошего вопроса: «Расскажи про клиента, которому ты отказал — почему?»
- Только 3 вопроса, каждый на отдельной строке, без нумерации и маркеров""",
        f"Ты помогаешь эксперту распаковать знания в теме «{topic}» для наполнения контент-базы.",
    )
    questions = [q.strip() for q in result.splitlines() if q.strip() and not q.strip().startswith("#")]
    return questions[:3]

def gen_business_questions(topic: str, existing: str) -> list[str]:
    context = f"Уже описано для направления «{topic}»:\n{existing[:1500]}" if existing.strip() and existing.strip() != "# Продукты и услуги" else "Описания пока нет."
    result = llm_chat(
        f"""{context}

Придумай ровно 3 вопроса для описания продуктов, услуг и офферов в теме/направлении: «{topic}».
Спрашивай то, чего ещё нет выше: конкретные офферы, цены, тарифы, результаты клиентов, УТП, гарантии.
Только 3 вопроса, каждый на отдельной строке, без нумерации.""",
        f"Ты помогаешь заполнить описание бизнеса в направлении «{topic}» для контент-маркетинга.",
    )
    questions = [q.strip() for q in result.splitlines() if q.strip() and not q.strip().startswith("#")]
    return questions[:3]

def gen_audience_profile(topic: str, answers: list[tuple[str, str]]) -> str:
    qa_text = "\n\n".join(f"Вопрос: {q}\nОтвет: {a}" for q, a in answers)
    return llm_chat(
        f"""На основе ответов эксперта составь профиль целевой аудитории для проекта «{topic}» в Markdown:

{qa_text}

Структура профиля:
## Демография
## Главная боль и запрос
## Что пробовал раньше
## Где находится онлайн
## Ключевые возражения
## Желаемый результат
## Поисковые запросы (5–7 фраз)""",
        f"Ты маркетолог, составляешь профиль ЦА в проекте «{topic}» для контент-стратегии эксперта.",
    )

def gen_article_metadata(topic: str, mode: str) -> tuple[str, str, str]:
    mode_desc = ""
    if mode == "🔬 Статья-исследование":
        mode_desc = "Формат: глубокое аналитическое исследование с разбором данных, кейсов, технической аналитикой."
    elif mode == "📰 Новостной обзор":
        mode_desc = "Формат: обзор последних новостей, трендов и свежих событий за короткий период."
    else:
        mode_desc = "Формат: пошаговое руководство, практический SEO/GEO оптимизированный гайд."

    prompt = f"""На основе темы «{topic}» и формата «{mode}» ({mode_desc}) предложи метаданные для генерации статьи.
Ты должен вернуть строго JSON с тремя ключами:
"title" (привлекательный кликабельный заголовок H1 на русском языке, точно отражающий формат и тему),
"slug" (латинский URL-slug, например: "ai-research-2026"),
"query" (оптимальный поисковый запрос для DuckDuckGo на русском или английском для сбора свежей и глубокой информации по этой теме).

Верни ТОЛЬКО валидный JSON без разметки markdown и без каких-либо комментариев."""
    
    result = llm_chat(prompt, system="Ты помощник по планированию контента.")
    try:
        cleaned = result.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        data = json.loads(cleaned.strip())
        return data["title"], data["slug"], data["query"]
    except Exception as e:
        log.error("Failed to parse article metadata: %s, raw: %s", e, result)
        slug = get_topic_slug(topic)
        return f"Новое исследование: {topic}", slug, topic

# ── Вспомогательные ───────────────────────────────────────────────────────────

def get_topic_slug(topic: str) -> str:
    cyr = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    lat = "a b v g d e yo zh z i j k l m n o p r s t u f kh ts ch sh shch '' y ' e yu ya".split()
    tr = {c: l for c, l in zip(cyr, lat)}
    
    s = topic.lower().strip()
    s_tr = "".join(tr.get(c, c) for c in s)
    s_clean = re.sub(r"[^a-z0-9_\-]", "_", s_tr)
    s_clean = re.sub(r"_+", "_", s_clean).strip("_")
    return s_clean or "general"

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

async def send_transcript(update: Update, text: str) -> None:
    """Отправляет полный транскрипт, разбивая на части если > 4000 символов."""
    LIMIT = 4000
    if len(text) <= LIMIT:
        await update.message.reply_text(f"📝 *Транскрипт:*\n\n{text}", parse_mode="Markdown")
        return
    chunks = [text[i:i + LIMIT] for i in range(0, len(text), LIMIT)]
    for idx, chunk in enumerate(chunks, 1):
        header = f"📝 *Транскрипт ({idx}/{len(chunks)}):*\n\n" if idx == 1 else f"📝 *Транскрипт (часть {idx}/{len(chunks)}):*\n\n"
        await update.message.reply_text(header + chunk, parse_mode="Markdown")

def questions_keyboard(questions: list[str]) -> ReplyKeyboardMarkup:
    """Показывает вопросы в сообщении, кнопки — номера + навигация."""
    return ReplyKeyboardMarkup(
        [["1️⃣", "2️⃣", "3️⃣"],
         ["🔄 Новые вопросы"],
         ["🏠"]],
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
    status_msg = await update.message.reply_text("Транскрибирую...")
    file = await ctx.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    await file.download_to_drive(tmp_path)
    try:
        res = transcribe(tmp_path)
        try:
            await status_msg.delete()
        except Exception:
            pass
        return res
    except Exception as e:
        log.error("Transcription error: %s", e)
        try:
            await status_msg.delete()
        except Exception:
            pass
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
    review_file = Path("business/review_waiting.txt")
    if review_file.exists():
        text = await _transcribe_voice(update, ctx)
        if text:
            latest_reply = Path("business/latest_reply.json")
            latest_reply.write_text(json.dumps({
                "timestamp": time.time(),
                "type": "voice",
                "content": text
            }, ensure_ascii=False), encoding="utf-8")
            await update.message.reply_text("🎙 Правка передана в генератор статьи.")
        return ConversationHandler.END

    text = await _transcribe_voice(update, ctx)
    if text is None:
        return ConversationHandler.END

    ctx.user_data["text"] = text
    ctx.user_data["duration"] = getattr(update.message.voice or update.message.audio, "duration", 0)

    await send_transcript(update, text)

    keyboard = [[cat] for cat in CATEGORIES] + [["➕ Своя категория"], ["🏠"]]
    await update.message.reply_text(
        "Выбери категорию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return WAIT_CATEGORY

async def handle_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    category = update.message.text.strip()
    note_text = ctx.user_data.get("text", "")
    duration = ctx.user_data.get("duration", 0)

    if category == "➕ Своя категория":
        await update.message.reply_text(
            "Введите название вашей категории:",
            reply_markup=NAV_KEYBOARD
        )
        return WAIT_CUSTOM_CATEGORY

    if not note_text and ctx.user_data.get("forward_buffer"):
        note_text = "\n\n---\n\n".join(ctx.user_data["forward_buffer"])

    if not note_text:
        await update.message.reply_text("Что-то пошло не так, попробуй ещё раз.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    status_msg = await update.message.reply_text("Сохраняю...", reply_markup=ReplyKeyboardRemove())
    try:
        filename, content = format_voice_note(note_text, category, duration)
        url_or_path = gh_write(f"knowledge/voice/{filename}", content, f"voice: {filename}")
        
        try:
            await status_msg.delete()
        except Exception:
            pass

        keyboard = []
        if url_or_path.startswith("http"):
            keyboard.append([InlineKeyboardButton("🔍 Проверить на GitHub", url=url_or_path)])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await update.message.reply_text(
            f"✅ Сохранено: `{filename}`", 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )
        await update.message.reply_text("Возвращаюсь в главное меню:", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    ctx.user_data.clear()
    return ConversationHandler.END

async def handle_custom_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    category = update.message.text.strip()
    note_text = ctx.user_data.get("text", "")
    duration = ctx.user_data.get("duration", 0)

    if not note_text and ctx.user_data.get("forward_buffer"):
        note_text = "\n\n---\n\n".join(ctx.user_data["forward_buffer"])

    if not note_text:
        await update.message.reply_text("Что-то пошло не так, попробуй ещё раз.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    status_msg = await update.message.reply_text("Сохраняю...", reply_markup=ReplyKeyboardRemove())
    try:
        filename, content = format_voice_note(note_text, category, duration)
        url_or_path = gh_write(f"knowledge/voice/{filename}", content, f"voice: {filename}")
        
        try:
            await status_msg.delete()
        except Exception:
            pass

        keyboard = []
        if url_or_path.startswith("http"):
            keyboard.append([InlineKeyboardButton("🔍 Проверить на GitHub", url=url_or_path)])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        await update.message.reply_text(
            f"✅ Сохранено в категорию «{category}»: `{filename}`", 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )
        await update.message.reply_text("Возвращаюсь в главное меню:", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    ctx.user_data.clear()
    return ConversationHandler.END

# ── Режим: Экспертиза ─────────────────────────────────────────────────────────

async def choose_expert_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
        ["🪙 Криптовалюта", "➕ Другая тема"],
        ["🏠"]
    ]
    await update.message.reply_text(
        "Выбери тему для генерации вопросов экспертизы или нажми «➕ Другая тема»:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_EXPERT_TOPIC

async def handle_expert_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "➕ Другая тема":
        await update.message.reply_text("Введите тему вашей экспертизы:", reply_markup=NAV_KEYBOARD)
        return WAIT_EXPERT_QUERY
        
    if text in NEWS_TOPICS:
        ctx.user_data["expert_topic"] = text
        return await start_expert_questions(update, ctx)
        
    ctx.user_data["expert_topic"] = text
    return await start_expert_questions(update, ctx)

async def handle_expert_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    ctx.user_data["expert_topic"] = text
    return await start_expert_questions(update, ctx)

async def start_expert_questions(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    topic = ctx.user_data.get("expert_topic", "VK-реклама")
    status_msg = await update.message.reply_text(f"⏳ Читаю базу знаний и генерирую вопросы по теме «{topic}»...")
    files = gh_list("knowledge/voice")[:5]
    context_parts = [gh_read(f"knowledge/voice/{f}")[:400] for f in files if f]
    context = "\n---\n".join(context_parts)
    questions = gen_expert_questions(topic, context)
    ctx.user_data["expert_questions"] = questions
    try:
        await status_msg.delete()
    except Exception:
        pass
    await update.message.reply_text(
        f"💡 *Выбери тему для записи:* (Направление: {topic})\n\n{fmt_questions(questions)}",
        parse_mode="Markdown",
        reply_markup=questions_keyboard(questions),
    )
    return WAIT_EXPERT_PICK

async def expert_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    questions = ctx.user_data.get("expert_questions", [])

    if text == "🔄 Новые вопросы":
        return await start_expert_questions(update, ctx)

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

    await send_transcript(update, text)

    keyboard = [[cat] for cat in CATEGORIES] + [["➕ Своя категория"], ["🏠"]]
    await update.message.reply_text(
        "Выбери категорию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return WAIT_CATEGORY

# ── Режим: Бизнес ─────────────────────────────────────────────────────────────

# ── Режим: Бизнес ─────────────────────────────────────────────────────────────

async def choose_biz_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
        ["🪙 Криптовалюта", "➕ Другая тема"],
        ["🏠"]
    ]
    await update.message.reply_text(
        "Выбери направление бизнеса для генерации вопросов или нажми «➕ Другая тема»:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_BIZ_TOPIC

async def handle_biz_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "➕ Другая тема":
        await update.message.reply_text("Введите направление/тему бизнеса:", reply_markup=NAV_KEYBOARD)
        return WAIT_BIZ_QUERY
        
    if text in NEWS_TOPICS:
        ctx.user_data["biz_topic"] = text
        return await start_business_questions(update, ctx)
        
    ctx.user_data["biz_topic"] = text
    return await start_business_questions(update, ctx)

async def handle_biz_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    ctx.user_data["biz_topic"] = text
    return await start_business_questions(update, ctx)

async def start_business_questions(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    topic = ctx.user_data.get("biz_topic", "VK-реклама")
    slug = get_topic_slug(topic)
    
    status_msg = await update.message.reply_text(f"⏳ Смотрю что уже есть по теме «{topic}» и генерирую вопросы...")
    existing = gh_read(f"business/products_{slug}.md")
    questions = gen_business_questions(topic, existing)
    ctx.user_data["biz_questions"] = questions
    try:
        await status_msg.delete()
    except Exception:
        pass
    await update.message.reply_text(
        f"💼 *Вопросы про бизнес:* (Направление: {topic})\n\n{fmt_questions(questions)}",
        parse_mode="Markdown",
        reply_markup=questions_keyboard(questions),
    )
    return WAIT_BIZ_PICK

async def biz_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    questions = ctx.user_data.get("biz_questions", [])

    if text == "🔄 Новые вопросы":
        return await start_business_questions(update, ctx)

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
    topic = ctx.user_data.get("biz_topic", "VK-реклама")
    slug = get_topic_slug(topic)
    now = datetime.now(timezone.utc)

    await update.message.reply_text(f"📝 *Транскрипт:*\n\n{text[:500]}", parse_mode="Markdown")

    existing = gh_read(f"business/products_{slug}.md")
    entry = f"\n\n## {now.strftime('%d.%m.%Y')} — {question}\n\n{text}\n"
    if not existing.strip() or existing.strip() == "# Продукты и услуги":
        new_content = f"# Продукты и услуги ({topic})\n{entry}"
    else:
        new_content = existing.rstrip() + entry

    try:
        gh_write(f"business/products_{slug}.md", new_content, f"business: {now.strftime('%Y-%m-%d')} ({slug})")
        await update.message.reply_text(f"✅ Добавлено в business/products_{slug}.md", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    return ConversationHandler.END

# ── Режим: Аудитория ──────────────────────────────────────────────────────────

async def choose_aud_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
        ["🪙 Криптовалюта", "➕ Другая тема"],
        ["🏠"]
    ]
    await update.message.reply_text(
        "Выбери направление для анализа целевой аудитории или нажми «➕ Другая тема»:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_AUD_TOPIC

async def handle_aud_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "➕ Другая тема":
        await update.message.reply_text("Введите направление/тему проекта:", reply_markup=NAV_KEYBOARD)
        return WAIT_AUD_QUERY
        
    if text in NEWS_TOPICS:
        ctx.user_data["aud_topic"] = text
        return await start_audience_unpack(update, ctx)
        
    ctx.user_data["aud_topic"] = text
    return await start_audience_unpack(update, ctx)

async def handle_aud_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    ctx.user_data["aud_topic"] = text
    return await start_audience_unpack(update, ctx)

async def start_audience_unpack(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    topic = ctx.user_data.get("aud_topic", "VK-реклама")
    ctx.user_data["aud_answers"] = []
    ctx.user_data["aud_index"] = 0
    total = len(AUDIENCE_QUESTIONS)
    await update.message.reply_text(
        f"🎯 *Распаковка аудитории для темы «{topic}»* (вопрос 1 из {total})\n\n{AUDIENCE_QUESTIONS[0]}\n\n_Отвечай голосовым_",
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

    topic = ctx.user_data.get("aud_topic", "VK-реклама")
    status_msg = await update.message.reply_text("⏳ Все ответы собраны. Генерирую профиль ЦА...")
    profile = gen_audience_profile(topic, answers)
    ctx.user_data["aud_profile"] = profile
    try:
        await status_msg.delete()
    except Exception:
        pass

    await update.message.reply_text(
        f"📊 *Профиль целевой аудитории для темы «{topic}»:*\n\n{profile}",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["✅ Сохранить"], ["🔄 Уточнить"], ["🏠"]],
            resize_keyboard=True,
        ),
    )
    return WAIT_AUD_CONFIRM

async def audience_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == "✅ Сохранить":
        profile = ctx.user_data.get("aud_profile", "")
        topic = ctx.user_data.get("aud_topic", "VK-реклама")
        slug = get_topic_slug(topic)
        now = datetime.now(timezone.utc)
        content = (
            f"# Профиль целевой аудитории — {topic}\n\n"
            f"> Сгенерирован {now.strftime('%d.%m.%Y')} на основе ответов автора.\n\n"
            f"{profile}\n"
        )
        try:
            gh_write(f"business/audience_{slug}.md", content, f"audience: профиль ЦА {now.strftime('%Y-%m-%d')} ({slug})")
            await update.message.reply_text(f"✅ Профиль ЦА сохранён в business/audience_{slug}.md", reply_markup=MAIN_KEYBOARD)
        except Exception as e:
            await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)
        ctx.user_data.clear()
        return ConversationHandler.END

    if text == "🔄 Уточнить":
        await update.message.reply_text(
            "Что нужно уточнить? Ответь голосовым, добавлю в профиль:",
            reply_markup=NAV_KEYBOARD,
        )
        ctx.user_data["aud_extra"] = True
        return WAIT_AUD_ANSWER

    return WAIT_AUD_CONFIRM

# ── Режим: Новости ниши ───────────────────────────────────────────────────────

def is_article_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            return False
            
        # 1. Исключаем общие служебные и разделы/каталоги
        lower_path = parsed.path.lower()
        exclude_patterns = [
            '/tag/', '/tags/', '/category/', '/categories/', 
            '/archive/', '/archives/', '/author/', '/authors/',
            '/page/', '/search/', '/catalog/', '/pricing/', 
            '/login/', '/register/', '/signup/', '/signin/',
            '/contacts', '/about', '/privacy', '/terms'
        ]
        if any(pat in lower_path for pat in exclude_patterns):
            return False
            
        # Разделяем на сегменты
        segments = [s for s in path.split("/") if s]
        if not segments:
            return False
            
        # 2. Если всего один сегмент (например, domain.com/something)
        if len(segments) == 1:
            seg = segments[0]
            if len(seg) < 8:
                return False
            has_separator = '-' in seg or '_' in seg
            has_digit = any(c.isdigit() for c in seg)
            if not (has_separator or has_digit):
                return False
                
        # 3. Для многосегментных путей отсекаем страницы подразделов без новостного слага/ID
        last_seg = segments[-1]
        has_separator = '-' in last_seg or '_' in last_seg
        has_digit = any(c.isdigit() for c in last_seg)
        ends_with_ext = any(last_seg.endswith(ext) for ext in ['.html', '.htm', '.phtml', '.php', '.shtml'])
        
        if not (has_separator or has_digit or ends_with_ext) and len(last_seg) < 10:
            return False
            
        return True
    except Exception:
        return False

_TIER1_DOMAINS = {
    "arxiv.org", "github.com", "anthropic.com", "openai.com", "deepmind.com",
    "huggingface.co", "pytorch.org", "tensorflow.org", "paperswithcode.com",
    "proceedings.mlr.press", "aclanthology.org", "research.google",
    "ai.meta.com", "mistral.ai", "docs.python.org", "developer.mozilla.org",
}
_TIER2_DOMAINS = {
    "techcrunch.com", "venturebeat.com", "wired.com", "theverge.com",
    "arstechnica.com", "zdnet.com", "towardsdatascience.com", "substack.com",
    "mit.edu", "stanford.edu", "harvard.edu", "medium.com", "habr.com",
}

def load_exclusions() -> dict:
    excl_path = Path(__file__).parent.parent / "exclusions.json"
    if excl_path.exists():
        try:
            return json.loads(excl_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "domains": [],
        "title_phrases": ["топ-15", "топ-10", "топ-12", "топ-5", "топ-20", "лучших нейросетей", "лучших сервисов", "лучшие нейросети", "лучших инструмент", "рейтинг нейросет"],
        "url_keywords": ["luchshie", "luchshih", "top-15", "top-10", "top-12", "top-5", "rejting", "rating"],
        "snippet_phrases": ["подборка", "рейтинг лучших", "топ нейросетей для бизнеса"]
    }

def is_excluded(title: str, url: str, snippet: str, exclusions: dict) -> bool:
    title_lower = title.lower()
    url_lower = url.lower()
    snippet_lower = snippet.lower()
    
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if any(d == domain or domain.endswith("." + d) for d in exclusions.get("domains", [])):
            return True
    except Exception:
        pass
        
    if any(phrase in title_lower for phrase in exclusions.get("title_phrases", [])):
        return True
    if any(keyword in url_lower for keyword in exclusions.get("url_keywords", [])):
        return True
    if any(phrase in snippet_lower for phrase in exclusions.get("snippet_phrases", [])):
        return True
    return False

def get_source_tier(url: str) -> int:
    if not url:
        return 3
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if any(d in domain for d in _TIER1_DOMAINS):
            return 1
        if any(d in domain for d in _TIER2_DOMAINS):
            return 2
    except Exception:
        pass
    return 3

def fetch_news(query: str, max_results: int = 15) -> list[dict]:
    """Ищет свежие новости через DuckDuckGo с качественной фильтрацией по exclusions и ранжированием по TIER."""
    articles = []
    seen_urls = set()
    exclusions = load_exclusions()
    
    def add_article(title: str, url: str, snippet: str, date: str = "", source: str = ""):
        if not url or url in seen_urls:
            return
        if not is_article_url(url):
            return
        if is_excluded(title, url, snippet, exclusions):
            return
        
        tier = get_source_tier(url)
        articles.append({
            "title": title,
            "url": url,
            "body": snippet,
            "date": date,
            "source": source,
            "tier": tier
        })
        seen_urls.add(url)

    # 1. Пробуем новостной поиск с фильтром по времени (сначала за неделю, потом за месяц)
    for limit in ("w", "m"):
        if len(articles) >= max_results:
            break
        try:
            results = list(DDGS().news(query, max_results=max_results * 3, timelimit=limit, region="ru-ru"))
            for r in results:
                add_article(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("body", ""),
                    date=r.get("date", ""),
                    source=r.get("source", "")
                )
        except Exception as e:
            log.warning("News fetch error (news with timelimit=%s): %s", limit, e)
        
    # 2. Добираем через текстовый поиск, если нашли мало статей
    if len(articles) < 10:
        try:
            results = list(DDGS().text(query, max_results=max_results * 3, region="ru-ru"))
            for r in results:
                add_article(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                    source=""
                )
        except Exception as e:
            log.warning("News fetch error (text): %s", e)
            
    # Сортируем по авторитетности (tier 1 -> tier 2 -> tier 3)
    articles.sort(key=lambda x: x["tier"])
    return articles

async def choose_news_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
        ["🪙 Криптовалюта", "➕ Другая тема"],
        ["🏠"]
    ]
    await update.message.reply_text(
        "Выбери тему новостей или нажми «➕ Другая тема», чтобы ввести свой запрос:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_NEWS_TOPIC

async def handle_news_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    
    if text == "➕ Другая тема":
        await update.message.reply_text(
            "Введите ваш поисковый запрос для поиска новостей:",
            reply_markup=NAV_KEYBOARD
        )
        return WAIT_NEWS_QUERY
        
    if text in NEWS_TOPICS:
        ctx.user_data["news_query"] = NEWS_TOPICS[text]
        ctx.user_data["news_topic_name"] = text
        return await start_news_search(update, ctx)
        
    # Если ввели что-то другое, трактуем как кастомный запрос
    ctx.user_data["news_query"] = text
    ctx.user_data["news_topic_name"] = text
    return await start_news_search(update, ctx)

async def handle_news_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    ctx.user_data["news_query"] = text
    ctx.user_data["news_topic_name"] = f"Запрос: {text}"
    return await start_news_search(update, ctx)

async def start_news_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = ctx.user_data.get("news_query", NEWS_QUERY)
    topic_name = ctx.user_data.get("news_topic_name", "VK-реклама")
    
    status_msg = await update.message.reply_text(f"⏳ Ищу свежие новости по теме «{topic_name}»...")
    pool = fetch_news(query, max_results=15)

    try:
        await status_msg.delete()
    except Exception:
        pass

    if not pool:
        await update.message.reply_text(
            f"Не удалось найти новости по теме «{topic_name}». Попробуй другой запрос.",
            reply_markup=ReplyKeyboardMarkup([
                ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
                ["🪙 Криптовалюта", "➕ Другая тема"],
                ["🏠"]
            ], resize_keyboard=True)
        )
        return WAIT_NEWS_TOPIC

    ctx.user_data["news_pool"] = pool
    ctx.user_data["news_index"] = 0
    return await show_news_page(update, ctx)

async def show_news_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    pool = ctx.user_data.get("news_pool", [])
    index = ctx.user_data.get("news_index", 0)
    topic_name = ctx.user_data.get("news_topic_name", "VK-реклама")

    if not pool:
        await update.message.reply_text("Новостной пул пуст. Попробуйте выбрать тему заново.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    if index >= len(pool):
        index = 0
        ctx.user_data["news_index"] = 0
        await update.message.reply_text("Вы просмотрели все новости. Показываю сначала (по второму кругу).")

    items = pool[index:index + 3]
    ctx.user_data["news_items"] = items

    lines = []
    import html
    tier_labels = {1: "⭐⭐⭐", 2: "⭐⭐", 3: "⭐"}
    for i, item in enumerate(items, 1):
        emoji = ["1️⃣", "2️⃣", "3️⃣"][i - 1]
        title_escaped = html.escape(item.get('title', '—'))
        source_escaped = html.escape(item.get('source', ''))
        url = item.get('url', '')
        tier_star = tier_labels.get(item.get("tier", 3), "⭐")
        
        lines.append(
            f"{emoji} <b>{title_escaped}</b>\n"
            f"🔗 <a href=\"{url}\">Читать новость</a>\n"
            f"<i>{source_escaped}</i> • {item.get('date', '')[:10]} • Качество: {tier_star}"
        )
        if item.get("body"):
            body_escaped = html.escape(item['body'][:120])
            lines.append(f"↳ {body_escaped}…")
        lines.append("")

    keyboard_rows = []
    if items:
        number_buttons = ["1️⃣", "2️⃣", "3️⃣"][:len(items)]
        keyboard_rows.append(number_buttons)
    keyboard_rows.append(["🔄 Новые новости"])
    keyboard_rows.append(["🏠"])

    await update.message.reply_text(
        f"📰 <b>Свежие новости по теме «{topic_name}» (страница {index//3 + 1}):</b>\n\n" + "\n".join(lines).strip()
        + "\n\nВыбери новость и запиши свой комментарий эксперта:",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=ReplyKeyboardMarkup(
            keyboard_rows,
            resize_keyboard=True,
        ),
    )
    return WAIT_NEWS_PICK

async def news_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    items = ctx.user_data.get("news_items", [])

    if text == "🔄 Новые новости":
        ctx.user_data["news_index"] = ctx.user_data.get("news_index", 0) + 3
        return await show_news_page(update, ctx)

    idx = NUMS.get(text)
    if idx is not None and idx < len(items):
        item = items[idx]
        ctx.user_data["news_item"] = item
        title = item.get("title", "")
        url = item.get("url", "")
        
        import html
        title_escaped = html.escape(title)
        await update.message.reply_text(
            f"🎙 <b>{title_escaped}</b>\n\n🔗 <b>Ссылка на новость:</b> {url}\n\nЗапиши свой комментарий: что думаешь, согласен или нет, как это работает на практике?",
            parse_mode="HTML",
            disable_web_page_preview=True,
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
    body_text = item.get("body", "")
    now = datetime.now(timezone.utc)

    await send_transcript(update, text)

    filename = f"{now.strftime('%Y-%m-%d_%H-%M')}_новость.md"
    url_line = f"[{title}]({url})" if url else title
    content = (
        f"# 💡 Комментарий к новости — {now.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"> *Голосовой комментарий эксперта | UTC*\n\n"
        f"**Новость:** {url_line}\n\n"
    )
    if body_text:
        content += f"{body_text}\n\n"
    content += (
        f"**Мой комментарий:**\n\n{text}\n\n"
        f"---\n*Источник: voice_bot | {now.isoformat()}*\n"
    )

    status_msg = await update.message.reply_text("Сохраняю...", reply_markup=ReplyKeyboardRemove())
    try:
        url_or_path = gh_write(f"knowledge/voice/{filename}", content, f"voice: комментарий к новости {now.strftime('%Y-%m-%d')}")
        try:
            await status_msg.delete()
        except Exception:
            pass

        keyboard = []
        if url_or_path.startswith("http"):
            keyboard.append([InlineKeyboardButton("🔍 Проверить на GitHub", url=url_or_path)])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        await update.message.reply_text(
            f"✅ Сохранено: `{filename}`", 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )
        await update.message.reply_text("Возвращаюсь в главное меню:", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    ctx.user_data.clear()
    return ConversationHandler.END

# ── Режим: Создание статьи ───────────────────────────────────────────────────

async def choose_article_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 Статья для SEO и GEO"],
        ["🔬 Статья-исследование"],
        ["📰 Новостной обзор"],
        ["🏠"]
    ]
    await update.message.reply_text(
        "🚀 <b>Создание статьи с помощью AI-агентов</b>\n\n"
        "Выберите формат статьи:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_ARTICLE_MODE

async def handle_article_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    mode = update.message.text.strip()
    if mode not in ["🎯 Статья для SEO и GEO", "🔬 Статья-исследование", "📰 Новостной обзор"]:
        await update.message.reply_text("Пожалуйста, выберите формат из предложенных кнопок.")
        return WAIT_ARTICLE_MODE
    
    ctx.user_data["article_mode"] = mode
    
    if ctx.user_data.get("article_topic"):
        topic = ctx.user_data["article_topic"]
        status_msg = await update.message.reply_text("⏳ Генерирую метаданные статьи с помощью Llama...")
        title, slug, query = gen_article_metadata(topic, mode)
        ctx.user_data["article_title"] = title
        ctx.user_data["article_slug"] = slug
        ctx.user_data["article_query"] = query

        try:
            await status_msg.delete()
        except Exception:
            pass

        keyboard = [
            ["✅ Подтвердить и запустить"],
            ["🔄 Сгенерировать заново"],
            ["🏠"]
        ]
        await update.message.reply_text(
            f"📋 <b>Черновик настроек статьи:</b>\n\n"
            f"⚙️ <b>Формат:</b> {mode}\n"
            f"💡 <b>Тема:</b> {topic}\n"
            f"📝 <b>Заголовок H1:</b> {title}\n"
            f"🔗 <b>Slug:</b> {slug}\n"
            f"🔍 <b>Поисковый запрос:</b> {query}\n\n"
            f"Подтвердите запуск генерации роем агентов:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return WAIT_ARTICLE_CONFIRM

    await update.message.reply_text(
        f"Выбран формат: <b>{mode}</b>\n\n"
        f"Отправьте тему статьи текстовым сообщением или запишите голосовое с подробным описанием идеи:",
        parse_mode="HTML",
        reply_markup=NAV_KEYBOARD
    )
    return WAIT_ARTICLE_TOPIC

async def choose_article_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🚀 <b>Создание статьи с помощью AI-агентов</b>\n\n"
        "Отправьте тему статьи текстовым сообщением или запишите голосовое с подробным описанием идеи:",
        parse_mode="HTML",
        reply_markup=NAV_KEYBOARD
    )
    return WAIT_ARTICLE_TOPIC

async def handle_article_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    # If voice, transcribe it first
    if update.message.voice or update.message.audio:
        text = await _transcribe_voice(update, ctx)
        if text is None:
            return WAIT_ARTICLE_TOPIC
    else:
        text = update.message.text.strip()

    if not text:
        await update.message.reply_text("Тема не может быть пустой. Попробуйте еще раз.")
        return WAIT_ARTICLE_TOPIC

    ctx.user_data["article_topic"] = text
    status_msg = await update.message.reply_text("⏳ Генерирую метаданные статьи с помощью Llama...")
    
    # Generate metadata
    mode = ctx.user_data.get("article_mode", "🎯 Статья для SEO и GEO")
    title, slug, query = gen_article_metadata(text, mode)
    ctx.user_data["article_title"] = title
    ctx.user_data["article_slug"] = slug
    ctx.user_data["article_query"] = query

    try:
        await status_msg.delete()
    except Exception:
        pass

    keyboard = [
        ["✅ Подтвердить и запустить"],
        ["🔄 Сгенерировать заново"],
        ["🏠"]
    ]
    await update.message.reply_text(
        f"📋 <b>Черновик настроек статьи:</b>\n\n"
        f"⚙️ <b>Формат:</b> {mode}\n"
        f"💡 <b>Тема:</b> {text}\n"
        f"📝 <b>Заголовок H1:</b> {title}\n"
        f"🔗 <b>Slug:</b> {slug}\n"
        f"🔍 <b>Поисковый запрос:</b> {query}\n\n"
        f"Подтвердите запуск генерации роем агентов:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_ARTICLE_CONFIRM

async def handle_article_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    mode = ctx.user_data.get("article_mode", "🎯 Статья для SEO и GEO")
    if text == "🔄 Сгенерировать заново":
        topic = ctx.user_data.get("article_topic")
        if not topic:
            await update.message.reply_text("Что-то пошло не так, вернитесь в главное меню.", reply_markup=MAIN_KEYBOARD)
            return ConversationHandler.END
        status_msg = await update.message.reply_text("⏳ Генерирую новые метаданные...")
        title, slug, query = gen_article_metadata(topic, mode)
        ctx.user_data["article_title"] = title
        ctx.user_data["article_slug"] = slug
        ctx.user_data["article_query"] = query
        
        try:
            await status_msg.delete()
        except Exception:
            pass

        keyboard = [
            ["✅ Подтвердить и запустить"],
            ["🔄 Сгенерировать заново"],
            ["🏠"]
        ]
        await update.message.reply_text(
            f"📋 <b>Новый черновик настроек статьи:</b>\n\n"
            f"⚙️ <b>Формат:</b> {mode}\n"
            f"💡 <b>Тема:</b> {topic}\n"
            f"📝 <b>Заголовок H1:</b> {title}\n"
            f"🔗 <b>Slug:</b> {slug}\n"
            f"🔍 <b>Поисковый запрос:</b> {query}\n\n"
            f"Подтвердите запуск генерации:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return WAIT_ARTICLE_CONFIRM

    elif text == "✅ Подтвердить и запустить":
        topic = ctx.user_data.get("article_topic")
        title = ctx.user_data.get("article_title")
        slug = ctx.user_data.get("article_slug")
        query = ctx.user_data.get("article_query")

        if not all([topic, title, slug, query]):
            await update.message.reply_text("Ошибка: утеряны данные настроек. Попробуйте сначала.", reply_markup=MAIN_KEYBOARD)
            return ConversationHandler.END

        await update.message.reply_text(
            f"🚀 <b>Запускаю конвейер генерации статьи!</b>\n\n"
            f"⚙️ <b>Формат:</b> {mode}\n"
            f"Рой из 9 агентов начал работу в фоновом режиме.\n"
            f"Я буду присылать уведомления о каждом шаге и запрошу подтверждение на шаге 4 (исследование) и шаге 12 (публикация).",
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD
        )

        # Run orchestrator.py in background
        import subprocess
        cmd = [
            sys.executable,
            "scripts/orchestrator.py",
            "--topic", topic,
            "--title", title,
            "--slug", slug,
            "--query", query,
            "--mode", mode
        ]
        log.info("Starting orchestrator in background: %s", cmd)
        try:
            project_root = Path(__file__).parent.parent
            log_file_path = project_root / "orchestrator.log"
            log_file = open(log_file_path, "a", encoding="utf-8")
            subprocess.Popen(cmd, cwd=project_root, stdout=log_file, stderr=log_file)
        except Exception as e:
            log.error("Failed to start orchestrator: %s", e)
            await update.message.reply_text(f"❌ Ошибка запуска: {e}", reply_markup=MAIN_KEYBOARD)

        return ConversationHandler.END

    return WAIT_ARTICLE_CONFIRM

async def _transcribe_voice_msg(message, ctx: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    voice = message.voice or message.audio
    if not voice:
        return None
    file = await ctx.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    await file.download_to_drive(tmp_path)
    try:
        return transcribe(tmp_path)
    except Exception as e:
        log.error("Transcription error: %s", e)
        return None
    finally:
        tmp_path.unlink(missing_ok=True)

async def handle_reply_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    original_msg = update.message.reply_to_message
    if not original_msg:
        await update.message.reply_text("Этот метод работает только как ответ (Reply) на сообщение.")
        return ConversationHandler.END

    original_text = ""
    if original_msg.text:
        original_text = original_msg.text
    elif original_msg.caption:
        original_text = original_msg.caption
    elif original_msg.voice or original_msg.audio:
        status_msg = await update.message.reply_text("Транскрибирую исходное голосовое сообщение...")
        original_text = await _transcribe_voice_msg(original_msg, ctx)
        try:
            await status_msg.delete()
        except Exception:
            pass

    reply_text = ""
    if update.message.text:
        reply_text = update.message.text.strip()
    elif update.message.voice or update.message.audio:
        reply_text = await _transcribe_voice(update, ctx)

    if not reply_text:
        await update.message.reply_text("Не удалось распознать текст вашего ответа.")
        return ConversationHandler.END

    topic = f"Контекст: {original_text}\nИнструкция: {reply_text}" if original_text else reply_text
    
    ctx.user_data.clear()
    ctx.user_data["article_topic"] = topic

    keyboard = [
        ["🎯 Статья для SEO и GEO"],
        ["🔬 Статья-исследование"],
        ["📰 Новостной обзор"],
        ["🏠"]
    ]
    await update.message.reply_text(
        f"🚀 <b>Создание задачи из Reply</b>\n\n"
        f"Тема сформирована из ответа на сообщение.\n"
        f"Выберите формат статьи:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_ARTICLE_MODE

async def handle_forwarded_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if "forward_buffer" not in ctx.user_data:
        ctx.user_data["forward_buffer"] = []
        ctx.user_data["forward_media"] = []

    text = update.message.text or update.message.caption or ""
    text = text.strip()

    photo = update.message.photo
    if photo:
        status_msg = await update.message.reply_text("Скачиваю медиа из пересланного сообщения...")
        file = await ctx.bot.get_file(photo[-1].file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        await file.download_to_drive(tmp_path)
        try:
            photo_bytes = tmp_path.read_bytes()
            now = datetime.now(timezone.utc)
            import random
            rand_id = random.randint(1000, 9999)
            filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{rand_id}.jpg"
            rel_path = f"docs/articles/media/{filename}"
            
            # Сохраняем медиафайл
            gh_write_bin(rel_path, photo_bytes, f"media: {filename}")
            
            markdown_link = f"\n\n[Медиа](media/{filename})\n\n"
            if text:
                text = text + markdown_link
            else:
                text = markdown_link
                
            ctx.user_data["forward_media"].append(rel_path)
        except Exception as e:
            log.error("Failed to download media: %s", e)
            await update.message.reply_text(f"Ошибка загрузки медиа: {e}")
        finally:
            try:
                await status_msg.delete()
            except Exception:
                pass
            tmp_path.unlink(missing_ok=True)

    if not text and not photo:
        await update.message.reply_text("Поддерживаются только текстовые сообщения и фотографии.")
        return WAIT_FORWARD_ACTION

    if text:
        ctx.user_data["forward_buffer"].append(text)

    # Удаляем предыдущее сообщение о буфере для чистоты чата
    if "forward_status_msg_id" in ctx.user_data:
        try:
            await ctx.bot.delete_message(chat_id=update.effective_chat.id, message_id=ctx.user_data["forward_status_msg_id"])
        except Exception:
            pass

    keyboard = [
        ["📰 Создать новость", "🚀 Создать статью"],
        ["📚 Добавить в базу знаний", "🧹 Очистить буфер"],
        ["🏠"]
    ]
    count = len(ctx.user_data["forward_buffer"])
    msg = await update.message.reply_text(
        f"📥 Сообщение добавлено в буфер (всего собранных сообщений: {count}).\n\n"
        f"Вы можете переслать ещё сообщения или выбрать действие на клавиатуре:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    ctx.user_data["forward_status_msg_id"] = msg.message_id
    return WAIT_FORWARD_ACTION

async def handle_forward_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    action = update.message.text.strip()
    buffer = ctx.user_data.get("forward_buffer", [])

    if "forward_status_msg_id" in ctx.user_data:
        try:
            await ctx.bot.delete_message(chat_id=update.effective_chat.id, message_id=ctx.user_data["forward_status_msg_id"])
        except Exception:
            pass
        ctx.user_data.pop("forward_status_msg_id", None)

    if not buffer and action != "🧹 Очистить буфер":
        await update.message.reply_text("Буфер пересланных сообщений пуст.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    combined_text = "\n\n---\n\n".join(buffer)

    if action == "🧹 Очистить буфер":
        ctx.user_data.pop("forward_buffer", None)
        ctx.user_data.pop("forward_media", None)
        await update.message.reply_text("🧹 Буфер пересланных сообщений очищен.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    elif action == "📚 Добавить в базу знаний":
        ctx.user_data["text"] = combined_text
        ctx.user_data["duration"] = 0
        
        ctx.user_data.pop("forward_buffer", None)
        ctx.user_data.pop("forward_media", None)

        keyboard = [[cat] for cat in CATEGORIES] + [["➕ Своя категория"], ["🏠"]]
        await update.message.reply_text(
            "Выбери категорию для базы знаний:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        )
        return WAIT_CATEGORY

    elif action == "🚀 Создать статью":
        ctx.user_data["article_topic"] = combined_text
        
        ctx.user_data.pop("forward_buffer", None)
        ctx.user_data.pop("forward_media", None)

        keyboard = [
            ["🎯 Статья для SEO и GEO"],
            ["🔬 Статья-исследование"],
            ["📰 Новостной обзор"],
            ["🏠"]
        ]
        await update.message.reply_text(
            f"🚀 <b>Создание задачи из репостов</b>\n\n"
            f"Тема сформирована из пересланных сообщений.\n"
            f"Выберите формат статьи:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return WAIT_ARTICLE_MODE

    elif action == "📰 Создать новость":
        ctx.user_data["news_item"] = {
            "title": "Материалы из репоста",
            "body": combined_text,
            "url": ""
        }
        
        ctx.user_data.pop("forward_buffer", None)
        ctx.user_data.pop("forward_media", None)

        await update.message.reply_text(
            f"🎙 <b>Материалы из репоста</b>\n\n"
            f"Запишите ваш экспертный комментарий к этим материалам: что думаете, согласны или нет, как это работает на практике?",
            parse_mode="HTML",
            reply_markup=NAV_KEYBOARD,
        )
        return WAIT_NEWS_VOICE

    else:
        await update.message.reply_text("Неверный выбор. Пожалуйста, используйте кнопки на клавиатуре.")
        return WAIT_FORWARD_ACTION

async def handle_voice_note_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🎙 <b>Запись голосовой заметки</b>\n\n"
        "Отправьте или запишите голосовое сообщение (аудиозаметку) прямо в этот чат.\n"
        "Я автоматически переведу его в текст, помогу выбрать категорию и сохраню в базу знаний.",
        parse_mode="HTML",
        reply_markup=NAV_KEYBOARD
    )
    return WAIT_VOICE_NOTE

# ── Список заметок ────────────────────────────────────────────────────────────

async def menu_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    files = gh_list("knowledge/voice")[:5]
    if files:
        repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
        branch = os.environ.get("GITHUB_BRANCH", "main")
        
        lines = []
        for n in files:
            url = f"https://github.com/{repo}/blob/{branch}/knowledge/voice/{urllib.parse.quote(n)}"
            lines.append(f"• <a href=\"{url}\">{n}</a>")
            
        await update.message.reply_text(
            "<b>Последние заметки:</b>\n\n" + "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.message.reply_text("Заметок пока нет.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END

async def handle_text_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    review_file = Path("business/review_waiting.txt")
    if review_file.exists():
        text = update.message.text.strip()
        latest_reply = Path("business/latest_reply.json")
        latest_reply.write_text(json.dumps({
            "timestamp": time.time(),
            "type": "text",
            "content": text
        }, ensure_ascii=False), encoding="utf-8")
        await update.message.reply_text("✅ Ответ передан в генератор статьи.")
        return
    
    await update.message.reply_text(
        "Я не понял эту команду. Пожалуйста, используйте кнопки меню или отправьте голосовую заметку.",
        reply_markup=MAIN_KEYBOARD
    )

# ── Запуск ────────────────────────────────────────────────────────────────────

async def telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    import traceback
    log.error("Исключение при обработке апдейта:", exc_info=context.error)
    
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    
    error_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "error_type": type(context.error).__name__,
        "error_message": str(context.error),
        "traceback": tb_string,
        "source": "telegram_bot_handler",
        "update": str(update) if update else None
    }
    
    try:
        content = json.dumps(error_data, ensure_ascii=False, indent=2)
        gh_write("critical_error.json", content, f"fail: bot handler exception [{type(context.error).__name__}]")
        print("  [auto-healer] Сигнальный файл о сбое в обработчике успешно отправлен на GitHub")
    except Exception as e:
        print(f"[AUTO-HEALER ERROR] Не удалось отправить сигнальный файл на GitHub: {e}")
        
    if update and hasattr(update, "effective_message") and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ <b>Технический сбой.</b> Отчет отправлен ИИ-агенту, автоисправление применится в течение нескольких минут.",
                parse_mode="HTML"
            )
        except Exception:
            pass

async def post_init(application: Application) -> None:
    from telegram import BotCommand
    await application.bot.set_my_commands([
        BotCommand("start", "Главное меню / Запуск"),
        BotCommand("cancel", "Сбросить текущий режим / Отмена")
    ])

def main() -> None:
    result = 1 / 0
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if not (token := os.getenv("TG_BOT_TOKEN")):
        sys.exit("Нет TG_BOT_TOKEN")
    if not os.getenv("GROQ_KEY"):
        sys.exit("Нет GROQ_KEY")

    mode = "GitHub API" if os.getenv("GITHUB_TOKEN") else "локальный диск"
    print(f"Бот запущен | Сохранение: {mode}")

    app = Application.builder().token(token).post_init(post_init).build()
    app.add_error_handler(telegram_error_handler)

    home_filter = filters.Regex("^(🏠|🏠 Главное меню)$")

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
            MessageHandler(filters.Regex("^💡 Экспертиза$"), choose_expert_topic),
            MessageHandler(filters.Regex("^💼 Бизнес$"), choose_biz_topic),
            MessageHandler(filters.Regex("^🎯 Аудитория$"), choose_aud_topic),
            MessageHandler(filters.Regex("^📋 Заметки$"), menu_list),
            MessageHandler(filters.Regex("^📰 Новости ниши$"), choose_news_topic),
            MessageHandler(filters.Regex("^🚀 Создать статью$"), choose_article_mode),
            MessageHandler(filters.Regex("^🎤 Голосовая заметка$"), handle_voice_note_button),
            MessageHandler(filters.FORWARDED, handle_forwarded_message),
            MessageHandler(filters.REPLY & ~filters.COMMAND, handle_reply_entry),
        ],
        states={
            WAIT_CATEGORY: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category),
            ],
            WAIT_CUSTOM_CATEGORY: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_category),
            ],
            WAIT_EXPERT_TOPIC: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expert_topic),
            ],
            WAIT_EXPERT_QUERY: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expert_query),
            ],
            WAIT_EXPERT_PICK: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expert_pick),
            ],
            WAIT_EXPERT_VOICE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, expert_voice),
            ],
            WAIT_BIZ_TOPIC: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_biz_topic),
            ],
            WAIT_BIZ_QUERY: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_biz_query),
            ],
            WAIT_BIZ_PICK: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, biz_pick),
            ],
            WAIT_BIZ_VOICE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, biz_voice),
            ],
            WAIT_AUD_TOPIC: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_aud_topic),
            ],
            WAIT_AUD_QUERY: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_aud_query),
            ],
            WAIT_AUD_ANSWER: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, audience_answer),
            ],
            WAIT_AUD_CONFIRM: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, audience_confirm),
            ],
            WAIT_NEWS_TOPIC: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_news_topic),
            ],
            WAIT_NEWS_QUERY: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_news_query),
            ],
            WAIT_NEWS_PICK: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, news_pick),
            ],
            WAIT_NEWS_VOICE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, news_voice),
            ],
            WAIT_ARTICLE_MODE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_article_mode),
            ],
            WAIT_ARTICLE_TOPIC: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_article_topic),
                MessageHandler(filters.VOICE | filters.AUDIO, handle_article_topic),
            ],
            WAIT_ARTICLE_CONFIRM: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_article_confirm),
            ],
            WAIT_FORWARD_ACTION: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_forward_action),
            ],
            WAIT_VOICE_NOTE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    if port_str := os.getenv("PORT"):
        port = int(port_str)
        external_url = os.getenv("RENDER_EXTERNAL_URL")
        if not external_url:
            sys.exit("Error: RENDER_EXTERNAL_URL is not set in environment variables")
        
        print(f"Starting webhook on port {port} with URL {external_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"{external_url.rstrip('/')}/{token}",
            drop_pending_updates=True
        )
    else:
        print("Starting polling...")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        tb_string = "".join(traceback.format_exception(None, e, e.__traceback__))
        error_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": tb_string,
            "source": "telegram_bot_startup"
        }
        print(f"Критическая ошибка при запуске бота: {e}")
        try:
            content = json.dumps(error_data, ensure_ascii=False, indent=2)
            gh_write("critical_error.json", content, "fail: bot startup crash")
            print("Сигнальный файл о сбое запуска успешно отправлен на GitHub")
        except Exception as push_err:
            print(f"Не удалось отправить сигнальный файл о сбое запуска на GitHub: {push_err}")
        sys.exit(1)
