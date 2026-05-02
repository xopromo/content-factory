# Content Factory — CLAUDE.md

## Автономность

Делай всё самостоятельно без лишних вопросов к пользователю:
- Проверяй настройки через доступные инструменты (MCP, Bash, WebFetch) — не проси пользователя заходить в UI
- Читай файлы конфигурации перед тем как спрашивать о их содержимом
- Устанавливай нужные пакеты через pip/npm без согласования
- Коммить и пушить изменения сразу в `main` без дополнительного подтверждения
- Если что-то можно выяснить через инструмент — выясняй инструментом, не спрашивай пользователя

## Репозиторий

- GitHub: xopromo/content-factory
- GitHub Pages: https://xopromo.github.io/content-factory/
- Рабочая ветка: main (пушить сразу в main — GitHub Pages обслуживается из main/docs)

## Стек

- Python 3.11
- DuckDuckGo поиск: пакет `ddgs` (не `duckduckgo_search`)
- GitHub Actions: `.github/workflows/traffic-research.yml` — запуск каждый день в 09:00 UTC
- Инсайты: `docs/research/insights/index.json`
- GitHub Pages: из папки `docs/` ветки `main`

## Архитектура

- `traffic_researcher.py` — основной агент, реальный поиск через DuckDuckGo, 14 запросов → ~42 инсайта за запуск
- `freelancer_a_evolve.py` — FreelancerAgent на базе BaseAgent, использует ddgs + cloud LLM (Mistral/Cerebras/Gemini)
- `run_insights_search.py` — запускает FreelancerAgent на 5 задач
- `docs/` — GitHub Pages сайт с визуализацией инсайтов
