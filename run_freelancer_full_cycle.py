#!/usr/bin/env python3
"""Полный цикл фрилансера: поиск инсайтов + эволюция промпта"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

def run_command(cmd, name):
    """Запускает команду и выводит результат"""
    print(f"\n{'='*70}")
    print(f"🚀 {name}")
    print(f"{'='*70}\n")

    try:
        result = subprocess.run(cmd, shell=True, capture_output=False, text=True)
        if result.returncode != 0:
            print(f"❌ Ошибка при выполнении: {name}")
            return False
        return True
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

def main():
    print("\n" + "="*70)
    print("🧬 ПОЛНЫЙ ЦИКЛ ФРИЛАНСЕРА")
    print("="*70)
    print(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    steps = [
        ("python3 run_insights_search.py", "ЭТАП 1: Поиск новых инсайтов про рекламу в ВК"),
        ("python3 integrate_new_insights.py", "ЭТАП 2: Интеграция найденных инсайтов на сайт"),
        ("python3 run_freelancer_evolution.py", "ЭТАП 3: Эволюция промпта для улучшения качества"),
    ]

    failed_steps = []

    for cmd, name in steps:
        if not run_command(cmd, name):
            failed_steps.append(name)
            print(f"\n⚠️ Пропускаю остальные этапы из-за ошибки")
            break

    print(f"\n{'='*70}")
    print("📊 ИТОГИ ПОЛНОГО ЦИКЛА")
    print(f"{'='*70}")

    if not failed_steps:
        print("✅ ВСЕ ЭТАПЫ УСПЕШНО ЗАВЕРШЕНЫ!")
        print(f"⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return 0
    else:
        print(f"❌ Ошибки на этапах:")
        for step in failed_steps:
            print(f"   • {step}")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
