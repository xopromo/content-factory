#!/usr/bin/env python3
"""
Content Factory Orchestrator
Координирует рой из 9 субагентов через 14 шагов генерации статьи.
"""

import os
import sys
import json
import time
import argparse
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

try:
    from groq import Groq as _Groq
    _groq_client = _Groq(api_key=os.environ.get("GROQ_KEY", "")) if os.environ.get("GROQ_KEY") else None
except ImportError:
    _groq_client = None

try:
    from ddgs import DDGS as _DDGS
except ImportError:
    _DDGS = None

try:
    import trafilatura as _trafilatura
except ImportError:
    _trafilatura = None

ROOT = Path(__file__).parent.parent
PLANS_DIR = ROOT / "plans"
RETRO_DIR = ROOT / "retrospectives"
FEEDBACK_DIR = ROOT / "ai-clone" / "feedback"
KNOWLEDGE_DIR = ROOT / "knowledge"
RULES_FILE = ROOT / "ai-clone" / "rules.md"


# ── Telegram ──────────────────────────────────────────────────────────────────

def tg_notify(text: str) -> None:
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        print(f"[TG SKIP] {text}")
        return
    import urllib.request, urllib.parse
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload.encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[TG ERROR] {e}")


# ── Feedback aggregation ───────────────────────────────────────────────────────

def aggregate_feedback() -> str:
    """Читает все файлы feedback/ и формирует блок жестких ограничений."""
    files = sorted(FEEDBACK_DIR.glob("*.md"))
    if not files:
        return ""
    lines = ["## ЖЕСТКИЕ ОГРАНИЧЕНИЯ (из feedback автора):\n"]
    for f in files:
        if f.name.startswith("_"):
            continue
        content = f.read_text(encoding="utf-8")
        lines.append(f"### {f.stem}\n{content}\n")
    return "\n".join(lines)


# ── Plan management ────────────────────────────────────────────────────────────

def create_plan(title: str, slug: str) -> Path:
    """Создает чек-лист выполнения в plans/."""
    template = (PLANS_DIR / "_TEMPLATE.md").read_text(encoding="utf-8")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = template.replace("[Заголовок]", title).replace(
        "YYYY-MM-DD  ", f"{date_str}  ", 1
    ).replace(
        "YYYY-MM-DD HH:MM UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )
    plan_path = PLANS_DIR / f"{date_str}_{slug}.md"
    plan_path.write_text(content, encoding="utf-8")
    return plan_path


def update_step(plan_path: Path, step_num: int, status: str = "done") -> None:
    """Отмечает шаг в чек-листе выполненным или проваленным."""
    content = plan_path.read_text(encoding="utf-8")
    step_marker = f"- [ ] Шаг {step_num:02d}"
    if status == "done":
        content = content.replace(step_marker, f"- [x] Шаг {step_num:02d}", 1)
    elif status == "failed":
        content = content.replace(step_marker, f"- [!] Шаг {step_num:02d}", 1)
    plan_path.write_text(content, encoding="utf-8")


# ── HTML generator ────────────────────────────────────────────────────────────

def md_to_html(md_path: Path, html_path: Path, title: str) -> Path:
    """Конвертирует Markdown-статью в автономный HTML с дизайном проекта."""
    import markdown as _md
    import re
    md_text = md_path.read_text(encoding="utf-8")

    # Убираем ТОЛЬКО внешний wrapper ```markdown ... ``` если LLM завернул статью в него
    outer = re.match(r"^```markdown\s*\n([\s\S]*)\n```\s*$", md_text.strip())
    if outer:
        md_text = outer.group(1)

    # Отделяем JSON-LD блок (если есть) от основного текста
    jsonld_block = ""
    if "```json" in md_text and "@context" in md_text:
        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", md_text)
        if m:
            jsonld_block = f'<script type="application/ld+json">{m.group(1)}</script>'
            md_text = md_text[:m.start()] + md_text[m.end():]

    body_html = _md.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "nl2br"],
    )

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  {jsonld_block}
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #1F2937; --surface: #263348; --surface2: #2d3a50;
      --border: rgba(255,255,255,0.08); --primary: #818CF8;
      --text: #F9FAFB; --text-muted: #9CA3AF;
      --radius-sm: 6px; --radius-md: 8px; --radius-lg: 12px;
    }}
    body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; font-size: 16px; }}
    .nav {{
      display: flex; align-items: center; gap: 24px; padding: 0 32px; height: 52px;
      border-bottom: 1px solid var(--border); background: rgba(31,41,55,0.95);
      backdrop-filter: blur(8px); position: sticky; top: 0; z-index: 100;
    }}
    .nav-logo {{ font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; }}
    .nav-logo-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--primary); }}
    .nav-back {{ margin-left: auto; font-size: 13px; color: var(--text-muted); text-decoration: none; }}
    .nav-back:hover {{ color: var(--text); }}
    .article-wrap {{ max-width: 780px; margin: 48px auto; padding: 0 24px 80px; }}
    .article-wrap h1 {{ font-size: 32px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.25; margin-bottom: 24px; }}
    .article-wrap h2 {{ font-size: 22px; font-weight: 600; margin: 40px 0 12px; letter-spacing: -0.01em; }}
    .article-wrap h3 {{ font-size: 17px; font-weight: 600; margin: 28px 0 10px; }}
    .article-wrap h4 {{ font-size: 15px; font-weight: 600; margin: 20px 0 8px; color: var(--text-muted); }}
    .article-wrap p {{ margin-bottom: 16px; }}
    .article-wrap ul, .article-wrap ol {{ margin: 0 0 16px 24px; }}
    .article-wrap li {{ margin-bottom: 6px; }}
    .article-wrap table {{ width: 100%; border-collapse: collapse; margin: 24px 0; font-size: 14px; }}
    .article-wrap th {{ background: var(--surface2); padding: 10px 14px; text-align: left; font-weight: 600; border: 1px solid var(--border); }}
    .article-wrap td {{ padding: 9px 14px; border: 1px solid var(--border); }}
    .article-wrap tr:nth-child(even) td {{ background: rgba(255,255,255,0.02); }}
    .article-wrap code {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; background: var(--surface); padding: 2px 6px; border-radius: 4px; }}
    .article-wrap pre {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 20px; overflow-x: auto; margin: 20px 0; }}
    .article-wrap pre code {{ background: none; padding: 0; }}
    .article-wrap blockquote {{ border-left: 3px solid var(--primary); padding: 12px 20px; margin: 20px 0; background: var(--surface); border-radius: 0 var(--radius-md) var(--radius-md) 0; color: var(--text-muted); }}
    .article-wrap a {{ color: var(--primary); text-decoration: none; }}
    .article-wrap a:hover {{ text-decoration: underline; }}
    .article-wrap hr {{ border: none; border-top: 1px solid var(--border); margin: 32px 0; }}
    .mermaid {{ background: var(--surface); border-radius: var(--radius-md); padding: 20px; margin: 20px 0; overflow-x: auto; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({{startOnLoad:true, theme:'dark'}});</script>
</head>
<body>
  <nav class="nav">
    <div class="nav-logo"><div class="nav-logo-dot"></div>Content Factory</div>
    <a class="nav-back" href="/content-factory/">← Все статьи</a>
  </nav>
  <div class="article-wrap">
    {body_html}
  </div>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")
    return html_path


# ── Web search ────────────────────────────────────────────────────────────────
    """Вытаскивает полный текст страницы через trafilatura (без рекламы и мусора)."""
    if not _trafilatura or not url:
        return ""
    try:
        downloaded = _trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = _trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
            no_fallback=False,
        )
        return (text or "")[:max_chars]
    except Exception:
        return ""


def web_search_fresh(query: str, max_results: int = 3) -> list[dict]:
    """
    Слой 1: свежие новости за последнюю неделю.
    Возвращает список {title, url, date, source, text}.
    """
    if not _DDGS:
        return []
    for timelimit in ("w", "m"):  # неделя → если пусто, месяц
        try:
            items = list(_DDGS().news(query, max_results=max_results, timelimit=timelimit))
            if not items:
                continue
            results = []
            for item in items:
                url = item.get("url", "")
                full_text = _fetch_full_text(url)
                results.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "date": item.get("date", "")[:10],
                    "source": item.get("source", ""),
                    "text": full_text or item.get("body", ""),
                    "fresh": timelimit == "w",
                })
            return results
        except Exception as e:
            print(f"  [SEARCH] news/{timelimit} ошибка: {e}")
    return []


def web_search_deep(query: str, max_results: int = 5) -> list[dict]:
    """
    Слой 2: глубинные источники без ограничения по дате.
    Возвращает список {title, url, text}.
    """
    if not _DDGS:
        return []
    try:
        items = list(_DDGS().text(query, max_results=max_results))
        results = []
        for item in items:
            url = item.get("href", "")
            full_text = _fetch_full_text(url)
            results.append({
                "title": item.get("title", ""),
                "url": url,
                "text": full_text or item.get("body", ""),
            })
        return results
    except Exception as e:
        print(f"  [SEARCH] text ошибка: {e}")
        return []


def format_search_for_llm(fresh: list[dict], deep: list[dict]) -> str:
    """Форматирует результаты поиска для передачи в LLM."""
    parts = []

    if fresh:
        parts.append("## СВЕЖИЕ НОВОСТИ (последняя неделя)\n")
        for i, item in enumerate(fresh, 1):
            flag = "🔴 ГОРЯЧАЯ НОВОСТЬ" if item.get("fresh") else "🟡 Свежая"
            parts.append(
                f"### {flag} [{item['date']}] {item['title']}\n"
                f"Источник: {item['source']} | URL: {item['url']}\n\n"
                f"{item['text']}\n"
            )
    else:
        parts.append("## СВЕЖИЕ НОВОСТИ\n⚠️ Новостей за последнюю неделю не найдено.\n")

    if deep:
        parts.append("\n## ГЛУБИННЫЕ ИСТОЧНИКИ (любой период)\n")
        for item in deep:
            parts.append(
                f"### {item['title']}\nURL: {item['url']}\n\n{item['text']}\n"
            )

    return "\n---\n".join(parts)


# ── Step runner ────────────────────────────────────────────────────────────────

class StepResult:
    def __init__(self, step: int, agent: str):
        self.step = step
        self.agent = agent
        self.start = time.time()
        self.output: str = ""
        self.success: bool = False
        self.tokens: int = 0

    def finish(self, output: str, success: bool = True, tokens: int = 0) -> None:
        self.output = output
        self.success = success
        self.tokens = tokens
        elapsed = round(time.time() - self.start, 1)
        icon = "✅" if success else "❌"
        tg_notify(
            f"{icon} <b>Шаг {self.step:02d}</b> — {self.agent}\n"
            f"⏱ {elapsed}с | ~{tokens} токенов"
        )


def run_claude(prompt: str, context_files: list[Path] = None) -> tuple[str, int]:
    """
    Вызывает LLM для выполнения задачи агента.
    Использует Groq (llama-3.3-70b) если есть GROQ_KEY, иначе claude CLI.
    Возвращает (output, estimated_tokens).
    """
    context = ""
    if context_files:
        for f in context_files:
            if f.exists():
                context += f"\n\n### {f.name}\n{f.read_text(encoding='utf-8')}"

    feedback = aggregate_feedback()
    full_prompt = "\n\n".join(p for p in [feedback, context, prompt] if p.strip())
    tokens = len(full_prompt.split()) * 2

    if _groq_client:
        try:
            resp = _groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=8192,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip(), tokens
        except Exception as e:
            print(f"[GROQ ERROR] {e} — пробую claude CLI")

    # Fallback: claude CLI (без хуков проекта — запуск из /tmp)
    result = subprocess.run(
        ["claude", "-p", full_prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        cwd="/tmp",
    )
    output = result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    return output, tokens


# ── Human-in-the-Loop ─────────────────────────────────────────────────────────

def _tg_wait_reply(timeout: int = 600) -> tuple[str, str]:
    """
    Ждёт ответного сообщения от пользователя в Telegram.
    Возвращает (тип: 'text'|'voice', содержимое).
    Таймаут в секундах (по умолчанию 10 минут).
    """
    import urllib.request, urllib.parse, tempfile, time as _time
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = str(os.getenv("TG_CHAT_ID", ""))
    if not token or not chat_id:
        return "text", input("\nВаш ответ: ").strip().lower()

    # Получаем текущий offset чтобы не читать старые сообщения
    def _api(method, **params):
        url = f"https://api.telegram.org/bot{token}/{method}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())

    # Сдвигаем offset за последнее известное обновление
    try:
        updates = _api("getUpdates", limit=1, offset=-1)
        offset = updates["result"][-1]["update_id"] + 1 if updates["result"] else 0
    except Exception:
        offset = 0

    deadline = _time.time() + timeout
    print(f"  Ожидаю ответа в Telegram ({timeout//60} мин)...")

    while _time.time() < deadline:
        try:
            updates = _api("getUpdates", offset=offset, timeout=30, limit=5)
            for upd in updates.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                if str(msg.get("chat", {}).get("id", "")) != chat_id:
                    continue

                # Голосовое сообщение
                voice = msg.get("voice") or msg.get("audio")
                if voice and _groq_client:
                    file_id = voice["file_id"]
                    file_info = _api("getFile", file_id=file_id)
                    file_path = file_info["result"]["file_path"]
                    audio_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                        tmp_path = tmp.name
                    urllib.request.urlretrieve(audio_url, tmp_path)
                    try:
                        from groq import Groq as _G
                        client = _G(api_key=os.environ["GROQ_KEY"])
                        with open(tmp_path, "rb") as f:
                            result = client.audio.transcriptions.create(
                                file=(os.path.basename(tmp_path), f),
                                model="whisper-large-v3-turbo",
                                language="ru",
                                response_format="text",
                            )
                        transcription = result.strip()
                        tg_notify(f"🎙 Транскрипция правок:\n\n{transcription}")
                        return "voice", transcription
                    finally:
                        os.unlink(tmp_path)

                # Текстовое сообщение
                text = msg.get("text", "").strip()
                if text:
                    return "text", text

        except Exception as e:
            print(f"  [TG poll error] {e}")
            _time.sleep(5)

    return "text", "stop"  # таймаут — останавливаем


def human_review(title: str, content: str, step: int, auto: bool = False) -> tuple[bool, str]:
    """
    Интерактивная пауза с поддержкой голосовых правок из Telegram.
    Возвращает (approved: bool, corrections: str).
    auto=True — всегда одобряет без правок (тестовый режим).
    """
    tg_notify(
        f"⏸ <b>Шаг {step} — требуется ваше решение</b>\n\n"
        f"<b>{title}</b>\n\n{content[:1200]}\n\n"
        f"✅ <code>ok</code> — продолжить\n"
        f"🛑 <code>stop</code> — остановить\n"
        f"🎙 Голосовое — правки и уточнения (транскрибирую и учту)"
    )

    if auto:
        print(f"\n⏭  HUMAN REVIEW шаг {step} — пропущен (--auto-approve)")
        return True, ""

    print(f"\n{'='*60}")
    print(f"⏸  HUMAN REVIEW — Шаг {step}: {title}")
    print(f"{'='*60}")
    print(content[:1000])

    msg_type, answer = _tg_wait_reply(timeout=600)

    if msg_type == "voice":
        # Голосовые правки — одобряем с корректировками
        print(f"  Получены голосовые правки: {answer[:200]}")
        return True, answer

    answer_lower = answer.lower()
    if answer_lower in ("stop", "стоп", "нет", "no"):
        return False, ""

    # Любой другой текст = правки
    corrections = "" if answer_lower in ("ok", "y", "yes", "да", "") else answer
    return True, corrections


# ── Main pipeline ──────────────────────────────────────────────────────────────

AGENT_PROMPTS = {
    "knowledge-retriever": (
        "Ты агент семантического поиска по базе знаний автора. "
        "Твоя задача: найти в папке knowledge/ все фрагменты, "
        "релевантные теме '{topic}'. Используй grep и чтение файлов. "
        "Верни компактный контекстный пакет: цитаты, кейсы, личный опыт автора. "
        "Максимум 2000 токенов. Без лишних комментариев — только выжимка."
    ),
    "web-researcher": (
        "Ты технический аналитик. Тема: '{topic}'. "
        "Найди через WebSearch актуальные данные ТОЛЬКО из: официальной документации, "
        "репозиториев GitHub, блогов инженеров. "
        "Игнорируй SEO-агрегаторы, копипаст-статьи. "
        "Верни: топ-5 фактов с источниками, список LSI-ключей, предложение структуры H2-H3."
    ),
    "content-writer": (
        "Ты копирайтер-смысловик. Пиши черновик статьи '{title}' по структуре. "
        "Правила: {rules_excerpt}. "
        "Контекст из базы знаний: {knowledge_pack}. "
        "Данные из веб-исследования: {web_pack}. "
        "Пиши поблочно. Первое предложение каждого H2 — прямой ответ на вопрос (AEO). "
        "Интегрируй конкретные числа, команды, таблицы."
    ),
    "seo-geo-optimizer": (
        "Ты SEO/GEO-оптимизатор. Получи черновик статьи и: "
        "1. Интегрируй LSI-ключи естественно в текст. "
        "2. Проверь AEO: первые предложения H2 должны быть самодостаточными ответами. "
        "3. Сгенерируй Schema.org JSON-LD (Article или HowTo) для этой статьи. "
        "4. Верни оптимизированный текст + JSON-LD блок отдельно."
    ),
    "geo-emulator": (
        "Ты симулятор ИИ-поисковика (Perplexity/ChatGPT Search). "
        "Получи текст статьи о '{topic}'. "
        "Задача: представь, что пользователь спросил: '{search_query}'. "
        "1. Ответь на вопрос, используя ТОЛЬКО предоставленный текст. "
        "2. Укажи точные цитаты (с номерами абзацев), которые ты использовал. "
        "3. Оцени по шкале 1-10, насколько хорошо текст отвечает на этот запрос. "
        "4. Перечисли блоки, которые ИИ-поисковик проигнорировал, и почему. "
        "5. Дай 3 конкретные рекомендации по переписыванию для улучшения цитируемости."
    ),
    "editor-critic": (
        "Ты главный редактор. Проверь финальный текст статьи по критериям: "
        "1. Соответствие Tone of Voice из rules.md (стоп-слова, стиль). "
        "2. Работоспособность блоков кода (логика, синтаксис). "
        "3. Отсутствие канцеляризмов и пассивного залога. "
        "4. Наличие оригинальных элементов (кейсы, таблицы, схемы). "
        "5. GEO-стандарты: первые предложения разделов самодостаточны. "
        "Верни: оценку 1-10 по каждому критерию и список конкретных правок."
    ),
}


def run_pipeline(topic: str, title: str, slug: str, search_query: str, auto_approve: bool = False) -> None:
    print(f"\n🚀 Content Factory — запуск генерации: {title}")
    tg_notify(f"🚀 <b>Запуск генерации</b>\n📝 {title}\n🔍 {topic}")

    plan_path = create_plan(title, slug)
    context: dict = {"topic": topic, "title": title, "search_query": search_query}

    # Шаг 1: Оркестратор читает feedback
    r = StepResult(1, "lead-orchestrator")
    feedback = aggregate_feedback()
    context["feedback"] = feedback
    update_step(plan_path, 1)
    r.finish(feedback or "(нет feedback)", tokens=len(feedback.split()))

    # Шаг 2: knowledge-retriever
    r = StepResult(2, "knowledge-retriever")
    prompt = AGENT_PROMPTS["knowledge-retriever"].format(topic=topic)
    output, tokens = run_claude(prompt)
    context["knowledge_pack"] = output
    update_step(plan_path, 2)
    r.finish(output, tokens=tokens)

    # Шаг 3: web-researcher — двухслойный поиск через ddgs + full-text trafilatura
    r = StepResult(3, "web-researcher")
    print("  [Слой 1] Ищу свежие новости за неделю...")
    tg_notify(f"🔍 <b>Шаг 03</b> — web-researcher\n⏳ Ищу актуальные источники...")

    fresh = web_search_fresh(topic, max_results=3)
    print(f"  Найдено свежих: {len(fresh)}")

    print("  [Слой 2] Ищу глубинные источники...")
    deep = web_search_deep(f"{topic} руководство практика кейсы", max_results=5)
    print(f"  Найдено глубинных: {len(deep)}")

    search_block = format_search_for_llm(fresh, deep)

    has_fresh = any(s.get("fresh") for s in fresh)
    freshness_warning = "" if has_fresh else (
        "\n\n⚠️ ВНИМАНИЕ: горячих новостей за последнюю неделю не найдено. "
        "На шаге 4 автор должен решить: использовать имеющееся или выбрать другую тему."
    )

    synthesis_prompt = (
        f"Ты аналитик контента. Тема: «{topic}».\n\n"
        f"Ниже — реальные найденные материалы. Работай ТОЛЬКО с ними, "
        f"не добавляй факты из своих тренировочных данных.\n\n"
        f"{search_block}\n\n"
        f"Задача:\n"
        f"1. Определи главный информационный повод (самая свежая и значимая новость)\n"
        f"2. Выдели 5 ключевых фактов с URL-источниками\n"
        f"3. Предложи структуру статьи H2–H3 (6–8 разделов)\n"
        f"4. Составь 15 LSI-ключей\n"
        f"5. Сформулируй главный тезис одним предложением"
        f"{freshness_warning}"
    )
    output, tokens = run_claude(synthesis_prompt)
    context["web_pack"] = output
    context["fresh_news"] = fresh
    context["has_fresh_news"] = has_fresh
    update_step(plan_path, 3)
    r.finish(output, tokens=tokens)

    fresh_summary = "\n".join(
        f"🔴 [{s['date']}] {s['title']}" for s in fresh
    ) if fresh else "⚠️ Свежих новостей нет"

    # Шаг 4: HUMAN REVIEW структуры
    no_fresh_alert = "\n\n⚠️ Горячих новостей за неделю НЕТ — возможно стоит сменить тему!" if not has_fresh else ""
    approved, corrections = human_review(
        "Утвердите структуру и данные из исследования",
        f"📰 Информационные поводы:\n{fresh_summary}\n\n"
        f"📌 Тезис и структура:\n{output[:700]}\n\n"
        f"📚 База знаний:\n{context['knowledge_pack'][:200]}"
        f"{no_fresh_alert}",
        step=4,
        auto=auto_approve,
    )
    if not approved:
        tg_notify("🛑 Генерация остановлена пользователем на шаге 4.")
        sys.exit(0)
    if corrections:
        context["corrections"] = corrections
        tg_notify(f"📝 Правки учтены:\n{corrections[:300]}")
    update_step(plan_path, 4)

    # Шаги 5-6: content-writer
    rules_excerpt = RULES_FILE.read_text(encoding="utf-8")[:800] if RULES_FILE.exists() else ""
    corrections_block = f"\n\n## ПРАВКИ И УТОЧНЕНИЯ ОТ АВТОРА:\n{context['corrections']}" if context.get("corrections") else ""
    for step in (5, 6):
        r = StepResult(step, "content-writer")
        block = "1-3" if step == 5 else "4-6"
        prompt = (
            AGENT_PROMPTS["content-writer"].format(
                title=title,
                rules_excerpt=rules_excerpt,
                knowledge_pack=context["knowledge_pack"],
                web_pack=context["web_pack"],
            )
            + corrections_block
            + f"\n\nНапиши блоки {block} статьи."
        )
        output, tokens = run_claude(prompt)
        context[f"draft_{block}"] = output
        update_step(plan_path, step)
        r.finish(output, tokens=tokens)

    full_draft = context.get("draft_1-3", "") + "\n\n" + context.get("draft_4-6", "")

    # Шаг 7: diagram-illustrator
    r = StepResult(7, "diagram-illustrator")
    prompt = (
        f"Создай Mermaid.js диаграммы для статьи '{title}'. "
        f"Идентифицируй 2-3 процесса в тексте, которые выиграют от визуализации. "
        f"Верни готовые блоки ```mermaid ... ``` с пояснениями.\n\nТекст статьи:\n{full_draft[:3000]}"
    )
    output, tokens = run_claude(prompt)
    context["diagrams"] = output
    update_step(plan_path, 7)
    r.finish(output, tokens=tokens)

    # Шаг 8-9: seo-geo-optimizer
    r = StepResult(8, "seo-geo-optimizer")
    prompt = AGENT_PROMPTS["seo-geo-optimizer"] + f"\n\nЧерновик:\n{full_draft}"
    output, tokens = run_claude(prompt)
    context["optimized_draft"] = output
    update_step(plan_path, 8)
    update_step(plan_path, 9)
    r.finish(output, tokens=tokens)

    # Шаг 10: geo-emulator
    r = StepResult(10, "geo-emulator")
    prompt = AGENT_PROMPTS["geo-emulator"].format(
        topic=topic, search_query=search_query
    ) + f"\n\nТекст статьи:\n{context['optimized_draft']}"
    output, tokens = run_claude(prompt)
    context["geo_report"] = output
    update_step(plan_path, 10)
    r.finish(output, tokens=tokens)

    # Шаг 11: editor-critic
    r = StepResult(11, "editor-critic")
    prompt = (
        AGENT_PROMPTS["editor-critic"]
        + f"\n\nПравила автора:\n{rules_excerpt}\n\nСтатья:\n{context['optimized_draft']}"
    )
    output, tokens = run_claude(prompt)
    context["editor_report"] = output
    update_step(plan_path, 11)
    r.finish(output, tokens=tokens)

    # Шаг 12: HUMAN REVIEW перед публикацией
    preview = f"GEO-отчет:\n{context['geo_report'][:400]}\n\nРедактор:\n{context['editor_report'][:400]}"
    approved, corrections12 = human_review("Утвердите статью перед публикацией", preview, step=12, auto=auto_approve)
    if not approved:
        tg_notify("🛑 Публикация отменена пользователем на шаге 12.")
        sys.exit(0)
    update_step(plan_path, 12)
    update_step(plan_path, 13)

    # Шаг 14: deployer-publisher
    r = StepResult(14, "deployer-publisher")
    articles_dir = ROOT / "docs" / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    # Сохраняем MD
    article_path = articles_dir / f"{slug}.md"
    final_text = context["optimized_draft"]
    if len(final_text) < len(full_draft) * 0.5:
        final_text = full_draft
    article_path.write_text(final_text, encoding="utf-8")

    # Генерируем HTML
    html_path = articles_dir / f"{slug}.html"
    try:
        md_to_html(article_path, html_path, title)
        print(f"  HTML сгенерирован: {html_path.name}")
    except Exception as e:
        print(f"  [WARN] HTML не сгенерирован: {e}")
        html_path = None

    # git add + commit
    files_to_add = [str(article_path), str(plan_path)]
    if html_path and html_path.exists():
        files_to_add.append(str(html_path))
    subprocess.run(["git", "add"] + files_to_add, cwd=ROOT, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"feat: article '{title}' [{slug}]"],
        cwd=ROOT, capture_output=True, text=True
    )
    update_step(plan_path, 14)

    pages_url = f"https://xopromo.github.io/content-factory/articles/{slug}.html"
    r.finish(f"{article_path.name} + {slug}.html", tokens=50)
    tg_notify(
        f"🎉 <b>Статья опубликована!</b>\n"
        f"📝 {title}\n"
        f"📄 <a href='{pages_url}'>{pages_url}</a>"
    )
    print(f"\n✅ MD:   {article_path}")
    if html_path:
        print(f"✅ HTML: {html_path}")
        print(f"🌐 URL:  {pages_url}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content Factory Orchestrator")
    parser.add_argument("--topic", required=True, help="Тема статьи (для поиска)")
    parser.add_argument("--title", required=True, help="Заголовок H1 статьи")
    parser.add_argument("--slug", required=True, help="URL-slug статьи")
    parser.add_argument("--query", required=True, help="Поисковый запрос для GEO-теста")
    parser.add_argument("--auto-approve", action="store_true", help="Пропускать HITL-паузы (тестовый режим)")
    args = parser.parse_args()

    run_pipeline(
        topic=args.topic,
        title=args.title,
        slug=args.slug,
        search_query=args.query,
        auto_approve=args.auto_approve,
    )
