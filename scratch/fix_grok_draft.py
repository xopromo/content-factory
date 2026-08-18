import json
import os
import sys
from pathlib import Path

# Добавляем корень проекта в пути импорта
sys.path.append(str(Path(__file__).parent.parent))

from scripts.utils.validators import improve_readability_seo, detect_semantic_duplicates

state_path = Path("plans/.state/grok-image-novosti.json")
with open(state_path, "r", encoding="utf-8") as f:
    data = json.load(f)

draft = data["context"]["draft_1-3"]
print("--- ORIGINAL DRAFT ---")
print(draft)

# 1. Смысловые дубликаты
has_dups, report = detect_semantic_duplicates(draft)
print("\n--- DETECTED DUPS ---")
print(report)

if has_dups:
    from scripts.utils.llm_client import run_claude_common
    prompt = (
        f"Ты редактор. Объедини или удали дублирующиеся разделы статьи по отчёту.\n\n"
        f"Отчёт:\n{report}\n\n"
        f"Правило: при объединении сохраняй все уникальные факты из обоих разделов. "
        f"Не удаляй утверждения с ссылками [1], [2] и т.д. "
        f"Верни полный текст статьи.\n\n"
        f"Статья:\n{draft}"
    )
    merged, _ = run_claude_common(prompt)
    if len(merged) >= len(draft) * 0.6:
        draft = merged
        print("\n--- AFTER DEDUP ---")
        print(draft)

# 2. Читаемость и слова-паразиты
improved = improve_readability_seo(draft)
if improved != draft:
    draft = improved
    print("\n--- AFTER READABILITY ---")
    print(draft)

data["context"]["draft_1-3"] = draft

with open(state_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("\nSaved new state!")
