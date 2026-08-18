import json
import re
from pathlib import Path

db_path = Path(r"c:\Users\асус\Desktop\клод\антигравити, всякое\content-factory\scratch\vibe-coding-hub\docs\articles\tasks.json")

def clean_to_last_question(text):
    if not text:
        return ""
    text = text.replace("✅ <b>Результат выполнения задачи:</b>\n\n", "")
    for separator in ["Созданные файлы или решения:", "Созданные файлы:", "Решение:", "Отчет о проделанной работе:"]:
        if separator in text:
            text = text.split(separator)[0]
    
    text = text.strip()
    
    # Find all sentences ending with a question mark
    questions = re.findall(r'([^.!?]*\?[”"\'»]?)', text)
    if questions:
        # Keep the last question sentence
        last_q = questions[-1].strip()
        # Clean any leading meta text or quotes
        last_q = re.sub(r'^[^?]*задал вопрос:\s*', '', last_q)
        last_q = last_q.strip('"\'«»“” ')
        return last_q
    return text

tasks = json.loads(db_path.read_text(encoding="utf-8"))
for t in tasks:
    if t.get("result"):
        # We only clean conversational/short tasks
        if len(t["text"]) < 50 and any(w in t["text"].lower() for w in ["вопрос", "да", "нет", "продолжить", "привет"]):
            old = t["result"]
            new = clean_to_last_question(old)
            if old != new:
                print(f"Cleaned task #{t['id']}:\n  OLD: {old}\n  NEW: {new}\n")
                t["result"] = new

db_path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")
print("Cleaned successfully!")
