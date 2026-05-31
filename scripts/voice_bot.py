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

import os, re, sys, base64, logging, tempfile, urllib.request, urllib.parse, json, asyncio
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
WAIT_CUSTOM_CATEGORY = 10
WAIT_NEWS_TOPIC    = 11
WAIT_NEWS_QUERY    = 12
WAIT_EXPERT_TOPIC  = 13
WAIT_EXPERT_QUERY  = 14
WAIT_BIZ_TOPIC     = 15
WAIT_BIZ_QUERY     = 16
WAIT_AUD_TOPIC     = 17
WAIT_AUD_QUERY     = 18

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

NEWS_QUERY = "нейросети искусственный интеллект маркетинг 2026"

NEWS_TOPICS = {
    "🎯 VK-реклама": "VK-реклама таргетинг продвижение новости",
    "🤖 Нейросети и ИИ": "нейросети искусственный интеллект маркетинг 2026",
    "🪙 Криптовалюта": "криптовалюта биткоин трейдинг новости",
}

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

    await send_transcript(update, text)

    keyboard = [[cat] for cat in CATEGORIES] + [["➕ Своя категория"], ["🏠 Главное меню"]]
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

async def handle_custom_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
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
        await update.message.reply_text(f"✅ Сохранено в категорию «{category}»: `{filename}`", parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    return ConversationHandler.END

# ── Режим: Экспертиза ─────────────────────────────────────────────────────────

async def choose_expert_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
        ["🪙 Криптовалюта", "➕ Другая тема"],
        ["🏠 Главное меню"]
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
    await update.message.reply_text(f"⏳ Читаю базу знаний и генерирую вопросы по теме «{topic}»...")
    files = gh_list("knowledge/voice")[:5]
    context_parts = [gh_read(f"knowledge/voice/{f}")[:400] for f in files if f]
    context = "\n---\n".join(context_parts)
    questions = gen_expert_questions(topic, context)
    ctx.user_data["expert_questions"] = questions
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

    keyboard = [[cat] for cat in CATEGORIES] + [["➕ Своя категория"], ["🏠 Главное меню"]]
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
        ["🏠 Главное меню"]
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
    
    await update.message.reply_text(f"⏳ Смотрю что уже есть по теме «{topic}» и генерирую вопросы...")
    existing = gh_read(f"business/products_{slug}.md")
    questions = gen_business_questions(topic, existing)
    ctx.user_data["biz_questions"] = questions
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
        ["🏠 Главное меню"]
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
    await update.message.reply_text("⏳ Все ответы собраны. Генерирую профиль ЦА...")
    profile = gen_audience_profile(topic, answers)
    ctx.user_data["aud_profile"] = profile

    await update.message.reply_text(
        f"📊 *Профиль целевой аудитории для темы «{topic}»:*\n\n{profile}",
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

def fetch_news(query: str, max_results: int = 15) -> list[dict]:
    """Ищет свежие новости через DuckDuckGo, возвращает list[{title, url, body}]."""
    articles = []
    seen_urls = set()
    
    # 1. Пробуем новостной поиск
    try:
        results = list(DDGS().news(query, max_results=max_results * 2))
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls and is_article_url(url):
                articles.append(r)
                seen_urls.add(url)
    except Exception as e:
        log.warning("News fetch error (news): %s", e)
        
    # 2. Добираем через текстовый поиск, если нашли мало статей
    if len(articles) < 5:
        try:
            results = list(DDGS().text(query, max_results=max_results * 2, region="ru-ru"))
            for r in results:
                url = r.get("href", "")
                if url and url not in seen_urls and is_article_url(url):
                    articles.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "body": r.get("body", ""),
                        "source": "",
                        "date": ""
                    })
                    seen_urls.add(url)
        except Exception as e:
            log.warning("News fetch error (text): %s", e)
            
    return articles[:max_results]

async def choose_news_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
        ["🪙 Криптовалюта", "➕ Другая тема"],
        ["🏠 Главное меню"]
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
    
    await update.message.reply_text(f"⏳ Ищу свежие новости по теме «{topic_name}»...")
    pool = fetch_news(query, max_results=15)

    if not pool:
        await update.message.reply_text(
            f"Не удалось найти новости по теме «{topic_name}». Попробуй другой запрос.",
            reply_markup=ReplyKeyboardMarkup([
                ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
                ["🪙 Криптовалюта", "➕ Другая тема"],
                ["🏠 Главное меню"]
            ], resize_keyboard=True)
        )
        return WAIT_NEWS_TOPIC

    # Выбираем случайные 3 из пула
    import random
    random.shuffle(pool)
    items = pool[:3]

    ctx.user_data["news_items"] = items
    lines = []
    import html
    for i, item in enumerate(items, 1):
        emoji = ["1️⃣", "2️⃣", "3️⃣"][i - 1]
        title_escaped = html.escape(item.get('title', '—'))
        source_escaped = html.escape(item.get('source', ''))
        url = item.get('url', '')
        
        lines.append(f"{emoji} <b>{title_escaped}</b>\n🔗 <a href=\"{url}\">Читать новость</a>\n<i>{source_escaped}</i> • {item.get('date', '')[:10]}")
        if item.get("body"):
            body_escaped = html.escape(item['body'][:120])
            lines.append(f"↳ {body_escaped}…")
        lines.append("")

    keyboard_rows = []
    if items:
        number_buttons = ["1️⃣", "2️⃣", "3️⃣"][:len(items)]
        keyboard_rows.append(number_buttons)
    keyboard_rows.append(["🔄 Новые новости"])
    keyboard_rows.append(["🏠 Главное меню"])

    await update.message.reply_text(
        f"📰 <b>Свежие новости по теме «{topic_name}»:</b>\n\n" + "\n".join(lines).strip()
        + "\n\nВыбери новость и запиши свой комментарий эксперта:",
        parse_mode="HTML",
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
        return await start_news_search(update, ctx)

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

    await send_transcript(update, text)

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

async def post_init(application: Application) -> None:
    from telegram import BotCommand
    await application.bot.set_my_commands([
        BotCommand("start", "Главное меню / Запуск"),
        BotCommand("cancel", "Сбросить текущий режим / Отмена")
    ])

def main() -> None:
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

    home_filter = filters.Regex("^🏠 Главное меню$")

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
            MessageHandler(filters.Regex("^💡 Экспертиза$"), choose_expert_topic),
            MessageHandler(filters.Regex("^💼 Бизнес$"), choose_biz_topic),
            MessageHandler(filters.Regex("^🎯 Аудитория$"), choose_aud_topic),
            MessageHandler(filters.Regex("^📋 Заметки$"), menu_list),
            MessageHandler(filters.Regex("^📰 Новости ниши$"), choose_news_topic),
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
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)

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
    main()
