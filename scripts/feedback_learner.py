#!/usr/bin/env python3
"""
Feedback Learner — скрипт для автоматического обучения на основе обратной связи.

Функции:
1. Парсит обратную связь пользователя (например, "Запомни: Devika — ошибка, правильно Devin").
2. Генерирует новые правила для learning_rules.md.
3. Обновляет базу знаний (knowledge/) и PROJECT_STATE.md.
"""

import re
import json
import os
from datetime import datetime
from typing import List, Dict

# Пути к файлам
LEARNING_RULES_PATH = "ai-clone/feedback/learning_rules.md"
PROJECT_STATE_PATH = "PROJECT_STATE.md"
KNOWLEDGE_DIR = "knowledge/"


def parse_feedback(text: str) -> Dict:
    """
    Парсит обратную связь пользователя и возвращает новое правило.
    Примеры:
    - "Запомни: Devika — ошибка, правильно Devin" → правило замены.
    - "Не используй слово 'инновационный'" → стоп-слово.
    """
    # Правило замены (например, "Devika → Devin")
    replace_pattern = r"запомни:\s*(.+?)\s*—\s*ошибка,\s*правильно\s*(.+?)(?:$|\.|\!)"
    replace_match = re.search(replace_pattern, text, re.IGNORECASE)
    if replace_match:
        wrong, correct = replace_match.groups()
        return {
            "rule_id": f"lr-{datetime.now().strftime('%m%d%H%M')}",
            "trigger": f"{wrong}|{wrong.lower()}|{wrong.capitalize()}",
            "action": f"Заменить на '{correct}' и заблокировать статью для проверки",
            "severity": "CRITICAL",
            "source": f"user_feedback_{datetime.now().strftime('%Y-%m-%d')}",
            "applied_to": ["entity-validator", "content-writer"]
        }
    
    # Стоп-слово (например, "Не используй 'инновационный'")
    stopword_pattern = r"не\s+используй\s+[\'\"](.+?)[\'\"]"
    stopword_match = re.search(stopword_pattern, text, re.IGNORECASE)
    if stopword_match:
        word = stopword_match.group(1)
        return {
            "rule_id": f"lr-{datetime.now().strftime('%m%d%H%M')}",
            "trigger": word,
            "action": f"Удалить слово '{word}' из текста",
            "severity": "WARNING",
            "source": f"user_feedback_{datetime.now().strftime('%Y-%m-%d')}",
            "applied_to": ["content-writer", "editor-critic"]
        }
    
    return None


def update_learning_rules(new_rule: Dict) -> None:
    """Добавляет новое правило в learning_rules.md."""
    if not os.path.exists(LEARNING_RULES_PATH):
        raise FileNotFoundError(f"Файл {LEARNING_RULES_PATH} не найден")
    
    with open(LEARNING_RULES_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем блок ```json ... ``` для извлечения правил
    match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
    if not match:
        raise ValueError("Не найден блок ```json в файле правил")
        
    json_str = match.group(1).strip()
    rules = json.loads(json_str)
    
    # Добавляем новое правило
    rules.append(new_rule)
    
    # Обновляем JSON в файле
    updated_json = json.dumps(rules, indent=2, ensure_ascii=False)
    old_block = match.group(0)
    new_block = f"```json\n{updated_json}\n```"
    updated_content = content.replace(old_block, new_block)
    
    # Обновляем дату последнего изменения
    updated_content = re.sub(
        r"\*\*Последнее обновление\*\*: \d{4}-\d{2}-\d{2}",
        f"**Последнее обновление**: {datetime.now().strftime('%Y-%m-%d')}",
        updated_content
    )
    
    with open(LEARNING_RULES_PATH, 'w', encoding='utf-8') as f:
        f.write(updated_content)


def update_project_state(feedback_summary: str) -> None:
    """Добавляет информацию об обратной связи в PROJECT_STATE.md."""
    if not os.path.exists(PROJECT_STATE_PATH):
        raise FileNotFoundError(f"Файл {PROJECT_STATE_PATH} не найден")
    
    with open(PROJECT_STATE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Добавляем раздел "Обучение на обратной связи", если его нет
    if "## Обучение на обратной связи" not in content:
        content += "\n\n## Обучение на обратной связи\n\n> Автоматическое обновление правил на основе коррекций пользователя."
    
    # Добавляем новую запись
    new_entry = f"\n- [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {feedback_summary}"
    content += new_entry
    
    with open(PROJECT_STATE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)


def save_to_knowledge(feedback: str) -> str:
    """Сохраняет обратную связь в базу знаний."""
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    filename = f"{KNOWLEDGE_DIR}feedback_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# Обратная связь от пользователя\n\n**Дата**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n**Содержание**:\n{feedback}\n\n**Тэги**: #обратная_связь #коррекция")
    return filename


def main(feedback_text: str) -> str:
    """Основная функция обработки обратной связи."""
    # 1. Парсим обратную связь
    new_rule = parse_feedback(feedback_text)
    if not new_rule:
        return "Не удалось распознать формат обратной связи. Примеры:\n- 'Запомни: Devika — ошибка, правильно Devin'\n- 'Не используй слово \"инновационный\"'"
    
    # 2. Обновляем learning_rules.md
    update_learning_rules(new_rule)
    
    # 3. Сохраняем в базу знаний
    filename = save_to_knowledge(feedback_text)
    
    # 4. Обновляем PROJECT_STATE.md
    feedback_summary = f"Добавлено правило {new_rule['rule_id']}: {new_rule['trigger']} → {new_rule['action']}"
    update_project_state(feedback_summary)
    
    # 5. Коммитим изменения
    os.system(f'git add {LEARNING_RULES_PATH} {PROJECT_STATE_PATH} {filename}')
    os.system(f'git commit -m "feedback: {new_rule["rule_id"]} — {new_rule["trigger"]}"')
    
    return f"[OK] Обработана обратная связь:\n- Добавлено правило: {new_rule['trigger']} → {new_rule['action']}\n- Сохранено в: {filename}\n- Обновлен: {PROJECT_STATE_PATH}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        feedback = ' '.join(sys.argv[1:])
        print(main(feedback))
    else:
        print("Использование: python feedback_learner.py 'Ваша обратная связь'")