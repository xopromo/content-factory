#!/usr/bin/env python3
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple

# Загрузка переменных окружения для локальной разработки
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

# Инициализация провайдеров
# 1. Groq
try:
    from groq import Groq as _Groq
    _groq_client = _Groq(api_key=os.environ.get("GROQ_KEY", "")) if os.environ.get("GROQ_KEY") else None
    _groq_client2 = _Groq(api_key=os.environ.get("GROQ_KEY_2", "")) if os.environ.get("GROQ_KEY_2") else None
except ImportError:
    _groq_client = None
    _groq_client2 = None

# 2. Gemini (google-genai)
try:
    from google import genai as _genai
    _gemini_key = os.environ.get("GEMINI_KEY", "")
    _gemini_client = _genai.Client(api_key=_gemini_key) if _gemini_key else None
except ImportError:
    _gemini_client = None

# 3. Mistral
try:
    from mistralai import Mistral as _Mistral
    _mistral_key = os.environ.get("MISTRAL_KEY", "")
    _mistral_client = _Mistral(api_key=_mistral_key) if _mistral_key else None
except ImportError:
    _mistral_client = None

# 4. Cerebras
try:
    from cerebras.cloud.sdk import Cerebras as _Cerebras
    _cerebras_key = os.environ.get("CEREBRAS_KEY", "")
    _cerebras_client = _Cerebras(api_key=_cerebras_key) if _cerebras_key else None
except ImportError:
    _cerebras_client = None

# 5. OpenRouter / OpenAI
try:
    from openai import OpenAI as _OpenAI
    _openrouter_key = os.environ.get("OPENROUTER_KEY", "")
    _openrouter_client = _OpenAI(
        api_key=_openrouter_key,
        base_url="https://openrouter.ai/api/v1",
    ) if _openrouter_key else None
except ImportError:
    _openrouter_client = None

_groq_cooldown_until = 0.0


# Получение доступных клиентов Groq с ротацией
def get_groq_clients() -> List:
    clients = []
    if _groq_client:
        clients.append(_groq_client)
    if _groq_client2:
        clients.append(_groq_client2)
    return clients


# Вспомогательная функция для авто-бэкоффа при ошибке 429
def call_groq_with_retry(client, model: str, messages: List[Dict], max_tokens: int = 1024, temperature: float = 0.7) -> str:
    global _groq_cooldown_until
    retries = 3
    base_delay = 3.0
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            # Проверяем на Rate Limit (обычно код 429 или в тексте ошибки)
            is_rate_limit = "429" in str(e) or "rate limit" in str(e).lower() or "limit exceeded" in str(e).lower()
            if is_rate_limit:
                _groq_cooldown_until = time.time() + 60.0  # Устанавливаем кулдаун на 60 секунд при ошибке лимита
                print(f"  [LLM CLIENT] Groq rate limit hit. Groq set on cooldown for 60s.")
                if attempt < retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"  [LLM CLIENT] Retrying in {delay}s... (Attempt {attempt+1}/{retries})")
                    time.sleep(delay)
                else:
                    raise e
            else:
                raise e
    raise RuntimeError("Failed after retries")


# Логика Mock-ответов для локального тестирования
def get_mock_response(prompt: str, is_fast: bool = False) -> str:
    prompt_lower = prompt.lower()
    if is_fast:
        if "оцени поисковый запрос" in prompt_lower:
            return "PASSED\nЗапрос достаточно специфичен."
        if "сравни структуру и заголовки" in prompt_lower or "heading reduction" in prompt_lower:
            return "PASSED\nВсе заголовки соответствуют правилам."
        if "проверь текст на наличие галлюцинаций" in prompt_lower:
            return "HEALTHY\nГаллюцинаций не обнаружено."
        if "извлеки все проверяемые утверждения" in prompt_lower:
            return "[]"
        if "entity-validator" in prompt_lower or "бренды" in prompt_lower:
            return "[]"
        if "temporality" in prompt_lower or "временные несоответствия" in prompt_lower:
            return "TEMPORAL_OK\nВременных ошибок нет."
        return "PASSED"
    else:
        # Тяжелые задачи
        if "напиши статью" in prompt_lower or "content-writer" in prompt_lower or "копирайтер-смысловик" in prompt_lower or "черновик статьи" in prompt_lower:
            return "# Тестовая статья (MOCK)\n\nЭто тестовый текст статьи, сгенерированный в Mock-режиме для экономии токенов. Он должен быть достаточно длинным (более 200 символов), чтобы успешно пройти валидацию длины черновика на шаге проверки контента в оркестраторе."
        if "выдели 3-5 ключевых углов" in prompt_lower:
            return "1. Первый угол\n2. Второй угол\n3. Третий угол"
        return "Mock Response: Успешная тестовая генерация."


def run_gemini_rest(prompt: str) -> str:
    gemini_key = os.getenv("GEMINI_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_KEY is not set")
    import urllib.request
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    return res["candidates"][0]["content"]["parts"][0]["text"].strip()


def run_claude_common(prompt: str, context: str = "", inject_feedback: bool = False) -> Tuple[str, int]:
    """
    Вызывает LLM для тяжелых задач (написание текстов, глубокий синтез).
    Использует Gemini 2.0 Flash ➔ Llama 3.3 70B ➔ Llama 3.1 8B ➔ Mistral ➔ claude CLI.
    """
    if os.getenv("MOCK_LLM") == "1":
        return get_mock_response(prompt, is_fast=False), 100

    parts = []
    # Для совместимости с оркестратором
    if inject_feedback:
        # Пытаемся импортировать из оркестратора (избегая циклического импорта)
        try:
            from scripts.orchestrator import aggregate_feedback
            parts.append(aggregate_feedback())
        except ImportError:
            pass
    if context:
        parts.append(context)
    parts.append(prompt)
    
    full_prompt = "\n\n".join(p for p in parts if p.strip())
    tokens = len(full_prompt.split()) * 2
    errors = []

    # 1. Gemini (как основной бесплатный провайдер с 1M контекстом)
    gemini_key = os.getenv("GEMINI_KEY")
    gemini_success = False
    gemini_response = None
    
    if _gemini_client or gemini_key:
        import time as _time
        for attempt in range(3):
            try:
                if _gemini_client:
                    resp = _gemini_client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=full_prompt,
                    )
                    gemini_response = resp.text.strip()
                    gemini_success = True
                    break
                else:
                    gemini_response = run_gemini_rest(full_prompt)
                    gemini_success = True
                    break
            except Exception as e:
                err_str = str(e)
                err_msg = f"Gemini Error (Attempt {attempt+1}/3): {e}"
                print(f"  [LLM CLIENT WARNING] {err_msg}")
                errors.append(err_msg)
                
                # Если перегружено или превышен лимит запросов в минуту (429/ResourceExhausted), ждем и пробуем снова
                if "429" in err_str or "ResourceExhausted" in err_str or "rate limit" in err_str.lower():
                    sleep_time = 2 * (attempt + 1)
                    print(f"  [LLM CLIENT] Gemini rate limited (429). Retrying in {sleep_time}s...")
                    _time.sleep(sleep_time)
                else:
                    break
                    
        if gemini_success:
            return gemini_response, tokens

    # 2. Groq (Llama 3.3 70B с ротацией и авто-бэкоффом)
    groq_clients = get_groq_clients()
    if groq_clients:
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            if time.time() < _groq_cooldown_until:
                print(f"  [LLM CLIENT SKIP] Пропускаю Groq ({model}): Groq временно на кулдауне")
                errors.append(f"Groq Skip ({model}): Groq is on cooldown")
                continue
            # Проверяем, влезает ли промпт в лимит TPM модели
            model_tpm = 6000 if "8b" in model else 12000
            # Если промпт слишком велик (оставляет меньше 1024 токенов на ответ), пропускаем модель
            if tokens >= model_tpm - 1024:
                print(f"  [LLM CLIENT SKIP] Пропускаю Groq ({model}): размер промпта {tokens} слишком велик для TPM {model_tpm}")
                errors.append(f"Groq Skip ({model}): prompt size {tokens} exceeds model TPM limit {model_tpm}")
                continue
                
            for idx, gq in enumerate(groq_clients):
                try:
                    # Вычисляем безопасный max_tokens для провайдеров с низким TPM лимитом (Groq)
                    safe_max = max(1024, model_tpm - tokens - 500)
                    # Физический лимит длины генерации для стабильности
                    limit = 3000 if "70b" in model else 1024
                    current_max = min(limit, safe_max)

                    content = call_groq_with_retry(
                        client=gq,
                        model=model,
                        messages=[{"role": "user", "content": full_prompt}],
                        max_tokens=current_max,
                        temperature=0.7
                    )
                    return content, tokens
                except Exception as e:
                    err_msg = f"Groq Error ({model} - Токен #{idx+1}): {e}"
                    print(f"  [LLM CLIENT WARNING] {err_msg}")
                    errors.append(err_msg)

    # 3. Mistral API
    if _mistral_client:
        try:
            resp = _mistral_client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "user", "content": full_prompt}],
            )
            return resp.choices[0].message.content.strip(), tokens
        except Exception as e:
            err_msg = f"Mistral Error: {e}"
            print(f"  [LLM CLIENT WARNING] {err_msg}")
            errors.append(err_msg)

    # 4. Fallback: claude CLI
    try:
        import subprocess
        import tempfile
        tmp_dir = tempfile.gettempdir()
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=tmp_dir,
        )
        if result.returncode == 0:
            return result.stdout.strip(), tokens
    except Exception as e:
        errors.append(f"Claude CLI Error: {e}")

    detailed_errors = "\n".join(f"- {err}" for err in errors)
    raise RuntimeError(
        f"Не удалось выполнить тяжелый запрос к LLM. Все провайдеры вернули ошибку:\n{detailed_errors}"
    )


def run_fast_common(prompt: str, quality: str = "strong") -> Tuple[str, int]:
    """
    Быстрый вызов LLM для технических проверок и вспомогательных задач.
    Качество 'strong': Groq 70B ➔ Gemini ➔ Groq 8B
    Качество 'simple': Groq 8B ➔ Gemini ➔ Groq 70B
    """
    if os.getenv("MOCK_LLM") == "1":
        return get_mock_response(prompt, is_fast=True), 10

    tokens = len(prompt.split()) * 2
    errors = []
    groq_clients = get_groq_clients()

    def try_groq(model_name: str) -> str:
        if not groq_clients:
            raise ValueError("No Groq clients available")
        for idx, gq in enumerate(groq_clients):
            try:
                return call_groq_with_retry(
                    client=gq,
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                    temperature=0.2
                )
            except Exception as e:
                err_msg = f"Groq Fast Error ({model_name} - Токен #{idx+1}): {e}"
                errors.append(err_msg)
                print(f"  [LLM CLIENT WARNING] {err_msg}")
        raise RuntimeError(f"All Groq clients failed for model {model_name}")

    def try_gemini() -> str:
        gemini_key = os.getenv("GEMINI_KEY")
        if _gemini_client:
            try:
                resp = _gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                )
                return resp.text.strip()
            except Exception as e:
                err_msg = f"Gemini Fast Error: {e}"
                errors.append(err_msg)
                print(f"  [LLM CLIENT WARNING] {err_msg}")
                raise RuntimeError(err_msg)
        elif gemini_key:
            try:
                return run_gemini_rest(prompt)
            except Exception as e:
                err_msg = f"Gemini Fast REST Error: {e}"
                errors.append(err_msg)
                print(f"  [LLM CLIENT WARNING] {err_msg}")
                raise RuntimeError(err_msg)
        else:
            raise ValueError("No Gemini client or key available")

    # Задаем порядок опроса
    if quality == "strong":
        steps_to_try = [
            ("groq", "llama-3.3-70b-versatile"),
            ("gemini", None),
            ("groq", "llama-3.1-8b-instant")
        ]
    else:
        steps_to_try = [
            ("groq", "llama-3.1-8b-instant"),
            ("gemini", None),
            ("groq", "llama-3.3-70b-versatile")
        ]

    for provider, model in steps_to_try:
        if provider == "groq" and groq_clients:
            if time.time() < _groq_cooldown_until:
                print(f"  [LLM CLIENT SKIP] Пропускаю Groq ({model}) для быстрой задачи: Groq на кулдауне")
                continue
            model_tpm = 6000 if "8b" in model else 12000
            if tokens >= model_tpm - 1024:
                print(f"  [LLM CLIENT SKIP] Пропускаю Groq ({model}) для быстрой задачи: размер промпта {tokens} велик для TPM {model_tpm}")
                continue
            try:
                return try_groq(model), tokens
            except Exception:
                continue
        elif provider == "gemini" and (_gemini_client or os.getenv("GEMINI_KEY")):
            try:
                return try_gemini(), tokens
            except Exception:
                continue

    detailed_errors = "\n".join(f"- {err}" for err in errors)
    raise RuntimeError(
        f"Не удалось выполнить быстрый запрос к LLM (quality={quality}). Все провайдеры вернули ошибку:\n{detailed_errors}"
    )


def summarize_article_common(title: str, article_text: str, platform: str) -> str:
    """
    Специализированная функция саммари статей для researcher.py.
    Использует цепочку: Gemini (прямой REST) ➔ Groq 70B ➔ Mistral ➔ Cerebras.
    """
    if os.getenv("MOCK_LLM") == "1":
        return f"Это тестовое саммари для статьи '{title}' по теме '{platform}', сгенерированное локально."

    prompt = (
        f"Ты эксперт по digital-маркетингу. Прочитай статью и напиши саммари на русском языке "
        f"(3-5 предложений) — только конкретные инсайты и практические советы по теме {platform}. "
        f"Без воды.\n\nЗаголовок: {title}\n\nТекст:\n{article_text}"
    )

    errors = []

    # 1. Gemini REST (для стабильности в средах без SDK)
    gemini_key = os.getenv("GEMINI_KEY")
    if gemini_key:
        try:
            import urllib.request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            return res["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            errors.append(f"Gemini REST Error: {e}")

    # 2. Groq (через SDK с авто-бэкоффом)
    groq_clients = get_groq_clients()
    if groq_clients and time.time() >= _groq_cooldown_until:
        model_tpm = 12000
        tokens = len(prompt.split()) * 2
        if tokens < model_tpm - 1024:
            for client in groq_clients:
                try:
                    return call_groq_with_retry(
                        client=client,
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1024,
                        temperature=0.2
                    )
                except Exception as e:
                    errors.append(f"Groq SDK Error: {e}")

    # 3. Mistral API
    if _mistral_client:
        try:
            resp = _mistral_client.chat.complete(
                model="mistral-small-latest",
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            errors.append(f"Mistral Error: {e}")

    # 4. Cerebras
    if _cerebras_client:
        try:
            resp = _cerebras_client.chat.completions.create(
                model="llama3.1-8b",
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            errors.append(f"Cerebras Error: {e}")

    detailed_errors = "\n".join(f"- {err}" for err in errors)
    raise RuntimeError(
        f"Не удалось выполнить суммирование статьи. Все LLM-провайдеры вернули ошибку:\n{detailed_errors}"
    )
