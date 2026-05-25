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
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

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
    Запускает Claude Code CLI с заданным промптом.
    Возвращает (output, estimated_tokens).
    """
    context = ""
    if context_files:
        for f in context_files:
            if f.exists():
                context += f"\n\n### {f.name}\n{f.read_text(encoding='utf-8')}"

    full_prompt = (aggregate_feedback() + "\n\n" + context + "\n\n" + prompt).strip()

    result = subprocess.run(
        ["claude", "-p", full_prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    output = result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    tokens = len(full_prompt.split()) * 2  # грубая оценка
    return output, tokens


# ── Human-in-the-Loop ─────────────────────────────────────────────────────────

def human_review(title: str, content: str, step: int) -> bool:
    """
    Интерактивная пауза. В Telegram — кнопки approve/reject.
    В CLI — просит ввод.
    """
    tg_notify(
        f"⏸ <b>Шаг {step} — требуется ваше решение</b>\n\n"
        f"<b>{title}</b>\n\n{content[:800]}...\n\n"
        f"Ответьте: <code>ok</code> — продолжить, <code>stop</code> — остановить"
    )
    print(f"\n{'='*60}")
    print(f"⏸  HUMAN REVIEW — Шаг {step}: {title}")
    print(f"{'='*60}")
    print(content[:1000])
    print(f"\n[ok] Продолжить  |  [stop] Остановить  |  [edit] Открыть план в редакторе")
    answer = input("\nВаш ответ: ").strip().lower()
    return answer in ("ok", "y", "yes", "да", "")


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


def run_pipeline(topic: str, title: str, slug: str, search_query: str) -> None:
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

    # Шаг 3: web-researcher + HUMAN REVIEW
    r = StepResult(3, "web-researcher")
    prompt = AGENT_PROMPTS["web-researcher"].format(topic=topic)
    output, tokens = run_claude(prompt)
    context["web_pack"] = output
    update_step(plan_path, 3)
    r.finish(output, tokens=tokens)

    # Шаг 4: HUMAN REVIEW структуры
    approved = human_review(
        "Утвердите структуру и данные из исследования",
        f"Структура:\n{output[:600]}\n\nКонтекст из базы знаний:\n{context['knowledge_pack'][:400]}",
        step=4,
    )
    if not approved:
        tg_notify("🛑 Генерация остановлена пользователем на шаге 4.")
        sys.exit(0)
    update_step(plan_path, 4)

    # Шаги 5-6: content-writer
    rules_excerpt = RULES_FILE.read_text(encoding="utf-8")[:800] if RULES_FILE.exists() else ""
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
    approved = human_review("Утвердите статью перед публикацией", preview, step=12)
    if not approved:
        tg_notify("🛑 Публикация отменена пользователем на шаге 12.")
        sys.exit(0)
    update_step(plan_path, 12)
    update_step(plan_path, 13)

    # Шаг 14: deployer-publisher
    r = StepResult(14, "deployer-publisher")
    article_path = ROOT / "docs" / "articles" / f"{slug}.md"
    article_path.parent.mkdir(parents=True, exist_ok=True)
    article_path.write_text(context["optimized_draft"], encoding="utf-8")

    result = subprocess.run(
        ["git", "add", str(article_path), str(plan_path)],
        cwd=ROOT, capture_output=True
    )
    result = subprocess.run(
        ["git", "commit", "-m", f"feat: article '{title}' [{slug}]"],
        cwd=ROOT, capture_output=True, text=True
    )
    update_step(plan_path, 14)
    r.finish(result.stdout, tokens=50)

    tg_notify(f"🎉 <b>Статья опубликована!</b>\n📝 {title}\n📁 docs/articles/{slug}.md")
    print(f"\n✅ Готово: {article_path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content Factory Orchestrator")
    parser.add_argument("--topic", required=True, help="Тема статьи (для поиска)")
    parser.add_argument("--title", required=True, help="Заголовок H1 статьи")
    parser.add_argument("--slug", required=True, help="URL-slug статьи")
    parser.add_argument("--query", required=True, help="Поисковый запрос для GEO-теста")
    args = parser.parse_args()

    run_pipeline(
        topic=args.topic,
        title=args.title,
        slug=args.slug,
        search_query=args.query,
    )
