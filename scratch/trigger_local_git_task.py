import os
import json
import urllib.request
import urllib.parse
import subprocess
import time
from pathlib import Path

TG_BOT_TOKEN = "8702383164:AAG6c0saDPcNK5p6IIowsi9gc_ltmCzQbng"
CHANNEL_ID = -1004378273791
ROOT = Path("c:/Users/асус/Desktop/клод/антигравити, всякое/content-factory")
TASKS_FILE = ROOT / "docs/articles/tasks.json"

def send_msg(text):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["result"]["message_id"]

def run_git(cmd):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, shell=True, env=env)
    if res.returncode != 0:
        print(f"Git cmd failed: {' '.join(cmd)}")
        print(f"Error: {res.stderr.strip()}")
        return False
    return True

def main():
    print("1. Sending test task message to Telegram...")
    task_text = "Проверить автозапуск ИИ-агента Antigravity. Пожалуйста, напиши краткое приветственное сообщение и подтверди, что ты успешно получаешь задачи из GitHub и умеешь отвечать в канал!"
    
    msg_id = send_msg(
        f"🎯 <b>Новая голосовая задача от пользователя:</b>\n\n"
        f"{task_text}\n\n"
        f"⚡️ <i>ИИ-агент, возьми в работу. Отчет отправь ответом на это сообщение.</i>"
    )
    print(f"Sent task message. Telegram Message ID: {msg_id}")
    
    # Run git pull first to avoid conflicts
    print("2. Pulling latest code...")
    run_git(["git", "pull", "origin", "main"])
    
    # Read existing tasks
    print("3. Reading local tasks.json...")
    tasks = []
    if TASKS_FILE.exists():
        try:
            tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Error parsing tasks.json: {e}")
            
    next_id = 1
    if tasks:
        next_id = max(t.get("id", 0) for t in tasks) + 1
        
    new_task = {
        "id": next_id,
        "message_id": msg_id,
        "text": task_text,
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    tasks.append(new_task)
    
    # Write back
    print("4. Saving local tasks.json...")
    TASKS_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Commit and push via Git
    print("5. Committing and pushing via local Git client...")
    if run_git(["git", "add", "docs/articles/tasks.json"]):
        if run_git(["git", "commit", "-m", f"task: add test task #{next_id}"]):
            if run_git(["git", "push", "origin", "main"]):
                print("\n[SUCCESS] Test task created and pushed successfully to GitHub via local Git bridge!")
                print(f"Task ID: {next_id}")
                print("Wait for the task listener to detect it.")

if __name__ == "__main__":
    main()
