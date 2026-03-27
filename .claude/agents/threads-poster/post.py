#!/usr/bin/env python3
"""
📱 Threads Poster Script
Постит контент в Threads 100% бесплатно через threads-api
"""

import asyncio
import os
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from threads_api import ThreadsAPI
except ImportError:
    print("❌ Ошибка: threads-api не установлена")
    print("Установи: pip install threads-api")
    sys.exit(1)


class ThreadsPoster:
    def __init__(self):
        self.username = os.getenv("THREADS_USERNAME")
        self.password = os.getenv("THREADS_PASSWORD")
        self.api = ThreadsAPI()
        self.memory_file = Path(__file__).parent / "MEMORY.md"

    async def login(self):
        """Логин в Threads"""
        if not self.username or not self.password:
            raise ValueError(
                "❌ Не установлены THREADS_USERNAME и THREADS_PASSWORD\n"
                "Выполни:\n"
                "  export THREADS_USERNAME='your_username'\n"
                "  export THREADS_PASSWORD='your_password'"
            )

        print("🔐 Логинюсь в Threads...")
        await self.api.login(self.username, self.password)
        print("✅ Успешно залогинился!")

    async def post_text(self, caption: str) -> dict:
        """Постить текстовый пост"""
        print(f"📝 Постю: {caption[:50]}...")
        result = await self.api.post(caption=caption)
        print(f"✅ Пост создан!")
        return result

    async def post_image(self, caption: str, image_path: str) -> dict:
        """Постить пост с изображением"""
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Файл не найден: {image_path}")

        print(f"📸 Постю с картинкой: {image_path}")
        result = await self.api.post(caption=caption, image_path=image_path)
        print(f"✅ Пост с изображением создан!")
        return result

    async def post_carousel(self, caption: str, images: list) -> dict:
        """Постить галерею"""
        for img in images:
            if not Path(img).exists():
                raise FileNotFoundError(f"Файл не найден: {img}")

        print(f"🖼️ Постю галерею ({len(images)} фото)...")
        result = await self.api.post(caption=caption, carousel=images)
        print(f"✅ Галерея создана!")
        return result

    async def post_vk_insights(self, count: int = 5) -> list:
        """Постить инсайты из VK базы"""
        logs_file = Path(
            "/home/user/content-factory/docs/agents/data/logs.json"
        )

        if not logs_file.exists():
            raise FileNotFoundError(f"Файл логов не найден: {logs_file}")

        with open(logs_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        insights = data["logs"][:count]
        results = []

        for insight in insights:
            caption = (
                f"🔍 {insight['finding']}\n\n"
                f"📌 Анализ: {insight['analysis'][:150]}...\n\n"
                f"✅ Вывод: {insight['conclusion'][:150]}...\n\n"
                f"⭐ Релевантность: {int(insight['relevance_score']*100)}%\n\n"
                f"#ВКонтакте #Таргетинг #VKAds"
            )

            result = await self.post_text(caption)
            results.append(result)

            # Интервал между постами (избежать блокировки)
            await asyncio.sleep(60)

        return results

    def log_post(self, post_id: str, text: str = ""):
        """Логировать пост в MEMORY.md"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = (
            f"| {timestamp} | {text[:50]}... | ✅ | {post_id} |\n"
        )

        if self.memory_file.exists():
            with open(self.memory_file, "a", encoding="utf-8") as f:
                f.write(log_entry)

    async def main(self, action: str = "text", **kwargs):
        """Главная функция"""
        try:
            await self.login()

            if action == "text":
                result = await self.post_text(kwargs["caption"])
                self.log_post(result.get("id", ""), kwargs["caption"])

            elif action == "image":
                result = await self.post_image(kwargs["caption"], kwargs["image"])
                self.log_post(result.get("id", ""), kwargs["caption"])

            elif action == "carousel":
                result = await self.post_carousel(kwargs["caption"], kwargs["images"])
                self.log_post(result.get("id", ""), kwargs["caption"])

            elif action == "insights":
                count = kwargs.get("count", 5)
                results = await self.post_vk_insights(count)
                print(f"✅ Запостено {len(results)} инсайтов!")

            else:
                raise ValueError(f"Неизвестное действие: {action}")

            print("🎉 Готово!")

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            sys.exit(1)


async def main():
    """Точка входа"""
    import argparse

    parser = argparse.ArgumentParser(
        description="📱 Threads Poster - Постинг в Threads"
    )
    parser.add_argument(
        "--action",
        default="text",
        choices=["text", "image", "carousel", "insights"],
        help="Тип постинга",
    )
    parser.add_argument("--caption", help="Текст поста")
    parser.add_argument("--image", help="Путь к изображению")
    parser.add_argument(
        "--images", nargs="+", help="Пути к изображениям (для галереи)"
    )
    parser.add_argument(
        "--count", type=int, default=5, help="Количество инсайтов для постинга"
    )

    args = parser.parse_args()

    poster = ThreadsPoster()

    if args.action == "text":
        caption = args.caption or "Привет Threads! 🚀 Это автоматический пост!"
        await poster.main("text", caption=caption)

    elif args.action == "image":
        caption = args.caption or "Смотри картинку!"
        image = args.image or "image.jpg"
        await poster.main("image", caption=caption, image=image)

    elif args.action == "carousel":
        caption = args.caption or "Галерея!"
        images = args.images or ["image1.jpg", "image2.jpg"]
        await poster.main("carousel", caption=caption, images=images)

    elif args.action == "insights":
        await poster.main("insights", count=args.count)


if __name__ == "__main__":
    asyncio.run(main())
