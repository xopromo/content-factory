#!/usr/bin/env python3
"""
Threads Comment Agent - автоматический комментариатор для Threads
"""
import asyncio
import json
import random
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
        """Загружает конфиг из файла"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Config file not found: {self.config_path}")
            raise

    async def run(self, mode: str = "manual"):
        """Запускает агента в заданном режиме"""
        print(f"\n🤖 Threads Comment Agent - Mode: {mode.upper()}")
        print(f"⏰ Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Логинимся
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
        """Ручной режим - один проход поиска и комментирования"""
        await self._search_and_comment()

    async def _run_schedule(self):
        """Режим по расписанию - запускается в определённое время"""
        schedule_config = self.config["scheduling"]
        target_time = time.fromisoformat(schedule_config.get("time", "14:00"))

        print(f"📅 Scheduled mode - runs daily at {target_time}")

        while True:
            now = datetime.now().time()
            if now.hour == target_time.hour and now.minute == target_time.minute:
                print(f"\n▶️  Running scheduled task at {now}")
                await self._search_and_comment()
                await asyncio.sleep(60)  # Не запускаем дважды в одну минуту
            else:
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд

    async def _run_realtime(self):
        """Режим реального времени - слушает новые посты"""
        print("🔴 Real-time mode - listening for new posts...")
        print("⚠️  Note: requires premium access for real-time stream")

        while True:
            await self._search_and_comment()
            await asyncio.sleep(300)  # Проверяем каждые 5 минут

    async def _search_and_comment(self):
        """Ищет посты и комментирует их"""
        search_config = self.config["search"]
        comment_config = self.config["comment_generation"]
        filter_config = self.config["filters"]

        all_posts = []

        # Ищем по хэштегам
        for hashtag in search_config.get("hashtags", []):
            print(f"\n🔍 Searching for posts with {hashtag}...")
            posts = await self.threads.search_posts(hashtag, limit=search_config.get("limit", 5))
            if posts:
                all_posts.extend(posts)

        # Ищем по ключевым словам
        for keyword in search_config.get("keywords", []):
            print(f"🔍 Searching for posts with '{keyword}'...")
            posts = await self.threads.search_posts(keyword, limit=search_config.get("limit", 5))
            if posts:
                all_posts.extend(posts)

        if not all_posts:
            print("⚠️  No posts found")
            return

        # Фильтруем посты
        filtered_posts = self.searcher.filter_posts(all_posts, filter_config)

        # Комментируем посты
        commented_count = 0
        for post in filtered_posts[:search_config.get("limit", 5)]:
            post_id = post.get("id")

            # Пропускаем дублики
            if post_id in self.posted_comments:
                continue

            # Пропускаем свои посты
            if filter_config.get("skip_own_posts") and post.get("user", {}).get("username") == self.config["account"]["username"]:
                continue

            # Генерируем комментарий
            post_text = post.get("caption", "")
            comment = self.llm.generate_with_template(
                post_text,
                comment_config.get("templates", []),
                tone=comment_config.get("tone", "friendly")
            )

            if comment:
                success = await self.threads.reply_to_post(post_id, comment)
                if success:
                    commented_count += 1
                    self.posted_comments.add(post_id)
                    print(f"✅ Commented on post by @{post.get('user', {}).get('username')}")
                    print(f"   Comment: {comment[:100]}...")
                else:
                    print(f"❌ Failed to comment on post {post_id}")
            else:
                print(f"⚠️  Failed to generate comment for post {post_id}")

        print(f"\n📊 Session summary: {commented_count} comments posted")

    def save_config(self):
        """Сохраняет конфиг обратно в файл"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        print(f"✅ Config saved to {self.config_path}")

    def update_config(self, key_path: str, value):
        """Обновляет значение в конфиге (поддерживает вложенные ключи)"""
        keys = key_path.split(".")
        current = self.config
        for key in keys[:-1]:
            current = current[key]
        current[keys[-1]] = value


async def main():
    """Главная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Threads Comment Agent")
    parser.add_argument(
        "--mode",
        choices=["manual", "schedule", "realtime"],
        default="manual",
        help="Режим запуска"
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Путь к конфиг файлу"
    )
    parser.add_argument(
        "--hashtag",
        help="Переопределить хэштег для поиска"
    )
    parser.add_argument(
        "--tone",
        choices=["friendly", "professional", "witty", "casual"],
        help="Тон комментариев"
    )

    args = parser.parse_args()

    agent = ThreadsCommentAgent(args.config)

    # Переопределяем параметры если передали в аргументах
    if args.hashtag:
        agent.config["search"]["hashtags"] = [args.hashtag]
    if args.tone:
        agent.config["comment_generation"]["tone"] = args.tone

    try:
        await agent.run(mode=args.mode)
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
