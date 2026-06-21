# -*- coding: utf-8 -*-
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
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        
        # Clone with retries
        for attempt in range(3):
            try:
                res = subprocess.run(
                    ["git", "clone", f"https://github.com/{REPO}.git", repo_name],
                    cwd=str(ROOT / "scratch"),
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=60,
                    env=env
                )
                if res.returncode == 0:
                    print("Auto-clone succeeded.")
                    break
                print(f"Auto-clone failed (attempt {attempt + 1}/3): {res.stderr.strip()}")
            except subprocess.TimeoutExpired:
                print(f"Auto-clone timed out (attempt {attempt + 1}/3)")
            except Exception as e:
                print(f"Auto-clone exception: {e}")
            time.sleep(3)

def git_pull():
    import subprocess
    import time
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    
    # Try git fetch with retries
    for attempt in range(3):
        try:
            res_fetch = subprocess.run(
                ["git", "fetch", "origin", BRANCH],
                cwd=str(GIT_DIR),
                capture_output=True,
                shell=True,
                timeout=30,
                env=env
            )
            if res_fetch.returncode == 0:
                break
            print(f"git fetch failed (attempt {attempt + 1}/3): {res_fetch.stderr.decode('utf-8', errors='ignore').strip()}")
        except subprocess.TimeoutExpired:
            print(f"git fetch timed out (attempt {attempt + 1}/3)")
        except Exception as e:
            print(f"git fetch exception: {e}")
        time.sleep(2)
        
    try:
        # Force reset to origin to ensure we are exactly matched and have no merge/rebase issues
        res = subprocess.run(
            ["git", "reset", "--hard", f"origin/{BRANCH}"],
            cwd=str(GIT_DIR),
            capture_output=True,
            text=True,
            shell=True,
            timeout=30,
            env=env
        )
        if res.returncode != 0:
            print(f"git reset failed: {res.stderr.strip()}")
    except Exception as e:
        print(f"git pull exception during reset: {e}")

def git_push(message):
    import subprocess
    import time
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    
    try:
        # Commit tasks.json changes
        subprocess.run(["git", "add", TASKS_PATH], cwd=str(GIT_DIR), check=True, shell=True, timeout=20, env=env)
        status = subprocess.run(["git", "status", "--porcelain", TASKS_PATH], cwd=str(GIT_DIR), capture_output=True, text=True, shell=True, timeout=20, env=env)
        if status.stdout.strip():
            res_commit = subprocess.run(["git", "commit", "-m", f"{message} [skip render]"], cwd=str(GIT_DIR), capture_output=True, text=True, shell=True, timeout=20, env=env)
            if res_commit.returncode != 0:
                print(f"git commit failed: {res_commit.stderr.strip()}")
                return
        
        # Push to origin with retries
        for attempt in range(3):
            try:
                res_push = subprocess.run(
                    ["git", "push", "origin", BRANCH],
                    cwd=str(GIT_DIR),
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=30,
                    env=env
                )
                if res_push.returncode == 0:
                    print(f"Successfully pushed: {message}")
                    return
                
                print(f"git push failed (attempt {attempt + 1}/3): {res_push.stderr.strip()}")
            except subprocess.TimeoutExpired:
                print(f"git push timed out (attempt {attempt + 1}/3)")
            except Exception as e:
                print(f"git push exception: {e}")
            
            # Pull with rebase before retrying
            print(f"Attempting git pull --rebase before retrying push...")
            try:
                res_rebase = subprocess.run(
                    ["git", "pull", "--rebase", "origin", BRANCH],
                    cwd=str(GIT_DIR),
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=30,
                    env=env
                )
                if res_rebase.returncode != 0:
                    print(f"git pull --rebase failed: {res_rebase.stderr.strip()}. Aborting rebase and resetting to origin.")
                    subprocess.run(["git", "rebase", "--abort"], cwd=str(GIT_DIR), capture_output=True, shell=True, timeout=20, env=env)
                    git_pull()
            except Exception as rebase_err:
                print(f"Error during pull --rebase: {rebase_err}")
                
            time.sleep(3)
            
        print("Failed to push changes to GitHub after all attempts.")
    except Exception as e:
        print(f"git push outer exception: {e}")

def gh_read_tasks():
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
    
    # Aggressively clean game meta-commentary:
    import re
    result_clean = result.strip()
    
    # Discard everything before "Мой следующий вопрос" or similar if present
    match = re.search(r'(?:Мой следующий вопрос|Следующий вопрос|вопрос):\s*(.*)', result_clean, re.IGNORECASE | re.DOTALL)
    if match:
        result_clean = match.group(1).strip()
        
    # Extract only the sentences that actually contain a question mark and are not repeating what user said
    sentences = re.split(r'(?<=[.!?])\s+', result_clean)
    question_sentences = []
    for s in sentences:
        s_strip = s.strip()
        if not s_strip:
            continue
        # Skip sentences containing common game state explanations
        if any(w in s_strip.lower() for w in ["вы ответили", "ответили:", "ожидайте ответа"]):
            continue
        question_sentences.append(s_strip)
        
    if question_sentences:
        result_clean = " ".join(question_sentences)
        
    # Strip any bot prefixes
    for prefix in ["ИИ-агент (ты):", "ИИ-агент:", "Antigravity:", "Ответ:"]:
        if result_clean.startswith(prefix):
            result_clean = result_clean[len(prefix):].strip()
            
    return result_clean.strip()


def is_agent_command(text):
    text_clean = text.strip().lower()
    greetings = ["привет", "привет!", "как дела", "как дела?", "кто ты", "кто ты?", "прием", "прием прием"]
    if text_clean in greetings:
        return False
    if len(text_clean) < 10 and not any(c in text_clean for c in ["/", "run", "do"]):
        return False
    return True

def run_agent_loop(task_text, history=None):
    import subprocess
    import json
    import re
    from pathlib import Path

    print(f"🤖 Entering agent loop for task: {task_text}")
    
    # Retrieve relevant semantic memories
    memories_str = ""
    try:
        from scripts.jarvis_memory import search_memories
        memories = search_memories(task_text, limit=4)
        valid_m = [m for m in memories if m.get("similarity", 0) > 0.5]
        if valid_m:
            memories_str = "=== RELEVANT PAST MEMORIES ===\n"
            for m in valid_m:
                memories_str += f"- [{m['created_at']}] {m['content']}\n"
            memories_str += "\n"
    except Exception as me:
        print(f"Error fetching semantic memories: {me}")
    
    # Context of files
    claude_path = ROOT / "CLAUDE.md"
    project_state_path = ROOT / "PROJECT_STATE.md"
    
    claude_md = claude_path.read_text(encoding="utf-8", errors="ignore") if claude_path.exists() else ""
    project_state_md = project_state_path.read_text(encoding="utf-8", errors="ignore") if project_state_path.exists() else ""
    
    context = (
        f"=== CLAUDE.md ===\n{claude_md[:4000]}\n\n"
        f"=== PROJECT_STATE.md ===\n{project_state_md[:4000]}\n\n"
        f"{memories_str}"
    )
    
    agent_history = []
    
    # We will loop up to 8 iterations
    for step in range(8):
        print(f"--- Step {step + 1} of 8 ---", flush=True)
        prompt = (
            "Ты — автономный ИИ-агент разработчик Antigravity. Ты запущен локально на ПК пользователя.\n"
            "Твоя задача — выполнить поручение пользователя в текущей рабочей директории.\n"
            "Доступные инструменты (вызывай их, выводя строго одну JSON-структуру в формате {\"tool\": \"...\"}):\n"
            "1. Прочитать файл: {\"tool\": \"read_file\", \"path\": \"relative/path/to/file\"}\n"
            "2. Записать/создать файл: {\"tool\": \"write_file\", \"path\": \"relative/path/to/file\", \"content\": \"содержимое\"}\n"
            "3. Посмотреть список файлов в папке: {\"tool\": \"list_dir\", \"path\": \"relative/path\"}\n"
            "4. Запустить терминальную команду (powershell): {\"tool\": \"run_command\", \"command\": \"команда\"}\n"
            "5. Завершить выполнение и выдать финальный ответ: {\"tool\": \"final_answer\", \"answer\": \"твое сообщение\"}\n"
            "6. Отправить документ в Telegram: {\"tool\": \"send_document\", \"path\": \"relative/path/to/file\", \"caption\": \"описание\"}\n"
            "7. Отправить фото/картинку в Telegram (отобразится прямо в чате): {\"tool\": \"send_photo\", \"path\": \"relative/path/to/file\", \"caption\": \"описание\"}\n"
            "8. Поиск по долговременной памяти (Jarvis Memory): {\"tool\": \"search_memory\", \"query\": \"поисковый запрос\"}\n\n"
            "Совет по генерации картинок: Если пользователь просит нарисовать или сгенерировать изображение/мем, ты можешь скачать изображение по URL: https://image.pollinations.ai/prompt/<url_encoded_prompt> с помощью python (например: python -c \"import urllib.request; urllib.request.urlretrieve('https://image.pollinations.ai/prompt/some_prompt', 'image.png')\") через run_command, а затем отправить файл с помощью send_photo.\n"
            "ВАЖНО: Если пользователь просит сгенерировать изображение/картинку, весь текст на ней должен быть строго на РУССКОМ языке (кроме логотипов и брендов), если иное не указано пользователем.\n\n"
            "Правила вызова инструментов:\n"
            "- Выводи ровно один JSON-вызов инструмента в конце своего ответа.\n"
            "- Если задача полностью выполнена, обязательно вызови tool 'final_answer'.\n\n"
            "История текущих размышлений и шагов:\n"
        )
        
        history_text = ""
        for h in agent_history:
            history_text += f"Шаг: {h['step']}\nМысли/Действие: {h['thought']}\nРезультат инструмента: {h['result']}\n\n"
            
        full_query = context + prompt + history_text + f"Текущая цель: {task_text}\nТвои мысли и следующий шаг (JSON):"
        
        # Call LLM
        response, _ = run_fast_common(full_query, quality="strong")
        print(f"Step {step + 1} thoughts:\n{response}", flush=True)
        
        # Try parsing JSON using a robust scanner
        tool_call = None
        open_indices = [i for i, char in enumerate(response) if char == '{']
        close_indices = [i for i, char in enumerate(response) if char == '}']
        
        # Try outer-most combinations first
        for s_idx in sorted(open_indices):
            for e_idx in sorted(close_indices, reverse=True):
                if e_idx > s_idx:
                    try:
                        tool_call = json.loads(response[s_idx:e_idx + 1])
                        break
                    except json.JSONDecodeError:
                        continue
            if tool_call:
                break
                
        # Fallback to reverse search if not found (e.g. nested blocks)
        if not tool_call:
            for s_idx in sorted(open_indices, reverse=True):
                for e_idx in sorted(close_indices, reverse=True):
                    if e_idx > s_idx:
                        try:
                            tool_call = json.loads(response[s_idx:e_idx + 1])
                            break
                        except json.JSONDecodeError:
                            continue
                if tool_call:
                    break
                    
        if not tool_call:
            if not open_indices or not close_indices:
                print(f"Step {step + 1} result: No JSON brackets found, treating as final answer.", flush=True)
                return response
            else:
                err_msg = "Ошибка парсинга JSON: не удалось извлечь валидный JSON блок из ответа."
                print(f"Step {step + 1} result: {err_msg}", flush=True)
                agent_history.append({
                    "step": step + 1,
                    "thought": response,
                    "result": err_msg
                })
                continue
            
        tool = tool_call.get("tool")
        print(f"Step {step + 1} calling tool: {tool_call}", flush=True)
        if tool == "final_answer":
            return tool_call.get("answer", response)
            
        # Execute tool
        result = ""
        try:
            if tool == "read_file":
                path = ROOT / tool_call.get("path", "")
                if path.exists():
                    result = path.read_text(encoding="utf-8", errors="ignore")[:4000]
                else:
                    result = f"Файл {tool_call.get('path')} не найден."
            elif tool == "write_file":
                path = ROOT / tool_call.get("path", "")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(tool_call.get("content", ""), encoding="utf-8")
                result = f"Успешно записано в {tool_call.get('path')}."
            elif tool == "list_dir":
                path = ROOT / tool_call.get("path", "")
                if path.exists() and path.is_dir():
                    files = [f.name for f in path.iterdir()]
                    result = f"Содержимое директории: {files}"
                else:
                    result = f"Директория {tool_call.get('path')} не найдена или не является папкой."
            elif tool == "run_command":
                cmd = tool_call.get("command", "")
                if cmd.strip().startswith("cd "):
                    result = "cd команда не поддерживается. Укажи Cwd или относительный путь."
                else:
                    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=str(ROOT), timeout=30)
                    result = f"Stdout: {res.stdout}\nStderr: {res.stderr}"
            elif tool == "send_document":
                file_rel = tool_call.get("path", "")
                path = ROOT / file_rel
                if path.exists() and path.is_file():
                    caption = tool_call.get("caption", "")
                    reply_msg_id = send_telegram_document(path, caption)
                    if reply_msg_id:
                        result = f"Документ {file_rel} успешно отправлен в Telegram. Message ID: {reply_msg_id}"
                    else:
                        result = f"Не удалось отправить документ {file_rel} в Telegram."
                else:
                    result = f"Файл {file_rel} для отправки не найден."
            elif tool == "send_photo":
                file_rel = tool_call.get("path", "")
                path = ROOT / file_rel
                if path.exists() and path.is_file():
                    caption = tool_call.get("caption", "")
                    reply_msg_id = send_telegram_photo(path, caption)
                    if reply_msg_id:
                        result = f"Изображение {file_rel} успешно отправлено в Telegram. Message ID: {reply_msg_id}"
                    else:
                        result = f"Не удалось отправить изображение {file_rel} в Telegram."
                else:
                    result = f"Файл {file_rel} для отправки не найден."
            elif tool == "search_memory":
                query = tool_call.get("query", "")
                try:
                    from scripts.jarvis_memory import search_memories
                    results = search_memories(query, limit=5)
                    if results:
                        formatted = "\n".join(f"- [{r['created_at']}] {r['content']} (similarity: {r['similarity']:.4f})" for r in results)
                        result = f"Результаты поиска в памяти:\n{formatted}"
                    else:
                        result = "В памяти ничего не найдено."
                except Exception as me:
                    result = f"Ошибка при поиске в памяти: {me}"
            else:
                result = f"Неизвестный инструмент: {tool}"
        except Exception as te:
            result = f"Ошибка: {te}"
            
        print(f"Step {step + 1} tool result: {result}", flush=True)
        agent_history.append({
            "step": step + 1,
            "thought": response,
            "result": result
        })
        
    return "Задача не была завершена за отведенное количество шагов. Последнее состояние: " + str(agent_history[-1])

def execute_ai_task(task_text, history=None):
    print(f"Executing task: {task_text}")
    
    if is_agent_command(task_text):
        try:
            return run_agent_loop(task_text, history)
        except Exception as ae:
            return f"Ошибка при работе ИИ-агента: {ae}"
            
    # Level 1: Normal dialogue with project context
    claude_path = ROOT / "CLAUDE.md"
    project_state_path = ROOT / "PROJECT_STATE.md"
    claude_md = claude_path.read_text(encoding="utf-8", errors="ignore") if claude_path.exists() else ""
    project_state_md = project_state_path.read_text(encoding="utf-8", errors="ignore") if project_state_path.exists() else ""
    
    project_context = (
        "\n--- ТЕКУЩИЙ КОНТЕКСТ ПРОЕКТОВ (ДЛЯ СПРАВКИ) ---\n"
        f"CLAUDE.md:\n{claude_md[:2000]}\n\n"
        f"PROJECT_STATE.md:\n{project_state_md[:2000]}\n"
        "-----------------------------------------------\n"
    )
    
    system_prompt = (
        "Ты Antigravity — умный ИИ-собеседник и разработчик.\n"
        f"Тебе доступен текущий контекст проектов на ПК пользователя:\n{project_context}\n"
        "Правила ведения диалога:\n"
        "1. Отвечай кратко, естественно и лаконично (максимум 1-3 предложения), как реальный собеседник в чате.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО пересказывать историю диалога или писать мета-комментарии о ходе игры.\n"
        "3. Если идет игра в 20 вопросов, просто отреагируй на последний ответ и сразу задай следующий вопрос.\n"
        "4. Для выполнения сложных команд по программированию или изменения файлов используй префикс 'агент' или '/agent' в запросе."
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
        return f"Ошибка при выполнении задачи: {e}"

def send_telegram_photo(file_path, caption=""):
    token = os.environ.get("TG_BOT_TOKEN")
    channel_id = -1004378273791
    if not token or not file_path.exists():
        return None
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    
    file_bytes = file_path.read_bytes()
    file_name = file_path.name
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    parts = []
    parts.append(f"--{boundary}")
    parts.append(f'Content-Disposition: form-data; name="chat_id"')
    parts.append("")
    parts.append(str(channel_id))
    
    if caption:
        parts.append(f"--{boundary}")
        parts.append(f'Content-Disposition: form-data; name="caption"')
        parts.append("")
        parts.append(caption)
        
    parts.append(f"--{boundary}")
    parts.append(f'Content-Disposition: form-data; name="photo"; filename="{file_name}"')
    parts.append("Content-Type: image/png")
    parts.append("")
    
    header_data = "\r\n".join(parts).encode("utf-8") + b"\r\n"
    footer_data = f"\r\n--{boundary}--\r\n".encode("utf-8")
    
    body = header_data + file_bytes + footer_data
    
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body))
    }
    
    # Try direct send first
    try:
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            res_data = json.loads(r.read())
            return res_data.get("result", {}).get("message_id")
    except Exception as direct_err:
        print(f"Direct Telegram photo send failed: {direct_err}. Attempting via proxy...")
        
    # Proxy fallback
    proxy_file = ROOT / "proxies.txt"
    if proxy_file.exists():
        try:
            from scripts.check_proxies import parse_proxy_line
            lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            valid_proxies = []
            for line in lines:
                parsed = parse_proxy_line(line)
                if parsed and parsed.get("type") in ("socks5", "http"):
                    valid_proxies.append(parsed)
            
            print(f"Found {len(valid_proxies)} proxies in proxies.txt for retry")
            for p in valid_proxies[:5]:
                try:
                    proxy_url = ""
                    if p["username"] and p["password"]:
                        proxy_url = f"{p['type']}://{p['username']}:{p['password']}@{p['server']}:{p['port']}"
                    else:
                        proxy_url = f"{p['type']}://{p['server']}:{p['port']}"
                        
                    proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
                    opener = urllib.request.build_opener(proxy_handler)
                    
                    req = urllib.request.Request(url, data=body, headers=headers)
                    with opener.open(req, timeout=20) as r:
                        res_data = json.loads(r.read())
                        print(f"Successfully sent Telegram photo via proxy: {proxy_url[:40]}")
                        return res_data.get("result", {}).get("message_id")
                except Exception as proxy_err:
                    print(f"Proxy photo send failed: {proxy_err}")
        except Exception as e:
            print(f"Failed to run proxy photo fallback: {e}")
            
    return None

def send_telegram_document(file_path, caption=""):
    token = os.environ.get("TG_BOT_TOKEN")
    channel_id = -1004378273791
    if not token or not file_path.exists():
        return None
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    
    file_bytes = file_path.read_bytes()
    file_name = file_path.name
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    parts = []
    parts.append(f"--{boundary}")
    parts.append(f'Content-Disposition: form-data; name="chat_id"')
    parts.append("")
    parts.append(str(channel_id))
    
    if caption:
        parts.append(f"--{boundary}")
        parts.append(f'Content-Disposition: form-data; name="caption"')
        parts.append("")
        parts.append(caption)
        
    parts.append(f"--{boundary}")
    parts.append(f'Content-Disposition: form-data; name="document"; filename="{file_name}"')
    parts.append("Content-Type: application/octet-stream")
    parts.append("")
    
    header_data = "\r\n".join(parts).encode("utf-8") + b"\r\n"
    footer_data = f"\r\n--{boundary}--\r\n".encode("utf-8")
    
    body = header_data + file_bytes + footer_data
    
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body))
    }
    
    # Try direct send first
    try:
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            res_data = json.loads(r.read())
            return res_data.get("result", {}).get("message_id")
    except Exception as direct_err:
        print(f"Direct Telegram document send failed: {direct_err}. Attempting via proxy...")
        
    # Proxy fallback
    proxy_file = ROOT / "proxies.txt"
    if proxy_file.exists():
        try:
            from scripts.check_proxies import parse_proxy_line
            lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            valid_proxies = []
            for line in lines:
                parsed = parse_proxy_line(line)
                if parsed and parsed.get("type") in ("socks5", "http"):
                    valid_proxies.append(parsed)
            
            print(f"Found {len(valid_proxies)} proxies in proxies.txt for retry")
            for p in valid_proxies[:5]:
                try:
                    proxy_url = ""
                    if p["username"] and p["password"]:
                        proxy_url = f"{p['type']}://{p['username']}:{p['password']}@{p['server']}:{p['port']}"
                    else:
                        proxy_url = f"{p['type']}://{p['server']}:{p['port']}"
                        
                    proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
                    opener = urllib.request.build_opener(proxy_handler)
                    
                    req = urllib.request.Request(url, data=body, headers=headers)
                    with opener.open(req, timeout=20) as r:
                        res_data = json.loads(r.read())
                        print(f"Successfully sent Telegram document via proxy: {proxy_url[:40]}")
                        return res_data.get("result", {}).get("message_id")
                except Exception as proxy_err:
                    print(f"Proxy document send failed: {proxy_err}")
        except Exception as e:
            print(f"Failed to run proxy document fallback: {e}")
            
def convert_markdown_tables(text):
    if not text:
        return ""
    lines = text.split("\n")
    new_lines = []
    table_lines = []
    
    def flush_table(t_lines):
        if not t_lines:
            return []
        
        parsed_rows = []
        for line in t_lines:
            stripped = line.strip()
            if stripped.startswith("|"):
                stripped = stripped[1:]
            if stripped.endswith("|"):
                stripped = stripped[:-1]
            parts = [p.strip() for p in stripped.split("|")]
            parsed_rows.append(parts)
            
        if len(parsed_rows) < 2:
            return t_lines
            
        headers = parsed_rows[0]
        sep_row = parsed_rows[1]
        
        is_sep = all(all(c in "-: " for c in cell) for cell in sep_row) if sep_row else False
        if not is_sep:
            return t_lines
            
        data_rows = parsed_rows[2:]
        formatted = []
        for row in data_rows:
            if not any(row):
                continue
                
            idx_str = ""
            col_start = 0
            if len(row) > 0:
                first_cell = row[0].replace("**", "").strip()
                if first_cell.isdigit():
                    idx_str = f"{first_cell}. "
                    col_start = 1
                    
            row_desc = []
            for col_idx in range(col_start + 1, len(headers)):
                if col_idx < len(row):
                    val = row[col_idx].strip()
                    if not val:
                        continue
                    header = headers[col_idx].strip()
                    row_desc.append(f"  • {header}: {val}")
                    
            main_title = row[col_start].strip() if len(row) > col_start else ""
            if main_title or row_desc:
                formatted.append(f"\n{idx_str}{main_title}")
                formatted.extend(row_desc)
                
        return formatted

    for line in lines:
        if "|" in line:
            table_lines.append(line)
        else:
            if table_lines:
                new_lines.extend(flush_table(table_lines))
                table_lines = []
            new_lines.append(line)
            
    if table_lines:
        new_lines.extend(flush_table(table_lines))
        
    return "\n".join(new_lines)

def clean_markdown_for_telegram(text):
    if not text:
        return ""
    
    # 1. Convert markdown tables to clean indented lists
    text = convert_markdown_tables(text)
    
    # 2. Escape the text to be HTML safe first
    import html
    escaped = html.escape(text)
    
    # 3. Process code blocks: ```[lang]\n(code)\n```
    import re
    escaped = re.sub(r'```[a-zA-Z0-9_-]*\n?(.*?)\n?```', r'<pre><code>\1</code></pre>', escaped, flags=re.DOTALL)
    
    # 4. Process inline code: `code`
    escaped = re.sub(r'`(.*?)`', r'<code>\1</code>', escaped)
    
    # 5. Process bold: **text**
    escaped = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped)
    
    # 6. Process italic: *text* and __text__ and _text_
    escaped = re.sub(r'\*(.*?)\*', r'<i>\1</i>', escaped)
    escaped = re.sub(r'__(.*?)__', r'<i>\1</i>', escaped)
    escaped = re.sub(r'\b_(.*?)_\b', r'<i>\1</i>', escaped)
    
    # 6.5. Process links: [text](url) -> <a href="url">text</a>
    escaped = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', escaped)
    
    # 7. Process headers line-by-line (e.g. ### Header)
    lines = escaped.split("\n")
    cleaned_lines = []
    for line in lines:
        if re.match(r'^#+\s+', line):
            header_content = re.sub(r'^#+\s+', '', line)
            header_content = re.sub(r'^<b>(.*?)</b>$', r'\1', header_content)
            line = f"<b>{header_content}</b>"
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines)

def send_telegram_reply(message_id, reply_text):
    token = os.environ.get("TG_BOT_TOKEN")
    channel_id = -1004378273791
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": reply_text,
        "parse_mode": "HTML"
    }
    if message_id:
        payload["reply_to_message_id"] = message_id
    
    # Try direct send first
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            res_data = json.loads(r.read())
            return res_data.get("result", {}).get("message_id")
    except Exception as direct_err:
        print(f"Direct Telegram send failed: {direct_err}. Attempting via proxy...")
        
    # Proxy fallback: parse proxies.txt and try them
    proxy_file = ROOT / "proxies.txt"
    if proxy_file.exists():
        try:
            from scripts.check_proxies import parse_proxy_line
            lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            valid_proxies = []
            for line in lines:
                parsed = parse_proxy_line(line)
                if parsed and parsed.get("type") in ("socks5", "http"):
                    valid_proxies.append(parsed)
            
            print(f"Found {len(valid_proxies)} proxies in proxies.txt for retry")
            
            # Try first 5 proxies
            for p in valid_proxies[:5]:
                try:
                    # urllib imported globally
                    # Create opener with proxy
                    proxy_url = ""
                    if p["username"] and p["password"]:
                        proxy_url = f"{p['type']}://{p['username']}:{p['password']}@{p['server']}:{p['port']}"
                    else:
                        proxy_url = f"{p['type']}://{p['server']}:{p['port']}"
                        
                    proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
                    opener = urllib.request.build_opener(proxy_handler)
                    
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with opener.open(req, timeout=8) as r:
                        res_data = json.loads(r.read())
                        print(f"Successfully sent Telegram reply via proxy: {proxy_url[:40]}")
                        return res_data.get("result", {}).get("message_id")
                except Exception as proxy_err:
                    print(f"Proxy send failed: {proxy_err}")
        except Exception as e:
            print(f"Failed to run proxy fallback: {e}")
            
    return None

def delete_telegram_message(message_id):
    if not message_id:
        return False
    token = os.environ.get("TG_BOT_TOKEN")
    channel_id = -1004378273791
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/deleteMessage"
    payload = {
        "chat_id": channel_id,
        "message_id": message_id
    }
    
    # Try direct first
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return True
    except Exception as direct_err:
        print(f"Direct Telegram delete failed: {direct_err}. Attempting via proxy...")
        
    # Proxy fallback
    proxy_file = ROOT / "proxies.txt"
    if proxy_file.exists():
        try:
            from scripts.check_proxies import parse_proxy_line
            lines = proxy_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            valid_proxies = []
            for line in lines:
                parsed = parse_proxy_line(line)
                if parsed and parsed.get("type") in ("socks5", "http"):
                    valid_proxies.append(parsed)
            
            for p in valid_proxies[:5]:
                try:
                    proxy_url = ""
                    if p["username"] and p["password"]:
                        proxy_url = f"{p['type']}://{p['username']}:{p['password']}@{p['server']}:{p['port']}"
                    else:
                        proxy_url = f"{p['type']}://{p['server']}:{p['port']}"
                        
                    proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
                    opener = urllib.request.build_opener(proxy_handler)
                    
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with opener.open(req, timeout=8) as r:
                        print(f"Successfully deleted Telegram message via proxy: {proxy_url[:40]}")
                        return True
                except Exception as proxy_err:
                    pass
        except Exception:
            pass
    return False

def run_proactive_checks_loop():
    import threading
    import json
    import subprocess
    import sys

    def trigger_auto_healer(source, traceback_content):
        error_data = {
            "source": source,
            "error_type": "AutonomousLocalLogCrash",
            "error_message": f"Detected traceback in local {source} logs.",
            "traceback": traceback_content
        }
        error_file = ROOT / "critical_error.json"
        try:
            error_file.write_text(json.dumps(error_data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Written local critical_error.json for {source}. Launching autonomous healer...")
            
            # Notify via Telegram that healing has started
            start_text = (
                f"🛠 <b>[Автономный ремонт локально]</b>\n"
                f"В логах <code>{source}</code> обнаружен сбой. Запускаю авто-исправление..."
            )
            send_telegram_reply(None, start_text)
            
            # Run cloud_healer.py process
            healer_script = ROOT / "scripts" / "cloud_healer.py"
            result = subprocess.run(
                [sys.executable, str(healer_script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=str(ROOT)
            )
            print("Healer Output:", result.stdout)
            if result.stderr:
                print("Healer Error:", result.stderr)
        except Exception as ex:
            print(f"Failed to trigger auto-healer: {ex}")
    
    def check_worker():
        print("🤖 Proactive checks loop started in background thread...")
        state_file = ROOT / "scratch" / "proactive_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        last_positions = {}
        if state_file.exists():
            try:
                last_positions = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
                
        while True:
            try:
                # 1. Check bot.log for errors
                bot_log = ROOT / "bot.log"
                if bot_log.exists():
                    curr_pos = last_positions.get("bot_log", 0)
                    size = bot_log.stat().st_size
                    if size < curr_pos:
                        curr_pos = 0 # log rotated
                        
                    if size > curr_pos:
                        with open(bot_log, "r", encoding="utf-8", errors="ignore") as f:
                            f.seek(curr_pos)
                            new_content = f.read()
                            
                        # Search for errors or tracebacks
                        if "ERROR" in new_content or "CRITICAL" in new_content or "Traceback" in new_content:
                            print(f"Proactive Alert: found errors in bot.log. Triggering auto-healer.")
                            trigger_auto_healer("telegram_bot_handler", new_content)
                            
                        last_positions["bot_log"] = size
                        
                # 2. Check orchestrator_run.log for errors
                orch_log = ROOT / "orchestrator_run.log"
                if orch_log.exists():
                    curr_pos = last_positions.get("orch_log", 0)
                    size = orch_log.stat().st_size
                    if size < curr_pos:
                        curr_pos = 0
                        
                    if size > curr_pos:
                        with open(orch_log, "r", encoding="utf-8", errors="ignore") as f:
                            f.seek(curr_pos)
                            new_content = f.read()
                            
                        if "ERROR" in new_content or "Traceback" in new_content:
                            print(f"Proactive Alert: found errors in orchestrator_run.log. Triggering auto-healer.")
                            trigger_auto_healer("orchestrator", new_content)
                            
                        last_positions["orch_log"] = size
                        
                # Save state
                state_file.write_text(json.dumps(last_positions), encoding="utf-8")
                
            except Exception as e:
                print(f"Error in proactive check iteration: {e}")
                
            # Check every 10 minutes (600 seconds)
            time.sleep(600)
            
    t = threading.Thread(target=check_worker, daemon=True)
    t.start()

def run_loop():
    print("🤖 Antigravity Task Listener is active and scanning for tasks...")
    # Start proactive checks loop in background
    try:
        run_proactive_checks_loop()
    except Exception as pe:
        print(f"Failed to start proactive checks: {pe}")
    
    while True:
        try:
            # Sync via git pull at the start of the loop
            git_pull()
            
            tasks = gh_read_tasks()
            updated = False
            
            for task in tasks:
                if task.get("status") == "pending":
                    print(f"Found new pending task #{task['id']}")
                    
                    # Always delegate tasks to VSCode Agent as requested by user
                    print(f"Task #{task['id']} delegated to VSCode...")
                    task["status"] = "pending_vscode"
                    updated = True
                    continue
                    
                    # Update status to running locally
                    task["status"] = "running"
                    
                    # Get thread history context
                    history = build_history_context(task, tasks)
                    if history:
                        print(f"Loaded context history with {len(history)} messages")
                    
                    # Execute task
                    result = execute_ai_task(task["text"], history)
                    
                    # Send response back to Telegram channel
                    escaped_result = clean_markdown_for_telegram(result)
                    reply_msg_id = send_telegram_reply(task["message_id"], escaped_result)
                    if reply_msg_id:
                        task["reply_message_id"] = reply_msg_id
                    
                    # Delete the status message 'Ок' if present
                    status_msg_id = task.get("status_message_id")
                    if status_msg_id:
                        print(f"Deleting status message {status_msg_id}...")
                        delete_telegram_message(status_msg_id)
                    
                    # Save completed task to semantic memory
                    try:
                        from scripts.jarvis_memory import add_memory
                        memory_text = f"Пользователь спросил: {task['text']}\nОтвет ИИ-агента (ты): {result}"
                        add_memory(memory_text, {"task_id": task["id"], "type": "task_completed"})
                        print(f"Task #{task['id']} successfully recorded to semantic memory.")
                    except Exception as me:
                        print(f"Failed to save task to semantic memory: {me}")
                    
                    # Update task state to completed
                    task["status"] = "completed"
                    task["result"] = result
                    task["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    updated = True
            
            if updated:
                gh_write_tasks(tasks, message="task: completed execution")
                
        except Exception as e:
            print(f"Error in task listener loop: {e}")
            
        # Poll interval: 5 seconds
        time.sleep(5)

if __name__ == "__main__":
    run_loop()
