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
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    from groq import Groq as _Groq
    _groq_client = _Groq(api_key=os.environ.get("GROQ_KEY", "")) if os.environ.get("GROQ_KEY") else None
    _groq_client2 = _Groq(api_key=os.environ.get("GROQ_KEY_2", "")) if os.environ.get("GROQ_KEY_2") else None
except ImportError:
    _groq_client = None
    _groq_client2 = None

try:
    from google import genai as _genai
    _gemini_key = os.environ.get("GEMINI_KEY", "")
    _gemini_client = _genai.Client(api_key=_gemini_key) if _gemini_key else None
except ImportError:
    _gemini_client = None

try:
    from mistralai.client.sdk import Mistral as _Mistral
    _mistral_key = os.environ.get("MISTRAL_KEY", "")
    _mistral_client = _Mistral(api_key=_mistral_key) if _mistral_key else None
except ImportError:
    _mistral_client = None

try:
    from cerebras.cloud.sdk import Cerebras as _Cerebras
    _cerebras_key = os.environ.get("CEREBRAS_KEY", "")
    _cerebras_client = _Cerebras(api_key=_cerebras_key) if _cerebras_key else None
except ImportError:
    _cerebras_client = None

try:
    from openai import OpenAI as _OpenAI
    _openrouter_key = os.environ.get("OPENROUTER_KEY", "")
    _openrouter_client = _OpenAI(
        api_key=_openrouter_key,
        base_url="https://openrouter.ai/api/v1",
    ) if _openrouter_key else None
except ImportError:
    _openrouter_client = None

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
STATE_DIR = ROOT / "plans" / ".state"   # Material Passport — состояние пайплайна

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
    jsonld_block = ""
    # Формат 1: <script type="application/ld+json">...</script> прямо в тексте
    m = re.search(r'<script type="application/ld\+json">([\s\S]*?)</script>', md_text)
    if m:
        jsonld_block = f'<script type="application/ld+json">{m.group(1)}</script>'
        md_text = md_text[:m.start()] + md_text[m.end():]
    elif "```json" in md_text and "@context" in md_text:
        # Формат 2: ```json { ... } ```
        m2 = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", md_text)
        if m2:
            jsonld_block = f'<script type="application/ld+json">{m2.group(1)}</script>'
            md_text = md_text[:m2.start()] + md_text[m2.end():]

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
                # Ищем закрывающую ] с учётом вложенных скобок
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
                # Пропускаем маркер и trailing whitespace/newline
                while j < len(text) and text[j] in (' ', '\t', '\n'):
                    j += 1
                i = j
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)

    # Убираем заголовок + INSUFFICIENT_SOURCES если раздел только из них состоит
    md_text = re.sub(
        r'\n#{2,4}[^\n]+\n+(?=\[INSUFFICIENT_SOURCES:)',
        '\n',
        md_text,
    )
    md_text = _remove_insufficient(md_text)
    # Убираем "Примечание по JSON-LD" если осталось
    md_text = re.sub(r'\*\*Примечание по JSON-LD:\*\*[^\n]*\n?', '', md_text)
    # Убираем служебный отчёт SEO-оптимизатора перед H1 (до первого одиночного #)
    h1_match = re.search(r'^# ', md_text, re.MULTILINE)
    if h1_match:
        md_text = md_text[h1_match.start():]
    # Убираем пустые секции: заголовок H2/H3 сразу за которым следует другой заголовок или конец
    md_text = re.sub(r'\n(#{2,4}[^\n]+)\n+(?=#{1,4}|\Z)', '\n', md_text)

    # Таблицы требуют пустую строку перед первой строкой — добавляем если строка перед | не пустая
    md_text = re.sub(r'(?m)^([^|\n#][^\n]*)\n(\|)', r'\1\n\n\2', md_text)

    # Убираем метки "Лид" и "Вывод" (как строки или как заголовки)
    md_text = re.sub(r'^\*\*Лид\*\*\s*\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^\*\*Вывод\*\*\s*\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^#+\s+\*?\*?Лид\*?\*?\s*\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^#+\s+\*?\*?Вывод\*?\*?\s*\n?', '', md_text, flags=re.MULTILINE)

    # Убираем заголовок Schema.org JSON-LD (он виден в тексте, но не нужен)
    # Используем [^\n]* чтобы захватить всю строку целиком (.*? останавливался на Schema.org)
    md_text = re.sub(r'^#+\s+[^\n]*Schema\.org[^\n]*\n?', '', md_text, flags=re.MULTILINE | re.IGNORECASE)

    # Убираем блок Примечания SEO-оптимизатора (утечка внутренних заметок в статью)
    md_text = re.sub(r'\*?\*?Примечания:\*?\*?.*$', '', md_text, flags=re.DOTALL)

    # Убираем <script> теги внутри ```json блоков (JSON-LD уже извлечён отдельно)
    md_text = re.sub(r'<script[^>]*>|</script>', '', md_text)

    # Убираем пустые ```json``` блоки (остаются после извлечения JSON-LD из <script> внутри блока)
    md_text = re.sub(r'```json\s*```', '', md_text, flags=re.DOTALL)

    # Убираем жирное форматирование из текста (заменяем **text** на text)
    md_text = re.sub(r'\*\*(.*?)\*\*', r'\1', md_text)

    body_html = _md.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
    )
    body_html = _make_code_collapsible(body_html)

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
    .code-wrap {{ margin: 20px 0; }}
    .code-wrap pre {{ margin: 0; border-radius: var(--radius-md) var(--radius-md) 0 0; }}
    .code-wrap.collapsed pre {{ max-height: 104px; overflow: hidden; position: relative; }}
    .code-wrap.collapsed pre::after {{
      content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 48px;
      background: linear-gradient(transparent, var(--surface)); pointer-events: none;
    }}
    .code-toggle {{
      display: block; width: 100%; padding: 8px 16px;
      background: var(--surface2); border: 1px solid var(--border); border-top: none;
      color: var(--text-muted); cursor: pointer; font-size: 12px;
      border-radius: 0 0 var(--radius-md) var(--radius-md); text-align: center;
    }}
    .code-toggle:hover {{ color: var(--text); }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({{startOnLoad:true, theme:'dark'}});</script>
  <script>
    document.addEventListener('DOMContentLoaded', function() {{
      document.querySelectorAll('.code-wrap').forEach(function(wrap) {{
        var btn = wrap.querySelector('.code-toggle');
        if (!btn) return;
        btn.addEventListener('click', function() {{
          wrap.classList.toggle('collapsed');
          btn.textContent = wrap.classList.contains('collapsed')
            ? btn.dataset.expand : btn.dataset.collapse;
        }});
      }});
    }});
  </script>
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

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _fetch_full_text(url: str, max_chars: int = 3000) -> str:
    """Вытаскивает полный текст страницы: httpx+bs4 → trafilatura → пусто."""
    if not url:
        return ""

    # Слой 1: httpx + BeautifulSoup (работает в облаке, не зависит от trafilatura)
    try:
        import httpx
        from bs4 import BeautifulSoup
        resp = httpx.get(url, headers=_FETCH_HEADERS, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            # убираем мусор
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            # берём основной контент
            main = (
                soup.find("article")
                or soup.find("main")
                or soup.find(id="content")
                or soup.find(class_="content")
                or soup.body
            )
            if main:
                text = " ".join(main.get_text(" ", strip=True).split())
                if len(text) > 200:
                    return text[:max_chars]
    except Exception:
        pass

    # Слой 2: trafilatura как резервный
    if _trafilatura:
        try:
            downloaded = _trafilatura.fetch_url(url)
            if downloaded:
                text = _trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                    favor_recall=True,
                    no_fallback=False,
                )
                return (text or "")[:max_chars]
        except Exception:
            pass

    return ""


def validate_entity_names(article_text: str, sources_text: str) -> tuple[bool, list[str]]:
    """
    Проверяет что названия компаний/продуктов в статье совпадают ТОЧНО с источниками.
    Возвращает (is_valid, list_of_errors).
    """
    import re

    errors = []

    # Служебные слова и метаметки которые игнорируем
    ignore_list = {
        'The', 'By', 'In', 'For', 'And', 'Or', 'As', 'Is', 'Was', 'Are', 'Be',
        'Have', 'Has', 'Do', 'Does', 'Did', 'Will', 'Would', 'Should', 'Could',
        'May', 'Might', 'Must', 'Can', 'Let', 'Make', 'Get', 'Put', 'Set', 'Go',
        # Служебные слова из отчётов
        'VERIFIED', 'UNVERIFIED', 'CONTRADICTED', 'FACT_CHECK_PASSED', 'FACT_CHECK_FAILED',
        'CRITICAL', 'ERROR', 'WARNING', 'PASSED', 'FAILED', 'OK', 'ИТОГ',
        # ALL_CAPS слова вообще игнорируем (это обычно аббревиатуры)
    }

    # Ищем известные компании/продукты в статье (капитализированные слова и фразы)
    # Паттерны типа: CompanyName, Product Name, "кавычки"
    entity_patterns = [
        (r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b', 'common'),  # CamelCase или два слова с заглавной
        (r'"([^"]+)"', 'quoted'),  # В кавычках
    ]

    found_entities = set()
    for pattern, pattern_type in entity_patterns:
        for match in re.finditer(pattern, article_text):
            entity = match.group(1).strip()
            if len(entity) > 2:  # Игнорируем короткие слова (I, A, и т.д.)
                found_entities.add(entity)

    # Проверяем каждую найденную сущность
    # Если сущность есть в статье, она ДОЛЖНА быть в источниках (примерно)
    for entity in sorted(found_entities):
        # Пропускаем служебные слова и ALL_CAPS
        if entity in ignore_list or entity.isupper():
            continue

        # Ищем: есть ли в источниках похожее НО ДРУГОЕ имя?
        # Это главный кейс: "Devika" в статье, "Devin" в источниках
        entity_lower = entity.lower()

        # Если точное совпадение есть — OK, пропускаем
        if entity_lower in sources_text.lower():
            continue

        # Ищем похожее слово в источниках (возможная опечатка)
        for match in re.finditer(r'\b[A-Z][a-zA-Z]{3,}\b', sources_text):
            source_word = match.group(0)
            if source_word in ignore_list or source_word.isupper():
                continue
            if entity_lower == source_word.lower():
                break  # Точное совпадение (case-insensitive) — OK
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, entity_lower, source_word.lower()).ratio()
            # 75-99%: похожее но не идентичное → возможная опечатка
            if 0.75 < ratio < 1.0:
                errors.append(
                    f"⚠️ ВОЗМОЖНАЯ ОШИБКА ИМЕНИ: в статье '{entity}', "
                    f"в источниках похожее слово '{source_word}' — проверь, не опечатка ли!"
                )
                break

    is_valid = len(errors) == 0
    return is_valid, errors


def assess_content_value(article_text: str) -> dict:
    """
    Оценивает ценность каждого блока контента в статье (H2 → параграфы).
    Возвращает {section_index: score, ...} где score 0-10.
    Используется для удаления низкоценностного контента.
    """
    import re

    # Разбиваем статью на секции (H2 + следующие параграфы)
    h2_pattern = r'^## (.+?)$'
    sections = re.split(rf'(?m)^##', article_text)

    scores = {}

    # Первая секция (лид) всегда важная
    if len(sections) > 0:
        scores[0] = 10

    # Оцениваем каждую H2-секцию
    for idx, section in enumerate(sections[1:], start=1):
        heading_match = re.match(r' (.+?)\n', section)
        if not heading_match:
            continue

        heading = heading_match.group(1).strip()
        body = section[heading_match.end():]

        # Красные флаги: низкоценностный контент
        low_value_keywords = [
            'дизайн', 'иконка', 'логотип', 'стиль', 'внешний вид',
            'переименован', 'переименовал', 'обновил иконку',
            'минималистичный дизайн', 'визуальный'
        ]

        # Считаем слова и специфичность
        word_count = len(body.split())
        has_numbers = bool(re.search(r'\d+', body))
        has_quotes = '>' in body  # блокквоты
        has_facts = bool(re.search(r'\[(\d+)\]', body))  # ссылки на источники

        # Логика оценки
        score = 5  # базовая оценка

        # Штрафы за низкоценность
        if any(keyword in heading.lower() for keyword in low_value_keywords):
            score -= 3

        # Бонусы за специфичность
        if has_numbers:
            score += 2
        if has_facts:
            score += 1
        if has_quotes:
            score += 1
        if word_count > 200:
            score += 1
        elif word_count < 50:
            score -= 2

        # Штраф если заголовок и первое предложение == одно и то же
        first_sentence = body.split('\n')[0] if body else ""
        if first_sentence.lower().find(heading.lower()) >= 0:
            # Заголовок повторяется в тексте
            score -= 2

        # Убеждаемся что не ниже 0 и не выше 10
        scores[idx] = max(0, min(10, score))

    return scores


def validate_numbers(article_text: str, sources: str) -> tuple[bool, str]:
    """
    Проверяет числа, цифры и проценты в статье по трём уровням:
    - Тип A: изобретённые числа (нет в источниках)
    - Тип B: математически неверный перевод (в N раз → проценты)
    - Тип C: неверная единица измерения
    - Тип D: число без контекста/базы сравнения
    Возвращает (ok, report).
    """
    prompt = (
        "Ты математический редактор. Проверь все числа, цифры и проценты в статье.\n\n"
        "## Правила проверки:\n\n"
        "**Тип A — Изобретённые числа:** число есть в тексте, но отсутствует в источниках\n"
        "**Тип B — Неверный перевод кратности:**\n"
        "  - «в N раз меньше» = снижение на (1 − 1/N)×100%, НЕ на N×100%\n"
        "  - «в N раз больше» = рост на (N−1)×100%, НЕ на N×100%\n"
        "  - Примеры ошибок: «в 4 раза меньше» → «на 400% меньше» ❌ (верно: на 75%)\n"
        "  -                  «в 2 раза больше» → «на 200% больше» ❌ (верно: на 100%)\n"
        "**Тип C — Неверная единица:** число правильное, единица другая\n"
        "**Тип D — Число без базы:** «на X% быстрее» без указания по сравнению с чем\n\n"
        "## Источники:\n"
        f"{sources[:2000]}\n\n"
        "## Статья:\n"
        f"{article_text}\n\n"
        "## Формат ответа:\n"
        "Если ошибок нет → одна строка: NUMBERS_OK\n"
        "Если есть → NUMBERS_FAIL, затем список:\n"
        "ТИП [A/B/C/D]: «цитата из текста» → ПРОБЛЕМА: объяснение → ИСПРАВИТЬ: правильный вариант\n"
        "Перечисляй только реальные ошибки, не придирайся к стилю."
    )
    result, _ = run_fast(prompt)
    ok = "NUMBERS_OK" in result and "NUMBERS_FAIL" not in result
    return ok, result


def detect_semantic_duplicates(article_text: str) -> tuple[bool, str]:
    """
    Находит H2-секции с повторяющимися тезисами (>50% смыслового пересечения).
    Возвращает (has_duplicates, report_str).
    """
    import re
    h2_sections = re.findall(r'^## .+?$', article_text, re.MULTILINE)
    if len(h2_sections) < 3:
        return False, "Секций слишком мало для проверки дубликатов"

    prompt = (
        f"Ты редактор. Проверь, нет ли смысловых повторов между разделами статьи.\n\n"
        f"Разделы H2:\n" + '\n'.join(f"  - {s[3:]}" for s in h2_sections) + "\n\n"
        f"Полный текст:\n{article_text[:6000]}\n\n"
        f"Найди пары разделов, которые говорят об одном и том же (>50% совпадение тезисов).\n\n"
        f"Если дубликатов нет → ответь одной строкой: DEDUP_OK\n"
        f"Если есть → ответь: DEDUP_FOUND\n"
        f"Затем для каждой пары:\n"
        f"MERGE: «заголовок A» + «заголовок B» → оставить «A» (или «B»), убрать другой\n"
        f"REASON: [одна строка почему они дублируют друг друга]"
    )
    result, _ = run_fast(prompt)
    return "DEDUP_FOUND" in result, result


def strengthen_weak_sections(article_text: str, sources: str) -> str:
    """
    Усиливает разделы с низкой информационной ценностью (score < 3).
    Добавляет конкретику или удаляет пустые блоки.
    """
    scores = assess_content_value(article_text)
    weak = {idx: s for idx, s in scores.items() if s < 4}
    if not weak:
        return article_text

    prompt = (
        f"Ты редактор. Усиль слабые разделы статьи — добавь конкретику или удали пустые.\n\n"
        f"Правила:\n"
        f"- Если раздел < 50 слов и нет фактов → удали его целиком\n"
        f"- Если раздел без цифр/примеров → добавь конкретику ИЗ источников\n"
        f"- НЕ придумывай данные которых нет в источниках\n"
        f"- НЕ трогай разделы с оценкой ≥ 4\n\n"
        f"Слабые разделы (индекс: оценка): {weak}\n\n"
        f"Источники:\n{sources[:2000]}\n\n"
        f"Статья:\n{article_text}"
    )
    result, _ = run_claude(prompt)
    return result if len(result) >= len(article_text) * 0.7 else article_text


def improve_readability_seo(article_text: str) -> str:
    """
    Улучшает читаемость SEO-статьи:
    - Разбивает абзацы длиннее 5 предложений
    - Убирает слова-паразиты
    - Делает первые предложения H2 прямыми ответами на вопрос заголовка
    - Устраняет однотипные структуры предложений подряд
    """
    prompt = (
        f"Ты редактор с фокусом на читаемость. Улучши статью строго по правилам:\n\n"
        f"1. АБЗАЦЫ: абзац длиннее 5 предложений — раздели на 2 по смыслу\n"
        f"2. ПЕРВЫЕ ПРЕДЛОЖЕНИЯ H2: должны содержать главный факт/тезис, а не вступление\n"
        f"   Плохо: «Рассмотрим, как работает Dynamic Workflows.»\n"
        f"   Хорошо: «Dynamic Workflows запускает до сотен субагентов параллельно в одной сессии.»\n"
        f"3. СЛОВА-ПАРАЗИТЫ: убери — данный, является, осуществляет, в рамках, в целях, "
        f"следует отметить, таким образом, в настоящее время\n"
        f"4. ПОВТОРЯЮЩАЯСЯ СТРУКТУРА: не более 2 предложений подряд с одинаковым началом "
        f"(«Это позволяет...», «Это даёт...», «Это означает...» — чередуй)\n"
        f"5. ВВОДНЫЕ КЛИШЕ: убери «В этой статье мы рассмотрим», «Давайте разберёмся», «Не секрет что»\n\n"
        f"Важно: не добавляй новых фактов — только улучшай стиль и структуру.\n"
        f"Возвращай полный текст статьи.\n\n"
        f"Статья:\n{article_text}"
    )
    result, _ = run_claude(prompt)
    return result if len(result) >= len(article_text) * 0.65 else article_text


def verify_article_logic(article_text: str, removed_sections: list[str] = None) -> tuple[bool, str]:
    """
    Проверяет логику и целостность статьи после удаления блоков.
    Возвращает (is_coherent, issues_report).

    Проверяет:
    1. Есть ли разрывы между соседними H2-блоками
    2. Есть ли ссылки на удалённые концепции
    3. Согласованность вывода с фактами
    """
    import re

    if removed_sections is None:
        removed_sections = []

    issues = []

    # Извлекаем все H2-секции
    sections = re.split(r'(^## .+?$)', article_text, flags=re.MULTILINE)
    h2_headings = []
    h2_bodies = []

    for i in range(1, len(sections), 2):
        if i < len(sections):
            heading = sections[i].strip('# ').strip()
            body = sections[i + 1] if i + 1 < len(sections) else ""
            h2_headings.append(heading)
            h2_bodies.append(body)

    # Проверка 1: Вывод ссылается на удалённые концепции?
    if h2_bodies:
        last_body = h2_bodies[-1]  # Последний блок обычно вывод

        # Ищем существительные в заголовках оставшихся блоков
        remaining_concepts = set()
        for heading in h2_headings[:-1]:  # все кроме последнего (вывод)
            words = heading.lower().split()
            remaining_concepts.update([w for w in words if len(w) > 3])

        # Ищем в выводе ссылки на удалённые концепции
        for removed in removed_sections:
            removed_words = removed.lower().split()
            for word in removed_words:
                if len(word) > 4 and word in last_body.lower():
                    # Это слово было в удалённом блоке и сейчас в выводе
                    issues.append(
                        f"⚠️ Вывод ссылается на удалённую концепцию '{word}' "
                        f"(была в блоке '{removed[:30]}...')"
                    )

    # Проверка 2: Очень короткие оставшиеся блоки (<100 слов после удаления)
    for i, body in enumerate(h2_bodies):
        word_count = len(body.split())
        if word_count < 80:
            issues.append(
                f"⚠️ Блок #{i+1} очень короткий ({word_count} слов) — "
                f"может быть неполным после удаления контекста"
            )

    # Проверка 3: Нет фактов в первых блоках (числа, ссылки)
    if h2_bodies:
        first_body = h2_bodies[0]
        has_facts = bool(re.search(r'\d+|http|\[[\d]\]', first_body))
        if not has_facts and len(h2_bodies) > 1:
            issues.append(
                "⚠️ Первый блок не содержит конкретных фактов/чисел — "
                "может быть слишком общим"
            )

    is_coherent = len(issues) == 0
    report = "\n".join(issues) if issues else "✅ Логика и целостность сохранены"

    return is_coherent, report


def rewrite_for_coherence(article_text: str, logic_issues: str, sources: str) -> str:
    """
    Переписывает оставшиеся блоки статьи чтобы восстановить целостность.
    Используется когда после удаления блоков выявлены проблемы логики.
    """
    prompt = (
        "Ты редактор-логик. Статья была сокращена (удалены некоторые H2-блоки), "
        "и теперь в ней есть проблемы с логикой и связностью.\n\n"
        "ПРОБЛЕМЫ:\n" + logic_issues + "\n\n"
        "ЗАДАЧА:\n"
        "1. Перепиши оставшиеся H2-блоки так чтобы они логически связывались\n"
        "2. Убери ссылки на удалённые концепции\n"
        "3. Убедись что вывод опирается на оставшиеся факты, а не на удалённые\n"
        "4. Расширь короткие блоки (если <100 слов) добавив больше деталей\n"
        "5. Используй ТОЛЬКО информацию из источников, не придумывай новое\n\n"
        "ИСТОЧНИКИ (для проверки):\n" + sources[:2000] + "\n\n"
        "СТАТЬЯ:\n" + article_text + "\n\n"
        "Верни только переписанную статью (без комментариев)."
    )
    result, _ = run_fast(prompt)
    return result


def reduce_excessive_headings(article_text: str, max_h2: int = 2, mode: str = "news") -> str:
    """
    Для режима NEWS: убирает лишние H2-заголовки если их больше чем max_h2.
    ВАЖНО: сохраняет порядок секций и не нарушает логику (не удаляет контекстные блоки).

    Стратегия:
    1. Сначала удаляем очень низкоценностные (<3 балла)
    2. Если всё ещё слишком много — объединяем соседние блоки вместо удаления
    """
    import re

    if mode != "news":
        return article_text

    # Оцениваем каждый блок
    scores = assess_content_value(article_text)

    # Если H2 меньше чем максимум — ничего не делаем
    h2_count = len(re.findall(r'^## ', article_text, re.MULTILINE))
    if h2_count <= max_h2:
        return article_text

    # СТРАТЕГИЯ 1: Удаляем ОЧЕНЬ низкоценностные блоки (score < 3)
    sections = re.split(r'(^## .+?$)', article_text, flags=re.MULTILINE)
    result_parts = []
    idx = 0
    section_idx = 0

    while idx < len(sections):
        if idx == 0:
            result_parts.append(sections[idx])
            idx += 1
        elif idx < len(sections) - 1 and sections[idx].startswith('##'):
            heading = sections[idx]
            body = sections[idx + 1] if idx + 1 < len(sections) else ""
            section_idx += 1
            score = scores.get(section_idx, 5)

            # Пороги: удаляем только очень низкие (score < 2)
            if score >= 2:
                result_parts.append(heading)
                result_parts.append(body)

            idx += 2
        else:
            idx += 1

    cleaned = ''.join(result_parts)
    remaining_h2 = len(re.findall(r'^## ', cleaned, re.MULTILINE))

    # СТРАТЕГИЯ 2: Если всё ещё слишком много H2 — объединяем вместо удаления
    if remaining_h2 > max_h2:
        # Берём индексы секций в ПОРЯДКЕ ПОЯВЛЕНИЯ (не по оценке!)
        # и удаляем только наихудшие из "средних" (не трогаем первую и последнюю)
        sections_data = []
        for i, score in scores.items():
            if i > 0:  # пропускаем лид
                sections_data.append((i, score))

        # Сортируем по ИНДЕКСУ (порядок в статье), но помечаем оценку
        sections_data.sort(key=lambda x: x[0])

        # Удаляем нижние (max_h2 - 1) секций по оценке, но СОХРАНЯЕМ ПОРЯДОК оставшихся
        num_to_remove = remaining_h2 - max_h2
        lowest_scores = sorted(sections_data, key=lambda x: x[1])[:num_to_remove]
        remove_indices = {i for i, _ in lowest_scores}

        # Перестраиваем, удаляя только те, что в remove_indices
        sections = re.split(r'(^## .+?$)', cleaned, flags=re.MULTILINE)
        result_parts = []
        section_idx = 0
        idx = 0

        while idx < len(sections):
            if idx == 0:
                result_parts.append(sections[idx])
                idx += 1
            elif idx < len(sections) - 1 and sections[idx].startswith('##'):
                section_idx += 1
                if section_idx not in remove_indices:
                    result_parts.append(sections[idx])
                    result_parts.append(sections[idx + 1] if idx + 1 < len(sections) else "")
                idx += 2
            else:
                idx += 1

        cleaned = ''.join(result_parts)

    return cleaned


def web_search_yandex(query: str, search_type: str = "news", max_results: int = 5) -> list[dict]:
    """
    Поиск через Yandex Search API (fallback при ошибках DuckDuckGo).
    search_type: 'news' или 'web'
    Возвращает список {title, url, date?, text}.
    """
    import requests

    api_key = os.getenv("YANDEX_API_KEY", "")
    folder_id = os.getenv("YANDEX_FOLDER_ID", "")

    if not api_key or not folder_id:
        return []

    try:
        url = "https://search-api.yandex.ru/search"
        headers = {
            "Authorization": f"Api-Key {api_key}",
        }
        params = {
            "query": query,
            "folderId": folder_id,
            "pageSize": max_results,
        }

        # Добавляем фильтр по типу поиска
        if search_type == "news":
            params["filter"] = "news"

        response = requests.get(url, headers=headers, params=params, timeout=8)
        response.raise_for_status()

        data = response.json()
        results = []

        for item in data.get("results", [])[:max_results]:
            result_url = item.get("url", "")
            full_text = _fetch_full_text(result_url)

            results.append({
                "title": item.get("title", ""),
                "url": result_url,
                "date": item.get("publishedDate", "")[:10] if item.get("publishedDate") else "",
                "source": item.get("domain", ""),
                "text": full_text or item.get("snippet", ""),
            })

        return results
    except Exception as e:
        print(f"  [SEARCH] yandex ошибка: {e}")
        return []


def web_search_fresh(query: str, max_results: int = 3) -> list[dict]:
    """
    Слой 1: свежие новости за последнюю неделю.
    Возвращает список {title, url, date, source, text}.
    Fallback: DuckDuckGo → Yandex Search API
    """
    # Попробуем DuckDuckGo
    if _DDGS:
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

    # Fallback: Yandex Search API
    print(f"  [SEARCH] trying Yandex Search API...")
    yandex_results = web_search_yandex(query, search_type="news", max_results=max_results)
    if yandex_results:
        return yandex_results

    return []


def web_search_deep(query: str, max_results: int = 5) -> list[dict]:
    """
    Слой 2: глубинные источники без ограничения по дате.
    Возвращает список {title, url, text}.
    Fallback: DuckDuckGo → Yandex Search API
    """
    # Попробуем DuckDuckGo
    if _DDGS:
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
            if results:
                return results
        except Exception as e:
            print(f"  [SEARCH] text ошибка: {e}")

    # Fallback: Yandex Search API
    print(f"  [SEARCH] trying Yandex Search API...")
    yandex_results = web_search_yandex(query, search_type="web", max_results=max_results)
    if yandex_results:
        # Преобразуем результаты в формат deep (без date)
        return [{"title": r["title"], "url": r["url"], "text": r["text"]} for r in yandex_results]

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


_TIER_TEXT_LIMIT = {1: 1200, 2: 700, 3: 350}  # символов текста по уровню авторитетности
_RAW_SOURCES_CAP = 7000  # суммарный лимит всего блока raw_sources


def format_raw_sources(fresh: list[dict], deep: list[dict]) -> str:
    """
    Форматирует сырые источники с порядковыми номерами и уровнем авторитетности.
    ⭐⭐⭐ = первичный источник (GitHub, arxiv, официальная дока)
    ⭐⭐   = качественный блог (TechCrunch, MIT, Хабр)
    ⭐     = общий источник
    Текст каждого источника ограничен _TIER_TEXT_LIMIT, итого не более _RAW_SOURCES_CAP символов.
    """
    parts = []
    idx = 1
    total_chars = 0
    all_items = [
        (item, True) for item in fresh
    ] + [
        (item, False) for item in deep
    ]
    # Tier-1 источники сначала
    all_items.sort(key=lambda x: _source_tier(x[0].get("url", "")))
    for item, is_fresh in all_items:
        text = item.get("text", "").strip()
        if not text:
            continue
        tier = _source_tier(item.get("url", ""))
        text = text[:_TIER_TEXT_LIMIT[tier]]
        date_line = f"Дата: {item.get('date', '')} | " if is_fresh else ""
        part = (
            f"[{idx}] {_TIER_LABEL[tier]} {item.get('title', 'Без заголовка')}\n"
            f"URL: {item.get('url', '')}\n"
            f"{date_line}Уровень: {_TIER_LABEL[tier]}\n\n"
            f"{text}"
        )
        total_chars += len(part)
        if total_chars > _RAW_SOURCES_CAP:
            break
        parts.append(part)
        idx += 1
    return "\n\n---\n\n".join(parts) if parts else "(источники не найдены)"


# ── FINER gate ────────────────────────────────────────────────────────────────

def finer_gate(topic: str, fresh: list[dict], deep: list[dict], mode: str = "seo") -> tuple[bool, str]:
    """
    FINER-оценка темы и исследовательской базы (адаптировано из ARS):
    F — Feasible:  достаточно ли источников для статьи
    I — Interesting: есть ли свежий инфоповод (последняя неделя)
    N — Novel:     не слишком ли тема перегружена однотипными источниками
    E — Engaging:  упоминаются ли в теме/источниках AI/tech-ключевые слова
    R — Relevant:  есть ли хотя бы один первичный источник (⭐⭐⭐)

    Блокирует пайплайн только при F=0 (физическая невозможность написать статью).
    Остальные флаги — предупреждения для HITL-шага 4.
    Возвращает (pass: bool, отчёт: str).
    """
    all_sources = fresh + deep
    real = [s for s in all_sources if len(s.get("text", "").strip()) > 100]
    total_chars = sum(len(s["text"]) for s in real)

    # F — Feasible: пороги зависят от режима
    # news: 1 источник и 300 симв. достаточно — свежих новостей мало по определению
    # seo/full: стандартные пороги
    _min_sources = 1 if mode == "news" else RESEARCH_MIN_SOURCES
    _min_chars   = 300 if mode == "news" else RESEARCH_MIN_CHARS
    f_score = min(len(real) / 5, 1.0)
    f_ok = len(real) >= _min_sources and total_chars >= _min_chars
    f_label = f"{'✅' if f_ok else '❌'} F Feasible: {len(real)} источников, {total_chars:,} симв."

    # I — Interesting/Fresh (механически)
    has_fresh = any(s.get("fresh") for s in fresh)
    i_label = f"{'✅' if has_fresh else '⚠️'} I Interesting: {'есть горячая новость' if has_fresh else 'нет новостей за неделю'}"

    # N — Novel: смотрим разнообразие доменов
    domains = set()
    for s in real:
        try:
            from urllib.parse import urlparse
            d = urlparse(s.get("url", "")).netloc.lower().removeprefix("www.")
            domains.add(d)
        except Exception:
            pass
    n_ok = len(domains) >= 2
    n_label = f"{'✅' if n_ok else '⚠️'} N Novel: {len(domains)} разных доменов {'(риск однобокости)' if not n_ok else ''}"

    # E — Engaging: AI/tech ключевые слова в теме или источниках
    ai_keywords = {"ai", "llm", "gpt", "claude", "нейросет", "model", "llama", "gemini",
                   "python", "api", "код", "разработ", "автомат", "агент"}
    topic_lower = topic.lower()
    e_ok = any(kw in topic_lower for kw in ai_keywords)
    e_label = f"{'✅' if e_ok else '⚠️'} E Engaging: {'тема в нише AI/tech' if e_ok else 'тема вне AI/tech ниши'}"

    # R — Relevant: хотя бы один ⭐⭐⭐ источник
    has_tier1 = any(_source_tier(s.get("url", "")) == 1 for s in real)
    r_label = f"{'✅' if has_tier1 else '⚠️'} R Relevant: {'есть первичный источник ⭐⭐⭐' if has_tier1 else 'только вторичные источники'}"

    warnings = []
    if not has_fresh:
        warnings.append("нет горячего инфоповода")
    if not n_ok:
        warnings.append("мало разных доменов — риск однобокости")
    if not has_tier1:
        warnings.append("нет первичных источников — факты сложнее верифицировать")

    lines = ["## FINER-оценка темы", f_label, i_label, n_label, e_label, r_label]
    if warnings:
        lines.append(f"\n⚠️ Предупреждения: {'; '.join(warnings)}")

    if not f_ok:
        lines.append("\n❌ СТОП: недостаточно источников для написания статьи.")
        lines.append("Рекомендация: смените тему или расширьте поисковый запрос.")
        return False, "\n".join(lines)

    lines.append("\n✅ Тема прошла проверку")
    return True, "\n".join(lines)


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


def run_claude(prompt: str, context_files: list[Path] = None, inject_feedback: bool = False) -> tuple[str, int]:
    """
    Вызывает LLM для выполнения задачи агента.
    Использует Groq (llama-3.3-70b) если есть GROQ_KEY, иначе claude CLI.
    Возвращает (output, estimated_tokens).
    inject_feedback=True только для content-writer (остальным не нужно).
    """
    context = ""
    if context_files:
        for f in context_files:
            if f.exists():
                context += f"\n\n### {f.name}\n{f.read_text(encoding='utf-8')}"

    parts = []
    if inject_feedback:
        parts.append(aggregate_feedback())
    if context:
        parts.append(context)
    parts.append(prompt)
    full_prompt = "\n\n".join(p for p in parts if p.strip())
    tokens = len(full_prompt.split()) * 2

    for _gq_idx, _gq in enumerate([_groq_client, _groq_client2]):
        if not _gq:
            continue
        try:
            resp = _gq.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=8192,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip(), tokens
        except Exception as e:
            label = "GROQ" if _gq_idx == 0 else "GROQ-2"
            next_label = "GROQ-2" if (_gq_idx == 0 and _groq_client2) else "Gemini"
            print(f"[ОШИБКА {label}] {e} — пробую {next_label}")

    if _gemini_client:
        try:
            resp = _gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=full_prompt,
            )
            return resp.text.strip(), tokens
        except Exception as e:
            print(f"[ОШИБКА GEMINI] {e} — пробую Mistral")

    if _mistral_client:
        try:
            resp = _mistral_client.chat.complete(
                model="mistral-small-latest",
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=8192,
            )
            return resp.choices[0].message.content.strip(), tokens
        except Exception as e:
            print(f"[ОШИБКА MISTRAL] {e} — пробую Cerebras")

    if _cerebras_client:
        try:
            resp = _cerebras_client.chat.completions.create(
                model="gpt-oss-120b",
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=8192,
            )
            msg = resp.choices[0].message
            text = msg.content or getattr(msg, "reasoning", None) or ""
            if text.strip():
                return text.strip(), tokens
            raise ValueError("пустой ответ")
        except Exception as e:
            print(f"[ОШИБКА CEREBRAS] {e} — пробую OpenRouter")

    if _openrouter_client:
        for _or_model in ["deepseek/deepseek-v4-flash:free", "nvidia/nemotron-3-super-120b-a12b:free", "meta-llama/llama-3.3-70b-instruct:free"]:
            try:
                resp = _openrouter_client.chat.completions.create(
                    model=_or_model,
                    messages=[{"role": "user", "content": full_prompt}],
                    max_tokens=8192,
                )
                text = resp.choices[0].message.content if resp.choices and resp.choices[0].message.content else ""
                if text.strip():
                    return text.strip(), tokens
                raise ValueError("пустой ответ")
            except Exception as e:
                print(f"[ОШИБКА OPENROUTER {_or_model}] {e}")
        print("  [openrouter] все модели недоступны — пробую claude CLI")

    # Предпоследний резерв: claude CLI с Haiku (быстро и дёшево)
    result = subprocess.run(
        ["claude", "-p", full_prompt, "--output-format", "text", "--model", "claude-haiku-4-5"],
        capture_output=True, text=True, cwd="/tmp",
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip(), tokens
    print(f"[ОШИБКА HAIKU] {result.stderr.strip()[:120]} — пробую Sonnet")

    # Последний резерв: claude CLI Sonnet
    result = subprocess.run(
        ["claude", "-p", full_prompt, "--output-format", "text"],
        capture_output=True, text=True, cwd="/tmp",
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
        "Ты копирайтер-смысловик. Пиши черновик статьи '{title}' по структуре.\n\n"
        "## АБСОЛЮТНЫЕ ПРАВИЛА ФАКТЧЕКИНГА (нарушение = брак):\n"
        "1. Ты можешь писать ТОЛЬКО факты, цифры, имена, события, названия продуктов, "
        "которые явно присутствуют в разделе «ВЕРИФИЦИРОВАННЫЕ ИСТОЧНИКИ» ниже.\n"
        "2. После каждого конкретного факта или цифры добавляй ссылку [N], "
        "где N — номер источника из раздела «ВЕРИФИЦИРОВАННЫЕ ИСТОЧНИКИ».\n"
        "3. ЗАПРЕЩЕНО дополнять статью фактами из тренировочных данных модели.\n"
        "4. Если данных из источников не хватает для полноценного раздела — "
        "напиши вместо него: [INSUFFICIENT_SOURCES: <что именно отсутствует>]\n"
        "5. Короткая достоверная статья лучше длинной с домыслами.\n"
        "6. ЗАПРЕЩЕНО вводить собственные классификации/таксономии (например «три класса», «два типа») "
        "если источник не использует эту классификацию явно.\n"
        "7. ЗАПРЕЩЕНО приписывать взгляды «экспертам», «аналитикам», «многим специалистам» "
        "если источник не содержит такой атрибуции.\n"
        "8. Если источник обрезан (текст обрывается на «...»), трактуй только то, что прямо написано — "
        "не интерпретируй намерения автора.\n\n"
        "Правила стиля: {rules_excerpt}.\n\n"
        "## СТРУКТУРА И ЖИВОСТЬ ТЕКСТА (выводы 2026-05-27):\n"
        "1. ЗАГОЛОВКИ: H2 не чаще чем через 2-3 абзаца. Под каждым H2 — минимум 2 полнотекстовых абзаца.\n"
        "   Заголовок = конкретный тезис, не абстрактный. ✅ «Усиление позиций в конкуренции», "
        "   ❌ «Новый этап гонки».\n"
        "2. СЛУЖЕБНЫЕ ОБОРОТЫ — УБИРАТЬ: «Это показывает, что», «Присоединившись к», "
        "   «Переход X показывает» — удали, начни со смысла. Каждое предложение должно добавлять новый факт.\n"
        "3. ЛИД (первое предложение раздела, особенно H2): прямой ответ на вопрос, без вводных слов. "
        "   ✅ «Компании теперь конкурируют за таланты», ❌ «Это показывает, что компании...»\n"
        "4. ДЕТАЛИ ВМЕСТО ШТАМПОВ: одна конкретная деталь > трёх штамповых фраз.\n"
        "   ❌ «известный специалист в области ИИ» → ✅ «автор курса с 4 млн просмотров»\n"
        "   ❌ «работал над ключевыми проектами» → ✅ «создавал автопилот в Tesla»\n"
        "5. ВЫВОД СТАТЬИ: ЗАПРЕЩЕНО писать очевидные выводы. Дать неочевидный инсайт — "
        "   переформулировать проблему, показать скрытое следствие, выявить противоречие, "
        "   предсказать последствие, которое НЕ очевидно из самих фактов.\n\n"
        "   ОЧЕНЬ ПЛОХО (очевидные выводы — ЗАПРЕЩЕНЫ):\n"
        "   ❌ «ИИ становится инструментом, который заменяет рутинные задачи» (в 2026 это всем известно)\n"
        "   ❌ «Инвестиции показывают интерес к ИИ» (банально)\n"
        "   ❌ «Технологии развиваются» (тавтология)\n\n"
        "   ХОРОШО (неочевидные инсайты):\n"
        "   ✅ «Программисты с низкой производительностью становятся невостребованными — "
        "нужны инженеры, способные управлять ИИ-системами и проверять их код» (вытекающее следствие)\n"
        "   ✅ «Инвестиции смещаются от 'может ли ИИ кодировать' к 'кто монополизирует рынок ИИ-разработки'» "
        "(меняется вопрос)\n"
        "   ✅ «Стандартизация ИИ-разработки означает что качество кода теперь зависит от платформы, "
        "а не от разработчика» (неочевидное следствие)\n\n"
        "## ОБЯЗАТЕЛЬНЫЙ ЧЕК-ЛИСТ ПЕРЕД ОТПРАВКОЙ:\n"
        "После написания проверь ВСЕ пункты (если хоть один НЕ выполнен → текст брак):\n"
        "☐ Первое предложение лида содержит КТО/ЧТО/КОГДА/ПОЧЕМУ?\n"
        "☐ Нет предложений начинающихся с «Это показывает», «Это значит», «Следует отметить»?\n"
        "☐ Каждое имя появляется максимум в двух соседних предложениях (потом -> он, она, они)?\n"
        "☐ H2 не чаще чем через 2-3 абзаца? (макс 2-3 H2 на весь текст)\n"
        "☐ Нет жирного текста внутри предложений (жирное только для H2/H3)?\n"
        "☐ ВЫВОД — это неочевидный инсайт? (НЕ повторение темы, НЕ банальность, НЕ известный факт 2024-2025г)?\n"
        "   Спроси себя: «Если бы это прочитал читатель, он бы сказал 'ну и что в этом нового?' — вывод брак».\n"
        "Нарушение любого пункта = текст переписывается.\n\n"
        "Контекст из базы знаний автора: {knowledge_pack}.\n\n"
        "Аналитика исследователя (структура, LSI, тезисы): {web_pack}.\n\n"
        "## ВЕРИФИЦИРОВАННЫЕ ИСТОЧНИКИ:\n{raw_sources}\n\n"
        "## ДЛЯ РЕЖИМА NEWS (короткие новости):\n"
        "- Объём: максимум 600 слов. Если больше — это не новость, а аналитика.\n"
        "- Структура: лид (ЧТО произошло) → детали (КАК/ПОЧЕМУ) → смысл (ЗНАЧЕНИЕ для читателя).\n"
        "- Заголовки: максимум 2 H2. Если получается больше — переделай в один логичный абзац.\n"
        "- Каждое слово на счету: убирай ВСЕ служебные обороты, даже если кажутся связующими.\n"
        "- ❌ Плохо: «Это важное событие показывает, что компания...» (10 слов вводного мусора)\n"
        "- ✅ Хорошо: «Компания запустила новый сервис...» (4 слова фактов)\n"
        "- Лид новости: в первом предложении должны быть ВСЕ ключевые факты (кто/что/когда/почему).\n\n"
        "Пиши поблочно. Первое предложение каждого H2 — прямой ответ на вопрос (AEO). "
        "Интегрируй конкретные числа, команды, таблицы — строго из источников выше.\n"
        "H2-заголовки — тезисы, не вопросы и не обращения. ЗАПРЕЩЕНО: «Что X даёт вам», «Как это изменит вас».\n"
        "ЗАПРЕЩЕНО обращение «вы/вам/тебе» в заголовках H2/H3.\n"
        "Английские технические термины не переводить дословно — писать в оригинале если нет устоявшегося русского.\n"
        "Вывод статьи — это ОБЯЗАТЕЛЬНО неочевидное следствие, противоречие, или меняющийся вопрос. "
        "Если вывод можно сформулировать как 'а значит <банальность>', то это брак. "
        "Читатель уносит НОВУЮ мысль, которую он сам не вывел бы из фактов."
    ),
    "fact-checker": (
        "Ты агент верификации фактов. Твоя задача — найти галлюцинации в черновике статьи.\n\n"
        "## ИНСТРУКЦИЯ:\n"
        "1. Прочитай раздел «ИСХОДНЫЕ ИСТОЧНИКИ» — это единственная допустимая фактическая база.\n"
        "2. Извлеки из черновика ВСЕ верифицируемые утверждения: "
        "числа, проценты, имена людей, названия организаций, "
        "названия продуктов/моделей, даты, события, технические параметры.\n"
        "3. ⚠️ ОСОБО ВНИМАТЕЛЬНО: Названия компаний и продуктов должны совпадать ТОЧНО с источниками:\n"
        "   Если в источнике 'Devin', а в статье 'Devika' → это CONTRADICTED (ошибка в имени).\n"
        "   Если в источнике 'Cognition Labs', а в статье 'Cognition' → проверь что это один и тот же.\n"
        "4. Для каждого утверждения проверь его наличие в исходных источниках.\n"
        "5. Классифицируй каждое утверждение:\n"
        "   — VERIFIED: явно присутствует в источниках (укажи номер источника [N])\n"
        "   — UNVERIFIED: не найдено ни в одном источнике (потенциальная галлюцинация)\n"
        "   — CONTRADICTED: противоречит тому, что написано в источниках ИЛИ имя неточно\n\n"
        "## ФОРМАТ ОТВЕТА:\n"
        "### ИТОГ\n"
        "VERIFIED: X | UNVERIFIED: Y | CONTRADICTED: Z\n\n"
        "### UNVERIFIED (требуют удаления или подтверждения источником):\n"
        "- «цитата из черновика» — пояснение\n\n"
        "### CONTRADICTED (требуют немедленного исправления):\n"
        "- «цитата из черновика» — что именно противоречит источнику [N] или как звучит правильно\n\n"
        "Если UNVERIFIED = 0 и CONTRADICTED = 0 → в конце напиши строку: FACT_CHECK_PASSED\n"
        "Если есть хотя бы одно UNVERIFIED или CONTRADICTED → напиши: FACT_CHECK_FAILED"
    ),
    "temporal-verifier": (
        "Ты агент проверки временной согласованности. "
        "Твоя задача — найти временные ошибки в тексте статьи.\n\n"
        "Ищи 5 типов ошибок:\n"
        "1. Ретроспективная арифметика: «X лет назад» при неверной дате\n"
        "2. Анахронизм: ссылка на продукт/событие раньше его выхода\n"
        "3. Устаревшие сравнения: «лучший на рынке» для продукта, у которого уже есть замена\n"
        "4. Дейктическое настоящее: «сейчас», «сегодня», «в этом году» без уточнения даты\n"
        "5. Версии без дат: упоминание версии без указания когда она актуальна\n\n"
        "Для каждой найденной ошибки:\n"
        "- TEMPORAL_WARN: «цитата» — тип ошибки — рекомендация\n\n"
        "Если ошибок нет → напиши: TEMPORAL_OK\n"
        "Если есть хотя бы одна → напиши: TEMPORAL_WARN_FOUND"
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
        "Верни: оценку 1-10 по каждому критерию в формате 'Критерий N: X/10', "
        "затем список конкретных правок."
    ),
    "devil-advocate": (
        "Ты агент оппонирования. Твоя роль — найти слабые места в статье перед публикацией.\n\n"
        "Задача:\n"
        "1. Определи главный тезис статьи (1 предложение).\n"
        "2. Сформулируй 2 сильных контраргумента к этому тезису.\n"
        "   Контраргумент сильный, если: опирается на реальную практику, "
        "   не является очевидным возражением, не опровергается самой статьёй.\n"
        "3. Проверь: упоминает ли статья эти контраргументы или ограничения?\n"
        "4. Оцени однобокость изложения по шкале 1-10 "
        "   (1 = полностью сбалансировано, 10 = пропаганда одной точки зрения).\n\n"
        "Формат ответа:\n"
        "ТЕЗИС: ...\n"
        "КОНТРАРГУМЕНТ 1: ...\n"
        "КОНТРАРГУМЕНТ 2: ...\n"
        "ПОКРЫТО В СТАТЬЕ: да/нет/частично\n"
        "ОДНОБОКОСТЬ: X/10\n"
        "РЕКОМЕНДАЦИЯ: [добавить раздел 'Ограничения и риски' | статья сбалансирована | ...]\n\n"
        "Если однобокость >= 7 → напиши: ADVOCATE_FLAG\n"
        "Если статья сбалансирована → напиши: ADVOCATE_OK"
    ),
    "news-writer": (
        "Ты журналист технологического издания. Напиши короткую информационную статью (~500-600 слов).\n\n"
        "## АБСОЛЮТНЫЕ ПРАВИЛА ФАКТЧЕКИНГА (нарушение = брак):\n"
        "1. Только факты, явно присутствующие в «ВЕРИФИЦИРОВАННЫХ ИСТОЧНИКАХ».\n"
        "2. После каждого факта или цифры — ссылка [N].\n"
        "3. ЗАПРЕЩЕНО дополнять фактами из памяти модели.\n"
        "4. Если данных не хватает для раздела — напиши: [INSUFFICIENT_SOURCES: <что отсутствует>]\n"
        "5. ЗАПРЕЩЕНО вводить таксономии и классификации, которых нет в источниках.\n"
        "6. ЗАПРЕЩЕНО приписывать взгляды «экспертам», если источник не содержит такой атрибуции.\n\n"
        "## КРИТИЧЕСКОЕ ПРАВИЛО ДЛЯ ЗАГОЛОВКОВ:\n"
        "- МАКСИМУМ 2 H2 заголовка (не больше!).\n"
        "- Каждый H2 должен быть ОТДЕЛЬНЫМ УГЛОМ, не просто пересказом первого предложения параграфа.\n"
        "- Заголовок и текст под ним НЕ должны быть тем же самым — заголовок = угол, текст = деталь.\n"
        "- ❌ ПЛОХО: H2 «Новый минималистичный дизайн» с параграфом «Google обновил дизайн, сделав его минималистичным»\n"
        "- ✅ ХОРОШО: H2 «Главный факт» с первым предложением, а второй и третий параграфы — развитие с новыми фактами\n\n"
        "Структура статьи:\n"
        "# {title}\n"
        "**Лид** (2-3 предложения — суть события, кто, что, когда, почему важно. ВСЕ ключевые факты в первом предложении!)\n"
        "## [H2: один главный факт или первый угол]\n"
        "[2-3 параграфа: развитие этого факта с конкретными деталями и контекстом]\n"
        "## [H2: второй угол или более широкая картина]\n"
        "[2-3 параграфа: почему это важно читателю, последствия, значимость]\n"
        "**Вывод** (1-2 предложения) — это новый смысл или угол, которого не было явно "
        "в тексте: последствие, неочевидная связь, инсайт для читателя. "
        "Читатель должен унести мысль, а не резюме.\n\n"
        "Дополнительные правила:\n"
        "- H2-заголовки — конкретные тезисы, не вопросы и не обращения. ЗАПРЕЩЕНО: «Что X даёт вам», «Как это изменит вас»\n"
        "- Английские технические термины не переводить дословно. vibe coding — не «вибро-кодинг». Писать в оригинале если нет устоявшегося русского термина\n"
        "- ЗАПРЕЩЕНО обращение «вы/вам/тебе» в заголовках H2/H3\n"
        "- ЗАПРЕЩЕНО создавать низкоценностные блоки (например о логотипах/иконках) если они не дают новой информации. Сосредоточься на главном.\n\n"
        "Правила стиля: {rules_excerpt}\n\n"
        "## ВЕРИФИЦИРОВАННЫЕ ИСТОЧНИКИ:\n{raw_sources}\n\n"
        "Напиши статью строго по структуре. Каждое H2 начинается с прямого ответа (AEO) и развивается в 2-3 параграфах."
    ),
}


def _source_tier(url: str) -> int:
    """Классифицирует источник по уровню авторитетности (1=первичный, 2=качественный, 3=общий)."""
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


_TIER_LABEL = {1: "⭐⭐⭐", 2: "⭐⭐", 3: "⭐"}


def run_fast(prompt: str) -> tuple[str, int]:
    """
    Быстрый вызов LLM для лёгких задач (проверки, классификации, короткие ответы).
    Использует llama-3.1-8b-instant (Groq) вместо 70b — экономия ~4x токенов.
    """
    tokens = len(prompt.split()) * 2
    for _gq_idx, _gq in enumerate([_groq_client, _groq_client2]):
        if not _gq:
            continue
        try:
            resp = _gq.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip(), tokens
        except Exception as e:
            label = "GROQ-FAST" if _gq_idx == 0 else "GROQ2-FAST"
            print(f"[ОШИБКА {label}] {e}")
    if _gemini_client:
        try:
            resp = _gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            return resp.text.strip(), tokens
        except Exception as e:
            print(f"[ОШИБКА GEMINI-FAST] {e}")
    if _cerebras_client:
        try:
            resp = _cerebras_client.chat.completions.create(
                model="gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            msg = resp.choices[0].message
            text = msg.content or getattr(msg, "reasoning", None) or ""
            if text.strip():
                return text.strip(), tokens
            raise ValueError("пустой ответ")
        except Exception as e:
            print(f"[ОШИБКА CEREBRAS-FAST] {e}")
    if _mistral_client:
        try:
            resp = _mistral_client.chat.complete(
                model="mistral-small-latest",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            return resp.choices[0].message.content.strip(), tokens
        except Exception as e:
            print(f"[ОШИБКА MISTRAL-FAST] {e}")
    if _openrouter_client:
        for _or_model in ["deepseek/deepseek-v4-flash:free", "nvidia/nemotron-3-super-120b-a12b:free", "meta-llama/llama-3.3-70b-instruct:free"]:
            try:
                resp = _openrouter_client.chat.completions.create(
                    model=_or_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                )
                text = resp.choices[0].message.content if resp.choices and resp.choices[0].message.content else ""
                if text.strip():
                    return text.strip(), tokens
                raise ValueError("пустой ответ")
            except Exception as e:
                print(f"[ОШИБКА OPENROUTER-FAST {_or_model}] {e}")
    return "", tokens


# ── Material Passport ─────────────────────────────────────────────────────────

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
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(slug: str) -> tuple[int, dict]:
    """
    Загружает сохранённое состояние пайплайна.
    Возвращает (последний_завершённый_шаг, контекст) или (0, {}) если нет состояния.
    """
    state_path = STATE_DIR / f"{slug}.json"
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
        f"Верни только одно число (целое от 1 до 10).\n\n{editor_report[:600]}"
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
    output, _ = run_fast(prompt)
    has_warns = "TEMPORAL_WARN_FOUND" in output
    return not has_warns, output


def run_devil_advocate(article: str) -> tuple[bool, str]:
    """
    Запускает агент оппонирования. Использует run_fast (меньшая модель достаточна).
    Возвращает (флаг_однобокости: bool, отчёт: str).
    """
    print("  [devil-advocate] Проверяю однобокость тезиса...")
    prompt = AGENT_PROMPTS["devil-advocate"] + f"\n\nСТАТЬЯ:\n{article[:4000]}"
    output, tokens = run_fast(prompt)
    flagged = "ADVOCATE_FLAG" in output
    icon = "⚠️" if flagged else "✅"
    tg_notify(
        f"{icon} <b>devil-advocate</b>\n"
        f"{'Обнаружена однобокость — рекомендуется добавить раздел ограничений' if flagged else 'Статья сбалансирована'}\n"
        f"~{tokens} токенов\n\n{output[:600]}"
    )
    return flagged, output


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
    auto_approve: bool = False, resume: bool = False, mode: str = "full",
) -> None:
    # ── Resume: загружаем сохранённое состояние ──────────────────────────────
    last_step, saved_ctx = load_state(slug) if resume else (0, {})
    if resume and last_step > 0:
        print(f"\n▶️  Возобновляем с шага {last_step + 1} (slug: {slug})")
        tg_notify(f"▶️ <b>Возобновление пайплайна</b>\nСлуг: {slug}\nПродолжаем с шага {last_step + 1}")
    else:
        mode_label = " [режим: новость]" if mode == "news" else ""
        print(f"\n🚀 Content Factory — запуск генерации{mode_label}: {title}")
        tg_notify(f"🚀 <b>Запуск генерации{mode_label}</b>\n📝 {title}\n🔍 {topic}")

    plan_path = create_plan(title, slug) if last_step == 0 else (PLANS_DIR / f"*_{slug}.md")
    # Если resume и план уже существует — найти его
    if resume and last_step > 0:
        matches = list(PLANS_DIR.glob(f"*_{slug}.md"))
        plan_path = matches[0] if matches else create_plan(title, slug)

    context: dict = {"topic": topic, "title": title, "search_query": search_query, "mode": mode}
    context.update(saved_ctx)  # восстанавливаем сохранённые данные
    # Синхронизируем search_query из passport (мог быть сужен на шаге 1.5)
    search_query = context.get("search_query", search_query)
    mode = context.get("mode", mode)

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
        scope_result, _ = run_fast(scope_prompt)
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
    if mode == "news":
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

        if mode == "news":
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
        if mode == "news":
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
        finer_ok, finer_report = finer_gate(topic, fresh, deep, mode=mode)
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
    if mode == "news":
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
        gap_result, _ = run_fast(gap_prompt)
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
        angles_result, _ = run_fast(angles_prompt)
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
    # Если автор выбрал конкретный вариант угла — передаём его явно в writer
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

    if mode == "news":
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
        cleaned = reduce_excessive_headings(full_draft, max_h2=2, mode="news")
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
        for step in (5, 6):
            block = "1-3" if step == 5 else "4-6"
            if last_step >= step and context.get(f"draft_{block}"):
                print(f"  [passport] Шаг {step} пропущен (уже выполнен)")
                continue
            r = StepResult(step, "content-writer")
            prompt = (
                AGENT_PROMPTS["content-writer"].format(
                    title=title,
                    rules_excerpt=rules_excerpt,
                    knowledge_pack=context.get("knowledge_pack", ""),
                    web_pack=context.get("web_pack", ""),
                    raw_sources=context.get("raw_sources", ""),
                )
                + corrections_block
                + f"\n\nНапиши блоки {block} статьи."
            )
            output, tokens = run_claude(prompt, inject_feedback=True)
            context[f"draft_{block}"] = output
            update_step(plan_path, step)
            r.finish(output, tokens=tokens)
            save_state(slug, context, step)
        full_draft = context.get("draft_1-3", "") + "\n\n" + context.get("draft_4-6", "")

    # Auto revision loop: быстрая само-проверка черновика (пропускается в режиме news)
    if mode == "news":
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
        revision_check, _ = run_fast(revision_prompt)
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

    # Шаг 6.4: INSUFFICIENT_SOURCES quality gate (пропускается в режиме news)
    import re as _re_q
    _isuf_count = len(_re_q.findall(r'\[INSUFFICIENT_SOURCES:', full_draft))
    if mode == "news":
        print("  [news] Quality Gate пропущен (режим новость)")
    elif _isuf_count > 1 and last_step < 6:
        print(f"  [quality-gate] {_isuf_count} незаполненных секций — ищу дополнительные источники...")
        tg_notify(f"🔍 <b>Quality Gate</b>: {_isuf_count} пустых секций — дозапрашиваю источники...")
        # Извлекаем что именно не хватает
        missing_topics = _re_q.findall(r'\[INSUFFICIENT_SOURCES:\s*([^\]]{10,100})', full_draft)
        for mt in missing_topics[:3]:
            # Берём первые значимые слова как поисковый запрос
            search_q = " ".join(mt.split()[:6]) + " 2026"
            extra = web_search_deep(search_q, max_results=2)
            if extra:
                extra_block = format_raw_sources([], extra)
                context["raw_sources"] = context.get("raw_sources", "") + "\n\n---\n\n" + extra_block
                print(f"    +{len(extra)} источников для: {search_q[:50]}")
        # Перезаписываем черновик с новыми источниками
        fix_prompt = (
            AGENT_PROMPTS["content-writer"].format(
                title=title,
                rules_excerpt=rules_excerpt,
                knowledge_pack=context.get("knowledge_pack", ""),
                web_pack=context.get("web_pack", ""),
                raw_sources=context.get("raw_sources", ""),
            )
            + corrections_block
            + f"\n\nВ черновике {_isuf_count} незаполненных секций. "
            + "Перепиши ТОЛЬКО эти секции, используя дополнительно найденные источники. "
            + "Если данных по-прежнему нет — убери этот раздел из структуры. "
            + "Остальной текст оставь без изменений.\n\n"
            + f"Черновик:\n{full_draft}"
        )
        fixed, _ = run_claude(fix_prompt, inject_feedback=True)
        if len(fixed) >= len(full_draft) * 0.5:
            full_draft = fixed
            context["draft_1-3"] = full_draft
            save_state(slug, context, 6)
            _isuf_remaining = len(_re_q.findall(r'\[INSUFFICIENT_SOURCES:', full_draft))
            print(f"  [quality-gate] ✅ Осталось незаполненных секций: {_isuf_remaining}")

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
        if _contradicted_count > 0:
            # Если осталось ≤3 CONTRADICTED после всех попыток — продолжаем с предупреждением
            # (обычно это формальные расхождения: опущенный квалификатор, синоним)
            if _contradicted_count <= 3:
                print(f"  [fact-autofix] ⚠️ Осталось {_contradicted_count} CONTRADICTED — продолжаю с предупреждением (формальные расхождения)")
                tg_notify(f"⚠️ <b>fact-autofix</b>: осталось {_contradicted_count} CONTRADICTED — продолжаю")
            else:
                # CONTRADICTED не уменьшились — останавливаем
                tg_notify(
                    f"🚫 <b>fact-checker: СТОП</b>\n\n"
                    f"В черновике обнаружены противоречия с источниками.\n\n"
                    f"{fact_report[:1000]}\n\n"
                    f"Генерация прекращена. Перезапустите с другой темой или добавьте источники."
                )
                print(f"\n🚫 fact-checker FAILED (CONTRADICTED):\n{fact_report}")
                sys.exit(1)
        elif mode in ("news", "seo") and _unverified_count > 0:
            # UNVERIFIED в режимах news/seo — вырезаем, не переписываем и не блокируем
            print(f"  [fact-checker] ✂️ {_unverified_count} UNVERIFIED → вырезаю из черновика (режим {mode})")
            tg_notify(f"✂️ <b>fact-strip</b>: убираю {_unverified_count} неверифицированных утверждений")
            strip_prompt = (
                f"Ты редактор. Из статьи нужно убрать конкретные утверждения, "
                f"которые не подтверждены источниками.\n\n"
                f"Список утверждений для удаления (из отчёта фактчекера):\n"
                f"{fact_report}\n\n"
                f"Задача: найди в тексте эти конкретные фразы и удали их или замени "
                f"на более осторожную формулировку без непроверенных деталей. "
                f"Не добавляй ничего нового. Не переписывай верифицированные части.\n\n"
                f"Статья:\n{full_draft}"
            )
            stripped, _ = run_claude(strip_prompt)
            if len(stripped) >= len(full_draft) * 0.5:
                full_draft = stripped
                context["draft_1-3"] = full_draft
                print(f"  [fact-checker] ✅ Неверифицированные утверждения убраны")
                fact_ok = True
            else:
                print(f"  [fact-checker] ⚠️ Strip вернул слишком короткий результат — продолжаю с оригиналом")
                fact_ok = True  # всё равно продолжаем — CONTRADICTED нет
        else:
            tg_notify(
                f"🚫 <b>fact-checker: СТОП</b>\n\n"
                f"В черновике обнаружены непроверенные утверждения.\n\n"
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

    # ── SEO-качество: три дополнительных прохода (только для seo/full) ──────────────
    if mode != "news":
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
    if mode == "news":
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
        if mode == "news":
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
    if mode == "news":
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
    if mode == "news":
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
    parser.add_argument("--resume", action="store_true", help="Возобновить с последнего сохранённого шага")
    parser.add_argument(
        "--mode", choices=["full", "seo", "news"], default="seo",
        help=(
            "Режим генерации: "
            "seo — полный пайплайн, гибкий фактчекинг (DEFAULT, ~30 мин); "
            "news — короткая новость, минимум шагов (~15 мин); "
            "full — максимальная точность, строгий фактчекинг (~60 мин, редко)"
        )
    )
    args = parser.parse_args()

    run_pipeline(
        topic=args.topic,
        title=args.title,
        slug=args.slug,
        search_query=args.query,
        auto_approve=args.auto_approve,
        resume=args.resume,
        mode=args.mode,
    )
