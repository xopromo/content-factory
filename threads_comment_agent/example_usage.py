#!/usr/bin/env python3
"""
Примеры использования Threads Comment Agent
"""
import asyncio
import json
from agent import ThreadsCommentAgent


async def example_1_manual_run():
    """Пример 1: Простой ручной запуск"""
    print("=" * 50)
    print("Пример 1: Ручной запуск (один проход)")
    print("=" * 50)

    agent = ThreadsCommentAgent()
    await agent.run(mode="manual")


async def example_2_custom_hashtags():
    """Пример 2: Поиск по кастомным хэштегам"""
    print("\n" + "=" * 50)
    print("Пример 2: Кастомные хэштеги")
    print("=" * 50)

    agent = ThreadsCommentAgent()
    agent.config["search"]["hashtags"] = ["#WebDevelopment", "#JavaScript", "#React"]
    agent.config["search"]["limit"] = 3
    await agent.run(mode="manual")


async def example_3_different_tone():
    """Пример 3: Разные тоны комментариев"""
    print("\n" + "=" * 50)
    print("Пример 3: Разные тоны")
    print("=" * 50)

    agent = ThreadsCommentAgent()

    tones = ["friendly", "professional", "witty"]
    for tone in tones:
        print(f"\n🎯 Tone: {tone}")
        agent.config["comment_generation"]["tone"] = tone
        agent.config["search"]["hashtags"] = ["#AI"]
        agent.config["search"]["limit"] = 1

        # Комментируем только 1 пост для примера
        # await agent.run(mode="manual")


async def example_4_use_gpt4all():
    """Пример 4: Использование GPT4All вместо Ollama"""
    print("\n" + "=" * 50)
    print("Пример 4: GPT4All")
    print("=" * 50)

    agent = ThreadsCommentAgent()
    agent.config["comment_generation"]["model"] = "gpt4all"
    agent.config["comment_generation"]["gpt4all_model"] = "orca-mini"
    await agent.run(mode="manual")


async def example_5_schedule_mode():
    """Пример 5: Режим по расписанию"""
    print("\n" + "=" * 50)
    print("Пример 5: Режим по расписанию (демо)")
    print("=" * 50)

    agent = ThreadsCommentAgent()
    agent.config["scheduling"]["mode"] = "schedule"
    agent.config["scheduling"]["time"] = "14:00"  # Запускается в 14:00

    print("⏰ Агент будет запускаться ежедневно в 14:00")
    print("⚠️  Для тестирования используйте mode='manual'")


async def example_6_realtime_mode():
    """Пример 6: Режим реального времени"""
    print("\n" + "=" * 50)
    print("Пример 6: Режим реального времени (демо)")
    print("=" * 50)

    agent = ThreadsCommentAgent()
    agent.config["scheduling"]["mode"] = "realtime"

    print("🔴 Агент будет проверять новые посты каждые 5 минут")
    print("⚠️  Требуется premium доступ для real-time stream")


def example_7_config_update():
    """Пример 7: Программное обновление конфига"""
    print("\n" + "=" * 50)
    print("Пример 7: Обновление конфига программно")
    print("=" * 50)

    agent = ThreadsCommentAgent()

    # Обновляем параметры
    agent.update_config("search.hashtags", ["#Python", "#ML"])
    agent.update_config("comment_generation.tone", "professional")
    agent.update_config("comment_generation.max_length", 200)

    print("✅ Конфиг обновлен:")
    print(json.dumps(agent.config, indent=2, ensure_ascii=False))

    # Сохраняем обновленный конфиг
    agent.save_config()


async def example_8_filters():
    """Пример 8: Использование фильтров"""
    print("\n" + "=" * 50)
    print("Пример 8: Фильтры постов")
    print("=" * 50)

    agent = ThreadsCommentAgent()

    # Только посты с минимум 10 лайками
    agent.config["filters"]["min_engagement"] = 10
    agent.config["filters"]["skip_duplicates"] = True
    agent.config["filters"]["skip_own_posts"] = True

    print("✅ Фильтры установлены:")
    print(json.dumps(agent.config["filters"], indent=2, ensure_ascii=False))
    print("\n⚠️  Агент будет пропускать:")
    print("- Посты с лайками < 10")
    print("- Уже закомментированные посты")
    print("- Ваши собственные посты")


async def main():
    """Главная функция с меню примеров"""
    print("\n🤖 Threads Comment Agent - Примеры использования\n")

    examples = [
        ("Ручной запуск", example_1_manual_run),
        ("Кастомные хэштеги", example_2_custom_hashtags),
        ("Разные тоны", example_3_different_tone),
        ("GPT4All вместо Ollama", example_4_use_gpt4all),
        ("Режим по расписанию", example_5_schedule_mode),
        ("Режим реального времени", example_6_realtime_mode),
        ("Обновление конфига", example_7_config_update),
        ("Использование фильтров", example_8_filters),
    ]

    for i, (name, func) in enumerate(examples, 1):
        print(f"{i}. {name}")

    print("\nДля запуска конкретного примера:")
    print("  python example_usage.py --example 1")
    print("  python example_usage.py --example 2")
    print("  ...")

    # Если запущен с аргументом --example
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--example":
        example_num = int(sys.argv[2]) - 1
        if 0 <= example_num < len(examples):
            _, func = examples[example_num]
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                func()
        else:
            print(f"❌ Пример {example_num + 1} не найден")


if __name__ == "__main__":
    asyncio.run(main())
