#!/bin/bash

# 🚀 Traffic Specialist Research Agent Launcher
# Запусти этот скрипт для исследования стратегий рекламы

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$PROJECT_DIR/traffic_researcher.py"
LOG_DIR="$PROJECT_DIR/docs/research/logs"

# Проверяем что скрипт существует
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "❌ Error: traffic_researcher.py not found at $PYTHON_SCRIPT"
    exit 1
fi

echo "============================================================"
echo "🚀 TRAFFIC SPECIALIST RESEARCH AGENT"
echo "============================================================"
echo ""
echo "📁 Project directory: $PROJECT_DIR"
echo "📝 Python script: $PYTHON_SCRIPT"
echo "📂 Logs directory: $LOG_DIR"
echo ""
echo "Starting research agent..."
echo "============================================================"
echo ""

# Запускаем агента
python3 "$PYTHON_SCRIPT"

# Проверяем успешность
if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "✅ RESEARCH COMPLETED SUCCESSFULLY"
    echo "============================================================"
    echo ""
    echo "📊 Latest results:"
    if [ -f "$PROJECT_DIR/docs/research/insights/index.json" ]; then
        python3 << 'EOF'
import json
with open('docs/research/insights/index.json') as f:
    data = json.load(f)
    print(f"  Total insights: {data.get('total_insights', 0)}")
    print(f"  Last updated: {data.get('last_updated', 'N/A')}")

    # Группируем по платформам
    by_platform = {}
    for insight in data.get('insights', []):
        platform = insight.get('platform')
        if platform not in by_platform:
            by_platform[platform] = 0
        by_platform[platform] += 1

    if by_platform:
        print("\n  Insights by platform:")
        for platform, count in sorted(by_platform.items()):
            print(f"    {platform}: {count}")
EOF
    fi
    echo ""
    echo "📱 View results: Open docs/traffic-research.html in your browser"
    echo ""
else
    echo ""
    echo "❌ Research failed with error code: $?"
    echo ""
    exit 1
fi
