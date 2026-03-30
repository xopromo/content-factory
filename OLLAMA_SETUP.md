# 🚀 Ollama Setup: Бесплатная локальная эволюция

Используем **Ollama** вместо платного Claude API!

---

## Установка Ollama

### На Linux/Mac:
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### На Windows:
Скачай с https://ollama.ai/download

### Проверка установки:
```bash
ollama --version
# ollama version is 0.1.0
```

---

## Запуск Ollama

### Вариант 1: Фоновый режим (рекомендуется)
```bash
# Запустить Ollama фоном (один раз)
ollama serve &
```

### Вариант 2: В отдельном терминале
```bash
# Терминал 1
ollama serve

# Терминал 2 (в другом окне)
./evolve-freelancer.sh
```

---

## Выбор модели

### Бесплатные модели в Ollama:

| Модель | Размер | Скорость | Качество | Команда |
|--------|--------|----------|----------|---------|
| **Mistral** | 4GB | ⚡⚡ Быстро | ⭐⭐⭐⭐ Отлично | `ollama pull mistral` |
| **Neural Chat** | 3GB | ⚡⚡⚡ Очень быстро | ⭐⭐⭐ Хорошо | `ollama pull neural-chat` |
| **Llama 2** | 7GB | ⚡ Нормально | ⭐⭐⭐⭐ Отлично | `ollama pull llama2` |
| **Dolphin Mixtral** | 26GB | ⚡ Нормально | ⭐⭐⭐⭐⭐ Лучше всех | `ollama pull dolphin-mixtral` |

### Рекомендуемая конфигурация:
```bash
# Скачать Mistral (лучший баланс скорости и качества)
ollama pull mistral

# Проверить что скачалась
ollama list
# NAME              ID              SIZE   MODIFIED
# mistral:latest    2e405c...       4.1GB  2 hours ago
```

---

## Настройка фрилансера

### Текущая конфигурация (`freelancer_a_evolve.py`):
```python
OLLAMA_MODEL = "mistral"              # ← Измени если надо
OLLAMA_BASE_URL = "http://localhost:11434"  # ← Стандартный адрес
```

### Переключиться на другую модель:
```python
# В freelancer_a_evolve.py, строка ~12
OLLAMA_MODEL = "llama2"  # или "neural-chat", "dolphin-mixtral"
```

---

## Запуск эволюции с Ollama

### Шаг 1: Убедиться что Ollama запущена
```bash
# Проверка
curl http://localhost:11434/api/tags
# Должно вернуть список моделей

# Если не работает → запустить
ollama serve &
sleep 2  # Ждем пока запустится
```

### Шаг 2: Запустить эволюцию
```bash
./evolve-freelancer.sh
```

### Результат:
```
======================================================================
🚀 A-EVOLVE: VK Targeting Insights Freelancer Evolution
======================================================================

📦 Initializing components...
  ✅ Agent: FreelancerAgent
  ✅ Benchmark: freelancer-insights
  ✅ Ollama available: mistral model

...

[1/5] Task: vk-targeting-001
       🧠 Generating with Ollama/mistral...
       ✅ Got response (245 tokens)
       Score: 0.87 ✅
```

---

## Полная автоматизация

### Создай скрипт запуска с Ollama:

```bash
cat > start-evolution.sh << 'EOF'
#!/bin/bash

echo "🚀 Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

sleep 3

echo "✅ Ollama ready, starting evolution..."
./evolve-freelancer.sh

# Cleanup
kill $OLLAMA_PID 2>/dev/null || true
EOF

chmod +x start-evolution.sh
```

### Использование:
```bash
./start-evolution.sh
# Само запустит Ollama и эволюцию!
```

---

## Мониторинг эволюции

### Во время работы:
```bash
# В другом терминале смотри статус Ollama
ollama list
ollama show mistral
```

### После эволюции:
```bash
# Проверь финальный промпт
cat freelancer_workspace/prompts/system.md

# Посмотри git историю мутаций
git log --oneline -20

# Сравни baseline vs evolved
git diff HEAD~10..HEAD freelancer_workspace/prompts/system.md
```

---

## Troubleshooting

### ❌ "Ollama not available"
```bash
# Проверить запущена ли
curl http://localhost:11434/api/tags

# Если не работает, запустить
ollama serve

# Если ошибка "port already in use", киллить процесс
pkill -f "ollama serve"
ollama serve
```

### ❌ "Model not found: mistral"
```bash
# Скачать модель
ollama pull mistral

# Проверить что скачалась
ollama list
```

### ❌ "Timeout waiting for Ollama"
```bash
# Модель слишком большая? Используй меньше
OLLAMA_MODEL = "neural-chat"  # 3GB вместо 4GB

# Или увеличь timeout в коде
timeout=120  # вместо 60
```

### ❌ Медленная генерация
```bash
# Используй более легкую модель
ollama pull neural-chat  # Только 3GB

# Или включи GPU acceleration
# (Настраивается в ollama config)
```

---

## Сравнение: Ollama vs Claude API

| Параметр | Ollama | Claude API |
|----------|--------|-----------|
| **Стоимость** | 💰 Бесплатно | 💸💸 $1-100 за запуск |
| **Скорость** | ⚡ 1-2 сек | ⚡ 5-30 сек (сеть) |
| **Зависимость** | 🏠 Локально | 🌐 Интернет + аккаунт |
| **Контроль** | 🎮 Полный | 📋 Ограничен |
| **Масштабируемость** | 📈 Неограниченно | 📊 По квотам |
| **Лучше всего для** | Локальная разработка | Production с гарантией |

---

## Чек-лист

- [ ] Установить Ollama: `curl -fsSL https://ollama.ai/install.sh | sh`
- [ ] Скачать модель: `ollama pull mistral`
- [ ] Запустить Ollama: `ollama serve &`
- [ ] Проверить подключение: `curl http://localhost:11434/api/tags`
- [ ] Запустить эволюцию: `./evolve-freelancer.sh`
- [ ] Смотреть логи и улучшения
- [ ] Проверить финальный промпт: `cat freelancer_workspace/prompts/system.md`
- [ ] Уважать открытый исходный код! ❤️

---

## Что дальше?

**После первой эволюции:**
```bash
# Смотри как улучшился промпт
git diff HEAD~3..HEAD freelancer_workspace/prompts/system.md

# Запусти еще раз (промпт начнет с лучшей версии)
./evolve-freelancer.sh

# Повторяй пока не будет идеально
```

---

**Статус:** ✅ Готово к использованию
**Стоимость:** 🆓 БЕСПЛАТНО
**Качество:** ⭐⭐⭐⭐ Excellent (Mistral)
**Скорость:** ⚡⚡ Fast (4-8 сек на задачу)
