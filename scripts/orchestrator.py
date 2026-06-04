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
sys.path.append(str(Path(__file__).parent.parent))

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
from typing import Optional

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from scripts.utils.llm_client import run_fast_common, run_claude_common, _gemini_client, _groq_client
from scripts.utils.validators import (
    validate_entity_names, validate_numbers, detect_semantic_duplicates,
    assess_content_value, verify_article_logic, rewrite_for_coherence,
    finer_gate, _source_tier, _TIER_LABEL, strengthen_weak_sections,
    improve_readability_seo, reduce_excessive_headings
)
from scripts.utils.search_helper import (
    web_search_fresh, web_search_deep, format_search_for_llm, format_raw_sources
)
from scripts.agent_prompts import AGENT_PROMPTS

ROOT = Path(__file__).parent.parent
PLANS_DIR = ROOT / "plans"
RETRO_DIR = ROOT / "retrospectives"
FEEDBACK_DIR = ROOT / "ai-clone" / "feedback"
KNOWLEDGE_DIR = ROOT / "knowledge"
RULES_FILE = ROOT / "ai-clone" / "rules.md"
STATE_DIR = ROOT / "plans" / ".state"   # Material Passport — состояние пайплайна

# ── GitHub REST API Helpers ───────────────────────────────────────────────────

def _gh_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "content-factory-bot/1.0"
    }
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return headers

def gh_read(path: str) -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        p = ROOT / path
        return p.read_text("utf-8") if p.exists() else ""
    import urllib.parse
    import base64
    repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
    branch = os.environ.get("GITHUB_BRANCH", "main")
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={branch}"
    try:
        req = urllib.request.Request(url, headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            return base64.b64decode(d["content"].replace("\n", "")).decode("utf-8")
    except Exception as e:
        print(f"  [gh_read] Warning: could not read {path} from GitHub: {e}")
        return ""

def gh_write(path: str, content: str, message: str) -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        p = ROOT / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")
        return str(p)
    import urllib.parse
    import base64
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
        print(f"  [gh_write] Warning: could not write {path} to GitHub: {e}")
        return path

def gh_list_dir(path: str) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        p = ROOT / path
        if not p.exists():
            return []
        return [{"name": f.name, "type": "file"} for f in p.glob("*")]
    import urllib.parse
    repo = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
    branch = os.environ.get("GITHUB_BRANCH", "main")
    url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={branch}"
    try:
        req = urllib.request.Request(url, headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read())
            if isinstance(res, list):
                return res
    except Exception as e:
        print(f"  [gh_list_dir] Warning: could not list {path} on GitHub: {e}")
    return []


# Минимальные требования к исследовательской базе перед запуском content-writer
RESEARCH_MIN_CHARS = 750      # символов реального текста из источников
RESEARCH_MIN_SOURCES = 2      # источников с текстом > 100 символов

# Домены по уровню авторитетности для ранжирования источников
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


# ── Telegram ──────────────────────────────────────────────────────────────────

TG_CHAT_ID_OVERRIDE = None
SENT_NOTIFICATION_IDS = []

def tg_notify(text: str) -> None:
    global SENT_NOTIFICATION_IDS
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = TG_CHAT_ID_OVERRIDE or os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        print(f"[TG SKIP] {text}")
        return

    # Проверяем, является ли сообщение критическим или важным
    is_critical_error = any(keyword in text.lower() for keyword in ["ошибка", "error", "критическ", "🚫", "🛑", "⚠️", "❌"])
    is_interaction = any(keyword in text for keyword in ["Подтвердите", "HUMAN REVIEW", "Ответьте:"])
    is_final = "опубликована" in text.lower() or "статья готова" in text.lower()

    if not (is_critical_error or is_interaction or is_final):
        # Пишем прогресс в логи консоли, но не шлем в Telegram
        print(f"[TG SILENT PROGRESS] {text.splitlines()[0] if text else ''}")
        return

    # Авто-определение шага для отображения прогресс-бара
    import re
    step_match = re.search(r"Шаг\s*0*(\d+)", text, re.IGNORECASE)
    if step_match:
        try:
            step = int(step_match.group(1))
            if 1 <= step <= 14:
                filled = "■" * step
                empty = "□" * (14 - step)
                percent = int((step / 14) * 100)
                progress = f"\n<code>[{filled}{empty}]</code> <b>{percent}%</b>\n"
                # Вставляем прогресс-бар после первой строки для красоты
                lines = text.split("\n")
                if len(lines) > 0:
                    lines.insert(1, progress.strip())
                    text = "\n".join(lines)
                else:
                    text = text + "\n" + progress
        except Exception:
            pass

    # Форматирование длинных ошибок в разворачиваемый блок <details>
    if is_critical_error and len(text) > 300:
        lines = text.split("\n")
        summary_title = lines[0] if lines else "Критическая ошибка"
        body = "\n".join(lines[1:])
        text = f"{summary_title}\n\n<details><summary>Подробнее об ошибке</summary>\n<pre>{body}</pre>\n</details>"

    import urllib.request, urllib.parse
    payload = json.dumps({
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True}
    })
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload.encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if res_data.get("ok"):
                msg_id = res_data["result"]["message_id"]
                
                # Финальные и интерактивные сообщения не удаляем
                is_critical = any(keyword in text for keyword in ["опубликована", "ошибка", "Подтвердите", "HUMAN REVIEW"])
                if not is_critical:
                    SENT_NOTIFICATION_IDS.append(msg_id)
                
                # Оставляем только последние 2 сообщения в ленте
                while len(SENT_NOTIFICATION_IDS) > 2:
                    old_msg_id = SENT_NOTIFICATION_IDS.pop(0)
                    del_payload = json.dumps({
                        "chat_id": chat_id,
                        "message_id": old_msg_id
                    })
                    del_req = urllib.request.Request(
                        f"https://api.telegram.org/bot{token}/deleteMessage",
                        data=del_payload.encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    try:
                        with urllib.request.urlopen(del_req, timeout=5) as del_resp:
                            pass
                    except Exception as del_err:
                        print(f"[TG DELETE ERROR] {del_err}")
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
    gh_write(f"plans/{plan_path.name}", content, f"feat: create plan for {slug}")
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
    gh_write(f"plans/{plan_path.name}", content, f"chore: update step {step_num} in plan")


# ── HTML generator ────────────────────────────────────────────────────────────

def _make_code_collapsible(html: str, min_lines: int = 5) -> str:
    """Оборачивает большие блоки кода в схлопываемый виджет."""
    import re

    def replace_pre(m: re.Match) -> str:
        pre_tag = m.group(0)
        line_count = pre_tag.count("\n")
        if line_count <= min_lines:
            return pre_tag
        label = f"↓ показать все {line_count} строк"
        return (
            f'<div class="code-wrap collapsed">'
            f"{pre_tag}"
            f'<button class="code-toggle" data-expand="{label}" '
            f'data-collapse="↑ свернуть">{label}</button>'
            f"</div>"
        )

    return re.sub(r"<pre[^>]*>.*?</pre>", replace_pre, html, flags=re.DOTALL)


def md_to_html(md_path: Path, html_path: Path, title: str) -> Path:
    """Конвертирует Markdown-статью в автономный HTML с дизайном проекта."""
    import markdown as _md
    import re
    md_text = md_path.read_text(encoding="utf-8")

    # Убираем ТОЛЬКО внешний wrapper ```markdown ... ``` если LLM завернул статью в него
    outer = re.match(r"^```markdown\s*\n([\s\S]*)\n```\s*$", md_text.strip())
    if outer:
        md_text = outer.group(1)

    # Отделяем JSON-LD блок — два формата: raw <script> или ```json code block
    jsonld_blocks = []
    
    # 1. Поиск всех тегов <script type="application/ld+json">
    for m in re.finditer(r'<script type="application/ld\+json">([\s\S]*?)</script>', md_text):
        jsonld_blocks.append(f'<script type="application/ld+json">{m.group(1).strip()}</script>')
    
    # Удаляем их из текста
    md_text = re.sub(r'<script type="application/ld\+json">([\s\S]*?)</script>', '', md_text)
    
    # 2. Поиск всех ```json с @context (если они еще не обернуты в <script>)
    for m2 in re.finditer(r"```json\s*([{\[][\s\S]*?[}\]])\s*```", md_text):
        content = m2.group(1)
        if "@context" in content:
            jsonld_blocks.append(f'<script type="application/ld+json">{content.strip()}</script>')
            
    # Удаляем ```json блоки, содержащие @context, из текста
    def _remove_json_context(match):
        if "@context" in match.group(0):
            return ""
        return match.group(0)
    md_text = re.sub(r"```json\s*([{\[][\s\S]*?[}\]])\s*```", _remove_json_context, md_text)

    jsonld_block = "\n  ".join(jsonld_blocks)

    # Убираем служебные секции SEO-оптимизатора — они не часть статьи
    _seo_sections = [
        r'## Целевые ключевые слова',
        r'## Оптимизированный текст',
        r'## AEO-аудит',
        r'## Schema\.org JSON-LD',
        r'## JSON-LD',
    ]
    for _pat in _seo_sections:
        md_text = re.sub(
            rf'\n{_pat}[^\n]*\n[\s\S]*?(?=\n## |\Z)',
            '',
            md_text,
        )
    # Убираем blockquote с инструкциями про плейсхолдеры JSON-LD
    md_text = re.sub(r'\n> \*\*Замените плейсхолдеры\*\*[^\n]*\n?', '', md_text)
    md_text = re.sub(r'\*\*Замените плейсхолдеры\*\*[^\n]*\n?', '', md_text)
    # Убираем горизонтальные разделители перед служебными секциями которые остались
    md_text = re.sub(r'\n---\s*\n\s*$', '', md_text)
    # Убираем дублирующиеся горизонтальные разделители (--- подряд несколько раз)
    md_text = re.sub(r'(\n---\s*){2,}', '\n---\n', md_text)

    # Удаляем маркеры [INSUFFICIENT_SOURCES: ...] — могут содержать вложенные [...] внутри
    # Используем жадный поиск до последней ] на строке (не захватываем через границы абзаца)
    def _remove_insufficient(text: str) -> str:
        result = []
        i = 0
        while i < len(text):
            if text[i:].startswith('[INSUFFICIENT_SOURCES:'):
                depth = 0
                j = i
                while j < len(text):
                    if text[j] == '[':
                        depth += 1
                    elif text[j] == ']':
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                # Пропускаем пробелы и переводы строк после закрывающей скобки
                while j < len(text) and text[j] in (' ', '\t', '\n'):
                    j += 1
                i = j
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)

    # Перед удалением маркеров убираем заголовки H2-H4, если после них сразу идет маркер нехватки
    md_text = re.sub(r'\n#{2,4}[^\n]+\n+(?=\[INSUFFICIENT_SOURCES:)', '\n', md_text)
    md_text = _remove_insufficient(md_text)
    md_text = re.sub(r'\*\*\*Примечание по JSON-LD:\*\*[^\n]*\n?', '', md_text)
    # Гарантируем, что статья начинается с первого H1 заголовка, убирая все метаданные до него
    h1_match = re.search(r'^# ', md_text, re.MULTILINE)
    if h1_match:
        md_text = md_text[h1_match.start():]
    # Зачищаем пустые H2-H4 заголовки в конце или в тексте
    md_text = re.sub(r'\n(#{2,4}[^\n]+)\n+(?=#{1,4}|\Z)', '\n', md_text)
    # Для корректного рендеринга таблиц markdown добавляем пустую строку перед таблицей
    md_text = re.sub(r'(?m)^([^|\n#][^\n]*)\n(\|)', r'\1\n\n\2', md_text)

    # Очищаем заголовки-маркеры структуры из текста (Лид, Вывод)
    md_text = re.sub(r'^\*\*Лид\*\*\s*\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^\*\*Вывод\*\*\s*\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^#+\s+\*?\*?Лид\*?\*?\s*\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^#+\s+\*?\*?Вывод\*?\*?\s*\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^#+\s+[^\n]*Schema\.org[^\n]*\n?', '', md_text, flags=re.MULTILINE | re.IGNORECASE)
    md_text = re.sub(r'\*?\*?Примечания:\*?\*?.*$', '', md_text, flags=re.DOTALL)
    # Убираем случайные теги script
    md_text = re.sub(r'<script[^>]*>|</script>', '', md_text)
    md_text = re.sub(r'```json\s*```', '', md_text, flags=re.DOTALL)

    # Убираем жирное форматирование из текста (заменяем **text** на text)
    md_text = re.sub(r'\*\*(.*?)\*\*', r'\1', md_text)

    body_html = _md.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
    )
    body_html = _make_code_collapsible(body_html)

    template_path = Path(__file__).parent / "templates" / "article_template.html"
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
    else:
        template = "<html><head><title>{title}</title>{jsonld_block}</head><body>{body_html}</body></html>"

    html = template.format(
        title=title,
        jsonld_block=jsonld_block,
        body_html=body_html
    )

    html_path.write_text(html, encoding="utf-8")
    return html_path

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


def run_claude(prompt: str, context_files: list[Path] = None, inject_feedback: bool = False) -> tuple[str, int]:
    """Вызывает LLM для выполнения задачи агента через общий llm_client."""
    from scripts.utils.llm_client import run_claude_common
    context = ""
    if context_files:
        for f in context_files:
            if f.exists():
                context += f"\n\n### {f.name}\n{f.read_text(encoding='utf-8')}"
    return run_claude_common(prompt, context, inject_feedback)


def run_fast(prompt: str, quality: str = "strong") -> tuple[str, int]:
    """Быстрый вызов LLM для лёгких или вспомогательных задач через общий llm_client."""
    from scripts.utils.llm_client import run_fast_common
    return run_fast_common(prompt, quality)


# ── Human-in-the-Loop ─────────────────────────────────────────────────────────

def _tg_wait_reply(timeout: int = 600) -> tuple[str, str]:
    """
    Ждёт ответного сообщения от пользователя в Telegram.
    Поддерживает файловый мост для работы в Webhook-режиме в облаке.
    """
    import urllib.request, urllib.parse, tempfile, time as _time, json
    from pathlib import Path
    
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = str(os.getenv("TG_CHAT_ID", ""))
    
    # Файловый мост для Webhook
    reply_file = ROOT / "business" / "latest_reply.json"
    initial_time = 0.0
    if reply_file.exists():
        try:
            initial_time = json.loads(reply_file.read_text(encoding="utf-8")).get("timestamp", 0.0)
        except Exception:
            pass

    if not token or not chat_id:
        return "text", input("\nВаш ответ: ").strip().lower()

    # Сдвигаем offset (для локального Polling)
    def _api(method, **params):
        url = f"https://api.telegram.org/bot{token}/{method}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())

    offset = 0
    try:
        updates = _api("getUpdates", limit=1, offset=-1)
        offset = updates["result"][-1]["update_id"] + 1 if updates["result"] else 0
    except Exception:
        pass

    deadline = _time.time() + timeout
    print(f"  Ожидаю ответа в Telegram ({timeout//60} мин) через файловый мост / getUpdates...")

    while _time.time() < deadline:
        # 1. Проверяем файловый мост (работает при Webhook)
        if reply_file.exists():
            try:
                data = json.loads(reply_file.read_text(encoding="utf-8"))
                if data.get("timestamp", 0.0) > initial_time:
                    msg_type = data.get("type", "text")
                    content = data.get("content", "")
                    print(f"  [file-bridge] Получен ответ: {content[:100]}")
                    return msg_type, content
            except Exception:
                pass

        # 2. Пробуем getUpdates (работает при Polling)
        try:
            updates = _api("getUpdates", offset=offset, timeout=5, limit=5)
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
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass

                # Текстовое сообщение
                text = msg.get("text", "").strip()
                if text:
                    return "text", text
        except Exception:
            # Игнорируем ошибки getUpdates (например, 409 Conflict в вебхук-режиме)
            pass

        _time.sleep(2)

    return "text", "stop"


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

    # Сигнализируем боту о начале ожидания ответа
    try:
        (ROOT / "business").mkdir(parents=True, exist_ok=True)
        (ROOT / "business" / "review_waiting.txt").write_text(str(step), encoding="utf-8")
    except Exception:
        pass

    try:
        msg_type, answer = _tg_wait_reply(timeout=600)
    finally:
        # Убираем сигнал ожидания
        try:
            (ROOT / "business" / "review_waiting.txt").unlink(missing_ok=True)
        except Exception:
            pass

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

def save_state(slug: str, context: dict, completed_step: int) -> None:
    """Сохраняет текущее состояние пайплайна в JSON. completed_step никогда не откатывается."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path = STATE_DIR / f"{slug}.json"
    # Не откатываем номер шага (resume после сбоя не должен перезаписывать прогресс)
    current_step = 0
    if state_path.exists():
        try:
            current_step = json.loads(state_path.read_text(encoding="utf-8")).get("completed_step", 0)
        except Exception:
            pass
    state = {
        "slug": slug,
        "completed_step": max(completed_step, current_step),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        # Сохраняем только сериализуемые строковые поля контекста
        "context": {
            k: v for k, v in context.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        },
    }
    content = json.dumps(state, ensure_ascii=False, indent=2)
    state_path.write_text(content, encoding="utf-8")
    gh_write(f"plans/.state/{slug}.json", content, f"chore: save state at step {completed_step}")


def load_state(slug: str) -> tuple[int, dict]:
    """
    Загружает сохранённое состояние пайплайна.
    Возвращает (последний_завершённый_шаг, контекст) или (0, {}) если нет состояния.
    """
    state_path = STATE_DIR / f"{slug}.json"
    if not state_path.exists():
        print(f"  [passport] Локальный файл состояния plans/.state/{slug}.json не найден. Загружаем с GitHub...")
        remote_content = gh_read(f"plans/.state/{slug}.json")
        if remote_content:
            try:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                state_path.write_text(remote_content, encoding="utf-8")
                print(f"  [passport] Файл состояния успешно скачан с GitHub.")
            except Exception as e:
                print(f"  [passport] Ошибка сохранения скачанного файла состояния: {e}")
        else:
            print(f"  [passport] Файл состояния {slug}.json не найден на GitHub.")
            
    if not state_path.exists():
        return 0, {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        step = state.get("completed_step", 0)
        ctx = state.get("context", {})
        print(f"  [passport] Загружено состояние: шаг {step} завершён ({state.get('saved_at', '')[:19]})")
        return step, ctx
    except Exception as e:
        print(f"  [passport] Ошибка загрузки: {e}")
        return 0, {}


def parse_editor_min_score(editor_report: str) -> int:
    """Извлекает минимальный балл из отчёта editor-critic. Использует run_fast (8b модель)."""
    import re
    scores = re.findall(r"(\d+)/10", editor_report)
    if scores:
        return min(int(s) for s in scores)
    # Запасной вариант: быстрый LLM-парсинг
    out, _ = run_fast(
        f"Извлеки минимальный балл из этого отчёта редактора. "
        f"Верни только одно число (целое от 1 до 10).\n\n{editor_report[:600]}",
        quality="simple"
    )
    digits = re.findall(r"\b([1-9]|10)\b", out)
    return int(digits[0]) if digits else 7


def run_gemini_spotcheck(claims_text: str) -> tuple[bool, str]:
    """
    Проверяет 5-7 ключевых утверждений через Gemini независимо от Groq.
    Возвращает (всё_ок: bool, отчёт: str).
    Вызывается только если _gemini_client доступен.
    """
    if not _gemini_client:
        return True, "(Gemini недоступен — spot-check пропущен)"

    prompt = (
        "Ты независимый fact-checker. Для каждого утверждения ниже ответь кратко: "
        "LIKELY_TRUE / LIKELY_FALSE / UNCERTAIN — и одним предложением поясни почему.\n\n"
        "Утверждения:\n"
        f"{claims_text}\n\n"
        "Если все утверждения LIKELY_TRUE или UNCERTAIN → напиши: SPOTCHECK_PASS\n"
        "Если хотя бы одно LIKELY_FALSE → напиши: SPOTCHECK_WARN"
    )
    try:
        resp = _gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        output = resp.text.strip()
        ok = "SPOTCHECK_WARN" not in output
        return ok, output
    except Exception as e:
        return True, f"(Gemini spot-check ошибка: {e})"


def run_temporal_check(article: str) -> tuple[bool, str]:
    """
    Проверяет временную согласованность статьи через run_fast (8b модель).
    Возвращает (ок: bool, отчёт: str).
    """
    print("  [temporal-check] Проверяю временную согласованность...")
    prompt = AGENT_PROMPTS["temporal-verifier"] + f"\n\nСТАТЬЯ:\n{article[:4000]}"
    output, _ = run_fast(prompt, quality="strong")
    has_warns = "TEMPORAL_WARN_FOUND" in output
    return not has_warns, output


def run_devil_advocate(article: str) -> tuple[bool, str]:
    """
    Запускает агент оппонирования. Использует run_fast (меньшая модель достаточна).
    Возвращает (флаг_однобокости: bool, отчёт: str).
    """
    print("  [devil-advocate] Проверяю однобокость тезиса...")
    prompt = AGENT_PROMPTS["devil-advocate"] + f"\n\nСТАТЬЯ:\n{article[:4000]}"
    output, tokens = run_fast(prompt, quality="strong")
    flagged = "ADVOCATE_FLAG" in output
    icon = "⚠️" if flagged else "✅"
    tg_notify(
        f"{icon} <b>devil-advocate</b>\n"
        f"{'Обнаружена однобокость — рекомендуется добавить раздел ограничений' if flagged else 'Статья сбалансирована'}\n"
        f"~{tokens} токенов\n\n{output[:600]}"
    )
    return flagged, output


def run_hallucination_detector(draft: str, raw_sources: str) -> tuple[bool, str]:
    """
    Детектор галлюцинаций — проверяет что все названия компаний, продуктов,
    персон в тексте присутствуют в исходных источниках.

    Ловит ошибки типа:
    - "Devika" когда в источнике только "Devin"
    - Неизвестные названия продуктов/компаний
    - Новые персоны, не упомянутые в источниках

    Возвращает (passed: bool, report: str).
    """
    import re

    print("  [hallucination-detector] Проверяю введение новых сущностей...")

    common_terms = {
        'Series', 'Round', 'Funding', 'API', 'SDK', 'CLI', 'HTTP', 'JSON', 'XML',
        'REST', 'GraphQL', 'SQL', 'NoSQL', 'AWS', 'GCP', 'Azure', 'VM', 'GPU',
        'USD', 'EUR', 'GBP', 'CNY', 'The', 'You', 'They', 'It', 'We',
        'May', 'June', 'July', 'August', 'AI', 'ML', 'NLP', 'CV', 'LLM',
        'Yandex', 'ITMO', 'Skolkovo', 'Director', 'Directors', 'Studio', 'University',
        'School', 'Russian', 'Russia', 'Telegram', 'Bot', 'Google', 'Microsoft',
        'YouTube', 'Shorts', 'Instagram', 'TikTok', 'Canva', 'Zapier', 'Bing',
        'Ads', 'Chrome', 'Edge', 'Adobe', 'Premiere', 'Final', 'Cut', 'Imagen',
        'Ultra', 'Pro', 'Nano', 'Flash', 'Online', 'Generated', 'Kling', 'Runway',
        'Sora', 'Midjourney', 'ChatGPT', 'OpenAI', 'Anthropic', 'Claude', 'Copilot',
        'Github', 'Facebook', 'Apple', 'iOS', 'Android', 'Windows', 'Mac', 'Linux',
        'Slack', 'Zoom', 'Ollama', 'Hugging', 'Face', 'Gemma', 'VRAM', 'RAM',
        'Macbook', 'Llama'
    }

    def extract_entities(text):
        entities = set()
        for word in re.findall(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b', text):
            if len(word) > 2:
                # Игнорируем сущность, если хотя бы одно слово из нее есть в common_terms
                parts = word.split()
                if not any(p in common_terms for p in parts) and word not in common_terms:
                    entities.add(word)
        return entities

    source_entities = extract_entities(raw_sources)
    draft_entities = extract_entities(draft)

    unknowns = draft_entities - source_entities

    if not unknowns:
        report = "✅ Все сущности присутствуют в источниках"
        return True, report

    blocking_entities = []

    for entity in unknowns:
        entity_lower = entity.lower()
        found_exact_match = False
        potential_misspelling = None

        for source_ent in source_entities:
            source_lower = source_ent.lower()
            if source_lower == entity_lower:
                found_exact_match = True
                break

            if source_lower in entity_lower or entity_lower in source_lower:
                potential_misspelling = source_ent
                break

            dist = abs(len(entity) - len(source_ent))
            if dist <= 2 and source_lower[:3] == entity_lower[:3]:
                potential_misspelling = source_ent
                break

        if not found_exact_match and len(entity) > 3:
            if potential_misspelling:
                blocking_entities.append(f"{entity} (похоже на {potential_misspelling}, но не совпадает)")
            else:
                blocking_entities.append(entity)

    status = len(blocking_entities) == 0

    if blocking_entities:
        report = "❌ Обнаружены неизвестные сущности:\n  " + "\n  ".join(blocking_entities)
    else:
        report = "✅ Все сущности подтверждены источниками"

    tg_notify(
        f"{'✅' if status else '❌'} <b>hallucination-detector</b>\n"
        f"{report[:600]}"
    )

    return status, report


def run_fact_checker(draft: str, raw_sources: str, step_label: str) -> tuple[bool, str]:
    """
    Запускает трёхуровневую проверку фактов:
    1. Основная (Groq 70b): проверка всех утверждений против источников
    2. Temporal (Groq 8b): проверка временной согласованности
    3. Gemini spot-check: независимая проверка 5-7 ключевых цифр/фактов
    Блокирует пайплайн при обнаружении UNVERIFIED или CONTRADICTED утверждений.
    """
    print(f"  [fact-checker] Уровень 1: проверка против источников...")
    prompt = (
        AGENT_PROMPTS["fact-checker"]
        + f"\n\n## ЧЕРНОВИК СТАТЬИ:\n{draft}\n\n"
        + f"## ИСХОДНЫЕ ИСТОЧНИКИ:\n{raw_sources}"
    )
    output, tokens = run_claude(prompt)
    passed = "FACT_CHECK_PASSED" in output

    # Уровень 2: temporal check (run_fast, дёшево)
    temp_ok, temp_report = run_temporal_check(draft)
    if not temp_ok:
        output += f"\n\n### TEMPORAL WARNINGS:\n{temp_report}"
        tg_notify(f"⚠️ <b>temporal-check</b>: найдены временные несоответствия\n{temp_report[:400]}")

    # Уровень 3: Gemini spot-check на 5-7 ключевых утверждений (если Groq нашёл VERIFIED)
    if passed and _gemini_client:
        import re
        verified_claims = re.findall(r"VERIFIED:.*?\[(\d+)\].*?(?:\n|$)", output)
        # Извлекаем первые 5 верифицированных фактов для spot-check
        claims_for_spot = "\n".join(
            line for line in output.split("\n")
            if "VERIFIED" in line
        )[:800]
        if claims_for_spot:
            spot_ok, spot_report = run_gemini_spotcheck(claims_for_spot)
            if not spot_ok:
                output += f"\n\n### GEMINI SPOTCHECK WARNINGS:\n{spot_report}"
                tg_notify(f"⚠️ <b>Gemini spot-check</b>: расхождение с основным fact-checker\n{spot_report[:400]}")
            else:
                print(f"  [gemini-spotcheck] ✅ SPOTCHECK_PASS")

    icon = "✅" if passed else "❌"
    tg_notify(
        f"{icon} <b>fact-checker [{step_label}]</b>\n"
        f"{'Все факты верифицированы' if passed else 'Найдены непроверенные утверждения'}\n"
        f"~{tokens} токенов\n\n"
        f"{output[:800]}"
    )
    return passed, output


def run_pipeline(
    topic: str, title: str, slug: str, search_query: str,
    auto_approve: bool = False, resume: bool = False,
    mode: str = "🎯 Статья для SEO и GEO",
    pipeline_mode: str = "seo",
) -> None:
    # ── Resume: загружаем сохранённое состояние ──────────────────────────────
    last_step, saved_ctx = load_state(slug) if resume else (0, {})
    if resume and last_step > 0:
        print(f"\n▶️  Возобновляем с шага {last_step + 1} (slug: {slug})")
        tg_notify(f"▶️ <b>Возобновление пайплайна</b>\nСлуг: {slug}\nПродолжаем с шага {last_step + 1}")
    else:
        print(f"\n🚀 Content Factory — запуск генерации: {title}")
        tg_notify(f"🚀 <b>Запуск генерации</b>\n📝 {title}\n🔍 {topic}\n⚙️ Формат: {mode} (пайплайн: {pipeline_mode})")

    plan_path = create_plan(title, slug) if last_step == 0 else (PLANS_DIR / f"*_{slug}.md")
    # Если resume и план уже существует — найти его
    if resume and last_step > 0:
        matches = list(PLANS_DIR.glob(f"*_{slug}.md"))
        if not matches:
            print(f"  [passport] План для {slug} не найден локально. Ищем на GitHub...")
            plans_files = gh_list_dir("plans")
            matched_file = None
            for f in plans_files:
                if f.get("name", "").endswith(f"_{slug}.md"):
                    matched_file = f.get("name")
                    break
            if matched_file:
                remote_content = gh_read(f"plans/{matched_file}")
                if remote_content:
                    try:
                        PLANS_DIR.mkdir(parents=True, exist_ok=True)
                        dest_path = PLANS_DIR / matched_file
                        dest_path.write_text(remote_content, encoding="utf-8")
                        print(f"  [passport] План {matched_file} успешно скачан с GitHub.")
                        matches = [dest_path]
                    except Exception as e:
                        print(f"  [passport] Ошибка сохранения скачанного плана: {e}")
            else:
                print(f"  [passport] План для {slug} не найден на GitHub.")
        
        plan_path = matches[0] if matches else create_plan(title, slug)

        # Также восстанавливаем draft статьи, если он есть на GitHub
        articles_dir = ROOT / "docs" / "articles"
        local_article = articles_dir / f"{slug}.md"
        if not local_article.exists():
            remote_article = gh_read(f"docs/articles/{slug}.md")
            if remote_article:
                try:
                    articles_dir.mkdir(parents=True, exist_ok=True)
                    local_article.write_text(remote_article, encoding="utf-8")
                    print(f"  [passport] Черновик статьи {slug}.md успешно скачан с GitHub.")
                except Exception as e:
                    print(f"  [passport] Ошибка сохранения скачанного черновика: {e}")

    context: dict = {"topic": topic, "title": title, "search_query": search_query, "mode": mode, "pipeline_mode": pipeline_mode}
    context.update(saved_ctx)  # восстанавливаем сохранённые данные
    # ...
    search_query = context.get("search_query", search_query)
    mode = context.get("mode", mode)
    pipeline_mode = context.get("pipeline_mode", pipeline_mode)

    # Шаг 1: Оркестратор читает feedback
    if last_step >= 1:
        print("  [passport] Шаг 1 пропущен (уже выполнен)")
    else:
        r = StepResult(1, "lead-orchestrator")
        feedback = aggregate_feedback()
        context["feedback"] = feedback
        update_step(plan_path, 1)
        r.finish(feedback or "(нет feedback)", tokens=len(feedback.split()))
        save_state(slug, context, 1)

    # Шаг 1.5: проверка специфичности поискового запроса
    # Цель: не «влезет ли в 1500 слов», а «вернёт ли запрос конкретные результаты»
    if last_step < 2:
        scope_prompt = (
            f"Оцени поисковый запрос: достаточно ли он специфичен, чтобы поисковик вернул "
            f"конкретные, релевантные результаты — а не общий обзор из 100 разных статей?\n\n"
            f"Тема: «{topic}»\n"
            f"Поисковый запрос: «{search_query}»\n\n"
            f"Примеры слишком общих запросов (вернут всё подряд):\n"
            f"- «ИИ инструменты для разработчиков» — слишком широко\n"
            f"- «машинное обучение 2026» — слишком широко\n\n"
            f"Примеры конкретных запросов (вернут нужное):\n"
            f"- «GitHub Copilot тарификация по запросам 2026» — конкретно\n"
            f"- «как работает механизм attention в трансформерах» — конкретно\n"
            f"- «Андрей Карпати vibe coding концепция» — конкретно\n\n"
            f"Если запрос СЛИШКОМ ОБЩИЙ — напиши один более конкретный запрос на русском (одна строка).\n"
            f"Если запрос ДОСТАТОЧНО КОНКРЕТНЫЙ — напиши: SCOPE_OK"
        )
        scope_result, _ = run_fast(scope_prompt, quality="simple")
        scope_result = scope_result.strip()
        if not scope_result or "SCOPE_OK" not in scope_result:
            lines = scope_result.splitlines()
            narrowed = lines[0].strip("•-* \"'`") if lines else ""
            if narrowed and len(narrowed) > 5:
                print(f"  [scope] ⚠️ Запрос слишком общий → уточняю: «{narrowed}»")
                tg_notify(f"🔍 <b>Шаг 1.5 — scope</b>: запрос уточнён\n«{search_query}» → «{narrowed}»")
                search_query = narrowed
                context["search_query"] = search_query
            else:
                print("  [scope] ✅ Запрос достаточно конкретен")
        else:
            print("  [scope] ✅ Запрос достаточно конкретен")
        save_state(slug, context, 1)

    # Шаг 2: knowledge-retriever (пропускается в режиме news)
    if pipeline_mode == "news":
        print("  [news] Шаг 2 пропущен (режим новость)")
        context.setdefault("knowledge_pack", "")
        save_state(slug, context, 2)
    elif last_step >= 2:
        print("  [passport] Шаг 2 пропущен (уже выполнен)")
    else:
        r = StepResult(2, "knowledge-retriever")
        prompt = AGENT_PROMPTS["knowledge-retriever"].format(topic=topic)
        output, tokens = run_claude(prompt)
        context["knowledge_pack"] = output
        update_step(plan_path, 2)
        r.finish(output, tokens=tokens)
        save_state(slug, context, 2)

    # Шаг 3: web-researcher — двухслойный поиск через ddgs + full-text trafilatura
    if last_step >= 3 and context.get("web_pack"):
        print("  [passport] Шаг 3 пропущен (уже выполнен)")
        fresh, deep = [], []  # списки не сериализуются в passport; FINER пропустится мягко
        has_fresh = context.get("has_fresh_news", False)
    else:
        r = StepResult(3, "web-researcher")
        _sq = search_query or topic

        if pipeline_mode == "news":
            # Режим новость: только свежие источники, без глубинного поиска
            print("  [news] Ищу свежие источники (1 слой)...")
            tg_notify(f"🔍 <b>Шаг 03 [новость]</b> — web-researcher\n⏳ Ищу свежие источники...")
            fresh = web_search_fresh(_sq, max_results=5)
            deep = []
            print(f"  Найдено свежих: {len(fresh)}")
        else:
            print("  [Слой 1] Ищу свежие новости за неделю...")
            tg_notify(f"🔍 <b>Шаг 03</b> — web-researcher\n⏳ Ищу актуальные источники...")
            fresh = web_search_fresh(_sq, max_results=3)
            print(f"  Найдено свежих: {len(fresh)}")
            print("  [Слой 2] Ищу глубинные источники...")
            deep = web_search_deep(f"{_sq} практика кейсы руководство", max_results=5)
            print(f"  Найдено глубинных: {len(deep)}")

        context["raw_sources"] = format_raw_sources(fresh, deep)
        search_block = format_search_for_llm(fresh, deep)
        has_fresh = any(s.get("fresh") for s in fresh)

        freshness_warning = "" if has_fresh else (
            "\n\n⚠️ ВНИМАНИЕ: горячих новостей за последнюю неделю не найдено. "
            "На шаге 4 автор должен решить: использовать имеющееся или выбрать другую тему."
        )
        if pipeline_mode == "news":
            synthesis_prompt = (
                f"Ты редактор новостного раздела. Тема: «{topic}».\n\n"
                f"Ниже — найденные материалы. Работай ТОЛЬКО с ними.\n\n"
                f"{search_block}\n\n"
                f"Задача:\n"
                f"1. Определи главный информационный повод\n"
                f"2. Выдели 3-5 ключевых фактов с URL-источниками\n"
                f"3. Предложи структуру новостной заметки (лид + 2-3 блока H2)\n"
                f"{freshness_warning}"
            )
        else:
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
        context["has_fresh_news"] = has_fresh
        update_step(plan_path, 3)
        r.finish(output, tokens=tokens)
        save_state(slug, context, 3)

    # Шаг 3.5: FINER gate — оцениваем тему, блокируем при F=0
    # При resume (last_step >= 3) поиск не выполнялся, fresh/deep пусты → пропускаем
    if last_step >= 3 and context.get("web_pack"):
        print("  [passport] FINER gate пропущен (уже выполнен на шаге 3)")
        finer_report = context.get("finer_report", "")
    else:
        finer_ok, finer_report = finer_gate(topic, fresh, deep, mode=pipeline_mode)
        context["finer_report"] = finer_report
        print(f"\n  [FINER gate]\n{finer_report}")
        if not finer_ok:
            tg_notify(
                f"🚫 <b>FINER gate: СТОП</b>\n\n{finer_report}\n\n"
                f"Генерация прекращена. Выберите другую тему или расширьте поисковый запрос."
            )
            print("\n🚫 FINER gate: нет источников. Генерация остановлена.")
            sys.exit(1)
        tg_notify(f"🔍 <b>FINER gate: OK</b>\n{finer_report}")

    fresh_summary = "\n".join(
        f"🔴 [{s['date']}] {s['title']} {_TIER_LABEL[_source_tier(s.get('url',''))]}"
        for s in fresh
    ) if fresh else "⚠️ Свежих новостей нет"

    # Шаг 3.6: Gap Analysis — определяем что важно для ЭТОЙ темы, но не попало в источники
    # Пропускается в режиме news (нет времени на дозапросы)
    if pipeline_mode == "news":
        print("  [news] Gap Analysis пропущен (режим новость)")
    elif last_step < 3:
        gap_prompt = (
            f"Тема статьи: «{topic}»\n\n"
            f"Найденные источники:\n{context.get('raw_sources', '')[:2000]}\n\n"
            f"Задача: определи, что ОБЯЗАТЕЛЬНО должна раскрыть полноценная статья на эту тему, "
            f"но чего НЕТ в найденных источниках.\n\n"
            f"Это зависит от типа темы:\n"
            f"- обзор инструментов/продуктов → конкретные инструменты или решения\n"
            f"- техническая тема → ключевые концепции, алгоритмы, исследования\n"
            f"- тема о человеке → важные события биографии, работы, цитаты\n"
            f"- аналитика → данные, исследования, статистика\n\n"
            f"Формат ответа: список поисковых запросов (1-5 штук), которые найдут недостающее.\n"
            f"Каждый запрос — отдельная строка, без нумерации и маркеров.\n"
            f"Если источники достаточно полны — напиши: COVERAGE_OK"
        )
        gap_result, _ = run_fast(gap_prompt, quality="strong")
        if "COVERAGE_OK" not in gap_result:
            queries = [
                line.strip("•-* ").strip()
                for line in gap_result.splitlines()
                if line.strip() and not line.startswith("#") and len(line.strip()) > 5
            ][:5]
            print(f"  [gap-analysis] Дозапрашиваю по {len(queries)} запросам...")
            tg_notify(f"🔍 <b>Gap Analysis</b>: дополняю источники по {len(queries)} запросам")
            for q in queries:
                extra = web_search_deep(q, max_results=2)
                if extra:
                    extra_block = format_raw_sources([], extra)
                    context["raw_sources"] = context.get("raw_sources", "") + "\n\n---\n\n" + extra_block
                    print(f"    +{len(extra)} источн. → «{q[:55]}»")
        save_state(slug, context, 3)

    # Шаг 3.7: генерируем 2-3 варианта угла статьи на основе реальных найденных источников
    if last_step < 3:
        angles_prompt = (
            f"Тема: «{topic}»\n\n"
            f"Найденные источники (заголовки и даты):\n"
            f"{context.get('raw_sources', '')[:3000]}\n\n"
            f"На основе РЕАЛЬНЫХ найденных материалов предложи 2-3 варианта угла статьи.\n"
            f"Каждый вариант — это конкретный журналистский угол, основанный на том, что реально есть в источниках.\n\n"
            f"Формат каждого варианта (строго):\n"
            f"ВАРИАНТ N: [заголовок-тезис одним предложением]\n"
            f"СВЕЖЕСТЬ: [дата самого свежего источника по этой теме]\n"
            f"ИСТОЧНИКИ: [сколько источников поддерживают этот угол]\n"
            f"СУТЬ: [что конкретно будет в статье, 1-2 предложения]\n\n"
            f"Важно: предлагай только то, что реально есть в источниках. "
            f"Не придумывай углы, которые нет чем подкрепить."
        )
        angles_result, _ = run_fast(angles_prompt, quality="strong")
        context["angles"] = angles_result
        print(f"\n  [варианты угла]\n{angles_result}")
        save_state(slug, context, 3)
    else:
        angles_result = context.get("angles", "")

    # Шаг 4: HUMAN REVIEW — выбор угла статьи + утверждение структуры
    angles_block = f"\n\n🎯 <b>Варианты угла статьи</b> (выберите номер в ответе):\n{angles_result}" if angles_result else ""
    approved, corrections = human_review(
        "Выберите угол статьи и утвердите данные исследования",
        f"📰 Свежие источники:\n{fresh_summary}\n"
        f"{angles_block}\n\n"
        f"📌 Анализ исследователя:\n{context.get('web_pack', '')[:400]}\n\n"
        f"{finer_report}\n\n"
        f"📚 База знаний:\n{context['knowledge_pack'][:150]}",
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
    save_state(slug, context, 4)

    # Шаги 5-6: content-writer (с обязательным grounding по верифицированным источникам)
    rules_excerpt = RULES_FILE.read_text(encoding="utf-8")[:800] if RULES_FILE.exists() else ""
    
    # Определяем выбранный угол статьи
    selected_angle_block = ""
    if angles_result and context.get("corrections"):
        selected_angle_block = (
            f"\n\n## ВЫБРАННЫЙ УГОЛ СТАТЬИ:\n"
            f"Автор выбрал следующее направление (учти при написании):\n"
            f"{context['corrections']}\n\n"
            f"Все доступные варианты были:\n{angles_result}"
        )
    elif angles_result:
        # Автор одобрил без правок — берём первый вариант
        selected_angle_block = (
            f"\n\n## УГОЛ СТАТЬИ:\n"
            f"Пиши по первому варианту из предложенных:\n{angles_result.splitlines()[0] if angles_result else ''}"
        )
        
    corrections_block = (
        f"\n\n## ПРАВКИ И УТОЧНЕНИЯ ОТ АВТОРА:\n{context['corrections']}"
        if context.get("corrections") else ""
    ) + selected_angle_block
    
    current_mode = context.get("mode", "🎯 Статья для SEO и GEO")
    if current_mode == "🔬 Статья-исследование":
        mode_instructions = (
            "\n\n## ФОРМАТ: СТАТЬЯ-ИССЛЕДОВАНИЕ (Technical Deep Dive / Research Paper)\n"
            "- Фокусируйся на глубоком техническом анализе, бенчмарках, архитектуре решений и деталях реализации.\n"
            "- Приводи точные цифры, сравнительные таблицы, примеры кода или конфигураций из источников.\n"
            "- Избегай общих фраз и поверхностных инструкций. Давай академический и экспертный разбор.\n"
            "- Обязательно укажи ограничения текущих решений и потенциальные направления развития.\n"
        )
    elif current_mode == "📰 Новостной обзор":
        mode_instructions = (
            "\n\n## ФОРМАТ: НОВОСТНОЙ ОБЗОР (News Analysis / Industry Update)\n"
            "- Сфокусируйся на свежем инфоповоде. Опиши главное событие последних дней/недели.\n"
            "- Сравни реакцию разных источников, мнения экспертов и представителей индустрии.\n"
            "- Опиши практические последствия новости: как это повлияет на рынок, разработчиков и бизнес.\n"
            "- Делай повествование динамичным, актуальным и структурированным по ключевым аспектам события.\n"
        )
    else:
        mode_instructions = (
            "\n\n## ФОРМАТ: СТАТЬЯ ДЛЯ SEO И GEO (SEO/GEO-optimized Guide / Tutorial)\n"
            "- Пиши в стиле пошагового практического руководства или подробного гайда.\n"
            "- Структурируй текст так, чтобы читатель мог легко повторить описанные шаги.\n"
            "- Естественно интегрируй LSI-ключи и следи, чтобы первые предложения H2 давали прямой ответ на вопросы (AEO).\n"
            "- Используй простые аналогии и форматируй списки для легкого сканирования глазами.\n"
        )

    if pipeline_mode == "news":
        # Режим новость: один вызов, промпт news-writer
        if last_step >= 5 and context.get("draft_1-3"):
            print("  [passport] Шаг 5 пропущен (уже выполнен)")
        else:
            r = StepResult(5, "news-writer")
            prompt = (
                AGENT_PROMPTS["news-writer"].format(
                    title=title,
                    rules_excerpt=rules_excerpt,
                    raw_sources=context.get("raw_sources", ""),
                )
                + corrections_block
            )
            output, tokens = run_claude(prompt, inject_feedback=True)
            context["draft_1-3"] = output
            context["draft_4-6"] = ""
            update_step(plan_path, 5)
            update_step(plan_path, 6)
            r.finish(output, tokens=tokens)
            save_state(slug, context, 6)
        full_draft = context.get("draft_1-3", "")

        # Шаг 6.3: reduce_excessive_headings для режима NEWS
        print(f"  [news-optim] Проверяю количество заголовков и ценность блоков...")
        cleaned = reduce_excessive_headings(full_draft, max_h2=2, pipeline_mode="news")
        if len(cleaned) != len(full_draft):
            print(f"  [news-optim] Оптимизация: удалены низкоценностные блоки")
            h2_before = len(__import__('re').findall(r'^## ', full_draft, __import__('re').MULTILINE))
            h2_after = len(__import__('re').findall(r'^## ', cleaned, __import__('re').MULTILINE))
            print(f"  [news-optim] H2 заголовков: {h2_before} → {h2_after}")

            # Шаг 6.3.1: Проверяем логику после удаления блоков
            print(f"  [logic-check] Проверяю целостность статьи после сокращения...")
            is_coherent, logic_report = verify_article_logic(cleaned)
            print(f"  [logic-check] {logic_report}")

            # Если есть проблемы — переписываем для целостности
            if not is_coherent:
                print(f"  [logic-rewrite] Обнаружены разрывы логики — переписываю...")
                tg_notify("🔄 <b>logic-rewrite</b>: Переписываю блоки для целостности статьи")
                rewritten = rewrite_for_coherence(cleaned, logic_report, context.get("raw_sources", ""))
                if len(rewritten) >= len(cleaned) * 0.6:
                    cleaned = rewritten
                    print(f"  [logic-rewrite] ✅ Статья переписана для целостности")
                else:
                    print(f"  [logic-rewrite] ⚠️ Переписанная версия слишком короткая — используюю оптимизированную")

            full_draft = cleaned
            context["draft_1-3"] = cleaned
    else:
        if last_step >= 6 and context.get("draft_1-3"):
            print("  [passport] Шаги 5-6 пропущены (уже выполнены)")
        else:
            if last_step < 5:
                r = StepResult(5, "content-writer")
                prompt = (
                    AGENT_PROMPTS["content-writer"].format(
                        title=title,
                        rules_excerpt=rules_excerpt,
                        knowledge_pack=context.get("knowledge_pack", ""),
                        web_pack=context.get("web_pack", ""),
                        raw_sources=context.get("raw_sources", ""),
                    )
                    + mode_instructions
                    + corrections_block
                    + "\n\nНапиши всю статью целиком от введения до заключения по предложенной структуре."
                )
                output, tokens = run_claude(prompt, inject_feedback=True)
                context["draft_1-3"] = output
                context["draft_4-6"] = ""
                update_step(plan_path, 5)
                r.finish(output, tokens=tokens)
                save_state(slug, context, 5)

            if last_step < 6:
                update_step(plan_path, 6)
                save_state(slug, context, 6)
        full_draft = context.get("draft_1-3", "")

    # Auto revision loop: быстрая само-проверка черновика (пропускается в режиме news)
    if pipeline_mode == "news":
        print("  [news] Auto-revision пропущен (режим новость)")
    elif last_step < 6:
        revision_prompt = (
            f"Ты редактор-корректор. Прочитай черновик статьи и найди:\n"
            f"1. Разделы с маркером [INSUFFICIENT_SOURCES] — перечисли их\n"
            f"2. Разделы короче 150 слов без конкретных фактов\n"
            f"3. Первые предложения H2, которые НЕ являются прямым ответом на вопрос\n\n"
            f"Если всё в порядке → напиши: DRAFT_OK\n"
            f"Если есть проблемы → напиши: DRAFT_ISSUES, затем список\n\n"
            f"Черновик:\n{full_draft[:5000]}"
        )
        revision_check, _ = run_fast(revision_prompt, quality="strong")
        if "DRAFT_ISSUES" in revision_check and "INSUFFICIENT_SOURCES" in revision_check:
            print("  [auto-revision] Обнаружены INSUFFICIENT_SOURCES — пересоздаю проблемные блоки")
            tg_notify("🔄 <b>auto-revision</b>: Найдены незаполненные блоки, пересоздаю...")
            fix_prompt = (
                AGENT_PROMPTS["content-writer"].format(
                    title=title,
                    rules_excerpt=rules_excerpt,
                    knowledge_pack=context.get("knowledge_pack", ""),
                    web_pack=context.get("web_pack", ""),
                    raw_sources=context.get("raw_sources", ""),
                )
                + corrections_block
                + f"\n\nТекущий черновик имеет незаполненные блоки:\n{revision_check}\n\n"
                + "Перепиши ТОЛЬКО блоки с [INSUFFICIENT_SOURCES], используя доступные источники. "
                + "Остальной текст оставь без изменений. Верни полный исправленный черновик."
            )
            fixed_draft, fix_tokens = run_claude(fix_prompt, inject_feedback=True)
            if len(fixed_draft) >= len(full_draft) * 0.7:
                full_draft = fixed_draft
                context["draft_1-3"] = full_draft  # обновляем для последующих шагов
                print("  [auto-revision] ✅ Черновик исправлен")
            save_state(slug, context, 6)

    # Шаг 6.4: hallucination-detector — блокируем если найдены новые неизвестные сущности
    halluc_ok, halluc_report = run_hallucination_detector(full_draft, context["raw_sources"])
    context["hallucination_report"] = halluc_report

    if not halluc_ok:
        if auto_approve:
            print(f"\n⚠️ [auto-approve] hallucination-detector FAILED, но продолжаем выполнение из-за --auto-approve:\n{halluc_report}")
            tg_notify(
                f"⚠️ <b>hallucination-detector: ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
                f"В черновике найдены неизвестные сущности, но генерация продолжается из-за --auto-approve.\n\n"
                f"{halluc_report[:600]}"
            )
        else:
            tg_notify(
                f"🚫 <b>hallucination-detector: СТОП</b>\n\n"
                f"В черновике найдены введённые сущности, отсутствующие в источниках.\n\n"
                f"{halluc_report[:1000]}\n\n"
                f"Генерация прекращена. Проверьте исходные источники или переформулируйте запрос."
            )
            print(f"\n🚫 hallucination-detector FAILED:\n{halluc_report}")
            sys.exit(1)

    print("  [hallucination-detector] ✅ Галлюцинаций не обнаружено")

    # Шаг 6.5: fact-checker — блокируем если найдены непроверенные утверждения
    fact_ok, fact_report = run_fact_checker(full_draft, context["raw_sources"], "6.5")
    context["fact_check_report"] = fact_report

    def _parse_fact_counts(report: str) -> tuple[int, int]:
        import re as _re
        _u = _re.search(r"UNVERIFIED:\s*\*{0,2}(\d+)", report)
        _c = _re.search(r"CONTRADICTED:\s*\*{0,2}(\d+)", report)
        return (int(_u.group(1)) if _u else 99), (int(_c.group(1)) if _c else 99)

    _unverified_count, _contradicted_count = (0, 0) if fact_ok else _parse_fact_counts(fact_report)

    # Авто-исправление CONTRADICTED (max 2 попытки)
    # Проверяем только CONTRADICTED — UNVERIFIED обрабатываются отдельно (strip)
    _contradicted_before_fix = _contradicted_count
    for _fix_attempt in range(2):
        if fact_ok or _contradicted_count == 0 or _contradicted_count > 8:
            break
        print(f"  [fact-autofix] Попытка {_fix_attempt + 1}: исправляю {_contradicted_count} CONTRADICTED...")
        tg_notify(f"🔄 <b>fact-autofix (попытка {_fix_attempt + 1})</b>: Исправляю противоречивые утверждения...")
        fix_prompt = (
            f"Ты редактор-фактчекер. В статье обнаружены CONTRADICTED-утверждения.\n\n"
            f"Отчёт фактчекера:\n{fact_report}\n\n"
            f"Исправь статью: удали или нейтрализуй только проблемные формулировки, "
            f"указанные в разделе CONTRADICTED. Остальной текст не меняй.\n\n"
            f"Статья:\n{full_draft}"
        )
        fixed, _ = run_claude(fix_prompt)
        if len(fixed) >= len(full_draft) * 0.7:
            full_draft = fixed
            context["draft_1-3"] = full_draft
            print(f"  [fact-autofix] ✅ Черновик исправлен — повторная проверка")
            fact_ok, fact_report = run_fact_checker(full_draft, context["raw_sources"], f"6.5r{_fix_attempt + 1}")
            context["fact_check_report"] = fact_report
            _unverified_count, _contradicted_count = (0, 0) if fact_ok else _parse_fact_counts(fact_report)
        else:
            break  # исправленная версия слишком короткая — прекращаем попытки

    if not fact_ok:
        if auto_approve:
            print(f"\n⚠️ [auto-approve] fact-checker FAILED, но продолжаем выполнение из-за --auto-approve:\n{fact_report}")
            tg_notify(
                f"⚠️ <b>fact-checker: ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
                f"В черновике обнаружены непроверенные утверждения, но генерация продолжается из-за --auto-approve.\n\n"
                f"{fact_report[:600]}"
            )
        else:
            tg_notify(
                f"🚫 <b>fact-checker: СТОП</b>\n\n"
                f"В черновике обнаружены непроверенные или противоречивые утверждения.\n\n"
                f"{fact_report[:1000]}\n\n"
                f"Генерация прекращена. Перезапустите с другой темой или добавьте источники."
            )
            print(f"\n🚫 fact-checker FAILED:\n{fact_report}")
            sys.exit(1)

    print("  [fact-checker] ✅ FACT_CHECK_PASSED")
    save_state(slug, context, 6)

    # Шаг 6.7: entity-validator — проверка названий компаний/продуктов
    print(f"  [entity-validator] Проверяю названия компаний и продуктов...")
    entity_valid, entity_errors = validate_entity_names(full_draft, context["raw_sources"])
    if entity_errors:
        print(f"  [entity-validator] ⚠️ Найдены ошибки в названиях:")
        for error in entity_errors:
            print(f"    {error}")
        # КРИТИЧЕСКИЕ ошибки (❌) блокируют статью, ПРЕДУПРЕЖДЕНИЯ (⚠️) логируют
        critical_errors = [e for e in entity_errors if e.startswith("❌")]
        if critical_errors:
            tg_notify(f"🚫 <b>entity-validator: КРИТИЧЕСКАЯ ОШИБКА</b>\n\n{''.join(critical_errors)}")
            print(f"\n🚫 entity-validator FAILED (критические ошибки в названиях):")
            for error in critical_errors:
                print(f"  {error}")
            sys.exit(1)
        else:
            # Только предупреждения — логируем и продолжаем
            tg_notify(f"⚠️ <b>entity-validator: предупреждения</b>\n\n{''.join([e for e in entity_errors if e.startswith('⚠️')])}")
    else:
        print(f"  [entity-validator] ✅ Все названия компаний совпадают с источниками")

    # Шаг 6.75: number-validator — проверка чисел, процентов, единиц измерения
    print(f"  [number-validator] Проверяю числа и проценты...")
    num_ok, num_report = validate_numbers(full_draft, context.get("raw_sources", ""))
    if not num_ok:
        tg_notify(f"🔢 <b>number-validator</b>: найдены числовые ошибки\n\n{num_report[:800]}")
        print(f"  [number-validator] ⚠️ Найдены числовые ошибки — исправляю...")
        fix_prompt = (
            f"Ты редактор. Исправь числовые ошибки в статье согласно отчёту.\n\n"
            f"Отчёт:\n{num_report}\n\n"
            f"Правила исправления:\n"
            f"- Тип A (изобретённые числа): удали число или замени на качественное описание\n"
            f"- Тип B (неверный перевод): исправь по формуле «в N раз меньше» = на (1-1/N)×100%\n"
            f"- Тип C (неверная единица): исправь единицу по источнику\n"
            f"- Тип D (нет базы): добавь «по сравнению с [X]» или удали процент\n"
            f"Не трогай числа без замечаний. Верни полный текст статьи.\n\n"
            f"Статья:\n{full_draft}"
        )
        fixed, _ = run_claude(fix_prompt)
        if len(fixed) >= len(full_draft) * 0.7:
            full_draft = fixed
            context["draft_1-3"] = full_draft
            print(f"  [number-validator] ✅ Числовые ошибки исправлены")
        else:
            print(f"  [number-validator] ⚠️ Автофикс вернул короткий результат — пропускаю")
    else:
        print(f"  [number-validator] ✅ Все числа корректны")
    # save_state вызывается в следующем шаге (7)

    # ── SEO-качество: три дополнительных прохода (для всех режимов, включая news, чтобы избежать воды и повторов) ──
    if True:
        # Шаг 6.8: Semantic dedup — убираем смысловые повторы между H2
        print("  [semantic-dedup] Ищу смысловые повторы между секциями...")
        has_dups, dedup_report = detect_semantic_duplicates(full_draft)
        if has_dups:
            tg_notify("🔄 <b>semantic-dedup</b>: Найдены повторы — объединяю секции...")
            merge_prompt = (
                f"Ты редактор. Объедини или удали дублирующиеся разделы статьи по отчёту.\n\n"
                f"Отчёт:\n{dedup_report}\n\n"
                f"Правило: при объединении сохраняй все уникальные факты из обоих разделов. "
                f"Не удаляй утверждения с ссылками [1], [2] и т.д. "
                f"Верни полный текст статьи.\n\n"
                f"Статья:\n{full_draft}"
            )
            merged, _ = run_claude(merge_prompt)
            if len(merged) >= len(full_draft) * 0.6:
                full_draft = merged
                context["draft_1-3"] = full_draft
                print("  [semantic-dedup] ✅ Дубликаты устранены")
            else:
                print("  [semantic-dedup] ⚠️ Результат слишком короткий — пропускаю")
        else:
            print("  [semantic-dedup] ✅ Смысловых повторов нет")
        tg_notify(f"🔍 <b>semantic-dedup</b>: {'повторы найдены и устранены' if has_dups else 'OK — повторов нет'}")

        # Шаг 6.9: Content value — усиляем слабые блоки
        print("  [content-value] Оцениваю ценность блоков...")
        scores = assess_content_value(full_draft)
        weak_count = sum(1 for s in scores.values() if s < 4)
        if weak_count > 0:
            print(f"  [content-value] ⚠️ Найдено {weak_count} слабых блоков — усиляю...")
            tg_notify(f"🔄 <b>content-value</b>: {weak_count} слабых блоков — усиляю")
            strengthened = strengthen_weak_sections(full_draft, context.get("raw_sources", ""))
            if strengthened != full_draft:
                full_draft = strengthened
                context["draft_1-3"] = full_draft
                print("  [content-value] ✅ Слабые блоки усилены")
            else:
                print("  [content-value] ⚠️ Без изменений (источники не позволяют добавить конкретику)")
        else:
            print("  [content-value] ✅ Все блоки достаточно ценные")

        # Шаг 6.10: Readability — читаемость и устранение паразитов
        print("  [readability] Улучшаю читаемость и устраняю слова-паразиты...")
        tg_notify("✍️ <b>readability</b>: улучшаю читаемость...")
        improved = improve_readability_seo(full_draft)
        if improved != full_draft:
            full_draft = improved
            context["draft_1-3"] = full_draft
            print("  [readability] ✅ Читаемость улучшена")
        else:
            print("  [readability] ⚠️ Без изменений")

        save_state(slug, context, 6)
    # ─────────────────────────────────────────────────────────────────────────────────

    # Шаг 7: diagram-illustrator (пропускается в режиме news)
    if pipeline_mode == "news":
        print("  [news] Диаграммы пропущены (режим новость)")
        context.setdefault("diagrams", "")
    else:
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

    # Проверка черновика перед публикацией
    _draft_bad_signs = ["передай мне реальную", "предоставь источники", "это не статья",
                        "сообщение об ошибке", "написать невозможно", "оптимизировать нечего"]
    if not full_draft or len(full_draft) < 200 or any(s in full_draft.lower() for s in _draft_bad_signs):
        print("❌ Черновик пустой или содержит ошибку LLM — генерация остановлена.")
        tg_notify("❌ <b>Генерация остановлена</b>: черновик пустой или невалидный.")
        sys.exit(1)

    # Шаг 8-9: seo-geo-optimizer
    if last_step >= 8 and context.get("optimized_draft"):
        print("  [passport] Шаги 8-9 пропущены (уже выполнены)")
    else:
        r = StepResult(8, "seo-geo-optimizer")
        if pipeline_mode == "news":
            seo_prompt = (
                "Ты SEO-оптимизатор. Получи короткую новостную статью и: "
                "1. Интегрируй 3-5 ключевых слов естественно в текст. "
                "2. Проверь AEO: первые предложения H2 должны быть самодостаточными ответами. "
                "3. Сгенерируй Schema.org JSON-LD (NewsArticle) для этой статьи. "
                "4. Верни оптимизированный текст + JSON-LD блок отдельно."
            )
            prompt = seo_prompt + f"\n\nСтатья:\n{full_draft}"
        else:
            prompt = AGENT_PROMPTS["seo-geo-optimizer"] + f"\n\nЧерновик:\n{full_draft}"
        output, tokens = run_claude(prompt)
        context["optimized_draft"] = output
        update_step(plan_path, 8)
        update_step(plan_path, 9)
        r.finish(output, tokens=tokens)
        save_state(slug, context, 8)

    # Шаг 10: geo-emulator (пропускается в режиме news)
    if pipeline_mode == "news":
        print("  [news] GEO-эмулятор пропущен (режим новость)")
        context.setdefault("geo_report", "")
    else:
        r = StepResult(10, "geo-emulator")
        prompt = AGENT_PROMPTS["geo-emulator"].format(
            topic=topic, search_query=search_query
        ) + f"\n\nТекст статьи:\n{context['optimized_draft']}"
        output, tokens = run_claude(prompt)
        context["geo_report"] = output
        update_step(plan_path, 10)
        r.finish(output, tokens=tokens)

    # Шаг 11: editor-critic (работает в том числе в режиме news)
    if last_step >= 11 and context.get("editor_report"):
        print("  [passport] Шаг 11 пропущен (уже выполнен)")
    else:
        r = StepResult(11, "editor-critic")
        prompt = (
            AGENT_PROMPTS["editor-critic"]
            + f"\n\nПравила автора:\n{rules_excerpt}\n\nСтатья:\n{context['optimized_draft']}"
        )
        output, tokens = run_claude(prompt)
        context["editor_report"] = output
        update_step(plan_path, 11)
        r.finish(output, tokens=tokens)
        save_state(slug, context, 11)

    # Шаг 11.5: devil-advocate (пропускается в режиме news)
    if pipeline_mode == "news":
        print("  [news] Devil-advocate пропущен (режим новость)")
        advocate_flagged, advocate_report = False, ""
    else:
        advocate_flagged, advocate_report = run_devil_advocate(context.get("optimized_draft", ""))
    context["advocate_report"] = advocate_report
    save_state(slug, context, 11)

    # Шаг 12: HUMAN REVIEW перед публикацией (включает отчёт devil-advocate)
    advocate_warning = f"\n\n⚠️ devil-advocate: {advocate_report[:300]}" if advocate_flagged else ""
    preview = (
        f"GEO-отчет:\n{context.get('geo_report', '')[:300]}\n\n"
        f"Редактор:\n{context.get('editor_report', '')[:300]}"
        f"{advocate_warning}"
    )
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
    subprocess.run(["git", "add"] + files_to_add, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    subprocess.run(
        ["git", "commit", "-m", f"feat: article '{title}' [{slug}]"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )

    # git push with GITHUB_TOKEN / Local fallback
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO", "xopromo/content-factory")
    branch = os.getenv("GITHUB_BRANCH", "main")
    if token:
        try:
            auth_url = f"https://x-access-token:{token}@github.com/{repo}.git"
            subprocess.run(["git", "remote", "set-url", "origin", auth_url], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
            subprocess.run(["git", "push", "origin", branch], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
            print("  [deployer-publisher] Изменения успешно отправлены на GitHub с помощью GITHUB_TOKEN")
        except Exception as e:
            print(f"  [deployer-publisher] [WARN] Ошибка отправки на GitHub с GITHUB_TOKEN: {e}")
    else:
        try:
            print("  [deployer-publisher] GITHUB_TOKEN не найден, пробуем обычный git push...")
            res = subprocess.run(["git", "push", "origin", branch], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if res.returncode == 0:
                print("  [deployer-publisher] Изменения успешно отправлены на GitHub (local push)")
            else:
                print(f"  [deployer-publisher] [WARN] Ошибка git push: {res.stderr.strip()}")
        except Exception as e:
            print(f"  [deployer-publisher] [WARN] Не удалось выполнить локальный git push: {e}")

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
    parser.add_argument("--mode", default="🎯 Статья для SEO и GEO", help="Формат статьи")
    parser.add_argument("--auto-approve", action="store_true", help="Пропускать HITL-паузы (тестовый режим)")
    parser.add_argument("--resume", action="store_true", help="Возобновить с последнего сохранённого шага")
    parser.add_argument(
        "--pipeline-mode", choices=["full", "seo", "news"], default="seo",
        help=(
            "Режим генерации: "
            "seo — полный пайплайн, гибкий фактчекинг (DEFAULT, ~30 мин); "
            "news — короткая новость, минимум шагов (~15 мин); "
            "full — максимальная точность, строгий фактчекинг (~60 мин, редко)"
        )
    )
    parser.add_argument("--chat-id", help="Telegram chat_id для отправки уведомлений")
    args = parser.parse_args()

    if args.chat_id:
        TG_CHAT_ID_OVERRIDE = args.chat_id

    try:
        run_pipeline(
            topic=args.topic,
            title=args.title,
            slug=args.slug,
            search_query=args.query,
            auto_approve=args.auto_approve,
            resume=args.resume,
            mode=args.mode,
            pipeline_mode=args.pipeline_mode,
        )
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        import html
        tb_str_escaped = html.escape(tb_str)
        err_msg = (
            f"❌ <b>Критическая ошибка пайплайна!</b>\n\n"
            f"Тема: <code>{args.topic}</code>\n"
            f"Ошибка: <code>{html.escape(str(e))}</code>\n\n"
            f"<details><summary>Стек-трейс (Traceback)</summary>\n<pre>{tb_str_escaped}</pre>\n</details>\n\n"
            f"Вы можете попробовать возобновить генерацию с последнего шага."
        )
        print(f"[FATAL ERROR] {e}")
        print(tb_str)
        try:
            import json
            error_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "traceback": tb_str,
                "args": {
                    "topic": args.topic,
                    "title": args.title,
                    "slug": args.slug,
                    "query": args.query,
                    "mode": args.mode,
                    "auto_approve": args.auto_approve,
                    "resume": args.resume
                }
            }
            (ROOT / "critical_error.json").write_text(json.dumps(error_data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  [auto-healer] Сигнальный файл critical_error.json успешно записан.")
            
            # Отправляем сигнальный файл на GitHub для моментальной реакции через REST API
            token = os.getenv("GITHUB_TOKEN")
            if token:
                gh_write("critical_error.json", json.dumps(error_data, ensure_ascii=False, indent=2), f"fail: orchestrator crashed on topic '{args.topic}'")
                print("  [auto-healer] Сигнальный файл успешно отправлен на GitHub")
        except Exception as json_err:
            print(f"[AUTO-HEALER ERROR] Не удалось записать или отправить сигнальный файл: {json_err}")
        try:
            tg_notify(err_msg)
        except Exception as tg_err:
            print(f"[TG NOTIFY ERROR] {tg_err}")
        sys.exit(1)
