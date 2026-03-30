# 🖥️ Persistent Server Setup: Ollama + Agents на расписании

Как настроить агентов так, чтобы они работали на сервере 24/7 по расписанию.

---

## 📐 Архитектура проекта

Проект **уже спроектирован для Ollama**:

```yaml
# .claude/agents/base-config.yml
budget mode:
  llm:
    provider: ollama
    host: http://localhost:11434  ← Ищет здесь Ollama!

  search:
    provider: duckduckgo          ← Бесплатный поиск
```

**Это значит:** Все агенты знают где искать Ollama. Нужна только установка.

---

## 🚀 Шаги установки на persistent сервере

### Шаг 1: Подготовка сервера (один раз)

```bash
# 1. SSH на сервер
ssh user@your.server.com

# 2. Установить Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 3. Скачать модели
ollama pull mistral          # 4GB (основная)
ollama pull neural-chat      # 3GB (анализ)
ollama pull codellama        # 5GB (код)

# 4. Проверить установку
ollama list
# NAME              ID              SIZE
# mistral:latest    ...             4.1GB
# neural-chat:latest ...            3.2GB
# codellama:latest  ...             5.1GB
```

### Шаг 2: Запустить Ollama фоном (один раз)

```bash
# Вариант A: Простой фон (session-зависимый)
ollama serve &

# Вариант B: systemd (рекомендуется)
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl status ollama

# Проверить работает ли
curl http://localhost:11434/api/tags
# Должно вернуть список моделей
```

### Шаг 3: Получить проект

```bash
# Если еще нет
git clone https://github.com/xopromo/content-factory
cd content-factory

# Если уже есть
git pull origin main
```

### Шаг 4: Установить зависимости

```bash
# Python для агентов
python3 -m venv venv
source venv/bin/activate
pip install duckduckgo-search requests beautifulsoup4

# Для A-Evolve
pip install -e /path/to/a-evolve
# или
pip install anthropic  # если используешь Claude API
```

---

## ⏰ Настройка расписания (cron)

### Вариант A: Запускать фрилансера каждые 6 часов

```bash
# Открыть crontab
crontab -e

# Добавить строку
0 */6 * * * cd /home/user/content-factory && ./evolve-freelancer.sh >> /tmp/freelancer.log 2>&1
```

### Вариант B: Запускать pipeline каждый день в 08:00

```bash
# Добавить в crontab
0 8 * * * cd /home/user/content-factory && ./run-agent-pipeline.sh "Анализ трендов таргетирования ВК" budget >> /tmp/pipeline.log 2>&1
```

### Вариант C: Комбо - несколько агентов

```bash
# Фрилансер каждые 6 часов
0 */6 * * * cd /home/user/content-factory && ./evolve-freelancer.sh >> /tmp/freelancer.log 2>&1

# Pipeline каждый день в 08:00
0 8 * * * cd /home/user/content-factory && ./run-agent-pipeline.sh "Тренды" budget >> /tmp/pipeline.log 2>&1

# Pipeline по выходным в 10:00 (расширенный анализ)
0 10 * * 0,6 cd /home/user/content-factory && ./run-agent-pipeline.sh "Глубокий анализ" budget >> /tmp/pipeline_weekend.log 2>&1
```

---

## 🔍 Мониторинг

### Проверить статус Ollama

```bash
# На сервере
curl http://localhost:11434/api/tags
ps aux | grep ollama
systemctl status ollama
```

### Смотреть логи агентов

```bash
# Логи фрилансера
tail -f /tmp/freelancer.log

# Логи pipeline
tail -f /tmp/pipeline.log

# Все логи
tail -f /tmp/*.log
```

### Проверить выполнение cron

```bash
# История выполнения cron
grep CRON /var/log/syslog | tail -20

# Или на macOS
log stream --predicate 'process == "cron"' --level debug
```

---

## 📊 Результаты работы

После запуска агентов будут создаваться:

```
freelancer_workspace/
├── prompts/
│   └── system.md         ← ЭВОЛЮЦИОНИРУЕТ с каждым запуском!
├── memory/
│   └── episodes.jsonl    ← История инсайтов
└── data/
    └── evolution_log.json ← Метрики улучшения

.claude/agents/
├── RESEARCH.md           ← Результаты поиска
├── BRAINSTORM.md         ← Сгенерированные идеи
├── CRITIQUE.md           ← Оценка идей
└── DECISION.md           ← Финальный вердикт

docs/
└── pipeline/
    ├── 1-freelancer.html ← GitHub Pages dashboard
    ├── 2-brainstormer.html
    └── data/results.json
```

---

## 🔧 Troubleshooting

### ❌ "Connection refused" при запуске агента

```bash
# Ollama не запущена
# Решение:
systemctl start ollama
# или
ollama serve &
```

### ❌ "Model not found: mistral"

```bash
# Модель не скачана
# Решение:
ollama pull mistral
ollama list  # проверить что скачалась
```

### ❌ Cron job не выполняется

```bash
# Проверить PATH в crontab
crontab -e
# Убедиться что используется полные пути:

# ❌ НЕПРАВИЛЬНО:
0 8 * * * cd ~/content-factory && ./evolve-freelancer.sh

# ✅ ПРАВИЛЬНО:
0 8 * * * cd /home/user/content-factory && /home/user/content-factory/evolve-freelancer.sh
```

### ❌ Ollama медленная

```bash
# Проверить нагрузку на систему
top
nvidia-smi  # если есть GPU

# Отключить ненужные модели
ollama rm neural-chat  # если не используется
ollama rm codellama

# Проверить память
free -h
```

---

## 📈 Оптимизация

### Для слабого сервера (1-2GB RAM)

```bash
# Использовать только mistral
ollama rm neural-chat codellama

# Настроить параметры в base-config.yml
models:
  default: mistral  # только эта
```

### Для мощного сервера (8GB+ RAM)

```bash
# Добавить больше моделей
ollama pull dolphin-mixtral
ollama pull llama2-uncensored

# Использовать GPU acceleration
# (зависит от видеокарты и CUDA)
```

### Для very frequent runs (много раз в день)

```bash
# Использовать более легкую модель
OLLAMA_MODEL=neural-chat  # 3GB вместо 4GB

# Или ограничить concurrent requests
# (в base-config.yml добавить параллелизм)
```

---

## ✅ Чек-лист завершения

- [ ] SSH доступ к серверу работает
- [ ] Ollama установлена: `ollama --version`
- [ ] Модели скачаны: `ollama list`
- [ ] Ollama работает: `curl http://localhost:11434/api/tags`
- [ ] Проект склонирован: `git clone ...`
- [ ] venv создан и активирован
- [ ] Зависимости установлены: `pip install -r requirements.txt`
- [ ] Скрипты исполняемы: `chmod +x *.sh`
- [ ] Cron задачи добавлены: `crontab -l`
- [ ] Логирование работает: `tail -f /tmp/*.log`
- [ ] GitHub Pages обновляется с результатами
- [ ] Prompt эволюционирует: `git log --oneline`

---

## 🎯 Финальная команда проверки

```bash
# На сервере одна команда проверяет всё:
#!/bin/bash
echo "🔍 System Check:"
echo "✓ Ollama: $(ollama --version 2>/dev/null || echo 'NOT FOUND')"
echo "✓ Models: $(ollama list 2>/dev/null | wc -l)"
echo "✓ Server: $(curl -s http://localhost:11434/api/tags | jq '.models | length') models available"
echo "✓ Git: $(git log --oneline | head -1)"
echo "✓ Python: $(python3 --version)"
echo "✓ Cron jobs: $(crontab -l 2>/dev/null | grep -v '^#' | wc -l)"
echo ""
echo "✅ Ready for autonomous operations!"
```

---

**Статус:** ✅ Готово к использованию на persistent сервере
**Масштабируемость:** Неограниченная (cron может запускать сколько угодно)
**Стоимость:** 0 руб/месяц (только электричество для сервера)
**Maintenance:** Раз в месяц проверить логи
