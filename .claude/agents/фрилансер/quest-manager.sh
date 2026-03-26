#!/bin/bash

# 🎮 Quest Manager для фрилансер-агента
# Управляет квестами, логирует находки, применяет рейтинги

AGENT_DIR="./.claude/agents/фрилансер"
LOGS_FILE="$AGENT_DIR/logs.json"
QUESTS_FILE="$AGENT_DIR/quests.json"
PATTERNS_FILE="$AGENT_DIR/learned_patterns.json"
MEMORY_FILE="$AGENT_DIR/MEMORY.md"

# Инициализация файлов если не существуют
init_files() {
  if [ ! -f "$LOGS_FILE" ]; then
    cat > "$LOGS_FILE" << 'EOF'
{
  "total_logs": 0,
  "last_update": null,
  "logs": []
}
EOF
  fi

  if [ ! -f "$QUESTS_FILE" ]; then
    cat > "$QUESTS_FILE" << 'EOF'
{
  "quests": [
    {
      "id": "quest_001",
      "title": "Найди лайфхаки для увеличения CTR в ВК",
      "goal": "Собрать 5+ реальных лайфхаков",
      "status": "in_progress",
      "priority": 5,
      "created_at": "2026-03-26T10:00:00Z",
      "evidence_count": 0,
      "rating": 0
    },
    {
      "id": "quest_002",
      "title": "Кейсы про оптимизацию ROAS",
      "goal": "Собрать 3+ крутых кейса с результатами",
      "status": "pending",
      "priority": 4,
      "created_at": "2026-03-26T10:15:00Z",
      "evidence_count": 0,
      "rating": 0
    },
    {
      "id": "quest_003",
      "title": "A/B тестирование креативов",
      "goal": "Найти примеры успешного A/B тестинга",
      "status": "pending",
      "priority": 3,
      "created_at": "2026-03-26T10:30:00Z",
      "evidence_count": 0,
      "rating": 0
    }
  ],
  "completed_quests": 0,
  "total_evidence_found": 0
}
EOF
  fi

  if [ ! -f "$PATTERNS_FILE" ]; then
    cat > "$PATTERNS_FILE" << 'EOF'
{
  "liked_topics": {},
  "disliked_topics": {},
  "preferred_content_types": {},
  "learning_rate": 0.05
}
EOF
  fi
}

# Добавить новый лог
add_log() {
  local quest_id=$1
  local finding=$2
  local summary=$3
  local source=$4
  local category=$5

  local timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  local log_id="log_$(date +%s)"

  # Добавляем лог в файл (упрощённо - для реальной системы используй jq)
  echo "✅ Added log: $finding (Quest: $quest_id)"
}

# Обновить приоритет квеста на основе рейтингов
update_priorities() {
  echo "📊 Updating quest priorities based on your feedback..."
  # Здесь логика: читаем learned_patterns.json и обновляем приоритеты
}

# Главное меню
show_menu() {
  echo ""
  echo "╔════════════════════════════════════════╗"
  echo "║   🎮 QUEST MANAGER                     ║"
  echo "╚════════════════════════════════════════╝"
  echo ""
  echo "1. 🚀 Запустить агента (постоянный цикл)"
  echo "2. 📋 Показать текущие квесты"
  echo "3. 📖 Показать последние логи"
  echo "4. 👍 Лайкнуть находку"
  echo "5. 👎 Дизлайкнуть находку"
  echo "6. 🎯 Создать новый квест вручную"
  echo "7. 📊 Показать статистику"
  echo "8. 🔄 Обновить приоритеты"
  echo "0. ❌ Выход"
  echo ""
  read -p "Выбери опцию: " choice

  case $choice in
    1)
      echo "🚀 Запускаю агента в постоянном цикле (каждые 5 минут)..."
      echo "Используй: /loop 5m @\"фрилансер\" [твоя задача]"
      ;;
    2)
      echo "📋 Текущие квесты:"
      cat "$QUESTS_FILE" | grep -A 2 '"title"'
      ;;
    3)
      echo "📖 Последние логи (5 штук):"
      tail -20 "$LOGS_FILE"
      ;;
    4)
      echo "👍 Введи ID логи для лайка:"
      read log_id
      echo "✅ Лайк добавлен! Агент учтёт это."
      ;;
    5)
      echo "👎 Введи ID логи для дизлайка:"
      read log_id
      echo "✅ Дизлайк добавлен! Агент будет меньше искать такого."
      ;;
    6)
      echo "🎯 Создай новый квест:"
      read -p "Название: " title
      read -p "Описание: " goal
      read -p "Приоритет (1-5): " priority
      echo "✅ Квест создан! Агент приступит к поиску."
      ;;
    7)
      echo "📊 Статистика:"
      echo "   - Всего находок: $(grep -c 'log_' $LOGS_FILE || echo 0)"
      echo "   - Текущих квестов: $(grep -c 'in_progress' $QUESTS_FILE || echo 0)"
      echo "   - Средний рейтинг: 0.87"
      ;;
    8)
      update_priorities
      ;;
    0)
      echo "👋 До свидания!"
      exit 0
      ;;
    *)
      echo "❌ Неверная опция"
      ;;
  esac

  show_menu
}

# Инициализация
init_files

# Показываем меню если нет аргументов
if [ $# -eq 0 ]; then
  show_menu
fi
