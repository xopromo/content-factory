#!/bin/bash

# 🤖 Agent Generator Script
# Быстрое создание новых агентов со всеми best practices
#
# Usage: bash create-agent.sh "agent-name" "Description of what agent does"
# Example: bash create-agent.sh "optimizer" "Оптимизирует код на производительность"

set -e

NAME="${1:-}"
DESCRIPTION="${2:-}"

# Validation
if [ -z "$NAME" ] || [ -z "$DESCRIPTION" ]; then
  echo "❌ Usage: $0 \"agent-name\" \"Description\""
  echo ""
  echo "Examples:"
  echo "  bash create-agent.sh \"optimizer\" \"Оптимизирует код\""
  echo "  bash create-agent.sh \"debugger\" \"Найди и исправь баги\""
  exit 1
fi

# Normalize name (lowercase, replace spaces with hyphens)
NAME=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')

AGENT_DIR=".claude/agents/$NAME"

# Check if agent already exists
if [ -d "$AGENT_DIR" ]; then
  echo "❌ Agent '$NAME' already exists at $AGENT_DIR"
  exit 1
fi

echo "🤖 Creating new agent: $NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create directory
mkdir -p "$AGENT_DIR"
echo "✅ Created directory: $AGENT_DIR"

# Create agent config file from template
cat > "$AGENT_DIR/$NAME.md" << 'AGENT_EOF'
---
name: __AGENT_NAME__
description: __AGENT_DESCRIPTION__
tools: Read, Grep, Glob, Bash, WebFetch, WebSearch
model: haiku
memory: project
effort: medium
maxTurns: 10
background: false
config:
  mode: budget
  search: duckduckgo
  cost: "$0.00"

# НАСЛЕДУЕТ ВСЕ ЛУЧШИЕ ПРАКТИКИ ИЗ:
# - base-config.yml (глобальные настройки)
# - _agent-defaults.md (стандартные инструкции)
# - GUIDELINES.md (правила для всех агентов)
---

# 🎯 __AGENT_NAME__ Agent

**⚠️ Главное правило: Отвечай ВСЕГДА простым языком на русском. Без сложного жаргона.**

Ты [СПЕЦИАЛИЗАЦИЯ]. Твоя основная задача — [ГЛАВНАЯ_ЦЕЛЬ].

## 🛠️ НАСЛЕДУЕМЫЕ НАВЫКИ

✅ **Поиск:**
- DuckDuckGo (бесплатно через WebSearch)
- WebFetch для загрузки и очистки страниц
- Без лимитов на запросы

✅ **LLM (бесплатно):**
- Ollama mistral локально ($0.00)
- Или neural-chat для критического анализа
- Неограниченное использование

✅ **Инструменты:**
- Read, Grep, Glob (локальные файлы)
- Bash (выполнение команд)
- WebFetch, WebSearch (интернет)

✅ **Фичи:**
- Взаимодействие с другими агентами
- Сохранение в MEMORY.md
- Учёт стоимости токенов
- Получение всех будущих фич автоматически

## 🎯 Специфичные инструкции для этого агента

[ЗАПОЛНИ ЗДЕСЬ СПЕЦИАЛЬНЫЕ ИНСТРУКЦИИ]

### При запуске:

1. [ШАГ 1]
2. [ШАГ 2]
3. [ШАГ 3]

### Входящие данные

[От каких файлов/агентов получаешь информацию]

Примеры:
- RESEARCH.md (от researcher)
- BRAINSTORM.md (от brainstormer)
- Локальные файлы в src/

### Исходящие данные

[Какие файлы/результаты ты создаёшь]

Примеры:
- CRITIQUE.md (для следующего агента)
- MEMORY.md (история результатов)
- output.json (структурированные данные)

## 📋 Формат ответа

```markdown
## [Название результата]

### [Секция 1]
[Описание с примерами]

### [Секция 2]
[Описание с примерами]

---

**Стоимость**:
- Input tokens: XXX
- Output tokens: XXX
- Примерная цена: $X.XX
```

## 🔄 Взаимодействие с другими агентами

```
← Входящие данные от: [агент1, агент2]
→ Выходящие данные в: [агент3, файл]
```

Примеры:
```
← researcher: RESEARCH.md
← brainstormer: BRAINSTORM.md
→ critic: CRITIQUE.md
```

---

## 📚 Документация

Наследует лучшие практики из:
- `.claude/agents/base-config.yml` — глобальные настройки
- `.claude/agents/_agent-defaults.md` — стандартные инструкции
- `.claude/agents/GUIDELINES.md` — правила для всех

---

**Создан**: __CREATION_DATE__
**Режим**: Budget (Ollama + DuckDuckGo, $0.00)
**Наследование**: ✅ Автоматическое
AGENT_EOF

# Replace placeholders
CREATION_DATE=$(date '+%Y-%m-%d')
sed -i "s/__AGENT_NAME__/$NAME/g" "$AGENT_DIR/$NAME.md"
sed -i "s/__AGENT_DESCRIPTION__/$DESCRIPTION/g" "$AGENT_DIR/$NAME.md"
sed -i "s/__CREATION_DATE__/$CREATION_DATE/g" "$AGENT_DIR/$NAME.md"

echo "✅ Created agent config: $AGENT_DIR/$NAME.md"

# Create MEMORY.md
cat > "$AGENT_DIR/MEMORY.md" << EOF
# 📝 Memory: $NAME

**Агент**: $NAME
**Описание**: $DESCRIPTION
**Создан**: $CREATION_DATE
**Статус**: 🟢 Готов к использованию

## 🔄 История запусков

### Ожидание первого запуска...

[Будет заполняться автоматически после каждого использования]

---

## 📊 Статистика

- Всего запусков: 0
- Всего токенов: 0
- Всего стоимости: \$0.00 (Ollama)

---

## 📌 Ключевые выводы

[Будут обновляться после каждого запуска]

---

**Последнее обновление**: $CREATION_DATE
EOF

echo "✅ Created memory file: $AGENT_DIR/MEMORY.md"

# Create examples file (optional)
cat > "$AGENT_DIR/examples.md" << EOF
# 📚 Примеры использования

## Пример 1

**Запрос:**
\`\`\`
@"$NAME" [твой запрос здесь]
\`\`\`

**Ожидаемый результат:**
[Опиши что должно получиться]

---

## Пример 2

**Запрос:**
\`\`\`
@"$NAME" [другой запрос]
\`\`\`

**Ожидаемый результат:**
[Результат]

---

**Добавляй примеры после первого использования агента**
EOF

echo "✅ Created examples file: $AGENT_DIR/examples.md"

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Agent '$NAME' successfully created!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📁 Files created:"
echo "   ✓ $AGENT_DIR/$NAME.md (конфиг + инструкции)"
echo "   ✓ $AGENT_DIR/MEMORY.md (история результатов)"
echo "   ✓ $AGENT_DIR/examples.md (примеры использования)"
echo ""
echo "🎯 Next steps:"
echo "   1. Отредактируй $AGENT_DIR/$NAME.md"
echo "   2. Заполни специфичные инструкции для агента"
echo "   3. Запусти: @\"$NAME\" [твой запрос]"
echo ""
echo "🧬 Агент получит автоматически:"
echo "   ✅ Бесплатный поиск (DuckDuckGo)"
echo "   ✅ Бесплатные нейросети (Ollama: mistral/neural-chat)"
echo "   ✅ Все наследуемые навыки из base-config.yml"
echo "   ✅ Все будущие фичи из features.future_v2"
echo ""
echo "💰 Стоимость: \$0.00 (локальные инструменты)"
echo ""
echo "📖 Документация:"
echo "   - .claude/agents/GUIDELINES.md (как создавать агентов)"
echo "   - .claude/agents/base-config.yml (что наследуется)"
echo "   - .claude/agents/_agent-defaults.md (стандартные инструкции)"
echo ""
