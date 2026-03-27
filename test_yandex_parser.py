#!/usr/bin/env python3
"""
Быстрый тест парсинга Яндекса через Playwright
"""
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def test_yandex_parsing():
    """Тестируем парсинг Яндекса"""

    search_query = "страховые компании москвы"

    with sync_playwright() as p:
        # Запустить браузер
        print("🚀 Запускаю браузер...")
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Перейти на Яндекс
        search_url = f"https://yandex.ru/search/?text={search_query}"
        print(f"🔍 Открываю: {search_url}")

        page.goto(search_url, timeout=30000)
        page.wait_for_load_state("networkidle")

        print("✅ Страница загружена")

        # Получить HTML
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')

        # Найти ссылки в результатах поиска
        # Яндекс использует классы для результатов
        results = []

        # Попробуем найти результаты (Яндекс часто меняет структуру)
        # Ищем h2 с ссылками
        for h2 in soup.find_all('h2', class_='ErgoPaidSnippet__title'):
            link = h2.find('a')
            if link:
                url = link.get('href')
                title = link.get_text().strip()
                results.append({
                    'title': title,
                    'url': url
                })

        # Если не нашли - попробуем другой селектор
        if not results:
            for h2 in soup.find_all('h2'):
                link = h2.find('a')
                if link and 'http' in link.get('href', ''):
                    url = link.get('href')
                    title = link.get_text().strip()
                    results.append({
                        'title': title,
                        'url': url
                    })

        # Вывести первые 4 результата
        print(f"\n📊 Найдено результатов: {len(results)}")
        print("=" * 80)

        for i, result in enumerate(results[:4], 1):
            print(f"\n[{i}] {result['title']}")
            print(f"    URL: {result['url']}")

        browser.close()

        print("\n" + "=" * 80)
        print(f"✅ Тест завершен. Получено {min(4, len(results))} результатов")

        return results[:4]

if __name__ == "__main__":
    print("🧪 ТЕСТ ПАРСИНГА ЯНДЕКСА\n")
    try:
        results = test_yandex_parsing()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
