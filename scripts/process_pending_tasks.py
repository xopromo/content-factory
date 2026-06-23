# -*- coding: utf-8 -*-
import os
import sys
import json
import urllib.parse
import time
import subprocess
from pathlib import Path

# Add content-factory to system path
ROOT = Path(__file__).parent.parent.resolve()
sys.path.append(str(ROOT))

from scripts.task_listener import GIT_DIR, TASKS_PATH, gh_read_tasks, gh_write_tasks, git_pull, edit_telegram_status

def notify_vscode_agent(task_id, prompt, conv_id, task_details):
    try:
        ls_path = Path("C:/Users/асус/AppData/Local/Programs/Antigravity/resources/bin/language_server.exe")
        if not ls_path.exists():
            print("Language Server executable not found, cannot notify VSCode agent.")
            return False
            
        msg_content = f"""[Служебное сообщение для ИИ-разработчика Antigravity]
Внимание: ты запущен в отдельном потоке (новом чате) для выполнения конкретной задачи.

Информация о задаче:
- ID задачи: {task_id}
- Message ID в Telegram: {task_details.get('message_id')}
- Status Message ID в Telegram: {task_details.get('status_message_id')}
- Исходный текст задачи: {prompt}

Инструкция по выполнению:
1. Выполни задачу в соответствии с правилами в CLAUDE.md и .agents/AGENTS.md.
2. После того как решение готово (файлы созданы/изменены, видео сгенерировано и т.д.):
   - Загрузи список задач через `gh_read_tasks` из `scripts.task_listener`.
   - Запиши подробный отчет или результат выполнения в поле 'result' задачи #{task_id} в файле `docs/articles/tasks.json` в Git репозитории.
   - Измени статус задачи #{task_id} на 'completed' и обнови 'completed_at'.
   - Пушни изменения в Git (вызови `gh_write_tasks` из `scripts.task_listener`).
   - Отправь текстовый ответ в Telegram в ответ на исходное сообщение с message_id = {task_details.get('message_id')}. Используй функцию `send_telegram_reply({task_details.get('message_id')}, <текст_ответа>)` из `scripts.task_listener`.
   - Если нужно отправить фото, используй `send_photo(<путь_к_фото>, reply_to_message_id={task_details.get('message_id')})` из `scripts.send_telegram_photo`.
   - Если нужно отправить видео/документ, используй `send_telegram_document(<путь_к_документу>, reply_to_message_id={task_details.get('message_id')})` из `scripts.task_listener`.
   - Обязательно удали статусное сообщение с status_msg_id = {task_details.get('status_message_id')} через `delete_telegram_message({task_details.get('status_message_id')})` из `scripts.task_listener`.
3. После выполнения всех шагов, вызови `final_answer` со своим отчетом, завершив работу.

Пожалуйста, приступай к выполнению прямо сейчас.
"""
        
        print(f"Sending system instruction to conversation {conv_id}...")
        res = subprocess.run(
            [str(ls_path), "agentapi", "send-message", conv_id, msg_content],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30
        )
        if res.returncode == 0:
            print("Successfully notified VSCode agent via agentapi!")
            return True
        else:
            print(f"Failed to notify VSCode agent: {res.stderr.strip()}")
            return False
    except Exception as e:
        print(f"Error notifying VSCode agent: {e}")
        return False

def is_pid_running(pid):
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        else:
            err = ctypes.windll.kernel32.GetLastError()
            if err == 5:  # ERROR_ACCESS_DENIED
                return True
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

def acquire_lock():
    lock_file = ROOT / "scratch" / "process_tasks.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if lock_file.exists():
        try:
            content = lock_file.read_text(encoding="utf-8").strip()
            if content:
                pid = int(content)
                if is_pid_running(pid):
                    print(f"Another task processor (PID {pid}) is already running. Exiting.")
                    return False
                else:
                    print(f"Stale lock file found (PID {pid} is not running). Removing it.")
        except Exception as e:
            print(f"Error checking lock file: {e}. Overwriting.")
            
    try:
        lock_file.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception as e:
        print(f"Failed to write lock file: {e}")
        return False

def release_lock():
    lock_file = ROOT / "scratch" / "process_tasks.lock"
    if lock_file.exists():
        try:
            lock_file.unlink()
        except Exception as e:
            print(f"Failed to release lock file: {e}")

def process_tasks():
    if not acquire_lock():
        return
    try:
        _process_tasks_inner()
    finally:
        release_lock()

def _process_tasks_inner():
    print("Performing git pull...")
    git_pull()
    
    tasks = gh_read_tasks()
    if not tasks:
        print("No tasks found or failed to read tasks.json. Aborting to prevent truncation.")
        return
    updated = False
    had_tasks = False
    
    ls_path = Path("C:/Users/асус/AppData/Local/Programs/Antigravity/resources/bin/language_server.exe")
    
    for task in tasks:
        if task.get("status") in ("pending", "pending_vscode"):
            had_tasks = True
            task_id = task["id"]
            prompt = task.get("text", "")
            msg_id = task.get("message_id")
            status_msg_id = task.get("status_message_id")
            
            # Check if this is a reply to another task
            reply_to_id = task.get("reply_to_message_id")
            parent_task = None
            if reply_to_id:
                for t in tasks:
                    if t.get("message_id") == reply_to_id:
                        parent_task = t
                        break
            
            # Heuristic: if no parent found by reply_to_id, find the latest task with "waiting_for_instruction"
            if not parent_task:
                try:
                    task_index = tasks.index(task)
                    for i in range(task_index - 1, -1, -1):
                        t = tasks[i]
                        if t.get("status") == "waiting_for_instruction":
                            parent_task = t
                            break
                except ValueError:
                    for t in reversed(tasks):
                        if t.get("status") == "waiting_for_instruction":
                            parent_task = t
                            break
            
            merged_prompt = prompt
            if parent_task:
                parent_text = parent_task.get("text", "").strip()
                if "youtube.com" in parent_text or "youtu.be" in parent_text or parent_text.startswith("http"):
                    merged_prompt = f"Ссылка: {parent_text}\nИнструкция: {prompt}"
                
                if parent_task.get("status") == "waiting_for_instruction":
                    print(f"Merged parent URL task #{parent_task['id']} with reply instruction #{task_id}")
                    parent_task["status"] = "completed"
                    parent_task["result"] = f"Обработано в рамках ответной задачи #{task_id}"
                    parent_task["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    parent_status_msg_id = parent_task.get("status_message_id")
                    if parent_status_msg_id:
                        try:
                            from scripts.task_listener import delete_telegram_message
                            delete_telegram_message(parent_status_msg_id)
                        except Exception:
                            pass
                    updated = True
            
            was_pending = (task["status"] == "pending")
            conv_id = task.get("vscode_conversation_id")
            notified = task.get("vscode_notified", False)
            
            if not conv_id and ls_path.exists():
                # Read pools configuration
                pools_path = Path(__file__).parent / "chat_pools.json"
                pools = {}
                if pools_path.exists():
                    try:
                        pools = json.loads(pools_path.read_text(encoding="utf-8"))
                    except Exception as pe:
                        print("Failed to read chat_pools.json:", pe)
                
                target_pool_key = None
                prompt_lower = prompt.lower()
                is_shorts = any(w in prompt_lower for w in ["шортс", "видео", "нарезка", "youtube", "comments", "плашка", "плашкой"])
                is_code = any(w in prompt_lower for w in ["код", "скрипт", "напиши", "исправь", "ошибка", "баг", "sqlite", "git"])
                
                if is_shorts:
                    target_pool_key = "shorts_pool"
                elif is_code:
                    target_pool_key = "code_pool"
                
                if target_pool_key and target_pool_key in pools and pools[target_pool_key]:
                    pool = pools[target_pool_key]
                    
                    # Count active tasks for each chat in the pool
                    active_counts = {cid: 0 for cid in pool}
                    for t in tasks:
                        if t.get("status") in ("pending", "pending_vscode") and t.get("id") != task_id:
                            cid = t.get("vscode_conversation_id")
                            if cid in active_counts:
                                active_counts[cid] += 1
                                
                    # Select the chat with minimum active tasks
                    best_cid = min(pool, key=lambda c: active_counts[c])
                    conv_id = best_cid
                    task["vscode_conversation_id"] = conv_id
                    task["vscode_notified"] = False
                    notified = False
                    updated = True
                    print(f"Routed task #{task_id} to pooled conversation {conv_id} (pool: {target_pool_key}, load: {active_counts[best_cid]} active tasks)")
                else:
                    # Default: simple questions go to general chat
                    conv_id = pools.get("general", "53b913fe-94c5-41ad-ad76-72fde5331225")
                    task["vscode_conversation_id"] = conv_id
                    task["vscode_notified"] = False
                    notified = False
                    updated = True
                    print(f"Routed task #{task_id} to general conversation {conv_id}")
                    
                if not conv_id:
                    print(f"Creating new conversation for task #{task_id}...")
                    title = f"Задача #{task_id}: {prompt[:50]}...".replace('"', "'")
                    try:
                        res = subprocess.run(
                            [str(ls_path), "agentapi", "new-conversation", "--model=pro", title],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="ignore",
                            timeout=30
                        )
                        data = json.loads(res.stdout)
                        conv_id = data["response"]["newConversation"]["conversationId"]
                        task["vscode_conversation_id"] = conv_id
                        task["vscode_notified"] = False
                        notified = False
                        updated = True
                        print(f"Created conversation {conv_id} for task #{task_id}")
                    except Exception as e:
                        print(f"Failed to create conversation for task #{task_id}: {e}")
            
            if was_pending:
                task["status"] = "pending_vscode"
                updated = True
                if status_msg_id:
                    try:
                        edit_telegram_status(status_msg_id, "⏳ <b>[15%]</b> ИИ-Агент: Стягиваю обновления из Git...")
                    except Exception:
                        pass
            
            # Log pending task
            print("\n=== PENDING_TEXT_TASK ===")
            print(f"ID: {task_id}")
            print(f"MsgID: {msg_id}")
            print(f"Prompt: {merged_prompt}")
            print(f"Conv ID: {conv_id}")
            print(f"Notified: {notified}")
            print("=========================\n")
            
            if conv_id and not notified:
                if status_msg_id:
                    try:
                        edit_telegram_status(status_msg_id, f"⚙️ <b>[35%]</b> ИИ-Агент: Ожидаю решения агентом в VSCode...")
                    except Exception:
                        pass
                success = notify_vscode_agent(task_id, merged_prompt, conv_id, task)
                if success:
                    task["vscode_notified"] = True
                    updated = True
                
    if updated:
        gh_write_tasks(tasks, message="task: VSCode initialized pending conversations")
        print("Updated tasks list saved and pushed to Git.")
        
    # Adaptive Polling Calculation
    state_file = ROOT / "scratch" / "adaptive_state.json"
    state = {"last_activity": time.time()}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    if had_tasks or updated:
        state["last_activity"] = time.time()
        
    elapsed = time.time() - state.get("last_activity", 0)
    
    if elapsed < 300:      # 5 minutes
        poll_interval = 15
        mode = "ACTIVE"
    elif elapsed < 900:    # 15 minutes
        poll_interval = 60
        mode = "STANDBY"
    else:
        poll_interval = 900
        mode = "SLEEP"
        
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state), encoding="utf-8")
    
    print(f"\n=== ADAPTIVE_POLLING ===")
    print(f"Mode: {mode}")
    print(f"Elapsed since activity: {int(elapsed)}s")
    print(f"Recommended interval: {poll_interval}s")
    print("========================\n")

if __name__ == "__main__":
    process_tasks()
