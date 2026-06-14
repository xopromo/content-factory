#!/usr/bin/env python3
"""
Task Listener Script (SOCKS5/HTTP compatible).
Checks the public Telegram HTML preview for the channel -1004378273791 (public slug: t.me/s/antigravity_tasks or similar,
or falls back to pulling a shared GitHub file docs/articles/tasks.json if write permissions exist,
or uses getUpdates via a separate polling method if webhook conflicts are avoided).

For a developer's local machine, the most robust way to read channel messages without getUpdates conflicts
and without requiring user-bot (Telethon) sessions is to have the bot on Render write the task to a JSON file
in the Git repository (e.g. docs/articles/tasks.json) whenever a task is posted.
The local script then pulls the repo (git pull) or fetches the file from GitHub, processes it, and push-updates the status.

Let's implement this elegant Git/JSON tasks sync:
1. When you click '📢 Отправить ИИ-агенту', the bot writes the task metadata to docs/articles/tasks.json on GitHub.
2. This script pulls the JSON from GitHub, detects 'pending' tasks, executes them, and writes the response.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import traceback
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

# Load dotenv
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scripts.utils.llm_client import run_fast_common

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPO", "xopromo/content-factory")
BRANCH = os.environ.get("GITHUB_BRANCH", "main")
TASKS_PATH = "docs/articles/tasks.json"

def _gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "antigravity-agent/1.0"
    }

def gh_read_tasks():
    if not GITHUB_TOKEN:
        # Local fallback
        p = ROOT / TASKS_PATH
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    url = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(TASKS_PATH)}?ref={BRANCH}"
    try:
        req = urllib.request.Request(url, headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            import base64
            content_str = base64.b64decode(d["content"].replace("\n", "")).decode("utf-8")
            return json.loads(content_str)
    except Exception as e:
        # File might not exist yet, return empty list
        return []

def gh_write_tasks(tasks, message="chore: update tasks list"):
    content = json.dumps(tasks, indent=2, ensure_ascii=False)
    
    # Save locally first
    p = ROOT / TASKS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

    if not GITHUB_TOKEN:
        return

    url = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(TASKS_PATH)}"
    sha = None
    try:
        req = urllib.request.Request(url + f"?ref={BRANCH}", headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read()).get("sha")
    except Exception:
        pass

    import base64
    payload = {
        "message": f"{message} [skip render]",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={**_gh_headers(), "Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            pass
    except Exception as e:
        print(f"Failed to write tasks list to GitHub: {e}")

def execute_ai_task(task_text):
    """
    Simulates AI agent executing the user's task.
    You can customize this to run real code, generate articles, files, etc.
    """
    print(f"Executing task: {task_text}")
    
    system_prompt = (
        "Ты Antigravity — автономный ИИ-разработчик и контент-генератор. "
        "Пользователь дал тебе задачу через Telegram-бота. Выполни её качественно. "
        "В ответе напиши краткий отчет о проделанной работе, созданных файлах или решении."
    )
    
    try:
        response, _ = run_fast_common(f"Task: {task_text}", quality="strong")
        return response
    except Exception as e:
        return f"Ошибка при выполнении задачи: {e}\n{traceback.format_exc()}"

def send_telegram_reply(message_id, reply_text):
    token = os.environ.get("TG_BOT_TOKEN")
    channel_id = -1004378273791
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": f"✅ <b>Результат выполнения задачи:</b>\n\n{reply_text}",
        "reply_to_message_id": message_id,
        "parse_mode": "HTML"
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            pass
    except Exception as e:
        print(f"Failed to send reply to Telegram: {e}")

def run_loop():
    print("🤖 Antigravity Task Listener is active and scanning for tasks...")
    
    while True:
        try:
            tasks = gh_read_tasks()
            updated = False
            
            for task in tasks:
                if task.get("status") == "pending":
                    print(f"Found new pending task #{task['id']}")
                    
                    # Update status to running
                    task["status"] = "running"
                    gh_write_tasks(tasks, message=f"task: start execution of #{task['id']}")
                    
                    # Execute task
                    result = execute_ai_task(task["text"])
                    
                    # Send response back to Telegram channel
                    send_telegram_reply(task["message_id"], result)
                    
                    # Update task state to completed
                    task["status"] = "completed"
                    task["result"] = result
                    task["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    updated = True
            
            if updated:
                gh_write_tasks(tasks, message="task: completed execution")
                
        except Exception as e:
            print(f"Error in task listener loop: {e}")
            
        # Poll interval: 30 seconds
        time.sleep(30)

if __name__ == "__main__":
    run_loop()
