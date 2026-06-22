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
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from datetime import datetime, timezone
from typing import Optional

from groq import Groq
from ddgs import DDGS
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters, TypeHandler,
    ApplicationHandlerStop,
)

# Настройка логирования в консоль и в файл bot.log
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent.parent / "bot.log", encoding="utf-8", mode="a")
    ]
)
log = logging.getLogger(__name__)

# Fallback functions for WebSocket wakeup broadcast and local transcription
def broadcast_ws_wakeup(task_id):
    pass

async def transcribe_via_local_pc(audio_path):
    return None

# Monkey-patch python-telegram-bot's webhook server to handle GET / requests with a 200 OK status
# and WebSocket wakeup connection at /ws/wakeup
try:
    import tornado.web
    import tornado.websocket
    from telegram.ext._utils.webhookhandler import WebhookAppClass, TelegramHandler
    
    ws_clients = set()
    pending_transcriptions = {}
    
    class RootHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("OK")
            
    class PCWakeupWebSocketHandler(tornado.websocket.WebSocketHandler):
        def check_origin(self, origin):
            return True
            
        def open(self):
            log.info("PC Task Listener WebSocket connected!")
            ws_clients.add(self)
            
        def on_close(self):
            log.info("PC Task Listener WebSocket disconnected!")
            if self in ws_clients:
                ws_clients.remove(self)
                
        def on_message(self, message):
            try:
                log.info("Received message from PC WebSocket: %s", message[:200])
                data = json.loads(message)
                if data.get("type") == "transcribe_response":
                    req_id = data.get("request_id")
                    if req_id in pending_transcriptions:
                        future = pending_transcriptions.get(req_id)
                        if future and not future.done():
                            future.set_result(data)
            except Exception as e:
                log.error("Error processing WebSocket message: %s", e)

    def broadcast_ws_wakeup_impl(task_id):
        import json
        payload = json.dumps({"type": "wakeup", "task_id": task_id, "timestamp": time.time()})
        log.info("Broadcasting WAKEUP to %d WebSocket client(s)", len(ws_clients))
        for client in list(ws_clients):
            try:
                client.write_message(payload)
            except Exception as e:
                log.error("Failed to write message to WS client: %s", e)
                if client in ws_clients:
                    ws_clients.remove(client)

    async def transcribe_via_local_pc_impl(audio_path):
        if not ws_clients:
            log.info("No PC WebSocket client connected. Skipping local transcription.")
            return None
            
        import base64
        import uuid
        import asyncio
        
        req_id = str(uuid.uuid4())
        log.info("Starting local PC transcription for %s. Request ID: %s", audio_path.name, req_id)
        
        try:
            with open(audio_path, "rb") as f:
                audio_data = base64.b64encode(f.read()).decode("utf-8")
                
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            pending_transcriptions[req_id] = future
            
            payload = json.dumps({
                "type": "transcribe_request",
                "request_id": req_id,
                "audio_data": audio_data,
                "file_ext": audio_path.suffix or ".ogg"
            })
            
            for client in list(ws_clients):
                try:
                    client.write_message(payload)
                except Exception as ce:
                    log.error("Failed to send transcribe request to client: %s", ce)
                    if client in ws_clients:
                        ws_clients.remove(client)
                        
            try:
                result_data = await asyncio.wait_for(future, timeout=45.0)
                if result_data.get("error"):
                    log.warning("Local PC transcription returned error: %s", result_data.get("error"))
                    return None
                text = result_data.get("text")
                if text:
                    log.info("Local PC transcription succeeded! Request ID: %s", req_id)
                    return text
            except asyncio.TimeoutError:
                log.warning("Local PC transcription timed out! Request ID: %s", req_id)
        except Exception as e:
            log.error("Error during local PC transcription: %s", e)
        finally:
            if req_id in pending_transcriptions:
                del pending_transcriptions[req_id]
                
        return None

    broadcast_ws_wakeup = broadcast_ws_wakeup_impl
    transcribe_via_local_pc = transcribe_via_local_pc_impl
            
    def patched_init(self, webhook_path, bot, update_queue, secret_token=None):
        self.shared_objects = {
            "bot": bot,
            "update_queue": update_queue,
            "secret_token": secret_token,
        }
        handlers = [
            (r"/?", RootHandler),
            (r"/ws/wakeup/?", PCWakeupWebSocketHandler),
            (rf"{webhook_path}/?", TelegramHandler, self.shared_objects)
        ]
        tornado.web.Application.__init__(self, handlers)
        
    WebhookAppClass.__init__ = patched_init
    log.info("Successfully monkey-patched WebhookAppClass to handle GET / and WS /ws/wakeup")
except Exception as patch_err:
    log.error("Failed to monkey-patch WebhookAppClass: %s", patch_err)

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
WAIT_TRANSCRIPT_ACTION = 24
WAIT_SUMMARY_ACTION = 25
WAIT_POST_COMMENT = 26

# ── Глобальные переменные статуса сборщика ────────────────────────────────────
LAST_HARVESTER_RUN = None
LAST_HARVESTER_ERROR = None

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

TASK_CHANNEL_ID = -1004378273791

NAV_KEYBOARD = ReplyKeyboardMarkup(
    [["🏠"]],
    resize_keyboard=True,
)

TRANSCRIPT_ACTION_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["💾 Сохранить в базу", "📝 Пост+Коммент"],
        ["✨ Восстановить речь", "📖 Разбить на абзацы"],
        ["🎬 Свернутый конспект", "📊 Сделать саммари"],
        ["📢 Отправить ИИ-агенту", "🚀 Создать статью"],
        ["🏠 Главное меню"]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

NUMS = {"1️⃣": 0, "2️⃣": 1, "3️⃣": 2}

# ── Работа с файлами (GitHub API или локальный диск) ──────────────────────────

def _gh_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "content-factory-bot/1.0"
    }

def gh_read(path: str) -> str:
    if not os.environ.get("GITHUB_TOKEN"):
        p = Path(__file__).parent.parent / path
        return p.read_text("utf-8") if p.exists() else ""
    repo = os.environ.get("GITHUB_REPO") or "xopromo/content-factory"
    branch = os.environ.get("GITHUB_BRANCH") or "main"
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={branch}"
    try:
        req = urllib.request.Request(url, headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            return base64.b64decode(d["content"].replace("\n", "")).decode("utf-8")
    except Exception:
        return ""

def gh_list_dir(path: str) -> list[dict]:
    if not os.environ.get("GITHUB_TOKEN"):
        p = Path(__file__).parent.parent / path
        if not p.exists():
            return []
        return [{"name": f.name, "type": "file"} for f in p.glob("*")]
    repo = os.environ.get("GITHUB_REPO") or "xopromo/content-factory"
    branch = os.environ.get("GITHUB_BRANCH") or "main"
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={branch}"
    try:
        req = urllib.request.Request(url, headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read())
            if isinstance(res, list):
                return res
    except Exception:
        pass
    return []

def gh_write(path: str, content: str, message: str) -> str:
    try:
        p = Path(__file__).parent.parent / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")
    except Exception as local_err:
        log.error("Failed to write local file in gh_write: %s", local_err)

    repo = os.environ.get("GITHUB_REPO") or "xopromo/content-factory"
    is_public = (repo == "xopromo/content-factory")
    if (is_public and path.startswith("knowledge/voice/")) or not os.environ.get("GITHUB_TOKEN"):
        return str(Path(__file__).parent.parent / path)
    branch = os.environ.get("GITHUB_BRANCH") or "main"
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    sha = None
    try:
        req = urllib.request.Request(url + f"?ref={branch}", headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read()).get("sha")
    except Exception:
        pass
    if "[skip render]" not in message:
        message = f"{message} [skip render]"
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    # Retry loop (up to 3 attempts) for writing to GitHub
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={**_gh_headers(), "Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                result = json.loads(r.read())
                return result.get("content", {}).get("html_url", path)
        except Exception as e:
            log.warning(f"gh_write attempt {attempt + 1}/3 failed: {e}")
            if attempt == 2:
                log.error("All gh_write attempts failed. Gracefully falling back to local file.")
                return str(Path(__file__).parent.parent / path)
            time.sleep(2)

def gh_write_bin(path: str, data: bytes, message: str) -> str:
    try:
        p = Path(__file__).parent.parent / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    except Exception as local_err:
        log.error("Failed to write local bin file in gh_write_bin: %s", local_err)

    repo = os.environ.get("GITHUB_REPO") or "xopromo/content-factory"
    is_public = (repo == "xopromo/content-factory")
    if (is_public and path.startswith("knowledge/voice/")) or not os.environ.get("GITHUB_TOKEN"):
        return str(Path(__file__).parent.parent / path)
    branch = os.environ.get("GITHUB_BRANCH") or "main"
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    sha = None
    try:
        req = urllib.request.Request(url + f"?ref={branch}", headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read()).get("sha")
    except Exception:
        pass
    if "[skip render]" not in message:
        message = f"{message} [skip render]"
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
    repo = os.environ.get("GITHUB_REPO") or "xopromo/content-factory"
    branch = os.environ.get("GITHUB_BRANCH") or "main"
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
    errors = []
    
    # 1. Попытка через Groq (Whisper)
    try:
        client = Groq(api_key=os.environ["GROQ_KEY"])
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=(audio_path.name, f),
                model="whisper-large-v3",
                language="ru",
                response_format="text",
            )
        return result.strip()
    except Exception as e:
        err_msg = f"Groq Whisper failed: {e}"
        log.warning(err_msg)
        errors.append(err_msg)

    # 2. Резервная попытка через Pollinations (whisper)
    try:
        import json
        import urllib.request
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        
        # Pollinations имеет OpenAI-совместимый эндпоинт для аудио/транскрипции или может принимать файлы
        # Но проще и надежнее использовать официальный API Gemini Flash, так как он принимает аудио файлы в base64
        # и отлично понимает речь прямо в рамках prompt'а.
        pass
    except Exception:
        pass

    # 3. Резервная попытка через Google Gemini 2.0 Flash REST (передача аудио в base64)
    gemini_key = os.environ.get("GEMINI_KEY")
    if gemini_key:
        try:
            import base64
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")
            
            # Определяем MIME тип
            suffix = audio_path.suffix.lower()
            mime_type = "audio/ogg"
            if suffix == ".mp3":
                mime_type = "audio/mp3"
            elif suffix == ".wav":
                mime_type = "audio/wav"
            elif suffix == ".m4a":
                mime_type = "audio/m4a"
                
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"inlineData": {"mimeType": mime_type, "data": audio_b64}},
                        {"text": "Напиши точную транскрипцию этой аудиозаписи на русском языке. Верни только текст транскрипции, без каких-либо комментариев."}
                    ]
                }],
                "generationConfig": {"temperature": 0.0}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                log.info("Successfully transcribed voice using Gemini 2.0 Flash REST fallback!")
                return text
        except Exception as gemini_err:
            err_msg = f"Gemini fallback transcription failed: {gemini_err}"
            log.warning(err_msg)
            errors.append(err_msg)

    detailed_errors = "; ".join(errors)
    raise RuntimeError(f"Все методы транскрипции завершились ошибкой: {detailed_errors}")


def llm_chat(prompt: str, system: str = "") -> str:
    """Sends chat prompt to shared llm_client"""
    from scripts.utils.llm_client import run_fast_common
    full_prompt = f"System Instructions: {system}\n\nUser Request:\n{prompt}" if system else prompt
    content, _ = run_fast_common(full_prompt, quality="strong")
    return content


# ── Генерация вопросов ────────────────────────────────────────────────────────

def gen_expert_questions(topic: str, context: str) -> list[str]:
    existing = f"Уже есть в базе знаний по этой теме:\n{context}" if context.strip() else "База знаний пока пуста."
    try:
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
        if questions:
            return questions[:3]
    except Exception as e:
        log.error("Failed to generate expert questions: %s", e)
    
    return [
        f"Расскажи про свой самый интересный кейс в теме «{topic}».",
        f"Какие главные ошибки совершают специалисты в теме «{topic}»?",
        f"С чего лучше всего начать продвижение/работу в теме «{topic}»?"
    ]

def gen_business_questions(topic: str, existing: str) -> list[str]:
    context = f"Уже описано для направления «{topic}»:\n{existing[:1500]}" if existing.strip() and existing.strip() != "# Продукты и услуги" else "Описания пока нет."
    try:
        result = llm_chat(
            f"""{context}

Придумай ровно 3 вопроса для описания продуктов, услуг и офферов в теме/направлении: «{topic}».
Спрашивай то, чего ещё нет выше: конкретные офферы, цены, тарифы, результаты клиентов, УТП, гарантии.
Только 3 вопроса, каждый на отдельной строке, без нумерации.""",
            f"Ты помогаешь заполнить описание бизнеса в направлении «{topic}» для контент-маркетинга.",
        )
        questions = [q.strip() for q in result.splitlines() if q.strip() and not q.strip().startswith("#")]
        if questions:
            return questions[:3]
    except Exception as e:
        log.error("Failed to generate business questions: %s", e)
        
    return [
        f"Какие продукты или услуги ты предлагаешь по направлению «{topic}»?",
        f"Какова стоимость твоих услуг или тарифная сетка в направлении «{topic}»?",
        f"Какое главное преимущество (УТП) твоих предложений по теме «{topic}»?"
    ]

def gen_audience_profile(topic: str, answers: list[tuple[str, str]]) -> str:
    qa_text = "\n\n".join(f"Вопрос: {q}\nОтвет: {a}" for q, a in answers)
    try:
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
    except Exception as e:
        log.error("Failed to generate audience profile: %s", e)
        return f"""## Демография
- Целевая аудитория в теме: {topic}

## Главная боль и запрос
- Требуется детальное описание болей (ошибка генерации профиля).

## Что пробовал раньше
- Различные стандартные решения.

## Где находится онлайн
- Социальные сети, тематические сообщества.

## Ключевые возражения
- Стоимость, сомнения в результате, нехватка времени.

## Желаемый результат
- Быстрый и качественный результат.

## Поисковые запросы (5–7 фраз)
- Как настроить {topic}
- Продвижение {topic}
- Обучение {topic}"""

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
    
    try:
        result = llm_chat(prompt, system="Ты помощник по планированию контента.")
        cleaned = result.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        data = json.loads(cleaned.strip())
        slug = data["slug"]
        if len(slug) > 50:
            slug = slug[:50].strip("_-")
        return data["title"], slug, data["query"]
    except Exception as e:
        log.error("Failed to generate/parse article metadata: %s", e)
        slug = get_topic_slug(topic)
        return f"Статья: {topic}", slug, topic

# ── Вспомогательные ───────────────────────────────────────────────────────────

def get_topic_slug(topic: str) -> str:
    cyr = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    lat = "a b v g d e yo zh z i j k l m n o p r s t u f kh ts ch sh shch '' y ' e yu ya".split()
    tr = {c: l for c, l in zip(cyr, lat)}
    
    s = topic.lower().strip()
    s_tr = "".join(tr.get(c, c) for c in s)
    s_clean = re.sub(r"[^a-z0-9_\-]", "_", s_tr)
    s_clean = re.sub(r"_+", "_", s_clean).strip("_")
    # Cap slug length to 50 chars to avoid OS "File name too long" errors (Errno 36)
    return s_clean[:50].strip("_") or "general"

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
    parse_mode = "HTML" if ("<" in text and ">" in text) else "Markdown"
    
    if parse_mode == "HTML":
        header_fn = lambda idx, total: f"📝 <b>Транскрипт ({idx}/{total}):</b>\n\n" if total > 1 else "📝 <b>Транскрипт:</b>\n\n"
    else:
        header_fn = lambda idx, total: f"📝 *Транскрипт ({idx}/{total}):*\n\n" if total > 1 else "📝 *Транскрипт:*\n\n"

    if len(text) <= LIMIT:
        header = header_fn(1, 1)
        await update.message.reply_text(header + text, parse_mode=parse_mode)
        return
        
    chunks = [text[i:i + LIMIT] for i in range(0, len(text), LIMIT)]
    for idx, chunk in enumerate(chunks, 1):
        header = header_fn(idx, len(chunks))
        await update.message.reply_text(header + chunk, parse_mode=parse_mode)

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

async def _download_and_transcribe_media(message, ctx: ContextTypes.DEFAULT_TYPE, status_msg=None) -> Optional[str]:
    media_obj = None
    media_type = None  # "audio" or "video"
    
    if message.voice:
        media_obj = message.voice
        media_type = "audio"
    elif message.audio:
        media_obj = message.audio
        media_type = "audio"
    elif message.video:
        media_obj = message.video
        media_type = "video"
    elif message.video_note:
        media_obj = message.video_note
        media_type = "video"
    elif message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("audio/"):
            media_obj = message.document
            media_type = "audio"
        elif mime.startswith("video/"):
            media_obj = message.document
            media_type = "video"
            
    if not media_obj:
        return None
        
    if status_msg:
        try:
            await status_msg.edit_text("Скачиваю медиафайл...")
        except Exception:
            pass
        
    file = await ctx.bot.get_file(media_obj.file_id)
    
    # Generate appropriate suffix
    orig_name = getattr(media_obj, "file_name", None) or "input"
    suffix = Path(orig_name).suffix or (".mp4" if media_type == "video" else ".ogg")
    
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        
    await file.download_to_drive(tmp_path)
    
    transcribe_path = tmp_path
    extracted_audio_path = None
    
    try:
        if media_type == "video":
            if status_msg:
                try:
                    await status_msg.edit_text("Извлекаю аудиодорожку...")
                except Exception:
                    pass
            ffmpeg_exe = "ffmpeg"
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                pass
            
            extracted_audio_path = tmp_path.with_suffix(".ogg")
            # Run ffmpeg to extract audio
            cmd = [
                ffmpeg_exe, "-y", "-i", str(tmp_path),
                "-vn", "-acodec", "libvorbis", "-ac", "1", "-ar", "16000",
                str(extracted_audio_path)
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            await process.wait()
            if extracted_audio_path.exists() and extracted_audio_path.stat().st_size > 0:
                transcribe_path = extracted_audio_path
            else:
                log.warning("ffmpeg audio extraction failed, attempting direct Whisper transcription of video")
                
        if status_msg:
            try:
                await status_msg.edit_text("Транскрибирую (запрос на ПК)...")
            except Exception:
                pass
                
        # Try local PC transcription first (over WS)
        res = await transcribe_via_local_pc(transcribe_path)
        if res:
            return res
            
        # Fallback to cloud APIs
        if status_msg:
            try:
                await status_msg.edit_text("Локальный Whisper недоступен. Расшифровываю через облако...")
            except Exception:
                pass
        res = transcribe(transcribe_path)
        return res
    except Exception as e:
        log.error("Transcription error: %s", e)
        if status_msg:
            try:
                await status_msg.edit_text(f"Ошибка транскрипции: {e}")
            except Exception:
                pass
        return None
    finally:
        tmp_path.unlink(missing_ok=True)
        if extracted_audio_path:
            extracted_audio_path.unlink(missing_ok=True)

async def _transcribe_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    message = update.message
    if not message:
        return None
        
    media_obj = message.voice or message.audio or message.video or message.video_note or message.document
    if media_obj:
        file_size = getattr(media_obj, "file_size", 0)
        MAX_SIZE = 20 * 1024 * 1024  # 20 MB
        if file_size > MAX_SIZE:
            size_mb = file_size / (1024 * 1024)
            await message.reply_text(
                f"⚠️ Файл слишком большой ({size_mb:.1f} МБ).\n"
                f"Telegram Bot API разрешает скачивать файлы размером не более 20 МБ.\n"
                f"Пожалуйста, сожмите видео или отправьте файл меньшего размера."
            )
            return None

    status_msg = await message.reply_text("Получаю медиафайл...")
    res = await _download_and_transcribe_media(message, ctx, status_msg)
    try:
        await status_msg.delete()
    except Exception:
        pass
    if res is None:
        await message.reply_text("Не удалось транскрибировать медиафайл.", reply_markup=MAIN_KEYBOARD)
    return res

# ── Вспомогательные функции очистки чата ──────────────────────────────────────

async def _delete_message_after_delay(bot, chat_id: int, message_id: int, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def _send_menu_with_cleanup(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode="HTML"):
    # Удаляем входящую команду / клик пользователя, если это текст и не медиафайл
    if update.message:
        has_media = any([
            update.message.voice, update.message.audio, update.message.video,
            update.message.video_note, update.message.document, update.message.photo
        ])
        if not has_media:
            try:
                await update.message.delete()
            except Exception:
                pass
    # Удаляем предыдущее меню
    old_id = ctx.user_data.get("last_menu_msg_id")
    if old_id:
        try:
            await ctx.bot.delete_message(chat_id=update.effective_chat.id, message_id=old_id)
        except Exception:
            pass
    # Отправляем новое меню
    msg = await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    ctx.user_data["last_menu_msg_id"] = msg.message_id
    return msg

def _clear_user_data_except_menu(ctx: ContextTypes.DEFAULT_TYPE):
    menu_id = ctx.user_data.get("last_menu_msg_id")
    forward_id = ctx.user_data.get("forward_status_msg_id")
    ctx.user_data.clear()
    if menu_id is not None:
        ctx.user_data["last_menu_msg_id"] = menu_id
    if forward_id is not None:
        ctx.user_data["forward_status_msg_id"] = forward_id

# ── Команды ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_menu_with_cleanup(
        update, ctx,
        "Привет! Выбери режим или просто отправь голосовое.",
        reply_markup=MAIN_KEYBOARD,
    )

async def cmd_version(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
    commit_hash = "Unknown"
    commit_date = "04.06.2026 22:45"
    try:
        import subprocess
        commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
        commit_date = subprocess.check_output(["git", "log", "-1", "--format=%cd", "--date=format:%d.%m.%Y %H:%M"]).decode().strip()
    except Exception:
        pass
    
    msg = await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"🤖 <b>Версия бота:</b>\n"
            f"• <b>Коммит:</b> <code>{commit_hash}</code>\n"
            f"• <b>Дата сборки:</b> {commit_date}\n"
            f"• <b>Провайдеры LLM:</b> Gemini, Groq, Mistral, Cerebras, Pollinations AI\n"
            f"• <b>Режим:</b> Webhook (Render)"
        ),
        parse_mode="HTML"
    )
    asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 30))

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_user_data_except_menu(ctx)
    msg = await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Отменено."
    )
    asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
    await _send_menu_with_cleanup(
        update, ctx,
        "Главное меню:",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END

async def go_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_user_data_except_menu(ctx)
    await _send_menu_with_cleanup(
        update, ctx,
        "Главное меню:",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END

# ── Режим: обычная голосовая заметка ─────────────────────────────────────────

async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        reply_to = update.message.reply_to_message
        ctx.user_data["reply_to_message_id"] = reply_to.message_id if reply_to else None
    # ── Делегирование голосовых сообщений активным сценариям ───────────────────
    if "article_mode" in ctx.user_data and "article_topic" not in ctx.user_data:
        return await handle_article_topic(update, ctx)
    if "expert_question" in ctx.user_data:
        return await expert_voice(update, ctx)
    if "biz_question" in ctx.user_data:
        return await biz_voice(update, ctx)
    if "aud_index" in ctx.user_data:
        return await audience_answer(update, ctx)
    if "news_item" in ctx.user_data:
        return await news_voice(update, ctx)
    if ctx.user_data.get("waiting_comment"):
        return await handle_post_comment(update, ctx)

    review_file = ROOT / "business" / "review_waiting.txt"
    if review_file.exists():
        text = await _transcribe_voice(update, ctx)
        if text:
            latest_reply = ROOT / "business" / "latest_reply.json"
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
    media = update.message.voice or update.message.audio or update.message.video or update.message.video_note
    ctx.user_data["duration"] = getattr(media, "duration", 0) if media else 0

    await send_transcript(update, text)

    await _send_menu_with_cleanup(
        update, ctx,
        "Что сделать с этой записью?",
        reply_markup=TRANSCRIPT_ACTION_KEYBOARD,
    )
    return WAIT_TRANSCRIPT_ACTION

async def handle_transcript_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    action = update.message.text.strip()
    text = ctx.user_data.get("text", "")
    
    if action == "🏠 Главное меню":
        _clear_user_data_except_menu(ctx)
        await _send_menu_with_cleanup(update, ctx, "Главное меню:", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
        
    elif action == "💾 Сохранить в базу":
        keyboard = [[cat] for cat in CATEGORIES] + [["➕ Своя категория"], ["🏠"]]
        await _send_menu_with_cleanup(
            update, ctx,
            "Выбери категорию для сохранения:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        )
        return WAIT_CATEGORY

    elif action == "📝 Пост+Коммент":
        ctx.user_data["waiting_comment"] = True
        await update.message.reply_text(
            "🎙 <b>Режим «Пост+Коммент»</b>\n\n"
            "Запишите ваш голосовой комментарий или пришлите его текстом. "
            "Я оформлю исходный пост в виде цитаты и прикреплю ваш комментарий.",
            parse_mode="HTML",
            reply_markup=NAV_KEYBOARD
        )
        return WAIT_POST_COMMENT
        
    elif action == "✨ Восстановить речь":
        if not text:
            msg = await update.message.reply_text("Нет текста для восстановления.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
            return WAIT_TRANSCRIPT_ACTION
            
        status_msg = await update.message.reply_text("✨ Восстанавливаю речь с помощью AI (убираю заикания, исправляю ошибки)...")
        clean_prompt = (
            "Ты профессиональный редактор. Твоя задача — очистить транскрибированный текст голосовой заметки.\n"
            "1. Удали все заикания, повторы слов, междометия и слова-паразиты (э-э, ну, как бы, типа, вот, значит, это самое и т.д.).\n"
            "2. Исправь грамматические, пунктуационные и орфографические ошибки.\n"
            "3. Сделай предложения более плавными и логичными, но ПОЛНОСТЬЮ сохрани исходный смысл, ключевые факты и тон автора.\n"
            "4. НЕ добавляй никаких собственных выводов, комментариев, приветствий или объяснений. Верни ТОЛЬКО очищенный текст."
        )
        try:
            cleaned_text = llm_chat(text, system=clean_prompt)
            ctx.user_data["text"] = cleaned_text
            try:
                await status_msg.delete()
            except Exception:
                pass
            await send_transcript(update, cleaned_text)
            
            await _send_menu_with_cleanup(
                update, ctx,
                "Речь успешно восстановлена! Что сделать дальше?",
                reply_markup=TRANSCRIPT_ACTION_KEYBOARD,
            )
        except Exception as e:
            log.error("Speech restoration failed: %s", e)
            try:
                await status_msg.delete()
            except Exception:
                pass
            msg = await update.message.reply_text(f"Не удалось восстановить речь: {e}")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
            
        return WAIT_TRANSCRIPT_ACTION
        
    elif action == "📖 Разбить на абзацы":
        if not text:
            msg = await update.message.reply_text("Нет текста для разбиения на абзацы.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
            return WAIT_TRANSCRIPT_ACTION
            
        status_msg = await update.message.reply_text("📖 Разбиваю текст на логические абзацы с помощью AI...")
        paragraph_prompt = (
            "Разбей следующий транскрибированный текст на логические абзацы.\n"
            "Правила:\n"
            "1. Раздели текст на смысловые абзацы с помощью пустых строк (двойного переноса строки).\n"
            "2. НЕ изменяй слова, формулировки или смысл. НЕ исправляй ошибки и не редактируй сам текст.\n"
            "3. НЕ добавляй никаких собственных выводов, комментариев, приветствий или объяснений. Верни ТОЛЬКО исходный текст, разделенный на абзацы."
        )
        try:
            paragraphed_text = llm_chat(text, system=paragraph_prompt)
            ctx.user_data["text"] = paragraphed_text
            try:
                await status_msg.delete()
            except Exception:
                pass
            await send_transcript(update, paragraphed_text)
            
            await _send_menu_with_cleanup(
                update, ctx,
                "Текст успешно разбит на абзацы! Что сделать дальше?",
                reply_markup=TRANSCRIPT_ACTION_KEYBOARD,
            )
        except Exception as e:
            log.error("Paragraph splitting failed: %s", e)
            try:
                await status_msg.delete()
            except Exception:
                pass
            msg = await update.message.reply_text(f"Не удалось разбить текст на абзацы: {e}")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
            
        return WAIT_TRANSCRIPT_ACTION

    elif action == "🎬 Свернутый конспект":
        if not text:
            msg = await update.message.reply_text("Нет текста для создания конспекта.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
            return WAIT_TRANSCRIPT_ACTION
            
        status_msg = await update.message.reply_text("🎬 Создаю свернутый интерактивный конспект с помощью AI...")
        collapse_prompt = (
            "Сделай структурированный интерактивный конспект (outline) следующего транскрибированного текста.\n"
            "Правила оформления:\n"
            "1. Раздели текст на смысловые блоки.\n"
            "2. Для каждого блока напиши емкий жирный заголовок-тезис с помощью HTML-тега <b>Заголовок-тезис</b>.\n"
            "3. Помести подробный текст этого блока внутрь тега раскрывающейся цитаты Telegram: <blockquote expandable>текст блока</blockquote>. Это критически важно! Тег должен быть строго в формате <blockquote expandable>...</blockquote>.\n"
            "4. Убедись, что все HTML-теги правильно закрыты (<b>...</b> и <blockquote expandable>...</blockquote>) and не пересекаются.\n"
            "5. НЕ используй никакую Markdown-разметку (никаких *, _, ` и т.д.), чтобы избежать ошибок разметки в Telegram.\n"
            "6. НЕ добавляй приветствий, мета-комментариев или объяснений. Верни ТОЛЬКО структурированный HTML-текст конспекта."
        )
        try:
            collapsed_text = llm_chat(text, system=collapse_prompt)
            # Remove any markdown code blocks model might wrap it in, e.g. ```html ... ```
            collapsed_text = re.sub(r"^```[a-zA-Z0-9]*\n", "", collapsed_text)
            collapsed_text = re.sub(r"\n```$", "", collapsed_text)
            collapsed_text = collapsed_text.strip()
            
            ctx.user_data["text"] = collapsed_text
            try:
                await status_msg.delete()
            except Exception:
                pass
            await send_transcript(update, collapsed_text)
            
            await _send_menu_with_cleanup(
                update, ctx,
                "Свернутый конспект готов! Что сделать дальше?",
                reply_markup=TRANSCRIPT_ACTION_KEYBOARD,
            )
        except Exception as e:
            log.error("Collapsible outline failed: %s", e)
            try:
                await status_msg.delete()
            except Exception:
                pass
            msg = await update.message.reply_text(f"Не удалось создать свернутый конспект: {e}")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
            
        return WAIT_TRANSCRIPT_ACTION
        
    elif action == "📢 Отправить ИИ-агенту":
        if not text:
            msg = await update.message.reply_text("Нет текста задачи для отправки.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
            return WAIT_TRANSCRIPT_ACTION
            
        status_msg = await update.message.reply_text("Ок")
        try:
            # Отправляем задачу в наш ИИ-канал
            task_msg = await ctx.bot.send_message(
                chat_id=TASK_CHANNEL_ID,
                text=text,
                parse_mode="HTML"
            )
            
            # Запись задачи в docs/articles/tasks.json на GitHub
            if not os.environ.get("GITHUB_TOKEN"):
                await update.message.reply_text(
                    "⚠️ <b>Внимание:</b> Переменная окружения <code>GITHUB_TOKEN</code> не настроена на сервере Render. "
                    "Не удалось синхронизировать задачу с GitHub. Настройте токен в панели управления Render.",
                    parse_mode="HTML"
                )
            else:
                try:
                    tasks_content = gh_read("docs/articles/tasks.json")
                    tasks = []
                    if tasks_content:
                        try:
                            tasks = json.loads(tasks_content)
                        except Exception as je:
                            log.error("Failed to parse existing tasks.json: %s", je)
                    
                    next_id = 1
                    if tasks:
                        next_id = max(t.get("id", 0) for t in tasks) + 1
                    
                    new_task = {
                        "id": next_id,
                        "message_id": task_msg.message_id,
                        "reply_to_message_id": ctx.user_data.get("reply_to_message_id"),
                        "text": text,
                        "status": "pending",
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    tasks.append(new_task)
                    
                    gh_write(
                        "docs/articles/tasks.json",
                        json.dumps(tasks, indent=2, ensure_ascii=False),
                        f"task: add task #{next_id}"
                    )
                    log.info("Successfully added task #%s to tasks.json on GitHub", next_id)
                    try:
                        broadcast_ws_wakeup(next_id)
                    except Exception as ws_ex:
                        log.error("Failed to broadcast WS wakeup: %s", ws_ex)
                except Exception as gh_err:
                    log.error("Failed to sync task with GitHub tasks.json: %s", gh_err)
                    try:
                        await update.message.reply_text(f"❌ Ошибка синхронизации с GitHub: {gh_err}")
                    except Exception:
                        pass

            try:
                await status_msg.delete()
            except Exception:
                pass
            await update.message.reply_text(
                "✅ Задача успешно отправлена!",
                reply_markup=MAIN_KEYBOARD,
                parse_mode="HTML"
            )
            return ConversationHandler.END
        except Exception as e:
            log.error("Failed to forward task to channel: %s", e)
            try:
                await status_msg.delete()
            except Exception:
                pass
            msg = await update.message.reply_text(f"❌ Не удалось отправить задачу: {e}\nУбедитесь, что бот добавлен администратором в канал задач.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
            return WAIT_TRANSCRIPT_ACTION

    elif action in ["🚀 Создать статью", "🚀 Создать статью на эту тему"]:
        if not text:
            msg = await update.message.reply_text("Нет темы/текста для генерации статьи.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
            return WAIT_TRANSCRIPT_ACTION
            
        instruction = ctx.user_data.get("reply_instruction", "")
        topic = f"Контекст: {text}\nИнструкция: {instruction}" if instruction else text
        ctx.user_data["article_topic"] = topic
        ctx.user_data.pop("reply_instruction", None)
        
        keyboard = [
            ["🎯 Статья для SEO и GEO"],
            ["🔬 Статья-исследование"],
            ["📰 Новостной обзор"],
            ["🏠"]
        ]
        await _send_menu_with_cleanup(
            update, ctx,
            f"🚀 <b>Создание задачи на написание статьи</b>\n\n"
            f"Тема сформирована из выбранного сообщения.\n"
            f"Выберите формат статьи:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return WAIT_ARTICLE_MODE

    elif action == "📊 Сделать саммари":
        if not text:
            msg = await update.message.reply_text("Нет текста для саммаризации.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
            return WAIT_TRANSCRIPT_ACTION
            
        status_msg = await update.message.reply_text("📊 Создаю саммари с помощью AI...")
        summary_prompt = (
            "Сделай краткое структурированное саммари (выжимку) следующего текста на русском языке.\n"
            "Выдели ключевые мысли, важные факты, цифры и выводы в виде маркированного списка.\n"
            "Будь лаконичен и структурирован. Не пиши приветствий или мета-комментариев."
        )
        try:
            summary_text = llm_chat(text, system=summary_prompt)
            ctx.user_data["summary_text"] = summary_text
            try:
                await status_msg.delete()
            except Exception:
                pass
            await update.message.reply_text(f"📊 *Саммари записи:*\n\n{summary_text}", parse_mode="Markdown")
            
            keyboard = [
                ["💾 Сохранить саммари в базу"],
                ["💾 Сохранить весь текст"],
                ["🏠 Главное меню"]
            ]
            await _send_menu_with_cleanup(
                update, ctx,
                "Что сделать дальше?",
                reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
            )
            return WAIT_SUMMARY_ACTION
        except Exception as e:
            log.error("Summarization failed: %s", e)
            try:
                await status_msg.delete()
            except Exception:
                pass
            msg = await update.message.reply_text(f"Не удалось сгенерировать саммари: {e}")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
            
        return WAIT_TRANSCRIPT_ACTION
        
    else:
        msg = await update.message.reply_text("Пожалуйста, выберите одно из действий на клавиатуре.")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
        return WAIT_TRANSCRIPT_ACTION

async def handle_summary_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    action = update.message.text.strip()
    
    if action == "🏠 Главное меню":
        _clear_user_data_except_menu(ctx)
        await _send_menu_with_cleanup(update, ctx, "Главное меню:", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END
        
    elif action == "💾 Сохранить саммари в базу":
        summary_text = ctx.user_data.get("summary_text", "")
        if not summary_text:
            msg = await update.message.reply_text("Нет саммари для сохранения.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
            return WAIT_TRANSCRIPT_ACTION
        # Replace main text with summary so handle_category saves it
        ctx.user_data["text"] = summary_text
        
        keyboard = [[cat] for cat in CATEGORIES] + [["➕ Своя категория"], ["🏠"]]
        await _send_menu_with_cleanup(
            update, ctx,
            "Выбери категорию для сохранения саммари:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        )
        return WAIT_CATEGORY
        
    elif action == "💾 Сохранить весь текст":
        keyboard = [[cat] for cat in CATEGORIES] + [["➕ Своя категория"], ["🏠"]]
        await _send_menu_with_cleanup(
            update, ctx,
            "Выбери категорию для сохранения всего текста:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        )
        return WAIT_CATEGORY
        
    else:
        msg = await update.message.reply_text("Пожалуйста, выберите одно из действий на клавиатуре.")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 5))
        return WAIT_SUMMARY_ACTION

async def handle_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    category = update.message.text.strip()
    note_text = ctx.user_data.get("text", "")
    duration = ctx.user_data.get("duration", 0)

    if category == "➕ Своя категория":
        await _send_menu_with_cleanup(
            update, ctx,
            "Введите название вашей категории:",
            reply_markup=NAV_KEYBOARD
        )
        return WAIT_CUSTOM_CATEGORY

    if not note_text and ctx.user_data.get("forward_buffer"):
        note_text = "\n\n---\n\n".join(ctx.user_data["forward_buffer"])

    if not note_text:
        await _send_menu_with_cleanup(update, ctx, "Что-то пошло не так, попробуй ещё раз.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    status_msg = await update.message.reply_text("Сохраняю...", reply_markup=ReplyKeyboardRemove())
    try:
        filename, content = format_voice_note(note_text, category, duration)
        url_or_path = await asyncio.to_thread(gh_write, f"knowledge/voice/{filename}", content, f"voice: {filename}")
        
        try:
            await status_msg.delete()
        except Exception:
            pass

        reply_markup = None
        
        msg_saved = await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Сохранено: `{filename}`", 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_saved.message_id, 10))
        
        await _send_menu_with_cleanup(update, ctx, "Возвращаюсь в главное меню:", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await _send_menu_with_cleanup(update, ctx, f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    _clear_user_data_except_menu(ctx)
    return ConversationHandler.END

async def handle_custom_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    category = update.message.text.strip()
    note_text = ctx.user_data.get("text", "")
    duration = ctx.user_data.get("duration", 0)

    if not note_text and ctx.user_data.get("forward_buffer"):
        note_text = "\n\n---\n\n".join(ctx.user_data["forward_buffer"])

    if not note_text:
        await _send_menu_with_cleanup(update, ctx, "Что-то пошло не так, попробуй ещё раз.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    status_msg = await update.message.reply_text("Сохраняю...", reply_markup=ReplyKeyboardRemove())
    try:
        filename, content = format_voice_note(note_text, category, duration)
        url_or_path = await asyncio.to_thread(gh_write, f"knowledge/voice/{filename}", content, f"voice: {filename}")
        
        try:
            await status_msg.delete()
        except Exception:
            pass

        reply_markup = None

        msg_saved = await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Сохранено в категорию «{category}»: `{filename}`", 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_saved.message_id, 10))
        
        await _send_menu_with_cleanup(update, ctx, "Возвращаюсь в главное меню:", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await _send_menu_with_cleanup(update, ctx, f"Ошибка сохранения: {e}", reply_markup=MAIN_KEYBOARD)

    _clear_user_data_except_menu(ctx)
    return ConversationHandler.END

# ── Режим: Экспертиза ─────────────────────────────────────────────────────────

async def choose_expert_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
        ["🪙 Криптовалюта", "➕ Другая тема"],
        ["🏠"]
    ]
    await _send_menu_with_cleanup(
        update, ctx,
        "Выбери тему для генерации вопросов экспертизы или нажми «➕ Другая тема»:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_EXPERT_TOPIC

async def handle_expert_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "➕ Другая тема":
        await _send_menu_with_cleanup(update, ctx, "Введите тему вашей экспертизы:", reply_markup=NAV_KEYBOARD)
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

    question = ctx.user_data.pop("expert_question", "")
    full_text = f"**Вопрос:** {question}\n\n**Ответ:** {text}" if question else text

    ctx.user_data["text"] = full_text
    media = update.message.voice or update.message.audio or update.message.video or update.message.video_note
    ctx.user_data["duration"] = getattr(media, "duration", 0) if media else 0

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
    await _send_menu_with_cleanup(
        update, ctx,
        "Выбери направление бизнеса для генерации вопросов или нажми «➕ Другая тема»:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_BIZ_TOPIC

async def handle_biz_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "➕ Другая тема":
        await _send_menu_with_cleanup(update, ctx, "Введите направление/тему бизнеса:", reply_markup=NAV_KEYBOARD)
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

    question = ctx.user_data.pop("biz_question", "")
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
        await asyncio.to_thread(gh_write, f"business/products_{slug}.md", new_content, f"business: {now.strftime('%Y-%m-%d')} ({slug})")
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
    await _send_menu_with_cleanup(
        update, ctx,
        "Выбери направление для анализа целевой аудитории или нажми «➕ Другая тема»:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_AUD_TOPIC

async def handle_aud_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "➕ Другая тема":
        await _send_menu_with_cleanup(update, ctx, "Введите направление/тему проекта:", reply_markup=NAV_KEYBOARD)
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

    ctx.user_data.pop("aud_index", None)
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
            await asyncio.to_thread(gh_write, f"business/audience_{slug}.md", content, f"audience: профиль ЦА {now.strftime('%Y-%m-%d')} ({slug})")
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

def parse_date(date_str: str, url: str = ""):
    try:
        from datetime import datetime
        if date_str:
            clean_str = date_str.replace('Z', '+00:00')
            return datetime.fromisoformat(clean_str)
    except Exception:
        pass
            
    if url:
        import re
        match = re.search(r'/(\d{4})[-/](\d{2})[-/](\d{2})/', url)
        if match:
            try:
                from datetime import datetime
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass
    return None

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

    # 1. Пробуем новостной поиск с фильтром по времени (сначала за день, потом за неделю)
    for limit in ("d", "w"):
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
        
    # 2. Добираем через текстовый поиск с ограничением за неделю, если нашли мало статей
    if len(articles) < 10:
        try:
            results = list(DDGS().text(query, max_results=max_results * 3, region="ru-ru", timelimit="w"))
            for r in results:
                add_article(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                    source=""
                )
        except Exception as e:
            log.warning("News fetch error (text): %s", e)
            
    # Фильтруем по дате с шагом в 1 сутки
    from datetime import datetime, timezone
    now_dt = datetime.now(timezone.utc)
    
    valid_articles = []
    for art in articles:
        art_dt = parse_date(art.get("date"), art.get("url"))
        if art_dt:
            if art_dt.tzinfo is None:
                art_dt = art_dt.replace(tzinfo=timezone.utc)
            art["parsed_datetime"] = art_dt
            valid_articles.append(art)
            
    if not valid_articles:
        return []

    filtered_articles = []
    for max_days in range(1, 8):  # Шаг от 1 до 7 суток
        filtered_articles = []
        for art in valid_articles:
            art_dt = art["parsed_datetime"]
            age_days = (now_dt - art_dt).days
            if age_days <= max_days:
                filtered_articles.append(art)
        # Если нашли хотя бы 5 статей, останавливаемся
        if len(filtered_articles) >= 5:
            break
            
    if filtered_articles:
        articles = filtered_articles
    else:
        articles = valid_articles

    # Сортируем: сначала самые свежие (по дате), при равенстве - по авторитетности (tier)
    def sort_key(art):
        dt_val = art.get("parsed_datetime", datetime.min.replace(tzinfo=timezone.utc))
        return (dt_val, 4 - art.get("tier", 3))

    articles.sort(key=sort_key, reverse=True)
    return articles

async def choose_news_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["🎯 VK-реклама", "🤖 Нейросети и ИИ"],
        ["🪙 Криптовалюта", "➕ Другая тема"],
        ["🏠"]
    ]
    await _send_menu_with_cleanup(
        update, ctx,
        "Выбери тему новостей или нажми «➕ Другая тема», чтобы ввести свой запрос:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAIT_NEWS_TOPIC

async def handle_news_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    
    if text == "➕ Другая тема":
        await _send_menu_with_cleanup(
            update, ctx,
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

def translate_to_russian_if_english(title: str, body: str) -> tuple[str, str]:
    import re
    has_english = bool(re.search(r'[a-zA-Z]{4,}', title + " " + body))
    has_russian = bool(re.search(r'[а-яА-ЯёЁ]{4,}', title + " " + body))
    if has_english and not has_russian:
        try:
            prompt = (
                f"Переведи заголовок и описание новости на русский язык. Сделай перевод естественным и кратким.\n\n"
                f"Заголовок: {title}\n"
                f"Описание: {body}\n\n"
                f"Верни ответ строго в формате JSON с ключами \"title\" и \"body\". Не добавляй никакого другого текста."
            )
            res = llm_chat(prompt, system="Ты технический переводчик.")
            res_clean = res.strip()
            if res_clean.startswith("```json"):
                res_clean = res_clean[7:]
            if res_clean.endswith("```"):
                res_clean = res_clean[:-3]
            data = json.loads(res_clean.strip())
            return data.get("title", title), data.get("body", body)
        except Exception:
            pass
    return title, body

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
    
    # Переводим англоязычные статьи на лету
    for item in items:
        if not item.get("translated", False):
            orig_title = item.get("title", "")
            orig_body = item.get("body", "")
            t_title, t_body = translate_to_russian_if_english(orig_title, orig_body)
            item["title"] = t_title
            item["body"] = t_body
            item["translated"] = True

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

    item = ctx.user_data.pop("news_item", {})
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

        reply_markup = None

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
    await _send_menu_with_cleanup(
        update, ctx,
        "🚀 <b>Создание статьи с помощью AI-агентов</b>\n\n"
        "Выберите формат статьи:",
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
        try:
            title, slug, query = gen_article_metadata(topic, mode)
            ctx.user_data["article_title"] = title
            ctx.user_data["article_slug"] = slug
            ctx.user_data["article_query"] = query
        finally:
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

    await _send_menu_with_cleanup(
        update, ctx,
        f"Выбран формат: <b>{mode}</b>\n\n"
        f"Отправьте тему статьи текстовым сообщением или запишите голосовое с подробным описанием идеи:",
        reply_markup=NAV_KEYBOARD
    )
    return WAIT_ARTICLE_TOPIC

async def choose_article_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await _send_menu_with_cleanup(
        update, ctx,
        "🚀 <b>Создание статьи с помощью AI-агентов</b>\n\n"
        "Отправьте тему статьи текстовым сообщением или запишите голосовое с подробным описанием идеи:",
        reply_markup=NAV_KEYBOARD
    )
    return WAIT_ARTICLE_TOPIC

async def handle_article_topic(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    # If voice, transcribe it first
    if update.message.voice or update.message.audio or update.message.video or update.message.video_note:
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
    try:
        # Generate metadata
        mode = ctx.user_data.get("article_mode", "🎯 Статья для SEO и GEO")
        title, slug, query = gen_article_metadata(text, mode)
        ctx.user_data["article_title"] = title
        ctx.user_data["article_slug"] = slug
        ctx.user_data["article_query"] = query
    finally:
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
        try:
            title, slug, query = gen_article_metadata(topic, mode)
            ctx.user_data["article_title"] = title
            ctx.user_data["article_slug"] = slug
            ctx.user_data["article_query"] = query
        finally:
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

        # Map mode to pipeline_mode
        pipeline_mode = "seo"
        if mode == "📰 Новостной обзор":
            pipeline_mode = "news"
        elif mode == "🔬 Статья-исследование":
            pipeline_mode = "full"

        # Run orchestrator.py in background
        import subprocess
        cmd = [
            sys.executable,
            "scripts/orchestrator.py",
            "--topic", topic,
            "--title", title,
            "--slug", slug,
            "--query", query,
            "--mode", mode,
            "--pipeline-mode", pipeline_mode,
            "--chat-id", str(update.effective_message.chat_id)
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
    return await _download_and_transcribe_media(message, ctx, status_msg=None)

async def handle_reply_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    original_msg = update.message.reply_to_message
    if not original_msg:
        await update.message.reply_text("Этот метод работает только как ответ (Reply) на сообщение.")
        return ConversationHandler.END

    review_file = ROOT / "business" / "review_waiting.txt"
    if review_file.exists():
        reply_text = ""
        if update.message.text:
            reply_text = update.message.text.strip()
        elif update.message.voice or update.message.audio or update.message.video or update.message.video_note:
            reply_text = await _transcribe_voice(update, ctx)
        
        if reply_text:
            latest_reply = ROOT / "business" / "latest_reply.json"
            latest_reply.write_text(json.dumps({
                "timestamp": time.time(),
                "type": "text" if update.message.text else "voice",
                "content": reply_text
            }, ensure_ascii=False), encoding="utf-8")
            await update.message.reply_text("✅ Ответ (через Reply) передан в генератор статьи.")
            return ConversationHandler.END

    original_text = ""
    if original_msg.text:
        original_text = original_msg.text
    elif original_msg.caption:
        original_text = original_msg.caption
    elif original_msg.voice or original_msg.audio or original_msg.video or original_msg.video_note:
        status_msg = await update.message.reply_text("Транскрибирую исходное медиасообщение...")
        original_text = await _transcribe_voice_msg(original_msg, ctx)
        try:
            await status_msg.delete()
        except Exception:
            pass

    reply_text = ""
    if update.message.text:
        reply_text = update.message.text.strip()
    elif update.message.voice or update.message.audio or update.message.video or update.message.video_note:
        reply_text = await _transcribe_voice(update, ctx)

    if not reply_text:
        await update.message.reply_text("Не удалось распознать текст вашего ответа.")
        return ConversationHandler.END

    FORMAT_ACTIONS = [
        "✨ Восстановить речь",
        "📖 Разбить на абзацы",
        "🎬 Свернутый конспект",
        "📊 Сделать саммари",
        "💾 Сохранить в базу",
        "📝 Пост+Коммент"
    ]
    if reply_text in FORMAT_ACTIONS:
        ctx.user_data["text"] = original_text
        # Also catch original message media to pass to post
        ctx.user_data["forward_media_ids"] = []
        if original_msg.photo:
            ctx.user_data["forward_media_ids"].append((original_msg.photo[-1].file_id, "photo"))
        elif original_msg.video:
            ctx.user_data["forward_media_ids"].append((original_msg.video.file_id, "video"))
        elif original_msg.document:
            ctx.user_data["forward_media_ids"].append((original_msg.document.file_id, "document"))
        return await handle_transcript_action(update, ctx)

    ctx.user_data["text"] = original_text
    ctx.user_data["reply_instruction"] = reply_text

    await update.message.reply_text(
        f"📥 <b>Получен текст сообщения и ваша инструкция.</b>\n\n"
        f"<b>Текст:</b>\n<i>{original_text[:300]}...</i>\n\n"
        f"<b>Инструкция:</b>\n<i>{reply_text}</i>\n\n"
        f"Выберите действие с этим материалом:",
        parse_mode="HTML",
        reply_markup=TRANSCRIPT_ACTION_KEYBOARD
    )
    return WAIT_TRANSCRIPT_ACTION

async def handle_forwarded_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if "forward_buffer" not in ctx.user_data:
        ctx.user_data["forward_buffer"] = []
        ctx.user_data["forward_media"] = []
        ctx.user_data["forward_media_ids"] = []

    text = update.message.text or update.message.caption or ""
    text = text.strip()

    media_obj = None
    media_type = None
    suffix = ".jpg"

    if update.message.photo:
        media_obj = update.message.photo[-1]
        media_type = "photo"
        suffix = ".jpg"
    elif update.message.video:
        media_obj = update.message.video
        media_type = "video"
        suffix = ".mp4"
    elif update.message.document:
        media_obj = update.message.document
        media_type = "document"
        suffix = Path(media_obj.file_name or "file").suffix or ".dat"

    if media_obj:
        status_msg = await update.message.reply_text("Сохраняю медиафайл локально...")
        try:
            file = await ctx.bot.get_file(media_obj.file_id)
            now = datetime.now(timezone.utc)
            import random
            rand_id = random.randint(1000, 9999)
            filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{rand_id}{suffix}"
            
            # Save strictly locally
            local_dir = Path(__file__).parent.parent / "docs" / "articles" / "media"
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / filename
            await file.download_to_drive(local_path)
            
            rel_path = f"docs/articles/media/{filename}"
            markdown_link = f"\n\n[Медиа](media/{filename})\n\n"
            if text:
                text = text + markdown_link
            else:
                text = markdown_link

            ctx.user_data["forward_media"].append(rel_path)
            ctx.user_data["forward_media_ids"].append((media_obj.file_id, media_type))
        except Exception as e:
            log.error("Failed to download media: %s", e)
            await update.message.reply_text(f"Ошибка загрузки медиа: {e}")
        finally:
            try:
                await status_msg.delete()
            except Exception:
                pass

    if not text and not media_obj:
        await update.message.reply_text("Поддерживаются только сообщения с текстом, фото, видео или документами.")
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
        ["📝 Пост+Коммент"],
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
        ctx.user_data.pop("forward_media_ids", None)
        await update.message.reply_text("🧹 Буфер пересланных сообщений очищен.", reply_markup=MAIN_KEYBOARD)
        return ConversationHandler.END

    elif action == "📝 Пост+Коммент":
        ctx.user_data["text"] = combined_text
        ctx.user_data["waiting_comment"] = True
        # Keep forward_media_ids in user_data to append them to the comment post later
        ctx.user_data.pop("forward_buffer", None)
        ctx.user_data.pop("forward_media", None)
        await update.message.reply_text(
            "🎙 <b>Режим «Пост+Коммент»</b>\n\n"
            "Запишите ваш голосовой комментарий или пришлите его текстом. "
            "Я оформлю исходный пост в виде цитаты и прикреплю ваш комментарий.",
            parse_mode="HTML",
            reply_markup=NAV_KEYBOARD
        )
        return WAIT_POST_COMMENT

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


async def handle_post_comment(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    # Get comment text
    comment_text = ""
    if update.message.text:
        comment_text = update.message.text.strip()
    elif update.message.voice or update.message.audio or update.message.video or update.message.video_note:
        status_msg = await update.message.reply_text("🎙 Распознаю ваш комментарий...")
        comment_text = await _transcribe_voice(update, ctx)
        try:
            await status_msg.delete()
        except Exception:
            pass

    if not comment_text:
        await update.message.reply_text("Не удалось получить комментарий. Пожалуйста, запишите голос или пришлите текст.")
        return WAIT_POST_COMMENT

    # Retrieve original text
    orig_text = ctx.user_data.get("text", "")
    
    # Strip any local media markdown links like [Медиа](media/...) or [Медиа](media\...)
    orig_text = re.sub(r"\s*\[Медиа\]\(media[/\\].*?\)\s*", "", orig_text).strip()
    
    # Format: Original text + Comment wrapped in <blockquote> with a label
    formatted_post = f"{orig_text}\n\n<b>Мой комментарий:</b>\n<blockquote>{comment_text}</blockquote>"
    
    # Retrieve media
    media_ids = ctx.user_data.get("forward_media_ids", [])
    
    chat_id = update.effective_chat.id
    
    try:
        if not media_ids:
            # Send text-only
            await ctx.bot.send_message(
                chat_id=chat_id,
                text=formatted_post,
                parse_mode="HTML"
            )
        elif len(media_ids) == 1:
            # Single media file
            file_id, media_type = media_ids[0]
            if len(formatted_post) <= 1024:
                if media_type == "photo":
                    await ctx.bot.send_photo(chat_id=chat_id, photo=file_id, caption=formatted_post, parse_mode="HTML")
                elif media_type == "video":
                    await ctx.bot.send_video(chat_id=chat_id, video=file_id, caption=formatted_post, parse_mode="HTML")
                else:
                    await ctx.bot.send_document(chat_id=chat_id, document=file_id, caption=formatted_post, parse_mode="HTML")
            else:
                # Text too long, send media first then text
                if media_type == "photo":
                    await ctx.bot.send_photo(chat_id=chat_id, photo=file_id)
                elif media_type == "video":
                    await ctx.bot.send_video(chat_id=chat_id, video=file_id)
                else:
                    await ctx.bot.send_document(chat_id=chat_id, document=file_id)
                await ctx.bot.send_message(chat_id=chat_id, text=formatted_post, parse_mode="HTML")
        else:
            # Media group (multiple files)
            media_group = []
            for i, (file_id, media_type) in enumerate(media_ids):
                # Attach caption to the first item only
                caption = formatted_post if (i == 0 and len(formatted_post) <= 1024) else None
                
                if media_type == "photo":
                    media_group.append(InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML" if caption else None))
                elif media_type == "video":
                    media_group.append(InputMediaVideo(media=file_id, caption=caption, parse_mode="HTML" if caption else None))
                else:
                    media_group.append(InputMediaDocument(media=file_id, caption=caption, parse_mode="HTML" if caption else None))
            
            await ctx.bot.send_media_group(chat_id=chat_id, media=media_group)
            
            # If text is too long for the first media caption, send it as a separate message
            if len(formatted_post) > 1024:
                await ctx.bot.send_message(chat_id=chat_id, text=formatted_post, parse_mode="HTML")
                
        await update.message.reply_text("✅ Пост с комментарием успешно сгенерирован и отправлен выше. Вы можете переслать его куда угодно в 1 клик!")
    except Exception as e:
        log.error("Failed to send post+comment: %s", e)
        await update.message.reply_text(f"⚠️ Ошибка отправки поста с комментарием: {e}\n\nПопробую прислать просто текстом:\n\n{formatted_post}", parse_mode="HTML")
    
    # Cleanup state
    _clear_user_data_except_menu(ctx)
    await _send_menu_with_cleanup(update, ctx, "Возвращаемся в главное меню:", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END

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
        repo = os.environ.get("GITHUB_REPO") or "xopromo/content-factory"
        branch = os.environ.get("GITHUB_BRANCH") or "main"
        
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

async def cmd_proxies(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
            
    # Отправляем сообщение о начале проверки
    status_msg = await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🔌 <b>Запуск проверки прокси...</b>\nПожалуйста, подождите.",
        parse_mode="HTML"
    )
    
    try:
        from scripts.check_proxies import check_all_proxies, generate_clickable_link
        working, dead = await check_all_proxies()
        
        # Удаляем временный статус
        try:
            await ctx.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)
        except Exception:
            pass
            
        if working:
            lines = [
                f"🔌 <b>Результаты проверки прокси:</b>",
                f"• Всего проверено: <code>{len(working) + len(dead)}</code>",
                f"• Рабочих: <code>{len(working)}</code>",
                f"• Нерабочих удалено: <code>{len(dead)}</code>",
                "",
                "<b>Список рабочих прокси (быстрые сверху):</b>"
            ]
            for i, p in enumerate(working, 1):
                link = generate_clickable_link(p)
                lines.append(f"{i}. <a href='{link}'>{p['type'].upper()} {p['server']}:{p['port']}</a> ({p['latency']}ms)")
                
            text_msg = "\n".join(lines)
        else:
            text_msg = (
                f"🔌 <b>Результаты проверки прокси:</b>\n"
                f"• Всего проверено: <code>{len(working) + len(dead)}</code>\n"
                f"• Рабочих: <code>0</code>\n"
                f"• Нерабочих удалено: <code>{len(dead)}</code>\n\n"
                f"❌ <b>Все прокси не работают!</b> Добавьте новые рабочие прокси."
            )
            
        # Отправляем финальное сообщение
        msg = await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text_msg,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        # Удаляем через 5 минут (300 сек) для чистоты чата
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 300))
        
        # Так как прокси-лист обновился (умершие удалены), нам нужно зафиксировать изменения на GitHub
        if dead:
            try:
                with open("proxies.txt", "r", encoding="utf-8") as f:
                    new_content = f.read()
                await asyncio.to_thread(gh_write, "proxies.txt", new_content, f"chore: prune {len(dead)} dead proxies")
            except Exception as e:
                print(f"Failed to push updated proxies.txt to GitHub: {e}")
                
    except Exception as e:
        try:
            await ctx.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)
        except Exception:
            pass
        msg = await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ <b>Ошибка при проверке прокси:</b>\n<code>{e}</code>",
            parse_mode="HTML"
        )
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 30))

async def cmd_harvester(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    global LAST_HARVESTER_RUN, LAST_HARVESTER_ERROR
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
            
    channel = os.getenv("TG_PROXY_CHANNEL")
    if not channel:
        msg = await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ <b>Канал для прокси не настроен!</b> Укажите <code>TG_PROXY_CHANNEL</code> в <code>.env</code>.",
            parse_mode="HTML"
        )
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 15))
        return
        
    status_msg = await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🔌 <b>Запуск сборщика прокси...</b>\nПроверяем и чистим канал {channel}. Пожалуйста, подождите.",
        parse_mode="HTML"
    )
    
    try:
        from scripts.proxy_harvester import run_harvester
        await run_harvester()
        
        LAST_HARVESTER_RUN = datetime.now()
        LAST_HARVESTER_ERROR = None
        
        try:
            await ctx.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)
        except Exception:
            pass
            
        msg = await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ <b>Работа сборщика завершена!</b>\nКанал {channel} успешно очищен от мертвых прокси и наполнен свежими.",
            parse_mode="HTML"
        )
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 30))
    except Exception as e:
        LAST_HARVESTER_ERROR = f"{type(e).__name__}: {e}"
        try:
            await ctx.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)
        except Exception:
            pass
        msg = await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ <b>Ошибка при работе сборщика:</b>\n<code>{e}</code>",
            parse_mode="HTML"
        )
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 30))

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
            
    proxy_channel = os.getenv("TG_PROXY_CHANNEL")
    github_token = os.getenv("GITHUB_TOKEN")
    vk_token = os.getenv("VK_TOKEN")
    if not vk_token:
        try:
            local_vk_config = ROOT.parent / "vk_config.json"
            if local_vk_config.exists():
                cfg = json.loads(local_vk_config.read_text(encoding="utf-8"))
                vk_token = cfg.get("token")
        except Exception:
            pass
            
    posted_count = 0
    last_run_str = "❌ Нет записей о запусках"
    try:
        state_path = ROOT / "posted_proxies.json"
        if state_path.exists():
            mtime = os.path.getmtime(state_path)
            last_run = datetime.fromtimestamp(mtime)
            last_run_str = last_run.strftime("%Y-%m-%d %H:%M:%S")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            posted_count = len(state)
    except Exception:
        pass
        
    last_run_mem = LAST_HARVESTER_RUN.strftime("%Y-%m-%d %H:%M:%S") if LAST_HARVESTER_RUN else "❌ Не запускался после старта бота"
    last_err_mem = LAST_HARVESTER_ERROR or "✅ Нет ошибок"
        
    state_dir = Path(__file__).parent.parent / "plans" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)

    if not slug:
        # Пытаемся получить список из GitHub
        state_files_info = await asyncio.to_thread(gh_list_dir, "plans/.state")

        # Загрузим и пропарсим локальные файлы состояния, отсортируем по saved_at
        local_states = []
        for f in state_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                saved_at = data.get("saved_at") or data.get("context", {}).get("saved_at", "")
                slug_val = data.get("slug")
                if slug_val:
                    local_states.append((saved_at, slug_val))
            except Exception:
                pass      
    lines = [
        "📊 <b>Статус и конфигурация сборщика прокси:</b>",
        f"• <b>Канал прокси (TG_PROXY_CHANNEL):</b> <code>{proxy_channel or '❌ Не настроен'}</code>",
        f"• <b>GitHub токен (GITHUB_TOKEN):</b> <code>{'✅ Настроен (длина: ' + str(len(github_token)) + ')' if github_token else '❌ Не настроен'}</code>",
        f"• <b>VK токен (VK_TOKEN):</b> <code>{'✅ Настроен (длина: ' + str(len(vk_token)) + ')' if vk_token else '❌ Не настроен'}</code>",
        f"• <b>Прокси в локальной базе:</b> <code>{posted_count}</code>",
        f"• <b>Последний запуск сборщика (в памяти):</b> <code>{last_run_mem}</code>",
        f"• <b>Последняя ошибка сборщика:</b> <code>{last_err_mem}</code>",
        f"• <b>Последнее изменение файла базы:</b> <code>{last_run_str}</code>",
        f"• <b>Режим работы бота:</b> <code>{'Webhook' if os.getenv('PORT') else 'Polling'}</code>",
    ]
    
    text_msg = "\n".join(lines)
    
    # Write status to GitHub for remote debugging
    try:
        status_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "proxy_channel": proxy_channel,
            "github_token_present": bool(github_token),
            "vk_token_present": bool(vk_token),
            "posted_count": posted_count,
            "last_harvester_run": last_run_mem,
            "last_harvester_error": last_err_mem,
            "last_run_str": last_run_str,
            "mode": 'Webhook' if os.getenv('PORT') else 'Polling'
        }
        from scripts.proxy_harvester import gh_write
        await asyncio.to_thread(gh_write, "docs/articles/bot_status.json", json.dumps(status_data, indent=2), "chore: update bot status from bot")
    except Exception as gh_err:
        log.error("Failed to write status to GitHub: %s", gh_err)

    msg = await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text_msg,
        parse_mode="HTML"
    )
    asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 60))

async def handle_text_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        reply_to = update.message.reply_to_message
        ctx.user_data["reply_to_message_id"] = reply_to.message_id if reply_to else None
    text = update.message.text.strip()
    
    # Перехватываем все кнопки устаревшей сессии (например, после перезапуска бота)
    news_buttons = [
        "🔄 Новые новости", "1️⃣", "2️⃣", "3️⃣",
        "🎯 VK-реклама", "🤖 Нейросети и ИИ", "🪙 Криптовалюта", "➕ Другая тема",
        "🏠", "🏠 Главное меню"
    ]
    if text in news_buttons:
        await update.message.reply_text(
            "⏳ Сессия была сброшена из-за обновления бота. Пожалуйста, начните заново, нажав на кнопку ниже:",
            reply_markup=MAIN_KEYBOARD
        )
        return

    review_file = ROOT / "business" / "review_waiting.txt"
    if review_file.exists():
        latest_reply = ROOT / "business" / "latest_reply.json"
        latest_reply.write_text(json.dumps({
            "timestamp": time.time(),
            "type": "text",
            "content": text
        }, ensure_ascii=False), encoding="utf-8")
        await update.message.reply_text("✅ Ответ передан в генератор статьи.")
        return
        
    # Проверяем, содержит ли входящий текст прокси
    lines = text.splitlines()
    new_proxies_found = []
    
    from scripts.check_proxies import parse_proxy_line
    for line in lines:
        parsed = parse_proxy_line(line)
        if parsed:
            new_proxies_found.append(parsed)
            
    if new_proxies_found:
        existing_raws = []
        if os.path.exists("proxies.txt"):
            with open("proxies.txt", "r", encoding="utf-8", errors="ignore") as f:
                existing_lines = f.readlines()
            for eline in existing_lines:
                eparsed = parse_proxy_line(eline)
                if eparsed:
                    existing_raws.append(eparsed["raw"])
                    
        added_count = 0
        all_raws = list(existing_raws)
        for p in new_proxies_found:
            if p["raw"] not in all_raws:
                all_raws.append(p["raw"])
                added_count += 1
                
        if added_count > 0:
            new_content = ""
            if os.path.exists("proxies.txt"):
                with open("proxies.txt", "r", encoding="utf-8", errors="ignore") as f:
                    old_lines = f.readlines()
                for oline in old_lines:
                    if oline.strip().startswith("#"):
                        new_content += oline
            
            if not new_content:
                new_content = f"# Updated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                
            for raw in all_raws:
                if raw not in new_content:
                    new_content += f"{raw}\n"
                    
            with open("proxies.txt", "w", encoding="utf-8") as f:
                f.write(new_content)
                
            try:
                await asyncio.to_thread(gh_write, "proxies.txt", new_content, f"chore: add {added_count} new proxies")
            except Exception as e:
                print(f"Failed to push proxies.txt to GitHub: {e}")
                
            await update.message.reply_text(
                f"✅ Добавлено <b>{added_count}</b> новых прокси (всего в списке: {len(all_raws)}).\n"
                f"Используйте команду /proxies для запуска проверки.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"ℹ️ Отправленные прокси уже присутствуют в списке (всего: {len(existing_raws)})."
            )
        return ConversationHandler.END
    
    # Если это просто текстовое сообщение, предлагаем отправить ИИ-агенту наравне с голосовыми
    ctx.user_data["text"] = text
    ctx.user_data["duration"] = 0
    
    await _send_menu_with_cleanup(
        update, ctx,
        "Что сделать с этой текстовой задачей?",
        reply_markup=TRANSCRIPT_ACTION_KEYBOARD,
    )
    return WAIT_TRANSCRIPT_ACTION

async def _direct_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    # Ищем лог-файл в корневой директории
    log_file = Path(__file__).parent.parent / "orchestrator.log"
    if not log_file.exists():
        log_file = Path("orchestrator.log")
    if not log_file.exists():
        await update.effective_message.reply_text("📋 Лог-файл orchestrator.log не найден.")
        return
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        content_tail = content[-1500:] if len(content) > 1500 else content
        import html
        content_tail_escaped = html.escape(content_tail)
        await update.effective_message.reply_text(
            f"📋 <b>Последние строки orchestrator.log (прямой перехват):</b>\n\n<code>{content_tail_escaped}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Ошибка при чтении лога: {e}")

async def _direct_pushlog(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log_file = Path(__file__).parent.parent / "orchestrator.log"
    if not log_file.exists():
        log_file = Path("orchestrator.log")
    if not log_file.exists():
        await update.effective_message.reply_text("📋 Лог-файл orchestrator.log не найден для отправки.")
        return
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        url = await asyncio.to_thread(gh_write, "docs/articles/log.txt", content, "chore: update log.txt from bot (direct)")
        await update.effective_message.reply_text(f"✅ Лог успешно отправлен на GitHub через REST API:\n{url}")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Ошибка при отправке лога на GitHub: {e}")

async def global_update_logger(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    # ── Перехват и прямое выполнение команд отладки ───────────────────────
    if update.message and update.message.text:
        cmd_text = update.message.text.strip().split()[0]
        if cmd_text in ("/pushlog", "/pushlog@neiromagie_bot"):
            try:
                await _direct_pushlog(update, ctx)
            except Exception as e:
                log.error("Error in _direct_pushlog intercept: %s", e)
            raise ApplicationHandlerStop()
        elif cmd_text in ("/log", "/log@neiromagie_bot"):
            try:
                await _direct_log(update, ctx)
            except Exception as e:
                log.error("Error in _direct_log intercept: %s", e)
            raise ApplicationHandlerStop()
        elif cmd_text.startswith("/resume"):
            try:
                await cmd_resume(update, ctx)
            except Exception as e:
                log.error("Error in cmd_resume intercept: %s", e)
            raise ApplicationHandlerStop()

    try:
        update_dict = update.to_dict() if hasattr(update, "to_dict") else str(update)
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "update": update_dict
        }
        log_file = Path(__file__).parent.parent / "webhook_log.json"
        updates = []
        if log_file.exists():
            try:
                updates = json.loads(log_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        updates.append(log_entry)
        updates = updates[-50:]
        log_file.write_text(json.dumps(updates, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # Записываем на GitHub только если запущен локально (чтобы не зацикливать сборки на Render)
        if not os.getenv("PORT"):
            await asyncio.to_thread(gh_write, "docs/articles/webhook_log.json", json.dumps(updates, ensure_ascii=False, indent=2), "diagnostics: log webhook update")
    except Exception as e:
        log.error("Error in global_update_logger: %s", e)

def log_bot_startup() -> None:
    try:
        import subprocess
        commit = ""
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        except Exception:
            pass
            
        status_data = {
            "status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "commit": commit,
            "env": {
                "TG_BOT_TOKEN_SET": bool(os.getenv("TG_BOT_TOKEN")),
                "GROQ_KEY_SET": bool(os.getenv("GROQ_KEY")),
                "GEMINI_KEY_SET": bool(os.getenv("GEMINI_KEY")),
                "GITHUB_TOKEN_SET": bool(os.getenv("GITHUB_TOKEN")),
                "GITHUB_BRANCH": os.getenv("GITHUB_BRANCH"),
                "PORT": os.getenv("PORT"),
                "RENDER_EXTERNAL_URL": os.getenv("RENDER_EXTERNAL_URL"),
                "TG_PROXY_CHANNEL": os.getenv("TG_PROXY_CHANNEL"),
                "VK_TOKEN_SET": bool(os.getenv("VK_TOKEN"))
            }
        }
        content = json.dumps(status_data, ensure_ascii=False, indent=2)
        gh_write("docs/articles/bot_status.json", content, "diagnostics: bot startup status online")
        print("  [diagnostics] Successful startup status logged to GitHub.")
    except Exception as e:
        print(f"  [diagnostics ERROR] Failed to log startup status: {e}")

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
        await asyncio.to_thread(gh_write, "critical_error.json", content, f"fail: bot handler exception [{type(context.error).__name__}]")
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

async def cmd_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
    log_file = Path(__file__).parent.parent / "orchestrator.log"
    if not log_file.exists():
        msg = await update.effective_message.reply_text("Файл orchestrator.log не найден.")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
        return
    try:
        # Читаем лог-файл безопасно с заменой некорректных байтов
        content = log_file.read_text(encoding="utf-8", errors="replace")
        content_tail = content[-1500:] if len(content) > 1500 else content
        
        # Экранируем HTML-теги, чтобы не ломать parse_mode="HTML" в Telegram
        import html
        content_tail_escaped = html.escape(content_tail)
        
        try:
            msg = await update.effective_message.reply_text(
                f"📋 <b>Последние строки orchestrator.log:</b>\n\n<code>{content_tail_escaped}</code>",
                parse_mode="HTML"
            )
        except Exception as html_err:
            # Если разметка сломалась или сообщение слишком длинное, отправляем как обычный текст
            msg = await update.effective_message.reply_text(
                f"📋 Последние строки orchestrator.log (Plain Text):\n\n{content_tail}",
                parse_mode=None
            )
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 60))
    except Exception as e:
        msg = await update.effective_message.reply_text(f"Ошибка при чтении лога: {e}")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))

async def cmd_pushlog(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
    log_file = Path(__file__).parent.parent / "orchestrator.log"
    if not log_file.exists():
        msg = await update.effective_message.reply_text("Файл orchestrator.log не найден для отправки.")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
        return
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        
        # Записываем на GitHub через REST API (работает без локального .git)
        url = await asyncio.to_thread(gh_write, "docs/articles/log.txt", content, "chore: update log.txt from bot")
        msg = await update.effective_message.reply_text(f"✅ Лог успешно отправлен на GitHub через REST API:\n{url}")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 15))
    except Exception as e:
        msg = await update.effective_message.reply_text(f"Ошибка при отправке лога на GitHub: {e}")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 15))

async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
    if ctx.args:
        slug = ctx.args[0].strip()
        log.info(f"cmd_resume received slug argument: {slug}")
    
    state_dir = Path(__file__).parent.parent / "plans" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    
    if not slug:
        # Пытаемся получить список из GitHub
        state_files_info = await asyncio.to_thread(gh_list_dir, "plans/.state")
        
        # Загрузим и пропарсим локальные файлы состояния, отсортируем по saved_at
        local_states = []
        for f in state_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                raw_saved = data.get("saved_at") or data.get("context", {}).get("saved_at", "")
                slug_val = data.get("slug")
                if not slug_val:
                    continue
                try:
                    saved_dt = datetime.fromisoformat(raw_saved)
                except Exception:
                    saved_dt = datetime.min
                local_states.append((saved_dt, slug_val))
            except Exception:
                pass
        
        if local_states:
            # Сортируем по saved_at по убыванию (самый свежий сверху)
            # Sort by datetime (most recent first)
            local_states.sort(key=lambda x: x[0], reverse=True)
            slug = local_states[0][1]
            log.info(f"cmd_resume selected slug from local state: {slug}")
        elif state_files_info:
            state_files_info = sorted(state_files_info, key=lambda x: x.get("name", ""), reverse=True)
            latest_file_name = state_files_info[0].get("name")
            slug = latest_file_name.replace(".json", "")
            log.info(f"cmd_resume selected slug from GitHub list: {slug}")
        else:
            msg = await update.effective_message.reply_text("Активные состояния для возобновления не найдены ни локально, ни на GitHub.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
            return

    if not slug:
        msg = await update.effective_message.reply_text("Не удалось определить slug статьи.")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
        return

    state_file = state_dir / f"{slug}.json"
    
    # Загружаем из GitHub если локально файла нет
    if not state_file.exists():
        msg_state = await update.effective_message.reply_text(f"⏳ Файл состояния '{slug}.json' не найден локально. Пытаюсь загрузить из GitHub...")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_state.message_id, 15))
        remote_content = gh_read(f"plans/.state/{slug}.json")
        if remote_content:
            try:
                state_file.write_text(remote_content, encoding="utf-8")
                msg_ok = await update.effective_message.reply_text("✅ Файл состояния успешно скачан с GitHub.")
                asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_ok.message_id, 10))
            except Exception as e:
                msg_err = await update.effective_message.reply_text(f"❌ Ошибка сохранения скачанного файла состояния: {e}")
                asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_err.message_id, 15))
                return
        else:
            msg_fail = await update.effective_message.reply_text(f"❌ Файл состояния для '{slug}' не найден ни локально, ни на GitHub.")
            asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_fail.message_id, 15))
            return

    try:
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        completed_step = state_data.get("completed_step", 0)
        saved_ctx = state_data.get("context", {})
        topic = saved_ctx.get("topic")
        title = saved_ctx.get("title")
        query = saved_ctx.get("search_query")
        mode = saved_ctx.get("mode")
        pipeline_mode = saved_ctx.get("pipeline_mode", "seo")
    except Exception as e:
        msg_parse = await update.effective_message.reply_text(f"Ошибка парсинга файла состояния: {e}")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_parse.message_id, 15))
        return

    if not all([topic, title, slug, query]):
        msg_data = await update.effective_message.reply_text(f"Недостаточно данных в файле состояния для возобновления '{slug}'.")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_data.message_id, 15))
        return

    # Запускаем оркестратор в фоне
    import subprocess
    cmd = [
        sys.executable,
        "scripts/orchestrator.py",
        "--topic", topic,
        "--title", title,
        "--slug", slug,
        "--query", query,
        "--mode", mode,
        "--pipeline-mode", pipeline_mode,
        "--resume",
        "--chat-id", str(update.effective_message.chat_id)
    ]
    log.info("Resuming orchestrator in background: %s", cmd)
    try:
        project_root = Path(__file__).parent.parent
        log_file_path = project_root / "orchestrator.log"
        log_file = open(log_file_path, "a", encoding="utf-8")
        subprocess.Popen(cmd, cwd=project_root, stdout=log_file, stderr=log_file)
        
        msg_resume = await update.effective_message.reply_text(
            f"▶️ <b>Возобновляю генерацию статьи!</b>\n\n"
            f"⚙️ <b>Формат:</b> {mode}\n"
            f"🔗 <b>Slug:</b> {slug}\n"
            f"Пайплайн продолжит работу с шага {completed_step + 1}.",
            parse_mode="HTML"
        )
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_resume.message_id, 15))
    except Exception as e:
        log.error("Failed to resume orchestrator: %s", e)
        msg_fail = await update.effective_message.reply_text(f"❌ Ошибка возобновления: {e}")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg_fail.message_id, 15))

async def proxy_harvester_loop() -> None:
    global LAST_HARVESTER_RUN, LAST_HARVESTER_ERROR
    # Ждем 2 минуты после старта, чтобы бот полностью инициализировался,
    # а затем запускаем первую проверку, чтобы сразу проверить прокси при перезапуске.
    await asyncio.sleep(120)
    while True:
        try:
            channel = os.getenv("TG_PROXY_CHANNEL")
            if channel:
                print("Starting scheduled proxy harvest...")
                from scripts.proxy_harvester import run_harvester
                await run_harvester()
                LAST_HARVESTER_RUN = datetime.now()
                LAST_HARVESTER_ERROR = None
                print("Scheduled proxy harvest completed.")
            else:
                print("Scheduled proxy harvest skipped (TG_PROXY_CHANNEL not set).")
        except Exception as e:
            print(f"Error in scheduled proxy harvest loop: {e}")
            LAST_HARVESTER_ERROR = f"{type(e).__name__}: {e}"
        # Засыпаем на 20 минут (1200 секунд)
        await asyncio.sleep(1200)

async def post_init(application: Application) -> None:
    from telegram import BotCommand
    await application.bot.set_my_commands([
        BotCommand("start", "Главное меню / Запуск"),
        BotCommand("cancel", "Сбросить текущий режим / Отмена"),
        BotCommand("log", "Показать лог оркестратора"),
        BotCommand("botlog", "Показать лог бота"),
        BotCommand("pushlog", "Отправить лог в репозиторий GitHub"),
        BotCommand("resume", "Возобновить генерацию статьи"),
        BotCommand("version", "Показать текущую версию бота"),
        BotCommand("status", "Показать статус и конфигурацию сборщика прокси")
    ])
    # Запускаем фоновую задачу сборщика прокси
    asyncio.create_task(proxy_harvester_loop())

def is_coding_task(text: str) -> bool:
    text_lower = text.lower()
    keywords = ["код", "скрипт", "файл", "доработай", "напиши", "запусти", "проверь", "git", "python", "listener", "бот", "логи", "посмотри", "агент", "agent"]
    return any(w in text_lower for w in keywords) or len(text) > 150

def clean_history_result(result):
    if not result:
        return ""
    result = result.replace("✅ <b>Результат выполнения задачи:</b>\n\n", "")
    for separator in ["Созданные файлы или решения:", "Созданные файлы:", "Решение:"]:
        if separator in result:
            result = result.split(separator)[0]
    result = result.replace("Отчет о проделанной работе:", "")
    
    import re
    result_clean = result.strip()
    match = re.search(r'(?:Мой следующий вопрос|Следующий вопрос|вопрос):\s*(.*)', result_clean, re.IGNORECASE | re.DOTALL)
    if match:
        result_clean = match.group(1).strip()
        
    sentences = re.split(r'(?<=[.!?])\s+', result_clean)
    question_sentences = []
    for s in sentences:
        s_strip = s.strip()
        if not s_strip:
            continue
        if any(w in s_strip.lower() for w in ["вы ответили", "ответили:", "ожидайте ответа"]):
            continue
        question_sentences.append(s_strip)
        
    if question_sentences:
        result_clean = " ".join(question_sentences)
        
    for prefix in ["ИИ-агент (ты):", "ИИ-агент:", "Antigravity:", "Ответ:"]:
        if result_clean.startswith(prefix):
            result_clean = result_clean[len(prefix):].strip()
            
    return result_clean.strip()

def build_history_context(task, all_tasks):
    history = []
    current_reply_to_id = task.get("reply_to_message_id")
    
    def find_task_by_any_msg_id(msg_id, tasks_list):
        for t in tasks_list:
            if t.get("message_id") == msg_id or t.get("reply_message_id") == msg_id:
                return t
        return None

    if current_reply_to_id:
        visited_ids = set()
        while current_reply_to_id and current_reply_to_id not in visited_ids:
            visited_ids.add(current_reply_to_id)
            parent = find_task_by_any_msg_id(current_reply_to_id, all_tasks)
            if parent:
                history.append(parent)
                current_reply_to_id = parent.get("reply_to_message_id")
            else:
                break
        history.reverse()
        
    target_history_len = 8
    if len(history) < target_history_len:
        ref_task = history[0] if history else task
        completed_before = []
        for t in all_tasks:
            if t.get("id") == ref_task.get("id"):
                break
            if t.get("status") == "completed" and t.get("result"):
                completed_before.append(t)
        
        needed = target_history_len - len(history)
        extra_history = completed_before[-needed:]
        history = extra_history + history
        
    return history

def run_direct_llm(task_text, history):
    system_prompt = (
        "Ты Antigravity — умный ИИ-собеседник и разработчик.\n"
        "Правила ведения диалога:\n"
        "1. Отвечай кратко, естественно и лаконично (максимум 1-3 предложения), как реальный собеседник в чате.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО пересказывать историю диалога, повторять предыдущие вопросы и ответы («Вы ответили...», «Я задал вопрос...») или писать мета-комментарии о ходе игры.\n"
        "3. Если идет игра в 20 вопросов, просто отреагируй на последний ответ (например: 'Понял, значит не в офисе.') и сразу задай следующий вопрос (например: 'Этот предмет больше футбольного мяча?').\n"
        "4. Только если пользователь дал конкретную техническую задачу по программированию или созданию файлов, выполни её и приложи лаконичный отчет в самом конце ответа."
    )
    
    full_prompt = f"{system_prompt}\n\n"
    if history:
        full_prompt += "История предыдущей беседы (контекст):\n"
        for h in history:
            full_prompt += f"Пользователь: {h['text']}\n"
            if h.get("result"):
                clean_res = clean_history_result(h["result"])
                if clean_res:
                    full_prompt += f"ИИ-агент (ты): {clean_res}\n"
        full_prompt += f"\nТекущее сообщение от пользователя: {task_text}\n\n"
        full_prompt += "ИИ-агент (ты): "
    else:
        full_prompt += task_text
        
    response = llm_chat(full_prompt)
    response_clean = response.strip()
    for prefix in ["ИИ-агент (ты):", "ИИ-агент:", "Antigravity:", "Ответ:"]:
        if response_clean.startswith(prefix):
            response_clean = response_clean[len(prefix):].strip()
    return response_clean

async def handle_channel_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    
    try:
        # Reply with 'Ок' to the channel task
        status_msg = await msg.reply_text("Ок")
        
        tasks_content = gh_read("docs/articles/tasks.json")
        tasks = []
        if tasks_content:
            try:
                tasks = json.loads(tasks_content)
            except Exception as je:
                log.error("Failed to parse tasks.json: %s", je)
        
        next_id = 1
        if tasks:
            next_id = max(t.get("id", 0) for t in tasks) + 1
        
        new_task = {
            "id": next_id,
            "message_id": msg.message_id,
            "status_message_id": status_msg.message_id,
            "reply_to_message_id": msg.reply_to_message.message_id if msg.reply_to_message else None,
            "text": text,
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        tasks.append(new_task)
        
        gh_write(
            "docs/articles/tasks.json",
            json.dumps(tasks, indent=2, ensure_ascii=False),
            f"task: add code task #{next_id}"
        )
        log.info("Successfully added task #%s to tasks.json on GitHub for local execution", next_id)
        try:
            broadcast_ws_wakeup(next_id)
        except Exception as ws_ex:
            log.error("Failed to broadcast WS wakeup: %s", ws_ex)
        
    except Exception as e:
        log.error("Error in handle_channel_text: %s", e)

async def handle_channel_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.voice:
        return
        
    try:
        # Transcribe audio file
        text = await _download_and_transcribe_media(msg, ctx, status_msg=None)
        if not text:
            return
            
        # Reply with 'Ок' to the voice message
        status_msg = await msg.reply_text("Ок")
        
        tasks_content = gh_read("docs/articles/tasks.json")
        tasks = []
        if tasks_content:
            try:
                tasks = json.loads(tasks_content)
            except Exception as je:
                log.error("Failed to parse tasks.json: %s", je)
        
        next_id = 1
        if tasks:
            next_id = max(t.get("id", 0) for t in tasks) + 1
        
        new_task = {
            "id": next_id,
            "message_id": msg.message_id,
            "status_message_id": status_msg.message_id,
            "reply_to_message_id": msg.reply_to_message.message_id if msg.reply_to_message else None,
            "text": text,
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        tasks.append(new_task)
        
        gh_write(
            "docs/articles/tasks.json",
            json.dumps(tasks, indent=2, ensure_ascii=False),
            f"task: add voice code task #{next_id}"
        )
        log.info("Successfully added voice task #%s to tasks.json on GitHub for local execution", next_id)
        try:
            broadcast_ws_wakeup(next_id)
        except Exception as ws_ex:
            log.error("Failed to broadcast WS wakeup: %s", ws_ex)
        
    except Exception as e:
        log.error("Error in handle_channel_voice: %s", e)

async def cmd_botlog(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        try:
            await update.effective_message.delete()
        except Exception:
            pass
            
    log_file = Path(__file__).parent.parent / "bot.log"
    if not log_file.exists():
        msg = await update.effective_message.reply_text("Файл bot.log не найден.")
        asyncio.create_task(_delete_message_after_delay(ctx.bot, update.effective_chat.id, msg.message_id, 10))
        return
        
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        content_tail = content[-3000:] if len(content) > 3000 else content
        
        import html
        content_tail_escaped = html.escape(content_tail)
        
        await update.effective_message.reply_text(
            f"📋 <b>Последние строки bot.log:</b>\n\n<code>{content_tail_escaped}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"Ошибка чтения лога: {e}")

async def cmd_checkenv(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        try:
            await update.effective_message.delete()
        except Exception:
            pass
    env_keys = ["GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_BRANCH", "TG_BOT_TOKEN"]
    res = {}
    for k in env_keys:
        v = os.environ.get(k)
        if v:
            if "TOKEN" in k or "KEY" in k:
                res[k] = f"Set (length {len(v)}, prefix {v[:4]}...)"
            else:
                res[k] = v
        else:
            res[k] = "Empty / Not Set"
    await update.effective_message.reply_text(
        f"⚙️ <b>GitHub & Telegram Environment variables:</b>\n\n<code>{json.dumps(res, indent=2)}</code>",
        parse_mode="HTML"
    )

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
    app.add_error_handler(telegram_error_handler)

    home_filter = filters.Regex("^(🏠|🏠 Главное меню)$")
    media_filter = filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE | filters.Document.AUDIO | filters.Document.VIDEO

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(media_filter, handle_voice),
            MessageHandler(filters.Regex("^💡 Экспертиза$"), choose_expert_topic),
            MessageHandler(filters.Regex("^💼 Бизнес$"), choose_biz_topic),
            MessageHandler(filters.Regex("^🎯 Аудитория$"), choose_aud_topic),
            MessageHandler(filters.Regex("^📋 Заметки$"), menu_list),
            MessageHandler(filters.Regex("^📰 Новости ниши$"), choose_news_topic),
            MessageHandler(filters.Regex("^🚀 Создать статью$"), choose_article_mode),
            MessageHandler(filters.Regex("^🎤 Голосовая заметка$"), handle_voice_note_button),
            MessageHandler(filters.FORWARDED, handle_forwarded_message),
            MessageHandler(filters.REPLY & ~filters.COMMAND, handle_reply_entry),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message),
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
                MessageHandler(media_filter, expert_voice),
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
                MessageHandler(media_filter, biz_voice),
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
                MessageHandler(media_filter, audience_answer),
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
                MessageHandler(media_filter, news_voice),
            ],
            WAIT_ARTICLE_MODE: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_article_mode),
            ],
            WAIT_ARTICLE_TOPIC: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_article_topic),
                MessageHandler(media_filter, handle_article_topic),
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
                MessageHandler(media_filter, handle_voice),
            ],
            WAIT_TRANSCRIPT_ACTION: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transcript_action),
            ],
            WAIT_SUMMARY_ACTION: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_summary_action),
            ],
            WAIT_POST_COMMENT: [
                MessageHandler(home_filter, go_home),
                MessageHandler(filters.TEXT | filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE, handle_post_comment),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(TypeHandler(Update, global_update_logger), group=-1)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("log", cmd_log))
    app.add_handler(CommandHandler("botlog", cmd_botlog))
    app.add_handler(CommandHandler("checkenv", cmd_checkenv))
    app.add_handler(CommandHandler("pushlog", cmd_pushlog))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("proxies", cmd_proxies))
    app.add_handler(CommandHandler("check_proxies", cmd_proxies))
    app.add_handler(CommandHandler("harvester", cmd_harvester))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.Chat(chat_id=TASK_CHANNEL_ID) & filters.VOICE, handle_channel_voice))
    app.add_handler(MessageHandler(filters.Chat(chat_id=TASK_CHANNEL_ID) & filters.TEXT & ~filters.COMMAND, handle_channel_text))
    app.add_handler(conv)

    log_bot_startup()

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
            drop_pending_updates=False
        )
    else:
        print("Starting polling...")
        app.run_polling(drop_pending_updates=False)


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
