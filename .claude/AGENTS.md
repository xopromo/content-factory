# 🤖 Агенты Content Factory

Три специализированных агента для разных задач. Могут работать вместе.

## 📖 Researcher Agent
**Цель**: Исследование и документирование кодовой базы

### Используй когда:
- Нужно разобраться в архитектуре модуля
- Исследовать паттерны использования
- Найти потенциальные проблемы
- Задокументировать находки

### Пример:
```
@"researcher" изучи архитектуру аутентификации в src/auth/
```

**Память**: `.claude/agents/researcher/RESEARCH.md` — обновляется автоматически

---

## 🔍 Code Reviewer Agent
**Цель**: Проверка кода на качество и безопасность

### Используй когда:
- Завершена разработка — нужна финальная проверка
- Внесены изменения в critical code
- Нужна вторая пара глаз перед mergе
- Проверить security уязвимости

### Пример:
```
@"code-reviewer" проверь последний коммит на security issues
```

**Модель**: Sonnet (оптимальный баланс)
**Разрешения**: Read-only (не может редактировать)

---

## ⚙️ Quality Analyzer Agent
**Цель**: Анализ сложности и качества кода

### Используй когда:
- Нужно улучшить поддерживаемость
- Высокая cyclomatic complexity
- Много дублирования
- Низкое тестовое покрытие

### Пример:
```
@"quality-analyzer" анализируй self-contained компоненты на сложность
```

**Модель**: Opus (для сложного анализа)
**Effort**: High (может потребить много токенов)

---

## 🔄 Взаимодействие между агентами

### Сценарий 1: Full Code Review Cycle
```
1. researcher исследует модуль (понимает архитектуру)
2. code-reviewer проверяет новый код
3. quality-analyzer предлагает улучшения
4. Claude основной диалог координирует результаты
```

### Сценарий 2: Before Merge
```
Claude → "запусти reviewer"
  ↓ получает findings
Claude → "запусти analyzer если критичных issues нет"
  ↓ качественные предложения
Claude → выводит итоговый отчет
```

### Сценарий 3: Scheduled Daily Review
```
# В cron каждый день в 9 AM
/schedule create "Daily Review" "0 9 * * *" --agent code-reviewer
```

---

## 🛠️ Как запустить

### Явно через диалог:
```
@"researcher" исследуй src/api/
```

### Автоматически (Claude сам выбирает):
```
Посмотри на качество нового кода
```
→ Claude выберет code-reviewer или quality-analyzer

### Как основной агент сессии:
```bash
claude --agent researcher
```

### По расписанию:
```
/schedule create "Weekly Quality Check" "0 10 * * 1" --agent quality-analyzer
```

---

## 📋 Память между сессиями

| Агент | Файл памяти | Тип |
|-------|-------------|-----|
| researcher | `.claude/agents/researcher/RESEARCH.md` | Проектная |
| code-reviewer | ~ (текущая сессия) | - |
| quality-analyzer | ~ (текущая сессия) | - |

**Проектная память** (в git) — видна всей команде
**Личная память** (в ~/.claude) — только тебе

---

## ⚙️ Конфигурация

Каждый агент имеет свой `.md` файл в `.claude/agents/[name]/[name].md`

Ключевые параметры:
```yaml
tools: Read, Grep, Bash          # разрешённые инструменты
disallowedTools: Write, Edit     # запрещённые
model: sonnet                    # sonnet/opus/haiku
memory: project                  # project/user/local
effort: high                     # low/medium/high/max
permissionMode: dontAsk          # default/dontAsk/bypassPermissions
```

---

## 🚀 Примеры реальных сценариев

### Сценарий: New Feature Review
```
1. Разработал новый API endpoint
2. researcher → разобрать как работают существующие endpoints
3. code-reviewer → проверить безопасность нового кода
4. quality-analyzer → убедиться что он не усложнил кодовую базу
5. Результат: полная уверенность перед PR
```

### Сценарий: Legacy Refactor
```
1. Хочу рефакторить старый модуль
2. researcher → изучить текущую архитектуру и зависимости
3. quality-analyzer → найти самые проблемные части
4. code-reviewer → валидировать рефакторинг
```

### Сценарий: Continuous Monitoring
```
/schedule create "Daily Check" "0 9 * * *" --agent code-reviewer
→ Каждый день проверяет новые коммиты
→ Если найдены проблемы → webhook уведомление
```

---

**Создано**: 2026-03-26
