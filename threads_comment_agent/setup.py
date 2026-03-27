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

def create_agent_py():
    """Содержимое agent.py"""
    return '''#!/usr/bin/env python3
"""Threads Comment Agent - автоматический комментариатор для Threads"""
import asyncio, json, random
from pathlib import Path
from datetime import datetime, time
from typing import Optional, List
from models import LocalLLM
from threads_connector import ThreadsConnector, ThreadsSearcher

class ThreadsCommentAgent:
    """Основной агент для комментирования Threads"""
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.llm = LocalLLM(self.config["comment_generation"])
        self.threads = ThreadsConnector(self.config)
        self.searcher = ThreadsSearcher()
        self.posted_comments = set()

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Config file not found: {self.config_path}")
            raise

    async def run(self, mode: str = "manual"):
        print(f"\\n🤖 Threads Comment Agent - Mode: {mode.upper()}")
        print(f"⏰ Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
        logged_in = await self.threads.login()
        if not logged_in:
            return
        try:
            if mode == "manual":
                await self._run_manual()
            elif mode == "schedule":
                await self._run_schedule()
            elif mode == "realtime":
                await self._run_realtime()
            else:
                print(f"❌ Unknown mode: {mode}")
        finally:
            self.threads.close()

    async def _run_manual(self):
        await self._search_and_comment()

    async def _run_schedule(self):
        schedule_config = self.config["scheduling"]
        target_time = time.fromisoformat(schedule_config.get("time", "14:00"))
        print(f"📅 Scheduled mode - runs daily at {target_time}")
        while True:
            now = datetime.now().time()
            if now.hour == target_time.hour and now.minute == target_time.minute:
                print(f"\\n▶️  Running scheduled task at {now}")
                await self._search_and_comment()
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(30)

    async def _run_realtime(self):
        print("🔴 Real-time mode - listening for new posts...")
        while True:
            await self._search_and_comment()
            await asyncio.sleep(300)

    async def _search_and_comment(self):
        search_config = self.config["search"]
        comment_config = self.config["comment_generation"]
        filter_config = self.config["filters"]
        all_posts = []

        for hashtag in search_config.get("hashtags", []):
            print(f"\\n🔍 Searching for posts with {hashtag}...")
            posts = await self.threads.search_posts(hashtag, limit=search_config.get("limit", 5))
            if posts:
                all_posts.extend(posts)

        if not all_posts:
            print("⚠️  No posts found")
            return

        filtered_posts = self.searcher.filter_posts(all_posts, filter_config)
        commented_count = 0

        for post in filtered_posts[:search_config.get("limit", 5)]:
            post_id = post.get("id")
            if post_id in self.posted_comments:
                continue
            if filter_config.get("skip_own_posts") and post.get("user", {}).get("username") == self.config["account"]["username"]:
                continue

            post_text = post.get("caption", "")
            comment = self.llm.generate_with_template(post_text, comment_config.get("templates", []), tone=comment_config.get("tone", "friendly"))

            if comment:
                success = await self.threads.reply_to_post(post_id, comment)
                if success:
                    commented_count += 1
                    self.posted_comments.add(post_id)
                    print(f"✅ Commented on post by @{post.get('user', {}).get('username')}")
                    print(f"   Comment: {comment[:100]}...")

        print(f"\\n📊 Session summary: {commented_count} comments posted")

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Threads Comment Agent")
    parser.add_argument("--mode", choices=["manual", "schedule", "realtime"], default="manual")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--hashtag", help="Override hashtag")
    parser.add_argument("--tone", choices=["friendly", "professional", "witty", "casual"], help="Comment tone")

    args = parser.parse_args()
    agent = ThreadsCommentAgent(args.config)

    if args.hashtag:
        agent.config["search"]["hashtags"] = [args.hashtag]
    if args.tone:
        agent.config["comment_generation"]["tone"] = args.tone

    try:
        await agent.run(mode=args.mode)
    except KeyboardInterrupt:
        print("\\n⏹️  Stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
'''

def create_models_py():
    """Содержимое models.py"""
    return '''"""Модуль для работы с локальными моделями (Ollama, GPT4All)"""
import requests
from typing import Optional

class LocalLLM:
    """Интерфейс для локальных LLM"""
    def __init__(self, config: dict):
        self.config = config
        self.model_type = config.get("model", "ollama")

    def generate_comment(self, post_content: str, tone: str = "friendly") -> str:
        """Генерирует комментарий к посту"""
        if self.model_type == "ollama":
            return self._generate_ollama(post_content, tone)
        elif self.model_type == "gpt4all":
            return self._generate_gpt4all(post_content, tone)
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")

    def _generate_ollama(self, post_content: str, tone: str) -> str:
        """Генерирует через Ollama"""
        try:
            url = self.config.get("ollama_url", "http://localhost:11434")
            model = self.config.get("ollama_model", "mistral")
            prompt = f"""Напиши краткий комментарий ({self.config.get('max_length', 280)} символов макс) на русском языке.
Тон: {tone}
Контекст поста: {post_content}
Требования: Не начинай с эмодзи, будь кратким, не спрашивай вопросов."""

            response = requests.post(f"{url}/api/generate", json={"model": model, "prompt": prompt, "stream": False})
            if response.status_code == 200:
                result = response.json().get("response", "").strip()
                return result[:self.config.get("max_length", 280)]
        except Exception as e:
            print(f"Ollama error: {e}")
        return None

    def _generate_gpt4all(self, post_content: str, tone: str) -> str:
        """Генерирует через GPT4All"""
        try:
            from gpt4all import GPT4All
            model_name = self.config.get("gpt4all_model", "orca-mini")
            model = GPT4All(model_name)
            prompt = f"Напиши краткий комментарий на русском ({self.config.get('max_length', 280)} символов). Тон: {tone}. Пост: {post_content}"
            response = model.generate(prompt, max_tokens=100)
            return response[:self.config.get("max_length", 280)]
        except Exception as e:
            print(f"GPT4All error: {e}")
        return None

    def generate_with_template(self, post_content: str, templates: list, tone: str = "friendly") -> str:
        """Генерирует комментарий на основе шаблонов"""
        import random
        comment_text = self.generate_comment(post_content, tone)
        if not comment_text:
            return None
        template = random.choice(templates)
        result = template.format(comment=comment_text)
        return result[:self.config.get("max_length", 280)]
'''

def create_threads_connector_py():
    """Содержимое threads_connector.py"""
    return '''"""Модуль для подключения к Threads API и работы с постами"""
from typing import List, Optional, Dict

class ThreadsConnector:
    """Подключение к Threads и работа с постами"""
    def __init__(self, config: dict):
        self.config = config
        self.api = None
        self._init_api()

    def _init_api(self):
        try:
            from threads_api import ThreadsAPI
            self.api = ThreadsAPI()
            print("✅ Threads API initialized")
        except ImportError:
            print("❌ threads-api не установлена. Установите: pip install threads-api")

    async def login(self) -> bool:
        try:
            username = self.config["account"]["username"]
            password = self.config["account"]["password"]
            await self.api.login(username, password)
            print(f"✅ Logged in as @{username}")
            return True
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    async def search_posts(self, query: str, limit: int = 10) -> Optional[List[Dict]]:
        try:
            posts = await self.api.search(query, limit=limit)
            return posts
        except Exception as e:
            print(f"⚠️  Search error: {e}")
            return []

    async def reply_to_post(self, post_id: str, comment: str, image_path: Optional[str] = None) -> bool:
        try:
            response = await self.api.reply(parent_post_id=post_id, caption=comment, image_path=image_path)
            return response is not None
        except Exception as e:
            print(f"❌ Reply error: {e}")
            return False

    def close(self):
        if self.api:
            self.api.close()

class ThreadsSearcher:
    """Поиск постов в Threads"""
    @staticmethod
    def filter_posts(posts: List[Dict], filters: dict) -> List[Dict]:
        filtered = posts
        min_engagement = filters.get("min_engagement", 0)
        if min_engagement > 0:
            filtered = [p for p in filtered if (p.get("likes_count", 0) + p.get("comments_count", 0) + p.get("reposts_count", 0)) >= min_engagement]
        return filtered

    @staticmethod
    def format_post_preview(post: Dict) -> str:
        text = post.get("caption", "")[:200]
        author = post.get("user", {}).get("username", "unknown")
        likes = post.get("likes_count", 0)
        comments = post.get("comments_count", 0)
        return f"@{author}: {text}... (❤️ {likes}, 💬 {comments})"
'''

def main():
    print("=" * 60)
    print("📦 СОЗДАНИЕ ВСЕХ ФАЙЛОВ THREADS COMMENT AGENT")
    print("=" * 60)

    all_files = files.copy()
    all_files["agent.py"] = create_agent_py()
    all_files["models.py"] = create_models_py()
    all_files["threads_connector.py"] = create_threads_connector_py()

    created = 0

    for filename, content in all_files.items():
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
    print(f"✅ Создано {created}/{len(all_files)} файлов")
    print("\nДалее:")
    print("  1. pip install -r requirements.txt")
    print("  2. Отредактируй config.json (username/password)")
    print("  3. python agent.py --mode manual")
    print("=" * 60)

if __name__ == "__main__":
    main()
