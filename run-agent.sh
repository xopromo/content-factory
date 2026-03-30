#!/bin/bash
# Universal agent runner - automatically activates venv and runs any agent script

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"
PYTHON="$VENV_PATH/bin/python3"

# Check if venv exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "📝 Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
    echo "✅ Virtual environment created"
    echo ""
fi

# Check if Python exists in venv
if [ ! -f "$PYTHON" ]; then
    echo "❌ Python not found in venv"
    exit 1
fi

# Get the script to run from argument or use default
SCRIPT_TO_RUN="${1:-run_freelancer_evolution.py}"

# Check if script exists
if [ ! -f "$SCRIPT_DIR/$SCRIPT_TO_RUN" ]; then
    echo "❌ Script not found: $SCRIPT_TO_RUN"
    echo ""
    echo "Usage: ./run-agent.sh [script_name.py]"
    echo ""
    echo "Available scripts:"
    ls -1 "$SCRIPT_DIR"/*.py 2>/dev/null | xargs -n1 basename || echo "  (no Python scripts found)"
    exit 1
fi

# Run the script with venv Python
echo "🚀 Running: $SCRIPT_TO_RUN"
echo "📦 Using: $PYTHON"
echo "=========================================="
echo ""

"$PYTHON" "$SCRIPT_DIR/$SCRIPT_TO_RUN" "${@:2}"
