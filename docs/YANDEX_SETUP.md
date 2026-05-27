# Yandex Search API — Инструкция настройки

## Зачем это нужно?

- **Русскоязычный поиск**: Yandex лучше понимает русский язык, чем DuckDuckGo
- **Стабильность**: Если DuckDuckGo упадёт (таймауты), автоматически переключимся на Yandex
- **Дешево**: ₽488 за 1000 запросов = копейки для новостного пайплайна
- **Fallback**: Если у тебя нет .env переменных — система просто использует только DuckDuckGo

## Как получить API ключи

### Шаг 1: Создай аккаунт Яндекс Облака

Если уже есть — переходи на Шаг 2.

1. Переходи на https://cloud.yandex.ru/
2. Нажми "Регистрация" (или логин если уже есть)
3. Подтверди email
4. Заполни данные: имя, страна, назначение (выбери "Разработка и тестирование")

### Шаг 2: Создай Service Account и API ключ

1. В консоли Яндекс Облака (https://console.cloud.yandex.ru/):
   - Слева в меню: **IAM и администрирование** → **Service Accounts**
   - Создай новый Service Account (имя: например `content-factory-api`)

2. Нажми на созданный Service Account
   - Вкладка **API ключи**
   - **Создать новый API ключ**
   - Скопируй ключ (это твой `YANDEX_API_KEY`)

3. В меню консоли найди **Cloud ID** (это твой `YANDEX_FOLDER_ID`):
   - Слева: **Управление ресурсами** → **Облако**
   - Скопируй ID облака

### Шаг 3: Настрой .env

```bash
# В корне проекта
nano .env
```

Добавь строки:

```env
YANDEX_API_KEY=<скопированный API ключ>
YANDEX_FOLDER_ID=<скопированный Cloud ID>
```

Сохрани (Ctrl+O → Enter → Ctrl+X)

### Шаг 4: Проверь что работает

```bash
# Тестируем поиск
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

from scripts.orchestrator import web_search_yandex
results = web_search_yandex('claude AI', max_results=3)
print(f'Найдено: {len(results)} результатов')
for r in results:
    print(f'  - {r[\"title\"][:50]}...')
"
```

Если вывод без ошибок — готово! ✅

## Как это работает в пайплайне

1. **Оркестратор** пытается найти свежие новости через DuckDuckGo
2. Если DuckDuckGo падает или возвращает 0 результатов → **автоматически переключается на Yandex**
3. Результаты одинакового формата, дальнейший пайплайн не изменяется
4. Логи показывают что использовалось: `[SEARCH] news/w ошибка: ...` → `[SEARCH] trying Yandex Search API...`

## Стоимость

За 100 статей в месяц (на каждую статью ~2-3 свежих поиска):

- **~300 запросов** × ₽488/1000 = **₽145 в месяц**

Это справедливо даже для активного использования.

## Ссылки

- [Документация Yandex Search API](https://yandex.cloud/ru/docs/search-api/)
- [Тарифы](https://aistudio.yandex.ru/docs/en/search-api/pricing)
- [API Reference](https://yandex.cloud/en/docs/search-api/api-ref/rest/overview)
