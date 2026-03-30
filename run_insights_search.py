#!/usr/bin/env python3
"""Запускает цикл поиска инсайтов про рекламу в ВК"""

import json
from pathlib import Path
from datetime import datetime
from freelancer_a_evolve import FreelancerAgent

# Задачи для поиска инсайтов
SEARCH_TASKS = [
    "Найди ТОП-5 самых эффективных стратегий таргетирования в ВК для 2026 года",
    "Какие ошибки делают новички при настройке таргета в ВК и как их избежать?",
    "Какие необычные инсайты про поведение пользователей ВК помогают повысить ROAS?",
    "Как оптимизировать креатив для ВК чтобы получить максимальный CTR?",
    "Какие новые фишки в ВК Ads появились в 2026 и как их использовать для рекламы?"
]

def main():
    print("="*70)
    print("🔍 ПОИСК ИНСАЙТОВ ПРО РЕКЛАМУ В ВК")
    print("="*70)
    print(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📋 Задач для поиска: {len(SEARCH_TASKS)}\n")

    # Инициализируем агента
    workspace_path = Path("freelancer_workspace").resolve()
    agent = FreelancerAgent(workspace_path=workspace_path)

    insights_found = []
    
    for idx, task in enumerate(SEARCH_TASKS, 1):
        print(f"\n{'='*70}")
        print(f"ЗАДАЧА {idx}/{len(SEARCH_TASKS)}")
        print(f"{'='*70}")
        print(f"📌 {task}\n")
        
        try:
            # Запускаем агента на задачу
            result = agent.solve(task)
            
            print(f"✅ Результат найден!\n")
            print(f"📝 Инсайты:\n{result[:500]}...\n" if len(result) > 500 else f"📝 Инсайты:\n{result}\n")
            
            insights_found.append({
                "task_id": f"search_{idx:03d}",
                "timestamp": datetime.now().isoformat(),
                "task": task,
                "result": result,
                "length": len(result)
            })
            
        except Exception as e:
            print(f"❌ Ошибка: {e}\n")
            insights_found.append({
                "task_id": f"search_{idx:03d}",
                "timestamp": datetime.now().isoformat(),
                "task": task,
                "error": str(e),
                "result": None
            })

    # Логируем результаты в JSON
    log_file = Path("insights_search_log.jsonl")
    
    print(f"\n{'='*70}")
    print("📊 РЕЗУЛЬТАТЫ ПОИСКА")
    print(f"{'='*70}")
    print(f"✅ Успешных поисков: {sum(1 for i in insights_found if 'result' in i and i['result'])}")
    print(f"❌ Ошибок: {sum(1 for i in insights_found if 'error' in i)}")
    print(f"📝 Всего символов найдено: {sum(i.get('length', 0) for i in insights_found)}")
    
    # Сохраняем логи
    with open(log_file, "a") as f:
        for insight in insights_found:
            f.write(json.dumps(insight, ensure_ascii=False) + "\n")
    
    print(f"\n💾 Логи сохранены в: {log_file}")
    print(f"⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n{'='*70}")
    print("✨ ЦИКЛ ПОИСКА ЗАВЕРШЕН!")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
