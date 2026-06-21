#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path
import traceback

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from scripts.telegram_notifier import send as tg_send

def call_gemini(prompt: str) -> str:
    api_key = os.getenv("GEMINI_KEY")
    if not api_key:
        raise ValueError("GEMINI_KEY не задан в переменных окружения")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.95,
            "maxOutputTokens": 8192
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        
    try:
        text = res["candidates"][0]["content"]["parts"][0]["text"]
        return text
    except (KeyError, IndexError) as e:
        raise ValueError(f"Некорректный ответ от API Gemini: {res}") from e

def call_groq(prompt: str) -> str:
    api_key = os.getenv("GROQ_KEY")
    if not api_key:
        raise ValueError("GROQ_KEY не задан в переменных окружения")
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 8192
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        
    try:
        text = res["choices"][0]["message"]["content"]
        return text
    except (KeyError, IndexError) as e:
        raise ValueError(f"Некорректный ответ от API Groq: {res}") from e

def call_openrouter(prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_KEY не задан в переменных окружения")
        
    errors = []
    for model in ["meta-llama/llama-3.3-70b-instruct:free", "openrouter/free"]:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 8192
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://github.com/xopromo/content-factory",
                    "X-Title": "Content Factory"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            return res["choices"][0]["message"]["content"]
        except Exception as e:
            errors.append(f"{model} failed: {e}")
            
    raise ValueError(f"OpenRouter failed with all models: {'; '.join(errors)}")

def call_llm(prompt: str) -> str:
    errors = []
    
    # 1. Пробуем Gemini
    try:
        print("Обращение к API Gemini...")
        return call_gemini(prompt)
    except Exception as e:
        err_msg = f"Gemini Error: {e}"
        print(err_msg)
        errors.append(err_msg)
        
    # 2. Пробуем Groq
    try:
        print("Обращение к API Groq...")
        return call_groq(prompt)
    except Exception as e:
        err_msg = f"Groq Error: {e}"
        print(err_msg)
        errors.append(err_msg)

    # 3. Пробуем OpenRouter
    try:
        print("Обращение к API OpenRouter...")
        return call_openrouter(prompt)
    except Exception as e:
        err_msg = f"OpenRouter Error: {e}"
        print(err_msg)
        errors.append(err_msg)
        
    raise ValueError(f"Все провайдеры LLM вернули ошибку: {'; '.join(errors)}")

def extract_code(llm_response: str) -> str:
    # Ищем код внутри ```python и ``` или ```
    lines = llm_response.splitlines()
    code_lines = []
    in_code = False
    
    for line in lines:
        if line.strip().startswith("```python") or line.strip().startswith("```py"):
            in_code = True
            continue
        elif line.strip().startswith("```") and in_code:
            in_code = False
            continue
            
        if in_code:
            code_lines.append(line)
            
    if not code_lines:
        # Если блок не найден, возвращаем исходный текст (возможно, модель вернула чистый код)
        return llm_response.strip()
        
    return "\n".join(code_lines)

def test_syntax(file_path: Path, code: str) -> tuple[bool, str]:
    # Записываем код во временный файл и проверяем синтаксис
    temp_file = file_path.with_suffix(".py.tmp")
    try:
        temp_file.write_text(code, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(temp_file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if result.returncode == 0:
            return True, ""
        else:
            return False, result.stderr
    finally:
        if temp_file.exists():
            temp_file.unlink()

def main() -> None:
    error_file = ROOT / "critical_error.json"
    if not error_file.exists():
        print("Файл critical_error.json не найден. Выход.")
        sys.exit(0)
        
    try:
        error_data = json.loads(error_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Ошибка чтения critical_error.json: {e}")
        tg_send(f"⚠️ <b>Облачный автохилер:</b> Не удалось прочитать critical_error.json.\n<code>{e}</code>")
        sys.exit(1)
        
    source = error_data.get("source", "unknown")
    error_type = error_data.get("error_type", "UnknownError")
    error_message = error_data.get("error_message", "")
    tb = error_data.get("traceback", "")
    
    print(f"Сбой обнаружен! Источник: {source}, Тип: {error_type}")
    
    # 1. Определяем файл для исправления
    target_file = None
    if source in ("telegram_bot_handler", "telegram_bot_startup"):
        target_file = ROOT / "scripts" / "voice_bot.py"
    elif source in ("github_actions_chelyabinsk", "github_actions_traffic"):
        target_file = ROOT / "researcher.py"
    elif source == "orchestrator":
        target_file = ROOT / "scripts" / "orchestrator.py"
        
    # Если в traceback есть файл в кавычках, попробуем проверить его существование
    # (полезно, если ошибка произошла в другом модуле)
    import re
    files_in_tb = re.findall(r'File "([^"]+\.py)"', tb)
    if files_in_tb:
        # Проверяем файлы по порядку, ищем локальные файлы проекта
        for f in files_in_tb:
            local_path = ROOT / f
            if local_path.exists():
                target_file = local_path
                break
                
    if not target_file or not target_file.exists():
        msg = f"❌ <b>Облачный автохилер:</b> Не удалось определить файл исходного кода для исправления. Источник: {source}"
        print(msg)
        tg_send(msg)
        # Удаляем файл ошибки, чтобы не зацикливаться
        error_file.unlink()
        subprocess.run(["git", "rm", "critical_error.json"], cwd=ROOT)
        subprocess.run(["git", "commit", "-m", "fail: remove unresolvable critical_error.json"], cwd=ROOT)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT)
        sys.exit(1)
        
    print(f"Файл для исправления: {target_file}")
    
    # Читаем исходный код
    source_code = target_file.read_text(encoding="utf-8")
    
    # 2. Формируем промпт
    prompt = f"""Ты — автономный робот-отладчик. Твоя задача — исправить критический сбой в коде проекта.
Файл, в котором произошла ошибка: {target_file.name}

Лог ошибки (Traceback):
```
{tb}
```

Исходный код файла {target_file.name}:
```python
{source_code}
```

Пожалуйста:
1. Тщательно проанализируй причину ошибки (traceback).
2. Найди проблемное место в коде и исправь его. Сделай код устойчивым к подобным сбоям (например, добавь безопасные проверки, оберни в try-except или добавь обработку пустых значений/сетевых ошибок).
3. Верни ИСПРАВЛЕННЫЙ КОД ФАЙЛА ПОЛНОСТЬЮ.
4. Ответ должен содержать ТОЛЬКО полный текст исправленного файла внутри markdown-блока ```python ... ```. Никаких дополнительных объяснений, комментариев вне кода или вводных слов быть не должно!
"""

    attempts = 3
    success = False
    compilation_error = ""
    current_code = None
    
    for attempt in range(1, attempts + 1):
        print(f"Попытка исправления {attempt}/{attempts}...")
        try:
            if current_code and compilation_error:
                # Если это повторная попытка, дополняем промпт ошибкой компилятора
                prompt = f"""Ты исправил код, но компилятор выдал ошибку:
```
{compilation_error}
```

Вот предложенный тобой код:
```python
{current_code}
```

Пожалуйста, исправь эту синтаксическую ошибку и верни ИСПРАВЛЕННЫЙ КОД ФАЙЛА ПОЛНОСТЬЮ внутри markdown-блока ```python ... ```. Без объяснений!"""

            llm_resp = call_llm(prompt)
            current_code = extract_code(llm_resp)
            
            # Проверяем синтаксис
            is_ok, err = test_syntax(target_file, current_code)
            if is_ok:
                success = True
                break
            else:
                compilation_error = err
                print(f"Синтаксическая ошибка в коде: {err}")
        except Exception as err_api:
            compilation_error = str(err_api)
            print(f"Ошибка обращения к API моделей: {err_api}")
            
    if success and current_code:
        # Сохраняем исправленный код
        target_file.write_text(current_code, encoding="utf-8")
        print(f"Код успешно исправлен в {target_file.name}")
        
        # Удаляем файл ошибки
        error_file.unlink()
        
        # Делаем коммит и пуш
        try:
            # Настраиваем гита пользователя
            subprocess.run(["git", "config", "--global", "user.email", "auto-healer@content-factory.local"], cwd=ROOT)
            subprocess.run(["git", "config", "--global", "user.name", "Cloud Auto Healer Agent"], cwd=ROOT)
            
            subprocess.run(["git", "add", str(target_file)], cwd=ROOT)
            subprocess.run(["git", "rm", "critical_error.json"], cwd=ROOT)
            subprocess.run(["git", "commit", "-m", f"fix: auto-healed {error_type} in {target_file.name}"], cwd=ROOT)
            
            # Пушим в main
            token = os.getenv("GITHUB_TOKEN")
            repo = os.getenv("GITHUB_REPO", "xopromo/content-factory")
            branch = os.getenv("GITHUB_BRANCH", "main")
            auth_url = f"https://x-access-token:{token}@github.com/{repo}.git"
            subprocess.run(["git", "remote", "set-url", "origin", auth_url], cwd=ROOT)
            subprocess.run(["git", "push", "origin", branch], cwd=ROOT)
            
            msg = (
                f"🎉 <b>Облачный автохилер:</b> Ошибка успешно исправлена!\n\n"
                f"• <b>Файл:</b> <code>{target_file.name}</code>\n"
                f"• <b>Ошибка:</b> <code>{error_type}</code>\n"
                f"• <b>Детали:</b> {error_message[:200]}\n\n"
                f"Изменения запушены в ветку <code>{branch}</code>. Сервер автоматически перезапускается с новым кодом!"
            )
            print(msg)
            tg_send(msg)
        except Exception as git_err:
            msg = f"⚠️ <b>Облачный автохилер:</b> Код исправлен локально, но произошла ошибка при пуше в Git: <code>{git_err}</code>"
            print(msg)
            tg_send(msg)
    else:
        # Не удалось исправить
        print("Автохилер не смог исправить ошибку за 3 попытки.")
        # Удаляем файл сбоя, чтобы не зацикливаться
        if error_file.exists():
            error_file.unlink()
            
        try:
            subprocess.run(["git", "config", "--global", "user.email", "auto-healer@content-factory.local"], cwd=ROOT)
            subprocess.run(["git", "config", "--global", "user.name", "Cloud Auto Healer Agent"], cwd=ROOT)
            subprocess.run(["git", "rm", "critical_error.json"], cwd=ROOT)
            subprocess.run(["git", "commit", "-m", f"fail: auto-healer could not resolve {error_type} in {target_file.name}"], cwd=ROOT)
            
            token = os.getenv("GITHUB_TOKEN")
            repo = os.getenv("GITHUB_REPO", "xopromo/content-factory")
            branch = os.getenv("GITHUB_BRANCH", "main")
            auth_url = f"https://x-access-token:{token}@github.com/{repo}.git"
            subprocess.run(["git", "remote", "set-url", "origin", auth_url], cwd=ROOT)
            subprocess.run(["git", "push", "origin", branch], cwd=ROOT)
            
            msg = (
                f"❌ <b>Облачный автохилер СДАЛСЯ:</b> Не удалось исправить ошибку за 3 попытки.\n\n"
                f"• <b>Файл:</b> <code>{target_file.name}</code>\n"
                f"• <b>Ошибка:</b> <code>{error_type}</code>\n"
                f"• <b>Трейсбэк ошибки:</b>\n<pre>{tb[:500]}</pre>\n\n"
                f"⚠️ <b>Внимание:</b> Требуется ручное исправление! Пожалуйста, запустите Antigravity локально."
            )
            tg_send(msg)
        except Exception as git_err:
            print(f"Ошибка Git при фиксации сдачи автохилера: {git_err}")

if __name__ == "__main__":
    main()
