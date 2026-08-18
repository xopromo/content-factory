import json
import os
import sys
from pathlib import Path

# Добавляем корень проекта в пути импорта
sys.path.append(str(Path(__file__).parent.parent))

from scripts.utils.llm_client import run_claude_common

state_path = Path("plans/.state/grok-image-novosti.json")
with open(state_path, "r", encoding="utf-8") as f:
    data = json.load(f)

draft = data["context"]["draft_1-3"]
title = data["context"]["title"]

prompt = f"""Ты шеф-редактор технологического издания. Тебе дан черновик новости под заголовком "{title}". 
В тексте обнаружено много повторов, однотипных примеров и воды (это произошло из-за отсутствия свежих источников на этой неделе).

Твоя задача — переписать черновик так, чтобы он стал качественной, ёмкой и интересной новостной заметкой:
1. Убери все дословные повторы абзацев и примеров (про медицину, транспорт и т.д.).
2. Напиши профессионально и живо. Вместо многократного повторения фразы "из-за отсутствия источников мы не можем..." напиши один раз в лиде или введении, что официальных подробностей или свежих анонсов за последнюю неделю не поступало.
3. Добавь полезного контекста: напомни, что Grok Image (или Grok с генерацией картинок от xAI) работает на базе моделей Flux (или других моделей генерации) и интегрирован в соцсеть X (Twitter), что делает ожидания его обновлений высокими.
4. Структурируй текст красиво (с заголовками H2), убери любые банальные ИИ-фразы и штампы.
5. Длина должна быть умеренной, но текст должен быть плотным и без воды.

Оригинальный черновик:
{draft}

Верни только финальный текст статьи в формате Markdown.
"""

print("Running professional rewrite...")
cleaned_draft, _ = run_claude_common(prompt)

print("\n--- CLEANED DRAFT ---")
print(cleaned_draft)

data["context"]["draft_1-3"] = cleaned_draft

with open(state_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("\nSuccessfully updated the state file!")
