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

# Fix Windows encoding issues with emojis/Unicode
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Load dotenv
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scripts.utils.llm_client import run_fast_common

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPO") or "xopromo/vibe-coding-hub"
BRANCH = os.environ.get("GITHUB_BRANCH") or "main"
TASKS_PATH = "docs/articles/tasks.json"

# Check if we should use a separate clone directory for the target repository
if "content-factory" in REPO.lower():
    GIT_DIR = ROOT
else:
    repo_name = REPO.split("/")[-1]
    GIT_DIR = ROOT / "scratch" / repo_name
    
    # Auto-clone if it doesn't exist yet
    if not GIT_DIR.exists():
        print(f"Directory {GIT_DIR} not found. Cloning repository {REPO}...")
        import subprocess
        GIT_DIR.parent.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(
            ["git", "clone", f"https://github.com/{REPO}.git", repo_name],
            cwd=str(ROOT / "scratch"),
            capture_output=True,
            text=True,
            shell=True
        )
        if res.returncode != 0:
            print(f"Auto-clone failed: {res.stderr.strip()}")

def git_pull():
    import subprocess
    try:
        # Run git pull to get latest changes from remote main
        res = subprocess.run(["git", "pull", "--rebase", "origin", BRANCH], cwd=str(GIT_DIR), capture_output=True, text=True, shell=True)
        if res.returncode != 0:
            err_msg = res.stderr.strip()
            print(f"git pull failed (code {res.returncode}): {err_msg}")
            
            # Self-healing: if we have merge/rebase conflicts, abort and force reset to origin
            err_lower = err_msg.lower()
            if "conflict" in err_lower or "unmerged" in err_lower or "rebasing" in err_lower or "pulling is not possible" in err_lower:
                print("Merge/rebase conflict detected. Aborting rebase and force resetting to origin...")
                subprocess.run(["git", "rebase", "--abort"], cwd=str(GIT_DIR), capture_output=True, shell=True)
                subprocess.run(["git", "merge", "--abort"], cwd=str(GIT_DIR), capture_output=True, shell=True)
                subprocess.run(["git", "reset", "--hard", f"origin/{BRANCH}"], cwd=str(GIT_DIR), capture_output=True, shell=True)
                # Try pull again after reset
                subprocess.run(["git", "pull", "origin", BRANCH], cwd=str(GIT_DIR), capture_output=True, shell=True)
    except Exception as e:
        print(f"git pull exception: {e}")

def git_push(message):
    import subprocess
    try:
        # Commit tasks.json changes
        subprocess.run(["git", "add", TASKS_PATH], cwd=str(GIT_DIR), check=True, shell=True)
        status = subprocess.run(["git", "status", "--porcelain", TASKS_PATH], cwd=str(GIT_DIR), capture_output=True, text=True, shell=True)
        if status.stdout.strip():
            res_commit = subprocess.run(["git", "commit", "-m", f"{message} [skip render]"], cwd=str(GIT_DIR), capture_output=True, text=True, shell=True)
            if res_commit.returncode != 0:
                print(f"git commit failed: {res_commit.stderr.strip()}")
                return
        
        # Loop to handle push retries with pull --rebase
        for attempt in range(3):
            git_pull()
            res_push = subprocess.run(["git", "push", "origin", BRANCH], cwd=str(GIT_DIR), capture_output=True, text=True, shell=True)
            if res_push.returncode == 0:
                print(f"Successfully pushed: {message}")
                return
            else:
                print(f"git push failed (attempt {attempt + 1}): {res_push.stderr.strip()}")
                time.sleep(2)
    except Exception as e:
        print(f"git push exception: {e}")

def gh_read_tasks():
    # Sync via git pull first
    git_pull()
    
    p = GIT_DIR / TASKS_PATH
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to parse tasks.json: {e}")
    return []

def gh_write_tasks(tasks, message="chore: update tasks list"):
    content = json.dumps(tasks, indent=2, ensure_ascii=False)
    
    # Save locally
    p = GIT_DIR / TASKS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

    # Sync via git push
    git_push(message)

def find_task_by_any_msg_id(msg_id, all_tasks):
    for t in all_tasks:
        if t.get("message_id") == msg_id or t.get("reply_message_id") == msg_id:
            return t
    return None

def build_history_context(task, all_tasks):
    history = []
    current_reply_to_id = task.get("reply_to_message_id")
    
    # Method 1: Follow reply-to chain if available
    if current_reply_to_id:
        visited_ids = set()
        while current_reply_to_id and current_reply_to_id not in visited_ids:
            visited_ids.add(current_reply_to_id)
            parent = find_task_by_any_msg_id(current_reply_to_id, all_tasks)
            if parent:
                history.append(parent)
                current_reply_to_id = parent.get("reply_to_message_id")
            else:
                break
        history.reverse()
        
    # If the reply chain is too short or empty, we fill it up with preceding completed tasks
    # to maintain continuous conversation context.
    target_history_len = 8
    if len(history) < target_history_len:
        # Find the earliest message currently in history (or the current task if history is empty)
        ref_task = history[0] if history else task
        
        completed_before = []
        for t in all_tasks:
            if t.get("id") == ref_task.get("id"):
                break
            if t.get("status") == "completed" and t.get("result"):
                completed_before.append(t)
        
        needed = target_history_len - len(history)
        extra_history = completed_before[-needed:]
        history = extra_history + history
        
    return history

def clean_history_result(result):
    if not result:
        return ""
    # Remove Telegram bold prefix if present
    result = result.replace("✅ <b>Результат выполнения задачи:</b>\n\n", "")
    
    # Split by "Созданные файлы" or similar developer headers to discard the developer report section
    for separator in ["Созданные файлы или решения:", "Созданные файлы:", "Решение:"]:
        if separator in result:
            result = result.split(separator)[0]
            
    # Remove "Отчет о проделанной работе:" header
    result = result.replace("Отчет о проделанной работе:", "")
    
    return result.strip()

def execute_ai_task(task_text, history=None):
    """
    Simulates AI agent executing the user's task.
    You can customize this to run real code, generate articles, files, etc.
    """
    print(f"Executing task: {task_text}")
    
    system_prompt = (
        "Ты Antigravity — автономный ИИ-ассистент, разработчик и контент-генератор.\n"
        "Правила ответов:\n"
        "1. Если пользователь просто ведет диалог (приветствует, отвечает на вопросы, играет в '20 вопросов' и т.д.), "
        "отвечай дружелюбно, естественно, кратко и только от первого лица. НЕ повторяй реплики пользователя, НЕ пиши мета-комментарии (вроде 'Вы ответили нет, теперь я...') "
        "и НЕ пиши никаких технических отчетов и списков созданных файлов.\n"
        "2. Пиши ответ напрямую, как реплику в чате.\n"
        "3. Только если пользователь дал конкретную техническую задачу (например, написать скрипт, изменить код, создать файл или автоматизировать процесс), "
        "выполни её и в самом конце ответа напиши краткий отчет о проделанной работе и измененных файлах."
    )
    
    # Build prompt with history context
    full_prompt = f"{system_prompt}\n\n"
    if history:
        full_prompt += "История предыдущей беседы (контекст):\n"
        for h in history:
            full_prompt += f"Пользователь: {h['text']}\n"
            if h.get("result"):
                clean_result = clean_history_result(h["result"])
                if clean_result:
                    full_prompt += f"ИИ-агент (ты): {clean_result}\n"
        full_prompt += f"\nТекущее сообщение от пользователя: {task_text}\n\n"
        full_prompt += "ИИ-агент (ты): "
    else:
        full_prompt += task_text
        
    try:
        response, _ = run_fast_common(full_prompt, quality="fast")
        response_clean = response.strip()
        for prefix in ["ИИ-агент (ты):", "ИИ-агент:", "Antigravity:", "Ответ:"]:
            if response_clean.startswith(prefix):
                response_clean = response_clean[len(prefix):].strip()
        return response_clean
    except Exception as e:
        return f"Ошибка при выполнении задачи: {e}\n{traceback.format_exc()}"

def send_telegram_reply(message_id, reply_text):
    token = os.environ.get("TG_BOT_TOKEN")
    channel_id = -1004378273791
    if not token:
        return None
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
            res_data = json.loads(r.read())
            return res_data.get("result", {}).get("message_id")
    except Exception as e:
        print(f"Failed to send reply to Telegram: {e}")
    return None

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
                    
                    # Get thread history context
                    history = build_history_context(task, tasks)
                    if history:
                        print(f"Loaded context history with {len(history)} messages")
                    
                    # Execute task
                    result = execute_ai_task(task["text"], history)
                    
                    # Send response back to Telegram channel
                    reply_msg_id = send_telegram_reply(task["message_id"], result)
                    if reply_msg_id:
                        task["reply_message_id"] = reply_msg_id
                    
                    # Update task state to completed
                    task["status"] = "completed"
                    task["result"] = result
                    task["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    updated = True
            
            if updated:
                gh_write_tasks(tasks, message="task: completed execution")
                
        except Exception as e:
            print(f"Error in task listener loop: {e}")
            
        # Poll interval: 3 seconds
        time.sleep(3)

if __name__ == "__main__":
    run_loop()
