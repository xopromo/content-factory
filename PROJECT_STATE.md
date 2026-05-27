# PROJECT STATE — Content Factory SEO/GEO
> Документ для восстановления контекста после компактинга чата.
> Обновлять при каждом значимом решении.
> Последнее обновление: 2026-05-27

---

## Что строим и зачем

**Цель:** Автономная система генерации SEO+GEO-статей на основе базы знаний автора («Второй мозг»).

**Ключевая идея:** Статьи должны содержать реальный опыт автора (кейсы, числа, личная позиция) — не рерайт интернета. Для этого нужна база знаний `knowledge/`, которую автор наполняет голосовыми заметками.

**GEO (Generative Engine Optimization)** — оптимизация под ИИ-поисковики (Perplexity, ChatGPT Search, Google AI Overview). Ключевой принцип: первые предложения каждого раздела должны быть самодостаточными ответами на вопрос заголовка.

---

## Архитектура (рой из 9 субагентов, 14 шагов)

```
Пользователь задаёт тему
        ↓
lead-orchestrator    — читает feedback, создаёт план в plans/
        ↓
knowledge-retriever  — ищет релевантные фрагменты в knowledge/
        ↓
web-researcher       — собирает данные из документации и GitHub
        ↓
⏸ HUMAN REVIEW #1   — пользователь утверждает структуру
        ↓
content-writer       — пишет черновик поблочно (2 итерации)
        ↓
diagram-illustrator  — создаёт Mermaid-диаграммы
        ↓
seo-geo-optimizer    — LSI-ключи + AEO-форматирование + Schema.org JSON-LD
        ↓
geo-emulator         — симулирует ИИ-поисковик, проверяет цитируемость
        ↓
editor-critic        — финальный аудит качества (5 критериев)
        ↓
⏸ HUMAN REVIEW #2   — пользователь утверждает статью
        ↓
deployer-publisher   — коммит в git, публикация в docs/articles/
```

---

## Структура директорий (Второй мозг)

```
content-factory/
├── CLAUDE.md                  # маршрутизатор контекста для всех агентов
├── PROJECT_STATE.md           # этот файл
├── .env                       # секреты (не в git!)
├── .env.example               # шаблон для .env
│
├── business/
│   ├── products.md            # продукты/услуги/офферы — НЕ ЗАПОЛНЕН
│   └── audience.md            # аватары ЦА — НЕ ЗАПОЛНЕН
│
├── ai-clone/
│   ├── rules.md               # Tone of Voice, стоп-слова, стиль автора
│   └── feedback/              # лог ошибок для самообучения
│       └── _TEMPLATE.md       # шаблон фиксации ошибки
│
├── knowledge/                 # ПУСТАЯ — главный приоритет для заполнения
│   └── voice/                 # сюда падают транскрипты голосовых заметок
│
├── plans/
│   └── _TEMPLATE.md           # чек-лист 14 шагов генерации
│
├── retrospectives/
│   └── _TEMPLATE.md           # шаблон метрик после публикации
│
└── scripts/
    ├── orchestrator.py        # главный пайплайн 14 шагов
    ├── knowledge_search.py    # ripgrep-поиск по knowledge/
    ├── agent_prompts.py       # системные промпты для всех 9 субагентов
    ├── telegram_notifier.py   # уведомления в Telegram по каждому шагу
    ├── voice_bot.py           # Telegram-бот для голосовых заметок
    └── run.sh                 # точка входа оркестратора
```

---

## Текущая ветка разработки

**Ветка:** `claude/vigilant-einstein-hPa8u`
**Статус:** не смерджена в main
**В main:** старая система (traffic research, chelyabinsk news — работают по расписанию через GitHub Actions)

Мерджить в main только после:
1. Заполнения `knowledge/` и `business/`
2. Успешного тестового прогона оркестратора

---

## Голосовой бот (voice_bot.py)

**Зачем:** самый быстрый способ наполнять `knowledge/` — наговорить голосовое в Telegram.

**Как работает:**
1. Отправляешь голосовое боту в Telegram
2. Groq Whisper транскрибирует (~5 сек на минуту речи)
3. Бот показывает транскрипт и предлагает выбрать категорию
4. Файл сохраняется в `knowledge/voice/YYYY-MM-DD_HH-MM_категория.md`

**Категории заметок:**
- 💼 Кейс — реальный результат с числами
- 💡 Инсайт — паттерн, открытие
- 📋 Гайд — пошаговая инструкция
- 🎯 Стратегия — рассуждения о подходе
- ❓ Гипотеза — идея для проверки
- 📝 Просто мысль — всё остальное

**Переменные окружения (в .env):**
```
TG_BOT_TOKEN=   # от @BotFather в Telegram
TG_CHAT_ID=     # свой id от @userinfobot
GROQ_KEY=       # от console.groq.com (бесплатно, ключи уже есть)
```

**Запуск:**
```bash
python3 scripts/voice_bot.py
```

**Где хостить:**
- **Render.com** (бесплатно, без карты) — worker service, работает 24/7
- Файлы сохраняются не на диск сервера, а прямо в GitHub репозиторий через GitHub API
- Нужен дополнительный ключ: `GITHUB_TOKEN` (Personal Access Token, права `contents:write`)
- Конфиг деплоя: `render.yaml` в корне репо

**Как задеплоить на Render:**
1. render.com → New → Blueprint → подключить репо xopromo/content-factory
2. Render найдёт `render.yaml` автоматически
3. В Environment Variables добавить: TG_BOT_TOKEN, GROQ_KEY, TG_CHAT_ID, GITHUB_TOKEN
4. Deploy — бот онлайн

**Как получить GITHUB_TOKEN:**
GitHub → Settings → Developer settings → Personal access tokens → Fine-grained
Права: Repository → xopromo/content-factory → Contents: Read and Write

---

## Что нужно установить

```bash
pip install python-telegram-bot groq ddgs requests trafilatura
```

Для поиска в knowledge/ нужен ripgrep:
```bash
# Ubuntu/Debian
apt install ripgrep
# Mac
brew install ripgrep
```

---

## Приоритеты — что делать дальше

### Приоритет 1 — наполнить knowledge/ (БЛОКЕР)
Без базы знаний `knowledge-retriever` возвращает пустой пакет → статьи без личного опыта автора.

**Варианты (по скорости):**
1. Экспорт Telegram-канала: Desktop → `···` → Экспорт → Plain text → кинуть в `knowledge/`
2. Голосовые заметки через `voice_bot.py` (запустить локально)
3. Скопировать лучшие посты/статьи вручную

**Формат:** любые `.md` или `.txt` файлы, структура папок произвольная.
Рекомендуемая структура:
```
knowledge/
  cases/     # кейсы с числами
  guides/    # гайды и инструкции
  voice/     # транскрипты голосовых (сюда пишет бот)
  posts/     # посты из соцсетей
```

### Приоритет 2 — заполнить business/
- `business/products.md` — что продаём, цены, офферы, УТП
- `business/audience.md` — кто покупает, боли, поисковые запросы

### Приоритет 3 — тестовый прогон оркестратора
```bash
./scripts/run.sh \
  --topic "VK таргетинг 2026" \
  --title "VK таргетинг: полный гайд по настройке аудиторий" \
  --slug "vk-targeting-2026" \
  --query "как настроить таргет в ВК в 2026 году"
```

---

## Feedback Loop — механика самообучения

При обнаружении ошибки в тексте:
1. Создать файл `ai-clone/feedback/YYYY-MM-DD_описание.md`
2. Шаблон: `ai-clone/feedback/_TEMPLATE.md`
3. Оркестратор перед каждым запуском читает все файлы из `feedback/` и передаёт как жёсткие ограничения всем субагентам

---

## Важные детали и нюансы

- **ddgs** — пакет для DuckDuckGo (не `duckduckgo_search`)
- **Groq Whisper** — модель `whisper-large-v3-turbo`, язык `ru`
- **GitHub Actions** уже работают на `main`: traffic research (каждый день 9:00 UTC) и chelyabinsk news (каждые 6 часов) — не трогать
- **GitHub Pages** обслуживается из `main/docs/` — туда публикуются готовые статьи
- **Human-in-the-Loop:** шаг 4 (структура) и шаг 12 (перед публикацией) — система ждёт подтверждения
- `.env` уже в `.gitignore` — секреты не попадут в репозиторий
- Рабочая ветка `claude/vigilant-einstein-hPa8u` — вся новая разработка только туда
