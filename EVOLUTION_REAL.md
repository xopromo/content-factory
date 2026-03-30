# 🧬 Real Evolution: Connect Claude API

Текущая эволюция — симуляция. Вот как сделать **реальную** эволюцию промптов!

---

## Шаг 1: Включить Claude API

### 1.1 Добавить API ключ
```bash
# В .env файл (не коммитить!)
ANTHROPIC_API_KEY=sk-ant-...
```

### 1.2 Обновить FreelancerAgent
```python
from anthropic import Anthropic

class FreelancerAgent(ae.BaseAgent):
    def __init__(self, workspace_path: str):
        super().__init__(workspace_path)
        self.client = Anthropic()
        self.model = "claude-3-5-sonnet-20241022"

    def solve(self, task: Task) -> Trajectory:
        # Вместо mock → реальный вызов Claude
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.system_prompt,  # Эволюционируемый промпт!
            messages=[
                {"role": "user", "content": task.input}
            ]
        )

        output = message.content[0].text

        return Trajectory(
            task_id=task.id,
            output=output,
            steps=[{"model": self.model, "usage": message.usage}]
        )
```

---

## Шаг 2: Улучшить оценку качества

### Текущая оценка (mock):
```python
def score(self, output: str, task: Task) -> float:
    return 0.5 + random_stuff()  # Всегда близко к 1.0
```

### Реальная оценка:
```python
def score(self, output: str, task: Task) -> float:
    score = 0.0

    # 1️⃣ Считать инсайты (💡 в тексте)
    insights = output.count("💡")
    if insights >= 3:
        score += 0.3
    elif insights >= 2:
        score += 0.15
    else:
        return 0.1  # No insights = bad

    # 2️⃣ Проверить структуру
    if "📊 Analysis:" in output:
        score += 0.2
    if "✅ Application:" in output:
        score += 0.2
    if "⭐ Impact:" in output:
        score += 0.15

    # 3️⃣ Проверить релевантность ВК
    vk_keywords = ["ВК", "VK", "интересам", "таргет", "аудитория"]
    vk_mentions = sum(output.lower().count(kw.lower())
                      for kw in vk_keywords)
    if vk_mentions >= 3:
        score += 0.15

    return min(1.0, score)
```

---

## Шаг 3: Пример реальной эволюции

### Цикл 1:
```
Базовый промпт:
"Ты специалист по ВК таргетированию. Найди инсайты."

Score: 0.65

🔀 МУТАЦИЯ:
"Ты специалист по ВК таргетированию. Найди РЕДКИЕ и
НЕОБЫЧНЫЕ инсайты, которые дают конкурентное преимущество."

Score: 0.78 ↑ УЛУЧШИЛОСЬ! ✅
```

### Цикл 2:
```
🔀 МУТАЦИЯ на основе лучшего:
"Ты специалист по ВК таргетированию.
Твоя роль: открывать СКРЫТЫЕ ПАТТЕРНЫ и тренды,
которые другие не видят. Всегда объясняй ПОЧЕМУ работает."

Score: 0.82 ↑↑ ЕЩЕ ЛУЧШЕ! ✅
```

### Цикл 3-10:
```
Продолжай мутировать, пока не упрется в потолок (1.0)

Видишь мутации:
✅ Более конкретные инструкции
✅ Лучше структурированные ответы
✅ Больше практических советов
✅ Выше релевантность к ВК
```

---

## Запуск реальной эволюции

### После интеграции Claude API:
```bash
./evolve-freelancer.sh
```

### Увидишь:
```
======================================================================
🧬 EVOLUTION CYCLE 1/10
======================================================================

🔀 MUTATION 1: "Найди инсайты" → "Найди редкие паттерны"
   Original length: 1451 chars

📊 Testing on Task 1...
   Score: 0.65 → 0.78 ↑ IMPROVED!

✨ Accepting mutation! Git tag: evo-1

--- CYCLE 2/10 ---

🔀 MUTATION 2: Укрепляю инструкции...
   Original: "...редкие паттерны..."
   Mutated:  "...редкие паттерны + объясни ПОЧЕМУ..."

📊 Testing...
   Score: 0.78 → 0.82 ↑ IMPROVED!

✨ Accepting! Git tag: evo-2

... (cycles 3-10)

🏆 FINAL: 0.65 → 0.94 (+29%)
```

---

## Что будет происходить?

```
GENERATION 0 (baseline):
System prompt v1 → Score: 0.65

GENERATION 1:
v1 → mutate → v1.1 (Score: 0.78) ✅ KEEP
    → mutate → v1.2 (Score: 0.72) ❌ DROP
    → mutate → v1.3 (Score: 0.68) ❌ DROP

GENERATION 2 (based on v1.1):
v1.1 → mutate → v1.1.1 (Score: 0.82) ✅ KEEP
     → mutate → v1.1.2 (Score: 0.80) ✅ KEEP
     → mutate → v1.1.3 (Score: 0.79) ❌ DROP

GENERATION 3 (best of best):
v1.1.2 → mutate → v1.1.2.1 (Score: 0.85) ✅ KEEP
       → ...

... after 10 cycles:
🏆 Final evolved prompt: v1.1.2.1.3... (Score: 0.94)
```

---

## Git история эволюции

```bash
git log --oneline | head -20

evo-10   Evolved prompt: +0.01% improvement
evo-9    Evolved prompt: +0.02% improvement
evo-8    Evolved prompt: +0.01% improvement
...
evo-1    First mutation: +0.13% improvement (0.65 → 0.78)
HEAD     Baseline: 0.65
```

Каждый коммит = один шаг эволюции. Можешь вернуться в любой момент!

---

## Чек-лист для реальной эволюции

- [ ] Установить Anthropic SDK: `pip install anthropic`
- [ ] Добавить `ANTHROPIC_API_KEY` в `.env`
- [ ] Обновить `freelancer_a_evolve.py`:
  - [ ] Добавить реальный вызов Claude в `solve()`
  - [ ] Улучшить `score()` функцию
  - [ ] Добавить логирование costs
- [ ] Запустить: `./evolve-freelancer.sh`
- [ ] Смотреть логи эволюции
- [ ] Проверить git: `git log --oneline -20`
- [ ] Анализировать финальный промпт

---

## Ожидаемые результаты

**После 10 циклов:**
```
Baseline:  0.65 (generic prompt)
Final:     0.94 (evolved prompt)
Improvement: +44%

💾 Граммер потом:
- 10 git commits (evo-1 до evo-10)
- Финальный промпт в freelancer_workspace/prompts/system.md
- История всех мутаций в git diff
```

---

**Статус:** 🔄 Ready for implementation
**Сложность:** ⭐⭐ (Just connect the API)
**Время:** ~5 минут интеграции + 2 минуты для 10 циклов эволюции
