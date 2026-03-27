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
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)  # Дай JavaScript время на рендеринг

        print("✅ Страница загружена")

        # Получить HTML
        html = page.content()

        # Сохрани HTML для анализа
        with open('yandex_page.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print("📄 HTML сохранен в yandex_page.html")

        soup = BeautifulSoup(html, 'html.parser')

        # Найти ссылки в результатах поиска
        results = []

        # Попробуем разные селекторы
        selectors = [
            ('h2', 'ErgoPaidSnippet__title'),
            ('h2', None),
            ('a', 'Link'),
            ('article', None),
            ('div', 'serp-item'),
        ]

        for tag, cls in selectors:
            if cls:
                elements = soup.find_all(tag, class_=cls)
            else:
                elements = soup.find_all(tag)

            for elem in elements[:5]:
                link = elem.find('a') if tag != 'a' else elem
                if link:
                    url = link.get('href', '')
                    title = link.get_text().strip()
                    if url and 'http' in url and title and len(title) > 5:
                        results.append({
                            'title': title[:100],
                            'url': url
                        })

            if results:
                print(f"✅ Найдены результаты используя селектор: {tag}, class={cls}")
                break

        if not results:
            print("⚠️  Селекторы не сработали. Проверь yandex_page.html")

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
