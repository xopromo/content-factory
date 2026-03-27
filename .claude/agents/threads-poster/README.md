# 📱 Threads Poster Agent

**Автоматический постинг в Threads - 100% бесплатно!**

## Быстрый старт

### 1. Установить библиотеку
```bash
pip install threads-api
```

### 2. Установить переменные окружения
```bash
export THREADS_USERNAME="your_username"
export THREADS_PASSWORD="your_password"
```

### 3. Запустить агента
```
@"threads-poster" постни "Привет Threads! 🚀" в Threads
```

## Команды агента

### 📝 Простой постинг
```
@"threads-poster" постни "текст поста" в Threads
```

### 🖼️ Постинг с изображением
```
@"threads-poster" постни "текст" с картинкой "image.jpg" в Threads
```

### 🎨 Галерея (несколько фото)
```
@"threads-poster" постни галерею из image1.jpg, image2.jpg, image3.jpg в Threads
```

### 📊 Постить инсайты
```
@"threads-poster" постни 5 лучших инсайтов из VK базы в Threads
```

### 🔄 Регулярный постинг
```
/loop 1h @"threads-poster" постни новый инсайт в Threads
```

## Структура проекта

```
.claude/agents/threads-poster/
├── threads-poster.md       # Конфигурация агента
├── README.md               # Этот файл
├── MEMORY.md              # История постов
├── examples.md            # Примеры кода
└── post.py                # Готовый скрипт для постинга
```

## Возможности

| Функция | Статус | Детали |
|---------|--------|--------|
| Текстовые посты | ✅ | До 500 символов |
| Изображения | ✅ | JPG, PNG (до 8MB) |
| Галерея | ✅ | До 10 изображений |
| Видео | ❌ | Скоро |
| Ответы на посты | ✅ | Нужен parent_id |
| Репосты | ✅ | Rethread |
| Лайки/Комментарии | ⏳ | В разработке |
| Хэштеги | ✅ | Поддерживаются |
| Тег пользователей | ✅ | @username |

## Стоимость

| Способ | Цена |
|--------|------|
| threads-api | **$0** ✅ |
| LATE API | ~$50/месяц |
| Ручной постинг | Бесплатно |

**Рекомендация: Используй threads-api - она абсолютно бесплатна!**

## FAQ

**Q: Нужна ли официальная API ключ?**
A: Нет! threads-api работает через браузер-автоматизацию (Selenium/Playwright). 100% бесплатно.

**Q: Есть ли лимиты на постинг?**
A: Примерно 100 постов в день. После этого может быть rate limit на 1-2 часа.

**Q: Безопасно ли это?**
A: Да, threads-api использует легальный способ (как обычный браузер). Но Threads может заблокировать аккаунт если постить очень много спама.

**Q: Как часто можно постить?**
A: Рекомендуется интервал 1-5 минут между постами для избежания блокировки.

**Q: Можно ли использовать несколько аккаунтов?**
A: Да, просто измени THREADS_USERNAME и THREADS_PASSWORD для каждого.

## Примеры использования

### Пример 1: Постить инсайты каждый час
```bash
/loop 1h @"threads-poster" постни новый инсайт про ВК в Threads
```

### Пример 2: Постить идеи от Brainstormer
```bash
@"threads-poster" возьми лучшую идею от brainstormer и постни в Threads
```

### Пример 3: Постить TOP-3 рекомендации от Judge
```bash
@"threads-poster" постни TOP-3 рекомендации от judge в Threads с картинками
```

## Интеграция с VK Pipeline

Агент может автоматически:
1. ✅ Читать инсайты из `/docs/agents/data/logs.json`
2. ✅ Форматировать их в красивые посты
3. ✅ Постить в Threads с картинками
4. ✅ Логировать историю постов в MEMORY.md
5. ✅ Ставить хэштеги (#ВКонтакте #Таргетинг #VKAds)

## Хостинг и автоматизация

### Локально (на твоем компьютере)
```bash
# Запустить один раз
python post.py

# Запустить регулярно (cron)
0 * * * * /usr/bin/python3 /path/to/post.py
```

### Через Claude Code
```
/loop 1h @"threads-poster" постни новый инсайт в Threads
```

### Через GitHub Actions (если нужна надежность)
```yaml
name: Threads Poster
on:
  schedule:
    - cron: "0 * * * *"  # Каждый час
jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Post to Threads
        run: python post.py
        env:
          THREADS_USERNAME: ${{ secrets.THREADS_USERNAME }}
          THREADS_PASSWORD: ${{ secrets.THREADS_PASSWORD }}
```

## Советы для успеха

1. **Уникальный контент** - Не постай один и тот же текст несколько раз
2. **Интересные картинки** - Визуальный контент = больше лайков
3. **Правильные хэштеги** - #ВКонтакте #Таргетинг #VKAds
4. **Взаимодействие** - Отвечай на комментарии
5. **Консистентность** - Постай регулярно (не спорадически)

## Контакты и поддержка

- [threads-api GitHub Issues](https://github.com/junhoyeo/threads-api/issues)
- [PyPI threads-api](https://pypi.org/project/threads-api/)
- [Наш проект VK Pipeline](https://github.com/xopromo/content-factory)

---

**Создано для автоматического постинга инсайтов в Threads! 🚀**
