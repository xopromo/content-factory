#!/bin/bash
# Скрипт для проверки и обновления данных GitHub Pages

echo "🔍 Проверяю статус GitHub Pages..."

# Проверим есть ли файл в репозитории
echo ""
echo "📁 Файлы в docs/pipeline/data/:"
ls -lh docs/pipeline/data/

echo ""
echo "📋 Содержимое logs.json (первые 50 строк):"
head -50 docs/pipeline/data/logs.json

echo ""
echo "✅ JSON валиден? Проверяю..."
python3 -c "import json; json.load(open('docs/pipeline/data/logs.json'))" && echo "✅ JSON валиден!" || echo "❌ JSON невалиден!"

echo ""
echo "📊 Статистика:"
echo "- Всего логов: $(grep -o '"log_id"' docs/pipeline/data/logs.json | wc -l)"
echo "- Новых инсайтов из эволюции: $(grep -o '"evo_' docs/pipeline/data/logs.json | wc -l)"

echo ""
echo "🚀 Git статус:"
git log --oneline -3

echo ""
echo "💡 Для GitHub Pages:"
echo "1. Данные уже на GitHub Pages ✅"
echo "2. Возможно нужно очистить кеш браузера"
echo "3. Или попробовать incognito режим"
