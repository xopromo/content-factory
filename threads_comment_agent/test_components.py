#!/usr/bin/env python3
"""
Тестирование отдельных компонентов Threads Comment Agent
"""
import asyncio
import json
from models import LocalLLM


def test_config_loading():
    """Тест 1: Загрузка конфигурации"""
    print("=" * 60)
    print("📝 Тест 1: Загрузка конфигурации")
    print("=" * 60)

    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        print("✅ config.json загружен")
        print(f"\n  Поиск по хэштегам: {config['search']['hashtags']}")
        print(f"  Модель: {config['comment_generation']['model']}")
        print(f"  Тон: {config['comment_generation']['tone']}")
        print(f"  Макс. длина: {config['comment_generation']['max_length']}")

        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def test_ollama_connection():
    """Тест 2: Подключение к Ollama"""
    print("\n" + "=" * 60)
    print("🚀 Тест 2: Подключение к Ollama")
    print("=" * 60)

    try:
        import requests

        print("🔌 Проверка подключения к http://localhost:11434...")
        response = requests.get("http://localhost:11434/api/tags", timeout=2)

        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            if models:
                print(f"✅ Ollama работает")
                print(f"\n  Доступные модели ({len(models)}):")
                for model in models[:5]:
                    print(f"    • {model['name']}")
                return True
            else:
                print("⚠️  Ollama работает, но модели не загружены")
                print("   Загрузите модель: ollama pull mistral")
                return False
        else:
            print(f"❌ Ollama не отвечает (статус {response.status_code})")
            return False

    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print("   Запустите: ollama serve")
        return False


def test_llm_generation():
    """Тест 3: Генерация комментариев"""
    print("\n" + "=" * 60)
    print("🤖 Тест 3: Генерация комментариев (LocalLLM)")
    print("=" * 60)

    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        llm_config = config["comment_generation"]
        llm = LocalLLM(llm_config)

        test_post = "Только что закончил читать статью о искусственном интеллекте. Очень интересно!"

        print(f"📝 Тестовый пост: {test_post}\n")
        print(f"🤖 Генерируем комментарий ({llm_config['model']})...\n")

        # Проверяем что модель установлена
        if llm_config["model"] == "ollama":
            import requests

            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=2)
                if response.status_code != 200:
                    print("❌ Ollama не запущена")
                    print("   Запустите: ollama serve")
                    return False

                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                required_model = llm_config.get("ollama_model", "mistral")

                if not models:
                    print("❌ Модели не загружены")
                    print(f"   Запустите: ollama pull {required_model}")
                    return False

                if required_model not in models and not any(required_model in m for m in models):
                    print(f"⚠️  Модель {required_model} не найдена")
                    print(f"   Доступные: {', '.join(models[:3])}")

            except Exception as e:
                print(f"❌ Ошибка проверки Ollama: {e}")
                return False

        print("⚠️  Генерация требует запущенного Ollama/GPT4All")
        print("   Для полного теста запустите:")
        print("   $ ollama serve")
        print("   $ python test_components.py --full")

        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def test_comment_templates():
    """Тест 4: Шаблоны комментариев"""
    print("\n" + "=" * 60)
    print("📋 Тест 4: Шаблоны комментариев")
    print("=" * 60)

    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        templates = config["comment_generation"]["templates"]

        print(f"✅ Найдено {len(templates)} шаблонов:\n")

        for i, template in enumerate(templates, 1):
            example = template.format(comment="отличный пост!")
            print(f"  {i}. {template}")
            print(f"     Пример: {example}\n")

        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def test_filters():
    """Тест 5: Фильтры"""
    print("\n" + "=" * 60)
    print("🔍 Тест 5: Фильтры постов")
    print("=" * 60)

    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        filters = config["filters"]

        print("✅ Конфигурация фильтров:\n")
        print(f"  • Минимум взаимодействий: {filters['min_engagement']}")
        print(f"  • Пропускать дублики: {filters['skip_duplicates']}")
        print(f"  • Пропускать свои посты: {filters['skip_own_posts']}")

        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def test_scheduling():
    """Тест 6: Расписание"""
    print("\n" + "=" * 60)
    print("📅 Тест 6: Расписание запуска")
    print("=" * 60)

    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        schedule = config["scheduling"]

        print("✅ Конфигурация расписания:\n")
        print(f"  • Режим: {schedule['mode']}")
        print(f"  • Частота: {schedule['frequency']}")
        print(f"  • Время: {schedule['time']}")

        modes = {
            "manual": "Запуск вручную: python agent.py --mode manual",
            "schedule": f"Запуск ежедневно в {schedule['time']}: python agent.py --mode schedule",
            "realtime": "Запуск в реальном времени: python agent.py --mode realtime",
        }

        print(f"\n  Текущий режим: {modes[schedule['mode']]}")

        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def main():
    """Главная функция"""
    import sys

    print("\n" + "🧪 ТЕСТИРОВАНИЕ КОМПОНЕНТОВ THREADS COMMENT AGENT\n")

    tests = [
        ("Конфигурация", test_config_loading),
        ("Ollama", test_ollama_connection),
        ("LLM генерация", test_llm_generation),
        ("Шаблоны", test_comment_templates),
        ("Фильтры", test_filters),
        ("Расписание", test_scheduling),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            results[name] = False

    # Итоговый отчет
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test}")

    print("\n" + "=" * 60)
    if passed == total:
        print("🎉 Все тесты пройдены! Можно использовать агент")
        print("\nНачать работу:")
        print("  $ python agent.py --mode manual")
        print("  $ python agent.py --mode manual --hashtag '#Python'")
        print("  $ python agent.py --mode manual --tone professional")
        return 0
    else:
        print(f"⚠️  Пройдено: {passed}/{total}")
        if not results["Ollama"]:
            print("\n⚠️  Для полной работы нужна Ollama:")
            print("  1. Установите Ollama: https://ollama.ai")
            print("  2. Запустите: ollama serve")
            print("  3. Загрузите модель: ollama pull mistral")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
