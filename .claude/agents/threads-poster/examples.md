# 📱 Примеры постинга в Threads

## Пример 1: Простой текстовый пост

```python
import asyncio
from threads_api import ThreadsAPI
import os

async def simple_post():
    api = ThreadsAPI()
    await api.login(
        os.getenv("THREADS_USERNAME"),
        os.getenv("THREADS_PASSWORD")
    )

    result = await api.post(
        caption="Привет Threads! 🎉 Это мой первый пост автоматически через API."
    )

    print(f"✅ Пост создан: {result}")

asyncio.run(simple_post())
```

## Пример 2: Пост с изображением

```python
async def post_with_image():
    api = ThreadsAPI()
    await api.login(
        os.getenv("THREADS_USERNAME"),
        os.getenv("THREADS_PASSWORD")
    )

    result = await api.post(
        caption="Смотри эту картинку! 📸",
        image_path="screenshot.jpg"
    )

    print(f"✅ Пост с изображением: {result}")

asyncio.run(post_with_image())
```

## Пример 3: Галерея (несколько изображений)

```python
async def post_carousel():
    api = ThreadsAPI()
    await api.login(
        os.getenv("THREADS_USERNAME"),
        os.getenv("THREADS_PASSWORD")
    )

    result = await api.post(
        caption="Смотри мою коллекцию! 🖼️",
        carousel=[
            "image1.jpg",
            "image2.jpg",
            "image3.jpg"
        ]
    )

    print(f"✅ Карусель создана: {result}")

asyncio.run(post_carousel())
```

## Пример 4: Ответ на пост

```python
async def reply_to_post():
    api = ThreadsAPI()
    await api.login(
        os.getenv("THREADS_USERNAME"),
        os.getenv("THREADS_PASSWORD")
    )

    # Нужен ID поста на который отвечаем
    result = await api.post(
        caption="Мой ответ на этот пост! 💬",
        parent_id="thread_id_12345"
    )

    print(f"✅ Ответ отправлен: {result}")

asyncio.run(reply_to_post())
```

## Пример 5: Постить инсайты из VK базы

```python
import json

async def post_vk_insights():
    api = ThreadsAPI()
    await api.login(
        os.getenv("THREADS_USERNAME"),
        os.getenv("THREADS_PASSWORD")
    )

    # Читаем инсайты из logs.json
    with open('/home/user/content-factory/docs/agents/data/logs.json', 'r') as f:
        data = json.load(f)

    # Берем первые 3 инсайта
    for insight in data['logs'][:3]:
        caption = f"""
🔍 {insight['finding']}

📌 Анализ: {insight['analysis'][:100]}...

✅ Вывод: {insight['conclusion'][:100]}...

#ВКонтакте #Таргетинг #VKAds
        """

        result = await api.post(caption=caption.strip())
        print(f"✅ Инсайт запостен: {insight['finding'][:30]}...")

asyncio.run(post_vk_insights())
```

## Пример 6: Регулярный постинг (каждый час)

```python
import asyncio
import time

async def scheduled_posting():
    counter = 1

    while True:
        try:
            api = ThreadsAPI()
            await api.login(
                os.getenv("THREADS_USERNAME"),
                os.getenv("THREADS_PASSWORD")
            )

            result = await api.post(
                caption=f"Пост №{counter} - Автоматический постинг каждый час! ⏰"
            )

            print(f"✅ Пост {counter} создан")
            counter += 1

            # Ждем 1 час (3600 секунд)
            await asyncio.sleep(3600)

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            await asyncio.sleep(60)

asyncio.run(scheduled_posting())
```

## Пример 7: С обработкой ошибок

```python
async def safe_posting(caption, max_retries=3):
    for attempt in range(max_retries):
        try:
            api = ThreadsAPI()
            await api.login(
                os.getenv("THREADS_USERNAME"),
                os.getenv("THREADS_PASSWORD")
            )

            result = await api.post(caption=caption)
            print(f"✅ Успешно: {result}")
            return result

        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1}/{max_retries} не удалась: {e}")

            if attempt < max_retries - 1:
                await asyncio.sleep(60 * (attempt + 1))
            else:
                print(f"❌ Не удалось создать пост после {max_retries} попыток")
                return None

# Использование
asyncio.run(safe_posting("Мой пост с защитой от ошибок!"))
```

---

**Все примеры 100% бесплатные! 🎉**
