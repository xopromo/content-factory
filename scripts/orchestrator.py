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
except ImportError:
    _groq_client = None

try:
    from google import genai as _genai
    _gemini_key = os.environ.get("GEMINI_KEY", "")
    _gemini_client = _genai.Client(api_key=_gemini_key) if _gemini_key else None
except ImportError:
    _gemini_client = None

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


def web_search_fresh(query: str, max_results: int = 3) -> list[dict]:
    """
    Слой 1: свежие новости за последнюю неделю.
    Возвращает список {title, url, date, source, text}.
    """
    if not _DDGS:
        return []
    for timelimit in ("w", "m"):  # неделя → если пусто, месяц
        try:
            items = list(_DDGS().news(query, max_results=max_results, timelimit=timelimit, region="ru-ru"))
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
        items = list(_DDGS().text(query, max_results=max_results, region="ru-ru"))
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

def finer_gate(topic: str, fresh: list[dict], deep: list[dict]) -> tuple[bool, str]:
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

    # F — Feasible (механически)
    f_score = min(len(real) / 5, 1.0)
    f_ok = len(real) >= RESEARCH_MIN_SOURCES and total_chars >= RESEARCH_MIN_CHARS
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
    Использует Groq (llama-3.3-70b) если есть GROQ_KEY, иначе Gemini, иначе claude CLI.
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

    errors = []

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
            err_msg = f"Groq Error: {e}"
            print(f"[GROQ ERROR] {e}")
            errors.append(err_msg)

    if _gemini_client:
        try:
            resp = _gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=full_prompt,
            )
            return resp.text.strip(), tokens
        except Exception as e:
            err_msg = f"Gemini Error: {e}"
            print(f"[GEMINI ERROR] {e}")
            errors.append(err_msg)

    # Fallback: claude CLI
    try:
        import tempfile
        tmp_dir = tempfile.gettempdir()
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            cwd=tmp_dir,
        )
        if result.returncode == 0:
            return result.stdout.strip(), tokens
        else:
            errors.append(f"claude CLI Error: {result.stderr.strip()}")
    except Exception as e:
        errors.append(f"claude CLI execution error: {e}")

    # Если ни один провайдер не сработал
    detailed_errors = "\n".join(f"- {err}" for err in errors)
    raise RuntimeError(
        f"Не удалось выполнить запрос к LLM. Все доступные провайдеры вернули ошибку:\n{detailed_errors}"
    )


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
    reply_file = Path("business/latest_reply.json")
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
        Path("business").mkdir(parents=True, exist_ok=True)
        Path("business/review_waiting.txt").write_text(str(step), encoding="utf-8")
    except Exception:
        pass

    try:
        msg_type, answer = _tg_wait_reply(timeout=600)
    finally:
        # Убираем сигнал ожидания
        try:
            Path("business/review_waiting.txt").unlink(missing_ok=True)
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
        "Контекст из базы знаний автора: {knowledge_pack}.\n\n"
        "Аналитика исследователя (структура, LSI, тезисы): {web_pack}.\n\n"
        "## ВЕРИФИЦИРОВАННЫЕ ИСТОЧНИКИ:\n{raw_sources}\n\n"
        "Пиши поблочно. Первое предложение каждого H2 — прямой ответ на вопрос (AEO). "
        "Интегрируй конкретные числа, команды, таблицы — строго из источников выше."
    ),
    "fact-checker": (
        "Ты агент верификации фактов. Твоя задача — найти галлюцинации в черновике статьи.\n\n"
        "## ИНСТРУКЦИЯ:\n"
        "1. Прочитай раздел «ИСХОДНЫЕ ИСТОЧНИКИ» — это единственная допустимая фактическая база.\n"
        "2. Извлеки из черновика ВСЕ верифицируемые утверждения: "
        "числа, проценты, имена людей, названия организаций, "
        "названия продуктов/моделей, даты, события, технические параметры.\n"
        "3. Для каждого утверждения проверь его наличие в исходных источниках.\n"
        "4. Классифицируй каждое утверждение:\n"
        "   — VERIFIED: явно присутствует в источниках (укажи номер источника [N])\n"
        "   — UNVERIFIED: не найдено ни в одном источнике (потенциальная галлюцинация)\n"
        "   — CONTRADICTED: противоречит тому, что написано в источниках\n\n"
        "## ФОРМАТ ОТВЕТА:\n"
        "### ИТОГ\n"
        "VERIFIED: X | UNVERIFIED: Y | CONTRADICTED: Z\n\n"
        "### UNVERIFIED (требуют удаления или подтверждения источником):\n"
        "- «цитата из черновика» — пояснение\n\n"
        "### CONTRADICTED (требуют немедленного исправления):\n"
        "- «цитата из черновика» — что именно противоречит источнику [N]\n\n"
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
    errors = []
    if _groq_client:
        try:
            resp = _groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip(), tokens
        except Exception as e:
            errors.append(f"Groq Fast Error: {e}")
            print(f"[GROQ FAST ERROR] {e}")
    if _gemini_client:
        try:
            resp = _gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            return resp.text.strip(), tokens
        except Exception as e:
            errors.append(f"Gemini Fast Error: {e}")
            print(f"[GEMINI FAST ERROR] {e}")

    detailed_errors = "\n".join(f"- {err}" for err in errors)
    raise RuntimeError(
        f"Не удалось выполнить быстрый запрос к LLM. Все провайдеры вернули ошибку:\n{detailed_errors}"
    )


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
    }

    def extract_entities(text):
        entities = set()
        for word in re.findall(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b', text):
            if len(word) > 2 and word not in common_terms:
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
) -> None:
    # ── Resume: загружаем сохранённое состояние ──────────────────────────────
    last_step, saved_ctx = load_state(slug) if resume else (0, {})
    if resume and last_step > 0:
        print(f"\n▶️  Возобновляем с шага {last_step + 1} (slug: {slug})")
        tg_notify(f"▶️ <b>Возобновление пайплайна</b>\nСлуг: {slug}\nПродолжаем с шага {last_step + 1}")
    else:
        print(f"\n🚀 Content Factory — запуск генерации: {title}")
        tg_notify(f"🚀 <b>Запуск генерации</b>\n📝 {title}\n🔍 {topic}\n⚙️ Формат: {mode}")

    plan_path = create_plan(title, slug) if last_step == 0 else (PLANS_DIR / f"*_{slug}.md")
    # Если resume и план уже существует — найти его
    if resume and last_step > 0:
        matches = list(PLANS_DIR.glob(f"*_{slug}.md"))
        plan_path = matches[0] if matches else create_plan(title, slug)

    context: dict = {"topic": topic, "title": title, "search_query": search_query, "mode": mode}
    context.update(saved_ctx)  # восстанавливаем сохранённые данные

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

    # Шаг 2: knowledge-retriever
    if last_step >= 2:
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
        print("  [Слой 1] Ищу свежие новости за неделю...")
        tg_notify(f"🔍 <b>Шаг 03</b> — web-researcher\n⏳ Ищу актуальные источники...")

        # search_query используется если задан явно (более специфичный запрос)
        _sq = search_query or topic
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
        finer_ok, finer_report = finer_gate(topic, fresh, deep)
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

    # Шаг 4: HUMAN REVIEW структуры (включает FINER-отчёт)
    approved, corrections = human_review(
        "Утвердите структуру и данные из исследования",
        f"📰 Информационные поводы:\n{fresh_summary}\n\n"
        f"📌 Тезис и структура:\n{context.get('web_pack', '')[:600]}\n\n"
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
    corrections_block = f"\n\n## ПРАВКИ И УТОЧНЕНИЯ ОТ АВТОРА:\n{context['corrections']}" if context.get("corrections") else ""
    
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
            + mode_instructions
            + corrections_block
            + f"\n\nНапиши блоки {block} статьи."
        )
        output, tokens = run_claude(prompt, inject_feedback=True)
        context[f"draft_{block}"] = output
        update_step(plan_path, step)
        r.finish(output, tokens=tokens)
        save_state(slug, context, step)

    full_draft = context.get("draft_1-3", "") + "\n\n" + context.get("draft_4-6", "")

    # Auto revision loop: быстрая само-проверка черновика (max 1 раз, run_fast)
    if last_step < 6:
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

    # Шаг 6.4: hallucination-detector — блокируем если найдены новые неизвестные сущности
    halluc_ok, halluc_report = run_hallucination_detector(full_draft, context["raw_sources"])
    context["hallucination_report"] = halluc_report

    if not halluc_ok:
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

    # Авто-исправление небольшого числа UNVERIFIED/CONTRADICTED (max 1 попытка)
    if not fact_ok:
        import re as _re
        _u = _re.search(r"UNVERIFIED:\s*\*{0,2}(\d+)", fact_report)
        _c = _re.search(r"CONTRADICTED:\s*\*{0,2}(\d+)", fact_report)
        _unverified_count = int(_u.group(1)) if _u else 99
        _contradicted_count = int(_c.group(1)) if _c else 99
    if not fact_ok and (_unverified_count + _contradicted_count) <= 5:
        print("  [fact-autofix] Найдены CONTRADICTED-утверждения — исправляю...")
        tg_notify("🔄 <b>fact-autofix</b>: Исправляю противоречивые утверждения...")
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
            print("  [fact-autofix] ✅ Черновик исправлен — повторная проверка")
            fact_ok, fact_report = run_fact_checker(full_draft, context["raw_sources"], "6.5r")
            context["fact_check_report"] = fact_report

    if not fact_ok:
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
    if last_step >= 8 and context.get("optimized_draft"):
        print("  [passport] Шаги 8-9 пропущены (уже выполнены)")
    else:
        r = StepResult(8, "seo-geo-optimizer")
        prompt = AGENT_PROMPTS["seo-geo-optimizer"] + f"\n\nЧерновик:\n{full_draft}"
        output, tokens = run_claude(prompt)
        context["optimized_draft"] = output
        update_step(plan_path, 8)
        update_step(plan_path, 9)
        r.finish(output, tokens=tokens)
        save_state(slug, context, 8)

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

    # Шаг 11.5: devil-advocate (run_fast — llama-3.1-8b-instant, экономия ~4x)
    advocate_flagged, advocate_report = run_devil_advocate(context.get("optimized_draft", ""))
    context["advocate_report"] = advocate_report
    save_state(slug, context, 11)

    # Шаг 12: HUMAN REVIEW перед публикацией (включает отчёт devil-advocate)
    advocate_warning = f"\n\n⚠️ devil-advocate: {advocate_report[:300]}" if advocate_flagged else ""
    preview = (
        f"GEO-отчет:\n{context['geo_report'][:300]}\n\n"
        f"Редактор:\n{context['editor_report'][:300]}"
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

    # git push with GITHUB_TOKEN
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO", "xopromo/content-factory")
    branch = os.getenv("GITHUB_BRANCH", "claude/vigilant-einstein-hPa8u")
    if token:
        try:
            auth_url = f"https://x-access-token:{token}@github.com/{repo}.git"
            subprocess.run(["git", "remote", "set-url", "origin", auth_url], cwd=ROOT, capture_output=True)
            subprocess.run(["git", "push", "origin", branch], cwd=ROOT, capture_output=True)
            print("  [deployer-publisher] Изменения успешно отправлены на GitHub")
        except Exception as e:
            print(f"  [deployer-publisher] [WARN] Ошибка отправки на GitHub: {e}")

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
    args = parser.parse_args()

    try:
        run_pipeline(
            topic=args.topic,
            title=args.title,
            slug=args.slug,
            search_query=args.query,
            auto_approve=args.auto_approve,
            resume=args.resume,
            mode=args.mode,
        )
    except Exception as e:
        import traceback
        err_msg = f"❌ <b>Критическая ошибка пайплайна!</b>\n\nТема: <code>{args.topic}</code>\nОшибка: <code>{e}</code>\n\nВы можете попробовать возобновить генерацию с последнего шага."
        print(f"[FATAL ERROR] {e}")
        traceback.print_exc()
        try:
            tg_notify(err_msg)
        except Exception as tg_err:
            print(f"[TG NOTIFY ERROR] {tg_err}")
        sys.exit(1)
