#!/usr/bin/env python3
"""
Проверка установки и настройки Threads Comment Agent
"""
import sys
import json
from pathlib import Path


def check_python_version():
    """Проверяет версию Python"""
    print("🐍 Python версия:", end=" ")
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 8):
        print(f"✅ {version}")
        return True
    else:
        print(f"❌ {version} (требуется 3.8+)")
        return False


def check_dependencies():
    """Проверяет установленные зависимости"""
    print("\n📦 Зависимости:")
    deps = {
        "requests": "requests для HTTP запросов",
        "threads_api": "threads-api для Threads API",
        "gpt4all": "gpt4all для локальных моделей",
    }

    all_ok = True
    for module, description in deps.items():
        try:
            __import__(module)
            print(f"  ✅ {module}")
        except ImportError:
            print(f"  ❌ {module} - {description}")
            all_ok = False

    return all_ok


def check_config_file():
    """Проверяет файл конфигурации"""
    print("\n⚙️  Конфигурация:")
    config_path = Path("config.json")

    if not config_path.exists():
        print(f"  ❌ config.json не найден")
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Проверяем обязательные поля
        checks = [
            ("account.username", "👤 Username", config.get("account", {}).get("username")),
            ("account.password", "🔑 Password", config.get("account", {}).get("password")),
            ("search.hashtags", "#️⃣  Hashtags", config.get("search", {}).get("hashtags")),
            ("comment_generation.model", "🤖 Model", config.get("comment_generation", {}).get("model")),
        ]

        all_ok = True
        for key, label, value in checks:
            if value and value != "your_username" and value != "your_password":
                print(f"  ✅ {label}")
            else:
                print(f"  ⚠️  {label} - {key} не настроен")
                all_ok = False

        return all_ok

    except json.JSONDecodeError:
        print(f"  ❌ config.json невалидный JSON")
        return False


def check_ollama():
    """Проверяет подключение к Ollama"""
    print("\n🚀 Ollama:")
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print("  ✅ Ollama работает на localhost:11434")
            return True
        else:
            print("  ⚠️  Ollama не отвечает")
            return False
    except Exception as e:
        print(f"  ❌ Ollama не запущена - {e}")
        print("     Запустите: ollama serve")
        return False


def check_modules():
    """Проверяет что все модули импортируются"""
    print("\n📚 Модули проекта:")
    modules = {
        "agent": "ThreadsCommentAgent",
        "models": "LocalLLM",
        "threads_connector": "ThreadsConnector",
    }

    all_ok = True
    for module, cls_name in modules.items():
        try:
            module_obj = __import__(module)
            if hasattr(module_obj, cls_name):
                print(f"  ✅ {module}.{cls_name}")
            else:
                print(f"  ⚠️  {module} найден, но класс {cls_name} не найден")
                all_ok = False
        except ImportError as e:
            print(f"  ❌ {module} - {e}")
            all_ok = False

    return all_ok


def main():
    """Главная функция проверки"""
    print("=" * 60)
    print("🧪 Проверка установки Threads Comment Agent")
    print("=" * 60)

    results = {
        "Python": check_python_version(),
        "Dependencies": check_dependencies(),
        "Config": check_config_file(),
        "Ollama": check_ollama(),
        "Modules": check_modules(),
    }

    print("\n" + "=" * 60)
    print("📊 Результат проверки:")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for check, result in results.items():
        status = "✅" if result else "⚠️ "
        print(f"{status} {check}")

    print("\n" + "=" * 60)
    if passed == total:
        print("🎉 Всё готово! Можно запускать агент")
        print("\nЗапуск:")
        print("  python agent.py --mode manual")
        print("  python agent.py --mode manual --hashtag '#AI'")
        return 0
    else:
        print(f"⚠️  Готово на {passed}/{total}")
        print("\nДля запуска нужно:")
        if not results["Python"]:
            print("  - Обновить Python до 3.8+")
        if not results["Dependencies"]:
            print("  - Установить зависимости: pip install -r requirements.txt")
        if not results["Config"]:
            print("  - Отредактировать config.json (добавить username/password)")
        if not results["Ollama"]:
            print("  - Запустить Ollama: ollama serve")
        return 1


if __name__ == "__main__":
    sys.exit(main())
