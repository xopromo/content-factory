#!/usr/bin/env python3
"""
Setup script - creates all Threads Comment Agent files in current directory
Run this in C:\content-factory\threads_comment_agent folder
"""
import json
import os

# Files to create
files = {
    "config.json": {
        "account": {
            "username": "your_username",
            "password": "your_password"
        },
        "search": {
            "hashtags": ["#AI", "#Tech", "#Python"],
            "keywords": ["machine learning", "automation"],
            "limit": 5
        },
        "comment_generation": {
            "model": "ollama",
            "ollama_url": "http://localhost:11434",
            "ollama_model": "mistral",
            "gpt4all_model": "orca-mini",
            "tone": "friendly",
            "max_length": 280,
            "templates": [
                "Интересно! {comment}",
                "Согласен, {comment}",
                "{comment} Спасибо за пост!"
            ]
        },
        "scheduling": {
            "mode": "manual",
            "frequency": "daily",
            "time": "14:00",
            "realtime": False
        },
        "filters": {
            "min_engagement": 0,
            "skip_duplicates": True,
            "skip_own_posts": True
        }
    },

    "requirements.txt": "threads-api>=1.1.14\nrequests>=2.31.0\ngpt4all>=3.0.0\nollama>=0.1.0\npython-dotenv>=1.0.0\n",

    "__init__.py": '"""\nThreads Comment Agent - автоматический комментариатор для Threads\n"""\n\nfrom agent import ThreadsCommentAgent\nfrom models import LocalLLM\nfrom threads_connector import ThreadsConnector, ThreadsSearcher\n\n__version__ = "0.1.0"\n__author__ = "Your Name"\n\n__all__ = [\n    "ThreadsCommentAgent",\n    "LocalLLM",\n    "ThreadsConnector",\n    "ThreadsSearcher",\n]\n',

    "quick_test.py": '''#!/usr/bin/env python3
"""
Быстрая проверка установки
"""
import sys
import json

def check_python():
    print("🐍 Python:", end=" ")
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info >= (3, 8):
        print(f"✅ {version}")
        return True
    else:
        print(f"❌ {version} (требуется 3.8+)")
        return False

def check_config():
    print("⚙️  Config:", end=" ")
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        username = config.get("account", {}).get("username")
        if username and username != "your_username":
            print(f"✅ Готово (@{username})")
            return True
        else:
            print("⚠️  Нужно установить username")
            return False
    except:
        print("❌ config.json не найден")
        return False

def main():
    print("\\n" + "=" * 50)
    print("🧪 БЫСТРАЯ ПРОВЕРКА")
    print("=" * 50 + "\\n")

    results = [
        ("Python", check_python()),
        ("Config", check_config()),
    ]

    print("\\n" + "=" * 50)
    if all(r[1] for r in results):
        print("✅ ГОТОВО!")
        print("\\nЗапусти:")
        print("  python agent.py --mode manual")
        return 0
    else:
        print("⚠️  Проверь конфиг")
        return 1

if __name__ == "__main__":
    sys.exit(main())
'''
}

def main():
    print("=" * 60)
    print("📦 СОЗДАНИЕ ФАЙЛОВ THREADS COMMENT AGENT")
    print("=" * 60)

    created = 0

    for filename, content in files.items():
        try:
            if filename == "config.json":
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(content, f, indent=2, ensure_ascii=False)
            else:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)

            print(f"✅ {filename}")
            created += 1
        except Exception as e:
            print(f"❌ {filename} - {e}")

    print("\n" + "=" * 60)
    print(f"✅ Создано {created}/{len(files)} файлов")
    print("\nДалее:")
    print("  1. pip install -r requirements.txt")
    print("  2. Отредактируй config.json (username/password)")
    print("  3. python quick_test.py")
    print("=" * 60)

if __name__ == "__main__":
    main()
