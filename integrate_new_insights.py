#!/usr/bin/env python3
"""Интегрирует найденные инсайты в данные сайта"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone

def extract_insights_from_text(text: str, source_task: str) -> list:
    """Извлекает отдельные инсайты из текста с помощью regex"""
    insights = []

    # Ищем блоки в формате: 💡 **Title** ... ⭐ **Impact:** ...
    pattern = r'💡\s*\*\*(.+?)\*\*\s*\n.*?📊\s*\*?\*?Analysis:\*?\*?\s*(.+?)(?=✅|$)\s*✅\s*\*?\*?Application:\*?\*?\s*(.+?)(?=⭐|$)\s*⭐\s*\*?\*?Impact:\*?\*?\s*(.+?)(?=🔗|$)(?:\s*🔗\s*(.+?))?(?=💡|$)'

    matches = re.finditer(pattern, text, re.DOTALL | re.MULTILINE)

    for i, match in enumerate(matches, 1):
        title = match.group(1).strip() if match.group(1) else ""
        analysis = match.group(2).strip() if match.group(2) else ""
        application = match.group(3).strip() if match.group(3) else ""
        impact = match.group(4).strip() if match.group(4) else ""
        source = match.group(5).strip() if match.group(5) else ""

        # Очищаем текст
        analysis = re.sub(r'\n+', ' ', analysis)[:500]
        application = re.sub(r'\n+', ' ', application)[:300]

        # Переводим impact в relevance_score
        relevance_map = {
            'high': 0.95,
            'medium-high': 0.85,
            'medium': 0.75,
            'medium-low': 0.65,
            'low': 0.45,
        }
        relevance = relevance_map.get(impact.lower(), 0.8)

        if title:
            insights.append({
                'title': title,
                'analysis': analysis,
                'application': application,
                'impact': impact,
                'relevance': relevance,
                'source': source
            })

    return insights

def clean_source_url(source: str) -> str:
    """Извлекает URL из markdown формата [текст](url) или просто url"""
    if not source:
        return "https://vk.com/ads"

    # Если это markdown ссылка: [текст](url)
    match = re.search(r'\]\((.+?)\)', source)
    if match:
        return match.group(1).strip()

    # Если это просто URL
    if source.startswith('http'):
        return source.strip()

    # Если это текст без URL, возвращаем дефолт
    return "https://vk.com/ads"

def create_log_entry(insight: dict, log_id: str, source_task: str, timestamp: str) -> dict:
    """Создаёт запись в формате logs.json"""
    return {
        "log_id": log_id,
        "timestamp": timestamp,
        "quest_id": f"quest_{log_id.split('_')[1]}",  # quest_033, quest_034, etc.
        "finding": insight['title'],
        "analysis": insight['analysis'],
        "conclusion": insight['application'],
        "source_url": clean_source_url(insight['source']),
        "relevance_score": insight['relevance'],
        "rating": 0,
        "user_feedback": None
    }

def main():
    print("="*70)
    print("🔗 ИНТЕГРАЦИЯ НОВЫХ ИНСАЙТОВ В САЙТ")
    print("="*70)

    # Читаем логи поиска
    search_log_file = Path("insights_search_log.jsonl")
    if not search_log_file.exists():
        print("❌ Файл insights_search_log.jsonl не найден")
        return

    # Читаем текущие логи
    logs_file = Path("docs/agents/data/logs.json")
    with open(logs_file, 'r', encoding='utf-8') as f:
        current_data = json.load(f)

    print(f"📊 Текущих инсайтов: {len(current_data['logs'])}")

    # Обрабатываем новые инсайты
    all_new_insights = []
    task_count = 0

    with open(search_log_file, 'r', encoding='utf-8') as f:
        lines = [line for line in f if line.strip()]

        # Берём только последние 5 успешных записей (новые)
        new_lines = lines[-5:] if len(lines) > 10 else lines

        for line in new_lines:
            task_count += 1
            entry = json.loads(line)

            if entry.get('result') and not entry.get('error'):
                print(f"\n✅ Задача {task_count}: {entry['task'][:60]}...")

                # Извлекаем инсайты из текста
                insights = extract_insights_from_text(entry['result'], entry['task'])
                print(f"   📌 Найдено инсайтов: {len(insights)}")

                for insight in insights:
                    all_new_insights.append({
                        **insight,
                        'task': entry['task'],
                        'timestamp': entry['timestamp']
                    })

    # Создаём новые log entries
    next_id = len(current_data['logs']) + 1
    new_log_entries = []

    for insight in all_new_insights:
        log_id = f"log_{next_id:03d}"
        timestamp = insight['timestamp']

        entry = create_log_entry(insight, log_id, insight['task'], timestamp)
        new_log_entries.append(entry)
        next_id += 1

        print(f"   ➕ {log_id}: {entry['finding'][:50]}...")

    # Добавляем в начало (новые первыми)
    current_data['logs'] = new_log_entries + current_data['logs']
    current_data['total_logs'] = len(current_data['logs'])
    current_data['last_update'] = datetime.now(timezone.utc).isoformat()

    # Сохраняем обновленные данные
    with open(logs_file, 'w', encoding='utf-8') as f:
        json.dump(current_data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"✅ УСПЕХ!")
    print(f"{'='*70}")
    print(f"✅ Добавлено новых инсайтов: {len(new_log_entries)}")
    print(f"📊 Всего инсайтов на сайте: {current_data['total_logs']}")
    print(f"📝 Файл обновлен: {logs_file}")
    print(f"🌐 Сайт обновит данные автоматически при F5\n")

if __name__ == "__main__":
    main()
