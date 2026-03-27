#!/usr/bin/env python3
"""
Простой тест парсинга Яндекса через requests
(без браузера)
"""
import requests
from bs4 import BeautifulSoup
import time

def test_yandex_simple():
    """Простой парсинг Яндекса"""

    search_query = "страховые компании москвы"

    # Headers как от реального браузера
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://www.yandex.ru/',
    }

    try:
        search_url = f"https://yandex.ru/search/?text={search_query}"
        print(f"🔍 Запрашиваю: {search_url}")

        response = requests.get(
            search_url,
            headers=headers,
            timeout=15
        )

        print(f"📊 Статус: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ Ошибка HTTP: {response.status_code}")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')

        # Попытаемся найти результаты разными селекторами
        results = []

        print("🔎 Ищу результаты...")

        # Селектор 1: основные результаты
        for item in soup.find_all('article', limit=10):
            link = item.find('a')
            if link:
                url = link.get('href', '')
                text = link.get_text().strip()
                if url and 'http' in url:
                    results.append({
                        'title': text[:100],
                        'url': url
                    })

        # Если ничего не нашли - попробуем другой селектор
        if not results:
            for h2 in soup.find_all('h2', limit=10):
                link = h2.find('a')
                if link:
                    url = link.get('href', '')
                    text = link.get_text().strip()
                    if url and 'http' in url:
                        results.append({
                            'title': text[:100],
                            'url': url
                        })

        # Вывести результаты
        if results:
            print(f"\n✅ Найдено результатов: {len(results)}")
            print("=" * 80)

            for i, result in enumerate(results[:4], 1):
                print(f"\n[{i}] {result['title']}")
                print(f"    URL: {result['url']}")

            print("\n" + "=" * 80)
        else:
            print("❌ Результаты не найдены (Яндекс может блокировать)")
            print(f"   HTML размер: {len(response.text)} символов")
            print(f"   Первые 500 символов: {response.text[:500]}")

        return results[:4]

    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети: {e}")
        return []
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    print("🧪 ТЕСТ ПРОСТОГО ПАРСИНГА ЯНДЕКСА\n")
    results = test_yandex_simple()
