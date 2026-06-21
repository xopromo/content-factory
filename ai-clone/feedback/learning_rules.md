# Learning Rules — Автоматически генерируемые правила обучения

> Формат: JSON-массив объектов. Обновляется скриптом `feedback_learner.py`.
> Правила применяются в пайплайне: entity-validator, content-writer, editor-critic.

## Шаблон правил
```json
[
  {
    "rule_id": "lr-XXX",
    "trigger": "строка или regex для поиска",
    "action": "что сделать при срабатывании",
    "severity": "CRITICAL|WARNING|INFO",
    "source": "источник правила (например, user_feedback_YYYY-MM-DD)",
    "applied_to": ["список инструментов, где применяется"],
    "created_at": "YYYY-MM-DD HH:MM:SS",
    "updated_at": "YYYY-MM-DD HH:MM:SS"
  }
]
```

## Примеры правил
```json
[
  {
    "rule_id": "lr-001",
    "trigger": "Devika|Devica|Devika AI",
    "action": "Заменить на 'Devin' и заблокировать статью для проверки",
    "severity": "CRITICAL",
    "source": "user_feedback_2026-05-27",
    "applied_to": ["entity-validator", "content-writer"],
    "created_at": "2026-06-22 00:00:00",
    "updated_at": "2026-06-22 00:00:00"
  }
]
```

## Логи обновлений
- 2026-06-22: Создан файл. Добавлен шаблон и пример правила.