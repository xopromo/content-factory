#!/usr/bin/env python3
import os
import re
import sys
from typing import Tuple, List, Dict
from scripts.utils.llm_client import run_fast_common, run_claude_common

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

_TIER_LABEL = {1: "⭐⭐⭐", 2: "⭐⭐", 3: "⭐"}


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


def validate_entity_names(article_text: str, sources_text: str) -> Tuple[bool, List[str]]:
    """
    Проверяет что названия компаний/продуктов в статье совпадают ТОЧНО с источниками.
    Возвращает (is_valid, list_of_errors).
    """
    errors = []

    # Служебные слова и метаметки которые игнорируем
    ignore_list = {
        'The', 'By', 'In', 'For', 'And', 'Or', 'As', 'Is', 'Was', 'Are', 'Be',
        'Have', 'Has', 'Do', 'Does', 'Did', 'Will', 'Would', 'Should', 'Could',
        'May', 'Might', 'Must', 'Can', 'Let', 'Make', 'Get', 'Put', 'Set', 'Go',
        # Служебные слова из отчётов
        'VERIFIED', 'UNVERIFIED', 'CONTRADICTED', 'FACT_CHECK_PASSED', 'FACT_CHECK_FAILED',
        'CRITICAL', 'ERROR', 'WARNING', 'PASSED', 'FAILED', 'OK', 'ИТОГ',
    }

    entity_patterns = [
        (r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b', 'common'),  # CamelCase или два слова с заглавной
        (r'"([^"]+)"', 'quoted'),  # В кавычках
    ]

    found_entities = set()
    for pattern, pattern_type in entity_patterns:
        for match in re.finditer(pattern, article_text):
            entity = match.group(1).strip()
            if len(entity) > 2:  # Игнорируем короткие слова
                found_entities.add(entity)

    # Проверяем каждую найденную сущность
    for entity in sorted(found_entities):
        if entity in ignore_list or entity.isupper():
            continue

        entity_lower = entity.lower()

        # Если точное совпадение есть — OK
        if entity_lower in sources_text.lower():
            continue

        # Ищем похожее слово в источниках (возможная опечатка)
        for match in re.finditer(r'\b[A-Z][a-zA-Z]{3,}\b', sources_text):
            source_word = match.group(0)
            if source_word in ignore_list or source_word.isupper():
                continue
            if entity_lower == source_word.lower():
                break  # Точное совпадение
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, entity_lower, source_word.lower()).ratio()
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
    """
    sections = re.split(rf'(?m)^##', article_text)
    scores = {}

    if len(sections) > 0:
        scores[0] = 10

    for idx, section in enumerate(sections[1:], start=1):
        heading_match = re.match(r' (.+?)\n', section)
        if not heading_match:
            continue

        heading = heading_match.group(1).strip()
        body = section[heading_match.end():]

        low_value_keywords = [
            'дизайн', 'иконка', 'логотип', 'стиль', 'внешний вид',
            'переименован', 'переименовал', 'обновил иконку',
            'минималистичный дизайн', 'визуальный'
        ]

        word_count = len(body.split())
        has_numbers = bool(re.search(r'\d+', body))
        has_quotes = '>' in body
        has_facts = bool(re.search(r'\[(\d+)\]', body))

        score = 5  # базовая оценка

        if any(keyword in heading.lower() for keyword in low_value_keywords):
            score -= 3

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

        first_sentence = body.split('\n')[0] if body else ""
        if first_sentence.lower().find(heading.lower()) >= 0:
            score -= 2

        scores[idx] = max(0, min(10, score))

    return scores


def validate_numbers(article_text: str, sources: str) -> Tuple[bool, str]:
    """
    Проверяет числа, цифры и проценты в статье.
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
    result, _ = run_fast_common(prompt, quality="simple")
    ok = "NUMBERS_OK" in result and "NUMBERS_FAIL" not in result
    return ok, result


def detect_semantic_duplicates(article_text: str) -> Tuple[bool, str]:
    """
    Находит H2-секции с повторяющимися тезисами (>50% смыслового пересечения).
    """
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
    result, _ = run_fast_common(prompt, quality="strong")
    return "DEDUP_FOUND" in result, result


def verify_article_logic(article_text: str, removed_sections: list = None) -> Tuple[bool, str]:
    """
    Проверяет логику и целостность статьи после удаления блоков.
    """
    if removed_sections is None:
        removed_sections = []

    issues = []

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
        last_body = h2_bodies[-1]

        remaining_concepts = set()
        for heading in h2_headings[:-1]:
            words = heading.lower().split()
            remaining_concepts.update([w for w in words if len(w) > 3])

        for removed in removed_sections:
            removed_words = removed.lower().split()
            for word in removed_words:
                if len(word) > 4 and word in last_body.lower():
                    issues.append(
                        f"⚠️ Вывод ссылается на удалённую концепцию '{word}' "
                        f"(была в блоке '{removed[:30]}...')"
                    )

    # Проверка 2: Очень короткие оставшиеся блоки
    for i, body in enumerate(h2_bodies):
        word_count = len(body.split())
        if word_count < 80:
            issues.append(
                f"⚠️ Блок #{i+1} очень короткий ({word_count} слов) — "
                f"может быть неполным после удаления контекста"
            )

    # Проверка 3: Нет фактов в первых блоках
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
    result, _ = run_fast_common(prompt, quality="strong")
    return result


def finer_gate(topic: str, fresh: list, deep: list, mode: str = "seo") -> Tuple[bool, str]:
    """
    FINER-оценка темы и исследовательской базы.
    """
    all_sources = fresh + deep
    real = [s for s in all_sources if len(s.get("text", "").strip()) > 100]
    total_chars = sum(len(s["text"]) for s in real)

    _min_sources = 1 if mode == "news" else 2
    _min_chars   = 300 if mode == "news" else 750
    f_ok = len(real) >= _min_sources and total_chars >= _min_chars
    f_label = f"{'✅' if f_ok else '❌'} F Feasible: {len(real)} источников, {total_chars:,} симв."

    has_fresh = any(s.get("fresh") for s in fresh)
    i_label = f"{'✅' if has_fresh else '⚠️'} I Interesting: {'есть горячая новость' if has_fresh else 'нет новостей за неделю'}"

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

    ai_keywords = {"ai", "llm", "gpt", "claude", "нейросет", "model", "llama", "gemini",
                   "python", "api", "код", "разработ", "автомат", "агент"}
    topic_lower = topic.lower()
    e_ok = any(kw in topic_lower for kw in ai_keywords)
    e_label = f"{'✅' if e_ok else '⚠️'} E Engaging: {'тема в нише AI/tech' if e_ok else 'тема вне AI/tech ниши'}"

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
    result, _ = run_claude_common(prompt)
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
    result, _ = run_claude_common(prompt)
    return result if len(result) >= len(article_text) * 0.65 else article_text


def reduce_excessive_headings(article_text: str, max_h2: int = 2, pipeline_mode: str = "seo") -> str:
    """
    Для режима NEWS: убирает лишние H2-заголовки если их больше чем max_h2.
    ВАЖНО: сохраняет порядок секций и не нарушает логику (не удаляет контекстные блоки).
    """
    if pipeline_mode != "news":
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
        sections_data = []
        for i, score in scores.items():
            if i > 0:  # пропускаем лид
                sections_data.append((i, score))

        sections_data.sort(key=lambda x: x[0])

        num_to_remove = remaining_h2 - max_h2
        lowest_scores = sorted(sections_data, key=lambda x: x[1])[:num_to_remove]
        remove_indices = {i for i, _ in lowest_scores}

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

