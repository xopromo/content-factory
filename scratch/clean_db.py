import json
import re
from pathlib import Path

db_path = Path(r"c:\Users\асус\Desktop\клод\антигравити, всякое\content-factory\scratch\vibe-coding-hub\docs\articles\tasks.json")

if not db_path.exists():
    print("Database path not found!")
    exit(1)

def clean_history_result(result):
    if not result:
        return ""
    result = result.replace("✅ <b>Результат выполнения задачи:</b>\n\n", "")
    
    for separator in ["Созданные файлы или решения:", "Созданные файлы:", "Решение:"]:
        if separator in result:
            result = result.split(separator)[0]
            
    result = result.replace("Отчет о проделанной работе:", "")
    
    result_clean = result.strip()
    match = re.search(r'(?:Мой следующий вопрос|Следующий вопрос|вопрос):\s*(.*)', result_clean, re.IGNORECASE | re.DOTALL)
    if match:
        result_clean = match.group(1).strip()
        
    sentences = re.split(r'(?<=[.!?])\s+', result_clean)
    question_sentences = []
    for s in sentences:
        s_strip = s.strip()
        if not s_strip:
            continue
        if any(w in s_strip.lower() for w in ["вы ответили", "ответили:", "ожидайте ответа"]):
            continue
        question_sentences.append(s_strip)
        
    if question_sentences:
        result_clean = " ".join(question_sentences)
        
    for prefix in ["ИИ-агент (ты):", "ИИ-агент:", "Antigravity:", "Ответ:"]:
        if result_clean.startswith(prefix):
            result_clean = result_clean[len(prefix):].strip()
            
    return result_clean.strip()

tasks = json.loads(db_path.read_text(encoding="utf-8"))
for t in tasks:
    if t.get("result"):
        old = t["result"]
        new = clean_history_result(old)
        if old != new:
            print(f"Cleaned task #{t['id']}:\n  OLD: {old}\n  NEW: {new}\n")
            t["result"] = new

db_path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")
print("Database cleaned successfully!")
