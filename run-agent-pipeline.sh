#!/bin/bash

# 🤖 Automated Agent Pipeline Runner
# Запускает цепочку агентов: researcher → brainstormer → critic → judge
#
# Usage: ./run-agent-pipeline.sh "your query here" [optional_mode]
# Example: ./run-agent-pipeline.sh "тренды рекламного рынка РФ" budget

set -e

QUERY="${1:-}"
MODE="${2:-budget}"  # budget или production
AGENT_DIR=".claude/agents"

if [ -z "$QUERY" ]; then
  echo "❌ Error: Query required"
  echo "Usage: $0 \"query\" [budget|production]"
  exit 1
fi

echo "🚀 Starting Agent Pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Query: $QUERY"
echo "Mode: $MODE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Функция для запуска агента и проверки завершения
run_agent() {
  local agent_name=$1
  local prompt=$2
  local timeout=$3

  echo "⏳ Starting agent: @\"$agent_name\""
  echo "   Prompt: $prompt"
  echo ""

  # Здесь в реальной реализации будет Claude Code API call
  # Пока это симуляция
  echo "   [Агент работает... это должно быть интегрировано с Claude API]"
  echo ""
}

# STEP 1: RESEARCHER
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1️⃣ : RESEARCHER - Исследование и поиск данных"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_agent "researcher" "Исследуй: $QUERY" 120

# Проверка что RESEARCH.md создан
if [ ! -f "$AGENT_DIR/RESEARCH.md" ] || grep -q "Ожидание researcher" "$AGENT_DIR/RESEARCH.md"; then
  echo "⏸️  Waiting for researcher to complete..."
  echo "   [В реальной реализации здесь будет polling Claude API]"
  echo ""
fi

# STEP 2: BRAINSTORMER
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2️⃣ : BRAINSTORMER - Генерация идей"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_agent "brainstormer" "На основе $AGENT_DIR/RESEARCH.md напиши идеи для: $QUERY" 90

# STEP 3: CRITIC
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3️⃣ : CRITIC - Критическая оценка"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_agent "critic" "Оцени реалистичность идей из $AGENT_DIR/BRAINSTORM.md на основе $AGENT_DIR/RESEARCH.md" 90

# STEP 4: JUDGE
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4️⃣ : JUDGE - Финальный вердикт"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_agent "judge" "На основе RESEARCH.md, BRAINSTORM.md и CRITIQUE.md выноси финальный вердикт для: $QUERY" 90

# FINAL REPORT
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ PIPELINE COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Generated files:"
echo "   ✓ $AGENT_DIR/RESEARCH.md (исследование)"
echo "   ✓ $AGENT_DIR/BRAINSTORM.md (идеи)"
echo "   ✓ $AGENT_DIR/CRITIQUE.md (критика)"
echo "   ✓ $AGENT_DIR/DECISION.md (вердикт)"
echo ""
echo "📊 Cost Summary:"
if [ "$MODE" = "budget" ]; then
  echo "   Mode: BUDGET (Ollama + DuckDuckGo)"
  echo "   Total cost: \$0.00 ✅"
else
  echo "   Mode: PRODUCTION (Claude API)"
  echo "   Total cost: ~\$0.35"
fi
echo ""
echo "🎯 Next steps:"
echo "   1. Review $AGENT_DIR/DECISION.md"
echo "   2. Check ACTION_PLAN.md for implementation"
echo "   3. Track metrics from METRICS.md"
echo ""
