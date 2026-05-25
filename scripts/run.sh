#!/usr/bin/env bash
# Content Factory — точка входа
# Использование: ./scripts/run.sh --topic "..." --title "..." --slug "..." --query "..."

set -e
cd "$(dirname "$0")/.."

python3 scripts/orchestrator.py "$@"
