import os
import json
import urllib.request
import urllib.parse
import base64
import time

TG_BOT_TOKEN = "8702383164:AAG6c0saDPcNK5p6IIowsi9gc_ltmCzQbng"
CHANNEL_ID = -1004378273791
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = "xopromo/content-factory"
BRANCH = "main"
TASKS_PATH = "docs/articles/tasks.json"

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

def gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "test-script/1.0"
    }

def main():
    print("Sending test task message to Telegram...")
    task_text = "Проверить автозапуск ИИ-агента Antigravity. Пожалуйста, напиши краткое приветственное сообщение и подтверди, что ты успешно получаешь задачи из GitHub и умеешь отвечать в канал!"
    
    msg_id = send_msg(
        f"🎯 <b>Новая голосовая задача от пользователя:</b>\n\n"
        f"{task_text}\n\n"
        f"⚡️ <i>ИИ-агент, возьми в работу. Отчет отправь ответом на это сообщение.</i>"
    )
    print(f"Sent task message. Telegram Message ID: {msg_id}")
    
    # Read existing tasks from GitHub
    print("Reading current tasks.json from GitHub...")
    url = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(TASKS_PATH)}?ref={BRANCH}"
    tasks = []
    sha = None
    try:
        req = urllib.request.Request(url, headers=gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            sha = d.get("sha")
            content_str = base64.b64decode(d["content"].replace("\n", "")).decode("utf-8")
            tasks = json.loads(content_str)
    except Exception as e:
        print("tasks.json not found on GitHub or empty, creating new.")
        
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
    
    # Write back to GitHub
    print("Writing new task to GitHub...")
    content = json.dumps(tasks, indent=2, ensure_ascii=False)
    payload = {
        "message": f"task: add test task #{next_id} [skip render]",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": BRANCH
    }
    if sha:
        payload["sha"] = sha
        
    write_url = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(TASKS_PATH)}"
    req = urllib.request.Request(
        write_url,
        data=json.dumps(payload).encode(),
        headers={**gh_headers(), "Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        print("Successfully wrote tasks.json to GitHub!")

if __name__ == "__main__":
    main()
