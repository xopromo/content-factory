#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

def run_pollinations_gemini(prompt: str) -> str:
    # 1. Попробуем Pollinations с перебором версий
    models = ["gemini", "gemini-3.5-flash", "gemini-fast", "gemini-flash-lite-3.1"]
    for model in models:
        url = "https://text.pollinations.ai/"
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "model": model,
            "json": False
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8").strip()
        except Exception as e:
            print(f"Pollinations {model} failed: {e}")
            continue

    # 2. Если Pollinations выдал 429 или упал, используем официальный Gemini REST по ключу из .env
    gemini_key = os.environ.get("GEMINI_KEY")
    if gemini_key:
        print("Trying official Gemini REST fallback using GEMINI_KEY...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8192}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print(f"Official Gemini API failed: {e}")
            
    # 3. Если все Gemini-методы вернули 429, пробуем Groq по ключу GROQ_KEY
    groq_key = os.environ.get("GROQ_KEY")
    if groq_key:
        print("Trying Groq fallback (openai/gpt-oss-120b)...")
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "openai/gpt-oss-120b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 4096
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {groq_key}"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Groq API failed: {e}")

    # 4. Пробуем Mistral по ключу MISTRAL_KEY
    mistral_key = os.environ.get("MISTRAL_KEY")
    if mistral_key:
        print("Trying Mistral fallback (mistral-large-latest)...")
        url = "https://api.mistral.ai/v1/chat/completions"
        payload = {
            "model": "mistral-large-latest",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 4096
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {mistral_key}"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Mistral API failed: {e}")

    print("All backends failed.")
    sys.exit(1)

def main():
    print("Zapusk bystrogo napisaniya stati pro vibecoding napryamuyu...")
    
    prompt = """Напиши полноценную, подробную и готовую к публикации статью про вайбкодинг (Vibecoding) и то, как ИИ меняет разработку ПО.
Статья должна быть на русском языке, содержать практические примеры, разделы с подзаголовками, структурированные списки и выводы.
Формат вывода: только чистый Markdown (начни сразу с заголовка #). Не добавляй никаких вводных слов от себя или рамок кода.

Ключевые темы, которые нужно раскрыть:
1. Что такое вайбкодинг простыми словами и откуда взялся этот термин.
2. Как меняется роль разработчика: от написания синтаксиса к системному мышлению, оркестрации и формулированию идей.
3. Плюсы вайбкодинга (скорость прототипирования, снижение порога входа, фокус на продукте).
4. Опасности и узкие горлышки (накапливание технического долга, потеря контроля над архитектурой, проблема "черного ящика", сложность отладки сгенерированного кода).
5. Будущее разработки: останутся ли классические программисты или все уйдут в "вайб".

Пиши максимально емко, профессионально, но увлекательно."""

    article_text = run_pollinations_gemini(prompt)
    
    # Путь для сохранения статьи
    output_dir = Path(__file__).parent.parent / "content-factory" / "articles"
    if not output_dir.exists():
        # Резервный путь, если структура каталогов отличается
        output_dir = Path(__file__).parent.parent / "articles"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "vibecoding_and_ai_advantages.html" # сохраним как html/md, но пока запишем напрямую
    
    # Для интеграции с блогом обернем Markdown в простой HTML-шаблон, если это требуется сайтом, 
    # либо запишем как чистый html. Посмотрим, какой формат обычно используется.
    # Запишем сначала в формате Markdown в .md, а также обновим html-версию.
    md_file = output_dir / "vibecoding_and_ai_advantages.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(article_text)
    print(f"Markdown state saved to: {md_file.resolve()}")

    # Обернем в базовую структуру HTML для публикации на GitHub Pages
    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вайбкодинг: Эра разработки на кончиках пальцев</title>
    <style>
        body {{
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        article {{
            background: #fff;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        }}
        h1, h2, h3 {{
            color: #111;
        }}
        pre {{
            background: #f4f4f4;
            padding: 15px;
            border-left: 5px solid #007acc;
            overflow-x: auto;
        }}
        code {{
            font-family: Consolas, Monaco, monospace;
            background: #f4f4f4;
            padding: 2px 5px;
            border-radius: 3px;
        }}
    </style>
</head>
<body>
    <article>
        <!-- HTML-версия статьи -->
        {article_text.replace(chr(10), '<br>')}
    </article>
</body>
</html>"""

    # Конвертируем переносы строк Markdown в базовый HTML для простоты теста
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML state saved to: {output_file.resolve()}")

if __name__ == "__main__":
    main()
