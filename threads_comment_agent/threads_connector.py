"""
Модуль для подключения к Threads API и работы с постами
"""
import asyncio
from typing import List, Optional, Dict

class ThreadsConnector:
    """Подключение к Threads и работа с постами"""

    def __init__(self, config: dict):
        self.config = config
        self.api = None
        self._init_api()

    def _init_api(self):
        """Инициализирует threads-api"""
        try:
            from threads_api import ThreadsAPI
            self.api = ThreadsAPI()
            print("✅ Threads API initialized")
        except ImportError:
            print("❌ threads-api не установлена. Установите: pip install threads-api")
            return False

    async def login(self) -> bool:
        """Логинится в Threads"""
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
        """Ищет посты по хэштегу или ключевому слову"""
        try:
            # Примечание: официальный API может не поддерживать поиск
            # Это зависит от версии threads-api
            posts = await self.api.search(query, limit=limit)
            return posts
        except Exception as e:
            print(f"⚠️  Search error: {e}")
            return []

    async def get_feed_posts(self, limit: int = 10) -> Optional[List[Dict]]:
        """Получает посты из ленты"""
        try:
            posts = await self.api.get_feed_posts(limit=limit)
            return posts
        except Exception as e:
            print(f"⚠️  Feed error: {e}")
            return []

    async def get_user_posts(self, username: str, limit: int = 10) -> Optional[List[Dict]]:
        """Получает посты конкретного пользователя"""
        try:
            user = await self.api.get_user(username)
            if user:
                posts = await self.api.get_user_posts(user.get("id"), limit=limit)
                return posts
            return []
        except Exception as e:
            print(f"⚠️  User posts error: {e}")
            return []

    async def reply_to_post(self, post_id: str, comment: str, image_path: Optional[str] = None) -> bool:
        """Отвечает на пост с комментарием"""
        try:
            response = await self.api.reply(
                parent_post_id=post_id,
                caption=comment,
                image_path=image_path
            )
            return response is not None
        except Exception as e:
            print(f"❌ Reply error: {e}")
            return False

    async def post(self, caption: str, image_path: Optional[str] = None) -> bool:
        """Постит в Threads"""
        try:
            response = await self.api.post(
                caption=caption,
                image_path=image_path
            )
            return response is not None
        except Exception as e:
            print(f"❌ Post error: {e}")
            return False

    def close(self):
        """Закрывает соединение"""
        if self.api:
            self.api.close()


class ThreadsSearcher:
    """Поиск постов в Threads"""

    @staticmethod
    def filter_posts(posts: List[Dict], filters: dict) -> List[Dict]:
        """Фильтрует посты по критериям"""
        filtered = posts

        # Минимальное количество взаимодействий
        min_engagement = filters.get("min_engagement", 0)
        if min_engagement > 0:
            filtered = [
                p for p in filtered
                if (p.get("likes_count", 0) + p.get("comments_count", 0) + p.get("reposts_count", 0)) >= min_engagement
            ]

        return filtered

    @staticmethod
    def format_post_preview(post: Dict) -> str:
        """Форматирует превью поста для анализа"""
        text = post.get("caption", "")[:200]
        author = post.get("user", {}).get("username", "unknown")
        likes = post.get("likes_count", 0)
        comments = post.get("comments_count", 0)

        return f"@{author}: {text}... (❤️ {likes}, 💬 {comments})"
