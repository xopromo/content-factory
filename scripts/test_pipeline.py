#!/usr/bin/env python3
"""
Smoke-тесты новых компонентов пайплайна.
Запуск: python scripts/test_pipeline.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def ok(label):  print(f"  ✅ {label}")
def fail(label, err): print(f"  ❌ {label}: {err}"); return False

results = []

print("\n=== 1. Импорт и инициализация клиентов ===")
try:
    import orchestrator as o
    ok("import orchestrator")
    print(f"  Groq:   {'✅ готов' if o._groq_client else '⚠️  нет GROQ_KEY'}")
    print(f"  Gemini: {'✅ готов' if o._gemini_client else '⚠️  нет GEMINI_KEY'}")
    print(f"  DDGS:   {'✅ готов' if o._DDGS else '❌ не установлен'}")
    results.append(True)
except Exception as e:
    fail("import orchestrator", e); results.append(False)

print("\n=== 2. Source quality ranking ===")
try:
    tests = [
        ("https://github.com/anthropics/claude", 1),
        ("https://arxiv.org/abs/2303.12528", 1),
        ("https://techcrunch.com/2026/01/01/ai", 2),
        ("https://randomsite.ru/article", 3),
        ("", 3),
    ]
    for url, expected in tests:
        tier = o._source_tier(url)
        assert tier == expected, f"URL={url}: ожидал {expected}, получил {tier}"
    ok(f"_source_tier() — {len(tests)} тестов пройдено")
    results.append(True)
except Exception as e:
    fail("_source_tier", e); results.append(False)

print("\n=== 3. FINER gate ===")
try:
    # Тест 1: пустые источники → F=0, должен вернуть False
    ok_flag, report = o.finer_gate("нейросети", [], [])
    assert not ok_flag, "Должен вернуть False при пустых источниках"
    assert "❌" in report
    ok("FINER gate: пустые источники → блокирует")

    # Тест 2: достаточно источников → должен вернуть True
    fake_sources = [
        {"url": "https://arxiv.org/test", "text": "A" * 1500, "fresh": True, "date": "2026-05-26",
         "title": "Test AI paper", "source": "arxiv"},
        {"url": "https://github.com/test", "text": "B" * 1500, "fresh": False, "date": "2026-05-20",
         "title": "Test repo", "source": "github"},
        {"url": "https://techcrunch.com/test", "text": "C" * 800, "fresh": False, "date": "2026-05-15",
         "title": "Test news", "source": "techcrunch"},
    ]
    ok_flag, report = o.finer_gate("openai gpt модели", fake_sources[:2], fake_sources[2:])
    assert ok_flag, f"Должен вернуть True при достаточных источниках. Report: {report}"
    ok("FINER gate: достаточно источников → пропускает")
    assert "✅ F" in report
    ok("FINER gate: отчёт содержит F-критерий")
    results.append(True)
except Exception as e:
    fail("finer_gate", e); results.append(False)

print("\n=== 4. Material Passport ===")
try:
    test_slug = "__test_passport__"
    test_ctx = {"topic": "test", "web_pack": "some content", "optimized_draft": "article text"}
    o.save_state(test_slug, test_ctx, 8)
    state_file = o.STATE_DIR / f"{test_slug}.json"
    assert state_file.exists(), "Файл состояния не создан"

    step, loaded = o.load_state(test_slug)
    assert step == 8, f"Ожидал step=8, получил {step}"
    assert loaded.get("web_pack") == "some content"
    assert loaded.get("optimized_draft") == "article text"

    # Чистим тестовый файл
    state_file.unlink()
    ok("save_state() → load_state(): данные сохранились и восстановились корректно")
    results.append(True)
except Exception as e:
    fail("material passport", e); results.append(False)

print("\n=== 5. run_fast() (llama-3.1-8b-instant) ===")
try:
    if not o._groq_client:
        print("  ⚠️  GROQ_KEY не задан — пропускаем")
        results.append(None)
    else:
        out, tokens = o.run_fast("Ответь одним словом: какого цвета небо?")
        assert len(out) > 0, "Пустой ответ"
        ok(f"run_fast(): ответ получен ({len(out)} символов, ~{tokens} токенов)")
        print(f"  Ответ: «{out[:80]}»")
        results.append(True)
except Exception as e:
    fail("run_fast", e); results.append(False)

print("\n=== 6. Temporal verifier (run_fast) ===")
try:
    if not o._groq_client:
        print("  ⚠️  GROQ_KEY не задан — пропускаем")
        results.append(None)
    else:
        # Текст с намеренной ошибкой: "сейчас лучший" — deictic present
        bad_text = "GPT-4 сейчас является лучшей моделью на рынке. 5 лет назад, в 2024 году, это казалось невозможным."
        ok_flag, report = o.run_temporal_check(bad_text)
        print(f"  Результат: {'OK' if ok_flag else 'WARN'}")
        print(f"  Фрагмент отчёта: {report[:200]}")
        ok("temporal_check(): отработал без исключений")
        results.append(True)
except Exception as e:
    fail("temporal_check", e); results.append(False)

print("\n=== 7. Devil-advocate (run_fast) ===")
try:
    if not o._groq_client:
        print("  ⚠️  GROQ_KEY не задан — пропускаем")
        results.append(None)
    else:
        sample = """
# Почему все компании обязаны внедрить ИИ прямо сейчас

## Введение
Нейросети увеличивают продуктивность на 300%. Каждая компания, которая не внедрила ИИ,
обречена на провал. Конкуренты используют ИИ и обгоняют вас. Промедление недопустимо.
"""
        flagged, report = o.run_devil_advocate(sample)
        print(f"  Однобокость обнаружена: {flagged}")
        print(f"  Фрагмент: {report[:300]}")
        ok("devil_advocate(): отработал без исключений")
        results.append(True)
except Exception as e:
    fail("devil_advocate", e); results.append(False)

print("\n=== 8. Gemini spot-check ===")
try:
    if not o._gemini_client:
        print("  ⚠️  GEMINI_KEY не задан — пропускаем (опциональный компонент)")
        results.append(None)
    else:
        claims = "VERIFIED: GPT-4 вышел в 2023 году [1]\nVERIFIED: Python создан Гвидо ван Россумом [2]"
        spot_ok, report = o.run_gemini_spotcheck(claims)
        print(f"  Spot-check: {'PASS' if spot_ok else 'WARN'}")
        print(f"  Фрагмент: {report[:200]}")
        ok("gemini_spotcheck(): отработал без исключений")
        results.append(True)
except Exception as e:
    fail("gemini_spotcheck", e); results.append(False)

# Итог
print("\n" + "="*50)
passed = sum(1 for r in results if r is True)
skipped = sum(1 for r in results if r is None)
failed = sum(1 for r in results if r is False)
print(f"Итог: ✅ {passed} прошли  ⚠️ {skipped} пропущены  ❌ {failed} провалились")
if failed > 0:
    sys.exit(1)
