# 🧪 Тестирование Threads Comment Agent

## Быстрая проверка установки

```bash
cd threads_comment_agent
python test_setup.py
```

**Вывод:**
- ✅ Python версия
- ✅ Установленные зависимости
- ✅ Конфигурация
- ✅ Ollama подключение
- ✅ Модули проекта

## Детальная диагностика компонентов

```bash
python test_components.py
```

**Проверяет:**
- 📝 Загрузка config.json
- 🚀 Подключение к Ollama
- 🤖 Генерация комментариев
- 📋 Шаблоны комментариев
- 🔍 Фильтры постов
- 📅 Расписание запуска

## Пошаговая проверка

### Шаг 1: Установка зависимостей

```bash
pip install -r requirements.txt
```

Проверка:
```bash
python -c "import threads_api; import requests; print('✅ OK')"
```

### Шаг 2: Установка Ollama (опционально)

```bash
# Загрузите https://ollama.ai

# Запустите Ollama
ollama serve

# В другом терминале загрузите модель
ollama pull mistral
```

Проверка:
```bash
curl http://localhost:11434/api/tags
```

### Шаг 3: Настройка config.json

```json
{
  "account": {
    "username": "your_username",
    "password": "your_password"
  },
  "search": {
    "hashtags": ["#AI"],
    "limit": 2
  }
}
```

Проверка:
```bash
python -c "import json; json.load(open('config.json'))" && echo '✅ JSON valid'
```

### Шаг 4: Тестирование компонентов

```bash
# Проверить всё
python test_setup.py

# Детальная диагностика
python test_components.py
```

## Пример работы

### Минимальный тест

```bash
python agent.py --mode manual --hashtag "#Test"
```

**Ожидаемый вывод:**
```
🤖 Threads Comment Agent - Mode: MANUAL
⏰ Started at 2024-01-15 14:30:00

✅ Logged in as @your_username

🔍 Searching for posts with #Test...
(поиск постов...)

✅ Commented on post by @author1
   Comment: Интересно! Отличный контент...

📊 Session summary: 1 comments posted
```

### Тест с разными параметрами

```bash
# Другой хэштег
python agent.py --mode manual --hashtag "#Python"

# Другой тон
python agent.py --mode manual --tone professional

# Свой конфиг
python agent.py --mode manual --config my_config.json
```

## Что тестировать

### ✅ Установка
- [ ] Python 3.8+
- [ ] threads-api установлена
- [ ] requests установлена
- [ ] config.json валидный JSON

### ✅ Конфигурация
- [ ] username и password установлены
- [ ] hashtags определены
- [ ] model выбран (ollama или gpt4all)
- [ ] templates содержат {comment}

### ✅ Ollama (если используется)
- [ ] Ollama запущена (localhost:11434)
- [ ] Модель загружена
- [ ] API отвечает на запросы

### ✅ Функциональность
- [ ] Агент логинится в Threads
- [ ] Находит посты по хэштегам
- [ ] Генерирует комментарии
- [ ] Постит комментарии успешно

## Типичные ошибки и решения

### ❌ "ModuleNotFoundError: No module named 'threads_api'"

```bash
pip install threads-api
```

### ❌ "Ollama connection error"

```bash
# Убедитесь что Ollama запущена
ollama serve

# Проверьте URL в config.json
curl http://localhost:11434/api/tags
```

### ❌ "Login error: Invalid credentials"

```bash
# Проверьте username и password в config.json
# Используйте пароль, не 2FA
# Убедитесь что аккаунт не заблокирован
```

### ❌ "No posts found"

```bash
# Попробуйте другие хэштеги
python agent.py --mode manual --hashtag "#AI"

# Проверьте что хэштег популярен
# Увеличьте limit в search конфиге
```

### ❌ "Failed to comment on post"

```bash
# Проверьте rate limiting (максимум комментариев/день)
# Проверьте что у вас есть разрешение комментировать
# Проверьте длину комментария (max_length в конфиге)
```

## Логирование

### Включить debug режим

Отредактируйте `agent.py` и добавьте:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Проверить логи

```bash
python agent.py --mode manual 2>&1 | tee agent.log
```

## Performance тест

```bash
import time
from agent import ThreadsCommentAgent

agent = ThreadsCommentAgent()
start = time.time()

# Тест
await agent._search_and_comment()

elapsed = time.time() - start
print(f"⏱️  Time: {elapsed:.2f}s")
```

## Автоматизированные тесты

```bash
# Запустить все тесты
python -m pytest tests/ -v

# Конкретный тест
python -m pytest tests/test_models.py -v
```

## Чек-лист перед использованием

- [ ] `python test_setup.py` - ✅
- [ ] `python test_components.py` - ✅
- [ ] `python agent.py --mode manual` - успешно запущен
- [ ] Первый комментарий постился в Threads
- [ ] Config.json сохранён с реальными данными
- [ ] Ollama работает (если используется)

## Успешная проверка

Если вы видите:

```
🎉 Все тесты пройдены! Можно использовать агент

Начать работу:
  $ python agent.py --mode manual
  $ python agent.py --mode manual --hashtag '#Python'
  $ python agent.py --mode manual --tone professional
```

✅ **Агент готов к использованию!**
