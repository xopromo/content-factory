# Learning Rules — Автоматическое обучение на обратной связи

> Правила, генерируемые на основе коррекций пользователя. Обновляются автоматически скриптом `scripts/feedback_learner.py`.

## Формат правил
```
{
  "rule_id": "уникальный_идентификатор",
  "trigger": "триггерная фраза или паттерн (regex)",
  "action": "что сделать при срабатывании",
  "severity": "CRITICAL|WARNING|INFO",
  "source": "источник обратной связи (например, user_feedback_2026-06-22)",
  "applied_to": ["content-writer", "editor-critic", "entity-validator"]
}
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
    "applied_to": [
      "entity-validator",
      "content-writer"
    ]
  },
  {
    "rule_id": "lr-002",
    "trigger": "запомни: (.+?) — это ошибка, правильно (.+?)",
    "action": "Добавить правило замены в learning_rules.md и обновить knowledge/",
    "severity": "INFO",
    "source": "user_feedback_2026-06-22",
    "applied_to": [
      "feedback_learner"
    ]
  },
  {
    "rule_id": "lr-06220045",
    "trigger": "Devika|devika|Devika",
    "action": "Заменить на 'Devin' и заблокировать статью для проверки",
    "severity": "CRITICAL",
    "source": "user_feedback_2026-06-22",
    "applied_to": [
      "entity-validator",
      "content-writer"
    ]
  },
  {
    "rule_id": "lr-06220045",
    "trigger": "Devika|devika|Devika",
    "action": "Заменить на 'Devin' и заблокировать статью для проверки",
    "severity": "CRITICAL",
    "source": "user_feedback_2026-06-22",
    "applied_to": [
      "entity-validator",
      "content-writer"
    ]
  }
]
```

## Как использовать
1. **Entity-validator**: Проверяет все capitalized phrases против триггеров с severity=CRITICAL.
2. **Content-writer**: Использует правила для автокоррекции при генерации текста.
3. **Feedback_learner**: Парсит обратную связь и добавляет новые правила.

---
**Последнее обновление**: 2026-06-22 (автоматически)