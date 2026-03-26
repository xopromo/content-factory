# 🔄 Цепочка агентов: Pipeline взаимодействия

## Архитектура взаимодействия

```
┌──────────────┐
│   User Query │
│  "Тренды РФ" │
└──────┬───────┘
       │
       ▼
   ┌─────────────────────────────────────────────────────────┐
   │ 1️⃣ RESEARCHER                                           │
   │    📊 Исследует + находит данные в интернете             │
   │    Модель: Ollama (mistral) / Claude API (budget mode)  │
   │    Стоимость: $0.00 (бесплатно)                        │
   │                                                          │
   │    OUTPUTS:                                              │
   │    ├─ RESEARCH.md (полный отчёт)                       │
   │    ├─ finding_1, finding_2, ...                        │
   │    └─ summary.json (структурированные данные)          │
   └──────┬────────────────────────────────────────────────┘
          │
          ▼
   ┌─────────────────────────────────────────────────────────┐
   │ 2️⃣ BRAINSTORMER                                          │
   │    💭 Генерирует идеи на основе research                 │
   │    Читает: ← RESEARCH.md                                 │
   │    Модель: Ollama (mistral)                             │
   │    Стоимость: $0.00 (бесплатно)                        │
   │                                                          │
   │    OUTPUTS:                                              │
   │    ├─ BRAINSTORM.md (список идей)                      │
   │    ├─ idea_1 (🚀 HIGH potential)                       │
   │    ├─ idea_2 (💡 INNOVATIVE)                           │
   │    ├─ idea_3 (🔄 INTEGRATION)                          │
   │    └─ ideas.json (структурированные идеи)              │
   └──────┬────────────────────────────────────────────────┘
          │
          ▼
   ┌─────────────────────────────────────────────────────────┐
   │ 3️⃣ CRITIC                                                │
   │    🔍 Критикует и оценивает идеи                        │
   │    Читает: ← BRAINSTORM.md + RESEARCH.md               │
   │    Модель: Ollama (neural-chat)                         │
   │    Стоимость: $0.00 (бесплатно)                        │
   │                                                          │
   │    OUTPUTS:                                              │
   │    ├─ CRITIQUE.md (оценка идей)                        │
   │    ├─ idea_1_risks (RED ⛔ realistic < 30%)             │
   │    ├─ idea_2_risks (YELLOW ⚠️ risks: 30-70%)            │
   │    ├─ idea_3_risks (GREEN ✅ viable > 70%)              │
   │    └─ critique.json (оценки и вероятности)             │
   └──────┬────────────────────────────────────────────────┘
          │
          ▼
   ┌─────────────────────────────────────────────────────────┐
   │ 4️⃣ JUDGE                                                 │
   │    ⚖️ Выносит финальный вердикт                         │
   │    Читает: ← RESEARCH.md + BRAINSTORM.md + CRITIQUE.md │
   │    Модель: Ollama (neural-chat)                         │
   │    Стоимость: $0.00 (бесплатно)                        │
   │                                                          │
   │    OUTPUTS:                                              │
   │    ├─ DECISION.md (финальный список)                   │
   │    ├─ TOP-5 идей к внедрению (с рейтингом)             │
   │    ├─ ACTION_PLAN.md (что делать)                      │
   │    └─ decision.json (вердикты)                         │
   └──────┬────────────────────────────────────────────────┘
          │
          ▼
   ┌─────────────────────────────────────────┐
   │ 📋 FINAL REPORT                         │
   │                                         │
   │ Включает:                               │
   │ - TOP-5 идей к внедрению                │
   │ - План действий на 4 недели              │
   │ - Ожидаемый ROI                         │
   │ - Риски и mitigation стратегии          │
   └─────────────────────────────────────────┘
```

---

## 📁 Файлы обмена данными

```
.claude/agents/
├── RESEARCH.md          ← Вывод researcher'а
├── BRAINSTORM.md        ← Вывод brainstormer'а (читает RESEARCH.md)
├── CRITIQUE.md          ← Вывод critic'а (читает RESEARCH.md + BRAINSTORM.md)
├── DECISION.md          ← Вывод judge'а (читает все три выше)
├── ACTION_PLAN.md       ← План внедрения
│
├── data/
│   ├── research/
│   │   └── findings.json       (структурированные находки)
│   ├── brainstorm/
│   │   └── ideas.json          (все идеи с оценками)
│   └── decisions/
│       ├── top5.json           (финальный топ-5)
│       └── risks.json          (риски для каждой идеи)
│
└── agents/
    ├── researcher/RESEARCH.md
    ├── brainstormer/brainstormer.md
    ├── critic/critic.md
    └── judge/judge.md
```

---

## 🚀 Как запустить Pipeline

### Вариант 1: ПОЛНОСТЬЮ АВТОМАТИЧЕСКИЙ

```bash
# Создать скрипт run-pipeline.sh
bash ./run-pipeline.sh "тренды рекламного рынка РФ"

# Скрипт автоматически запустит:
# 1. researcher → ждёт завершения
# 2. brainstormer → ждёт RESEARCH.md
# 3. critic → ждёт BRAINSTORM.md
# 4. judge → ждёт CRITIQUE.md
# 5. генерирует FINAL_REPORT.md
```

### Вариант 2: ПОШАГОВЫЙ (интерактивный)

```
Шаг 1: @"researcher" исследуй тренды рекламного рынка РФ
       ↓ ждём завершения, смотрим RESEARCH.md

Шаг 2: @"brainstormer" напиши идеи на основе RESEARCH.md
       ↓ смотрим BRAINSTORM.md, обсуждаем идеи

Шаг 3: @"critic" оцени идеи на реалистичность
       ↓ смотрим CRITIQUE.md, уточняем риски

Шаг 4: @"judge" выноси финальный вердикт
       ↓ смотрим DECISION.md и ACTION_PLAN.md
```

### Вариант 3: ФОНОВЫЙ (асинхронный)

```bash
# Запустить все агенты в фоне одновременно
# (но нужен порядок: researcher → остальные)

/loop 5m bash ./check-pipeline.sh
# Скрипт проверяет статус каждые 5 минут
```

---

## 🔗 Как передают данные агенты

### Способ 1: Через файлы Markdown (простейший)

```
researcher пишет в RESEARCH.md:
"# Исследование рекламного рынка РФ 2026
Главный вывод: Telegram +44%, TikTok +32%"

brainstormer читает RESEARCH.md:
"На основе RESEARCH.md предлагу идеи..."

critic читает RESEARCH.md + BRAINSTORM.md:
"Идея 1 нереалистична потому что..."

judge читает все три:
"Лучшие идеи: #3, #5, #7"
```

**Структура markdown файлов:**
```markdown
# [Название отчёта]

## Дата
2026-03-26

## Основные выводы
- Пункт 1
- Пункт 2

## Детали
[детальное описание]

## Следующий агент
→ @"next-agent-name"
```

### Способ 2: Через JSON (структурированные данные)

```json
// research_findings.json
{
  "query": "тренды рекламного рынка РФ",
  "timestamp": "2026-03-26T10:30:00Z",
  "findings": [
    {
      "title": "Telegram рост",
      "impact": 0.44,
      "confidence": 0.95
    }
  ],
  "next_agent": "brainstormer"
}
```

---

## 🎯 Пример реального использования

### Входящий запрос пользователя:
```
"Исследуй тренды рекламного рынка РФ и предложи стратегию для USE Optimizer"
```

### Шаг 1: Researcher
```
Ищет в интернете через DuckDuckGo
Анализирует: Telegram (44%), TikTok (32%), RMN (40%), AI (73% агентств)
Сохраняет в RESEARCH.md
```

### Шаг 2: Brainstormer
```
Читает RESEARCH.md
Генерирует идеи:
🚀 HIGH: "Telegram канал для USE Optimizer с AI-ассистентом"
💡 INNOVATIVE: "Micro-influencer partnerships для каждого сегмента"
🔄 INTEGRATION: "RMN + ChatBot для e-commerce"
Сохраняет в BRAINSTORM.md
```

### Шаг 3: Critic
```
Читает BRAINSTORM.md + RESEARCH.md
Оценивает реалистичность:
🟢 Idea 1: 85% вероятность успеха (легко внедрить)
🟡 Idea 2: 60% вероятность (нужны микро-инфлюенсеры)
🔴 Idea 3: 20% вероятность (RMN требует особого доступа)
Сохраняет в CRITIQUE.md
```

### Шаг 4: Judge
```
Читает все три документа
Выносит вердикт:
🥇 1-е место: Telegram канал (Score 9.2/10)
🥈 2-е место: Micro-influencer partnerships (Score 8.5/10)
🥉 3-е место: Performance-маркетинг (Score 8.1/10)

Создаёт ACTION_PLAN.md:
Неделя 1-2: Создать Telegram канал, написать контент
Неделя 3-4: Начать партнерства с микро-инфлюенсерами
Неделя 5-8: Запустить campaigns, собрать metrics

Сохраняет в DECISION.md
```

### Итоговый отчёт:
```
✅ FINAL REPORT: "Стратегия для USE Optimizer на Q2 2026"

TOP-5 идей:
1. Telegram канал (ROI 3:1, сроки 2 недели)
2. Micro-influencers (ROI 4:1, сроки 3 недели)
3. Performance marketing (ROI 2.5:1, сроки 1 неделя)
4. GEO-оптимизация (ROI 2:1, сроки 1 неделя)
5. AI-контент генерация (ROI 3:1, сроки 3 дня)

Риски: [список] + Mitigation: [для каждого риска]
```

---

## 💰 Стоимость полного Pipeline

| Этап | Агент | Модель | Токены | Стоимость |
|------|-------|--------|--------|-----------|
| 1 | researcher | Ollama (mistral) | 15K | $0.00 |
| 2 | brainstormer | Ollama (mistral) | 8K | $0.00 |
| 3 | critic | Ollama (neural-chat) | 10K | $0.00 |
| 4 | judge | Ollama (neural-chat) | 12K | $0.00 |
| **TOTAL** | **-** | **Ollama** | **45K** | **$0.00** |

**Сравнение:**
- Ollama (локально): **$0.00** ✅
- Claude API: **$0.35** (research + brainstorm + critique + judge)
- Экономия: **100%** при Ollama! 🚀

---

## 🛠️ Требования для запуска

```bash
# Локальный LLM
docker run -d -p 11434:11434 --name ollama ollama/ollama
ollama pull mistral
ollama pull neural-chat

# Python зависимости (уже в проекте)
pip install duckduckgo-search requests beautifulsoup4

# Claude Code agents (уже созданы)
.claude/agents/{researcher,brainstormer,critic,judge}/
```

---

## 🎯 Следующие шаги

1. **Запустить полный pipeline:**
   ```
   @"researcher" исследуй тренды рекламного рынка РФ
   ```

2. **После RESEARCH.md:**
   ```
   @"brainstormer" напиши идеи на основе RESEARCH.md
   ```

3. **После BRAINSTORM.md:**
   ```
   @"critic" оцени идеи на реалистичность
   ```

4. **После CRITIQUE.md:**
   ```
   @"judge" выноси финальный вердикт
   ```

5. **Получить финальный отчёт:**
   - DECISION.md (выбранные идеи)
   - ACTION_PLAN.md (план внедрения)
   - ROI и timeline

---

**Создано**: 2026-03-26
**Стоимость Pipeline**: $0.00 (с Ollama) или $0.35 (с Claude API)
**Экономия**: 100% на локальных LLM!
