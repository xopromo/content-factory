import pathlib

p = pathlib.Path("scripts/task_listener.py")
content = p.read_text(encoding="utf-8", errors="ignore")

# Find the start of execute_ai_task
start_pos = content.find("def execute_ai_task")
if start_pos == -1:
    print("Could not find execute_ai_task start position.")
    exit(1)

# Find the start of send_telegram_reply
end_pos = content.find("def send_telegram_reply")
if end_pos == -1:
    print("Could not find send_telegram_reply start position.")
    exit(1)

# Also fix the urllib scope bug in send_telegram_reply which starts at end_pos
send_reply_code = content[end_pos:]
send_reply_code = send_reply_code.replace("                    import urllib.request", "                    # urllib imported globally")

header = "# -*- coding: utf-8 -*-\n" + content[:start_pos]

rest_code = """
def is_agent_command(text):
    text_lower = text.lower()
    keywords = ["/agent", "агент", "agent", "напиши код", "создай файл", "выполни команду", "запусти скрипт", "/run"]
    return any(kw in text_lower for kw in keywords)

def run_agent_loop(task_text, history=None):
    import subprocess
    import json
    import re
    from pathlib import Path

    print(f"🤖 Entering agent loop for task: {task_text}")
    
    # Context of files
    claude_path = ROOT / "CLAUDE.md"
    project_state_path = ROOT / "PROJECT_STATE.md"
    
    claude_md = claude_path.read_text(encoding="utf-8", errors="ignore") if claude_path.exists() else ""
    project_state_md = project_state_path.read_text(encoding="utf-8", errors="ignore") if project_state_path.exists() else ""
    
    context = (
        f"=== CLAUDE.md ===\\n{claude_md[:4000]}\\n\\n"
        f"=== PROJECT_STATE.md ===\\n{project_state_md[:4000]}\\n\\n"
    )
    
    agent_history = []
    
    # We will loop up to 8 iterations
    for step in range(8):
        print(f"--- Step {step + 1} of 8 ---", flush=True)
        prompt = (
            "Ты — автономный ИИ-агент разработчик Antigravity. Ты запущен локально на ПК пользователя.\\n"
            "Твоя задача — выполнить поручение пользователя в текущей рабочей директории.\\n"
            "Доступные инструменты (вызывай их, выводя строго одну JSON-структуру в формате {\\\"tool\\\": \\\"...\\\"}):\\n"
            "1. Прочитать файл: {\\\"tool\\\": \\\"read_file\\\", \\\"path\\\": \\\"relative/path/to/file\\\"}\\n"
            "2. Записать/создать файл: {\\\"tool\\\": \\\"write_file\\\", \\\"path\\\": \\\"relative/path/to/file\\\", \\\"content\\\": \\\"содержимое\\\"}\\n"
            "3. Посмотреть список файлов в папке: {\\\"tool\\\": \\\"list_dir\\\", \\\"path\\\": \\\"relative/path\\\"}\\n"
            "4. Запустить терминальную команду (powershell): {\\\"tool\\\": \\\"run_command\\\", \\\"command\\\": \\\"команда\\\"}\\n"
            "5. Завершить выполнение и выдать финальный ответ: {\\\"tool\\\": \\\"final_answer\\\", \\\"answer\\\": \\\"твое сообщение\\\"}\\n\\n"
            "Правила вызова инструментов:\\n"
            "- Выводи ровно один JSON-вызов инструмента в конце своего ответа.\\n"
            "- Если задача полностью выполнена, обязательно вызови tool 'final_answer'.\\n\\n"
            "История текущих размышлений и шагов:\\n"
        )
        
        history_text = ""
        for h in agent_history:
            history_text += f"Шаг: {h['step']}\\nМысли/Действие: {h['thought']}\\nРезультат инструмента: {h['result']}\\n\\n"
            
        full_query = context + prompt + history_text + f"Текущая цель: {task_text}\\nТвои мысли и следующий шаг (JSON):"
        
        # Call LLM
        response, _ = run_fast_common(full_query, quality="strong")
        print(f"Step {step + 1} thoughts:\\n{response}", flush=True)
        
        # Try parsing JSON: find first '{' and last '}'
        start_idx = response.find('{')
        end_idx = response.rfind('}')
        if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
            print(f"Step {step + 1} result: No JSON brackets found, treating as final answer.", flush=True)
            return response
            
        json_str = response[start_idx:end_idx + 1]
        try:
            tool_call = json.loads(json_str)
        except Exception as je:
            err_msg = f"Ошибка парсинга JSON: {je} (извлеченная строка: {json_str!r})"
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
                    result = f"Stdout: {res.stdout}\\nStderr: {res.stderr}"
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
        "\\n--- ТЕКУЩИЙ КОНТЕКСТ ПРОЕКТОВ (ДЛЯ СПРАВКИ) ---\\n"
        f"CLAUDE.md:\\n{claude_md[:2000]}\\n\\n"
        f"PROJECT_STATE.md:\\n{project_state_md[:2000]}\\n"
        "-----------------------------------------------\\n"
    )
    
    system_prompt = (
        "Ты Antigravity — умный ИИ-собеседник и разработчик.\\n"
        f"Тебе доступен текущий контекст проектов на ПК пользователя:\\n{project_context}\\n"
        "Правила ведения диалога:\\n"
        "1. Отвечай кратко, естественно и лаконично (максимум 1-3 предложения), как реальный собеседник в чате.\\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО пересказывать историю диалога или писать мета-комментарии о ходе игры.\\n"
        "3. Если идет игра в 20 вопросов, просто отреагируй на последний ответ и сразу задай следующий вопрос.\\n"
        "4. Для выполнения сложных команд по программированию или изменения файлов используй префикс 'агент' или '/agent' в запросе."
    )
    
    # Build prompt with history context
    full_prompt = f"{system_prompt}\\n\\n"
    if history:
        full_prompt += "История предыдущей беседы (контекст):\\n"
        for h in history:
            full_prompt += f"Пользователь: {h['text']}\\n"
            if h.get("result"):
                clean_result = clean_history_result(h["result"])
                if clean_result:
                    full_prompt += f"ИИ-агент (ты): {clean_result}\\n"
        full_prompt += f"\\nТекущее сообщение от пользователя: {task_text}\\n\\n"
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
"""

p.write_text(header + rest_code + send_reply_code, encoding="utf-8")
print("Successfully wrote updated task_listener.py with correct encoding!")
