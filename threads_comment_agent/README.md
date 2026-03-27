# 🤖 Threads Comment Agent

Автоматический агент для комментирования Threads на заданную тему с использованием локальных LLM (Ollama, GPT4All) и официального Threads API.

## ✨ Возможности

- 🔍 **Поиск по хэштегам и ключевым словам** в Threads
- 🤖 **Генерация умных комментариев** с использованием Ollama или GPT4All
- 📅 **Три режима запуска**:
  - `manual` - один проход поиска и комментирования
  - `schedule` - автоматический запуск по расписанию (ежедневно в определённое время)
  - `realtime` - непрерывный мониторинг новых постов
- ⚙️ **Гибкая конфигурация** для всех сценариев
- 🛡️ **Фильтры** для пропуска дублей и своих постов

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Запуск Ollama (опционально)

Если хотите использовать Ollama:

```bash
ollama serve
# В другом терминале:
ollama pull mistral
```

### 3. Конфигурация

Отредактируйте `config.json`:

```json
{
  "account": {
    "username": "your_username",
    "password": "your_password"
  },
  "search": {
    "hashtags": ["#AI", "#Tech"],
    "keywords": ["machine learning"],
    "limit": 5
  },
  "comment_generation": {
    "model": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "mistral",
    "tone": "friendly",
    "max_length": 280
  },
  "scheduling": {
    "mode": "manual",
    "frequency": "daily",
    "time": "14:00"
  }
}
```

### 4. Запуск агента

**Ручной режим (один проход):**
```bash
python agent.py --mode manual
```

**По расписанию (ежедневно в 14:00):**
```bash
python agent.py --mode schedule
```

**Real-time (непрерывный мониторинг):**
```bash
python agent.py --mode realtime
```

## 🎯 Примеры использования

### Поиск по хэштегу и комментирование

```bash
python agent.py --mode manual --hashtag "#Python"
```

### Изменить тон комментариев

```bash
python agent.py --mode manual --tone witty
```

Доступные тоны:
- `friendly` - дружелюбный
- `professional` - профессиональный
- `witty` - остроумный
- `casual` - неформальный

### Использовать другой конфиг

```bash
python agent.py --mode manual --config my_config.json
```

## ⚙️ Конфигурация в деталях

### Поиск (`search`)

```json
{
  "hashtags": ["#AI", "#Tech"],      // Хэштеги для поиска
  "keywords": ["automation"],         // Ключевые слова
  "limit": 5                          // Макс постов в одном проходе
}
```

### Генерация комментариев (`comment_generation`)

```json
{
  "model": "ollama",                  // "ollama" или "gpt4all"
  "ollama_url": "http://localhost:11434",
  "ollama_model": "mistral",          // Модель Ollama
  "gpt4all_model": "orca-mini",       // Модель GPT4All
  "tone": "friendly",                 // Тон комментариев
  "max_length": 280,                  // Максимальная длина
  "templates": [                      // Шаблоны комментариев
    "Интересно! {comment}",
    "Согласен, {comment}",
    "{comment} Спасибо за пост!"
  ]
}
```

### Расписание (`scheduling`)

```json
{
  "mode": "manual",        // "manual", "schedule", "realtime"
  "frequency": "daily",    // "daily", "hourly", "custom"
  "time": "14:00",         // Время запуска (HH:MM)
  "realtime": false        // Слушать новые посты в реал-времени
}
```

### Фильтры (`filters`)

```json
{
  "min_engagement": 0,      // Минимум лайков+комментариев
  "skip_duplicates": true,  // Не комментировать дважды один пост
  "skip_own_posts": true    // Не комментировать свои посты
}
```

## 🏗️ Архитектура

```
threads_comment_agent/
├── agent.py              # Основной скрипт агента
├── models.py             # LocalLLM - работа с Ollama/GPT4All
├── threads_connector.py   # ThreadsConnector - API Threads
├── config.json           # Конфигурация
├── requirements.txt      # Зависимости
└── README.md            # Документация
```

## 🔧 Модули

### `LocalLLM`

Генерирует комментарии с использованием локальных моделей:

```python
from models import LocalLLM

config = {
    "model": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "mistral",
    "max_length": 280
}

llm = LocalLLM(config)
comment = llm.generate_comment("Пост о AI", tone="friendly")
```

### `ThreadsConnector`

Подключение и работа с Threads API:

```python
from threads_connector import ThreadsConnector

threads = ThreadsConnector(config)
await threads.login()
posts = await threads.search_posts("#AI", limit=5)
await threads.reply_to_post(post_id, "Интересный пост!")
```

### `ThreadsSearcher`

Фильтрация и форматирование постов:

```python
from threads_connector import ThreadsSearcher

searcher = ThreadsSearcher()
filtered = searcher.filter_posts(posts, filters)
preview = searcher.format_post_preview(post)
```

## 📊 Примеры вывода

```
🤖 Threads Comment Agent - Mode: MANUAL
⏰ Started at 2024-01-15 14:30:00

✅ Logged in as @myusername

🔍 Searching for posts with #AI...
✅ Commented on post by @techblog
   Comment: Отличная статья о машинном обучении! Долго искал такой материал...

✅ Commented on post by @aibythebay
   Comment: Спасибо за инсайты! Полностью согласен с вашим мнением...

📊 Session summary: 2 comments posted
```

## ⚠️ Важные замечания

1. **Аутентификация**: Используйте пароль от аккаунта (не 2FA с SMS)
2. **Rate Limiting**: Threads имеет ограничения на количество комментариев
3. **Локальные модели**: Убедитесь, что Ollama запущена на `localhost:11434`
4. **GPU**: Для быстрой работы рекомендуется GPU (CUDA/Metal)

## 🐛 Troubleshooting

### Ошибка подключения к Ollama

```
Ollama connection error: Connection refused
```

**Решение**: Убедитесь, что Ollama запущена:
```bash
ollama serve
```

### Ошибка входа в Threads

```
Login error: Invalid credentials
```

**Решение**: Проверьте username и password в config.json

### Нет найденных постов

```
⚠️  No posts found
```

**Решение**: Измените хэштеги или ключевые слова в конфиге

## 🔒 Безопасность

- **Не коммитьте** config.json с реальными учётными данными
- Используйте переменные окружения для чувствительных данных:

```python
import os
from dotenv import load_dotenv

load_dotenv()
config["account"]["username"] = os.getenv("THREADS_USERNAME")
config["account"]["password"] = os.getenv("THREADS_PASSWORD")
```

## 📝 Лицензия

MIT

## 🤝 Благодарности

- [threads-api](https://github.com/Danie1/threads-api) - Python клиент для Threads
- [Ollama](https://ollama.ai/) - локальные LLM
- [GPT4All](https://www.nomic.ai/gpt4all) - локальные модели
