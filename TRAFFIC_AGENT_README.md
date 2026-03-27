# 🎯 Traffic Specialist Research Agent - Быстрый старт

Полностью автоматизированный агент для исследования стратегий таргетированной рекламы!

## ⚡ 5 минут на старт

### 1️⃣ Запустить агента (один раз)
```bash
./run-traffic-research.sh
```

**Или прямо через Python:**
```bash
python3 traffic_researcher.py
```

### 2️⃣ Открыть результаты
Откройте в браузере:
```
docs/traffic-research.html
```

### 3️⃣ Изучить логи
Все логи сохраняются в:
```
docs/research/logs/          # Полные логи сессий
docs/research/insights/      # Структурированные инсайты
```

## 📊 Что ты получишь

✅ **10+ инсайтов** о рекламе в каждом запуске
✅ **Подробные логи** с мыслями и действиями агента
✅ **Визуальную панель** со всеми результатами
✅ **JSON индекс** для программной обработки

## 🤖 Как работает агент

1. **Собирает** лайфхаки по VK, Threads, Яндекс Директ
2. **Анализирует** информацию по категориям (таргетинг, бюджет и т.д.)
3. **Логирует** каждый шаг с временными метками
4. **Структурирует** знания в JSON для удобства
5. **Сохраняет** в git pages для долгосрочного хранения

## 🔄 Автоматизация

### На GitHub Actions (рекомендуется)
Агент будет запускаться **каждый день в 09:00 UTC** автоматически!
Просто закомми код и он будет работать. 🚀

Настроено в `.github/workflows/traffic-research.yml`

### На локальной машине (cron)
Добавь в crontab:
```bash
# Каждый день в 09:00
0 9 * * * cd /home/user/content-factory && python3 traffic_researcher.py

# Каждый час
0 * * * * cd /home/user/content-factory && python3 traffic_researcher.py
```

Отредактируй через:
```bash
crontab -e
```

## 📁 Структура проекта

```
traffic_researcher.py          # Основной агент
run-traffic-research.sh        # Скрипт для запуска
docs/
├── traffic-research.html      # Веб-панель 📊
├── TRAFFIC_RESEARCH.md        # Полная документация
└── research/
    ├── logs/
    │   └── session_*.json    # Логи (история действий)
    └── insights/
        ├── insights_*.json   # Инсайты по сессиям
        └── index.json        # Индекс всех инсайтов
.github/workflows/
└── traffic-research.yml      # Автоматизация на GitHub
```

## 💡 Примеры использования

### Пример 1: Одноразовое исследование
```bash
python3 traffic_researcher.py
# ✅ Готово! Посмотри results в docs/research/insights/index.json
```

### Пример 2: С логированием в файл
```bash
python3 traffic_researcher.py | tee traffic_research.log
```

### Пример 3: Интеграция с другим скриптом
```python
from traffic_researcher import TrafficResearchAgent

agent = TrafficResearchAgent()
agent.run()

# Получи результаты
with open('docs/research/insights/index.json') as f:
    import json
    results = json.load(f)
    print(f"Found {results['total_insights']} insights!")
```

## 🎯 Что дальше?

Агент собирает инсайты по:
- **VK**: таргетинг, бюджет, timing
- **Threads**: контент, хэштеги, монетизация
- **Яндекс Директ**: keywords, bidding, фильтрация

Используй эти знания для оптимизации своих кампаний! 📈

## 🔍 Где посмотреть результаты?

### 1. Визуальная панель (самое удобное)
```
Откройте: docs/traffic-research.html
```

### 2. JSON данные (для программистов)
```
docs/research/insights/index.json
```

### 3. Полные логи (для отладки)
```
docs/research/logs/session_*.json
```

## ⚙️ Требования

- Python 3.7+
- Доступ в интернет (для будущих версий)
- Git (опционально, для автоматизации)

## 📞 Помощь

- 📖 Полная документация: `docs/TRAFFIC_RESEARCH.md`
- 🐛 Проблемы? Проверь логи в `docs/research/logs/`
- 💬 Идеи? Открой Issue в GitHub

## 🚀 Будущие возможности

- [ ] Парсинг официальных блогов платформ
- [ ] Анализ реальных кейс-стади
- [ ] Рекомендации по нишам
- [ ] Интеграция с Dashboard'ом
- [ ] Экспорт в Slack/Telegram

---

**Готов начать?** Просто запусти:
```bash
./run-traffic-research.sh
```

Агент начнет исследование 🔍 и сохранит результаты в git pages! 📊
