#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.parse
from typing import List, Dict

try:
    from ddgs import DDGS as _DDGS
except ImportError:
    _DDGS = None

try:
    import trafilatura as _trafilatura
except ImportError:
    _trafilatura = None

from scripts.utils.validators import _source_tier, _TIER_LABEL

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_TIER_TEXT_LIMIT = {1: 1200, 2: 700, 3: 350}  # символов текста по уровню авторитетности
_RAW_SOURCES_CAP = 7000  # суммарный лимит всего блока raw_sources


def _fetch_full_text(url: str, max_chars: int = 3000) -> str:
    """Вытаскивает полный текст страницы: httpx+bs4 → trafilatura → пусто."""
    if not url:
        return ""

    # Слой 1: httpx + BeautifulSoup (работает в облаке, не зависит от trafilatura)
    try:
        import httpx
        from bs4 import BeautifulSoup
        resp = httpx.get(url, headers=_FETCH_HEADERS, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            # убираем мусор
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            # берём основной контент
            main = (
                soup.find("article")
                or soup.find("main")
                or soup.find(id="content")
                or soup.find(class_="content")
                or soup.body
            )
            if main:
                text = " ".join(main.get_text(" ", strip=True).split())
                if len(text) > 200:
                    return text[:max_chars]
    except Exception:
        pass

    # Слой 2: trafilatura как резервный
    if _trafilatura:
        try:
            downloaded = _trafilatura.fetch_url(url)
            if downloaded:
                text = _trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                    favor_recall=True,
                    no_fallback=False,
                )
                return (text or "")[:max_chars]
        except Exception:
            pass

    return ""


def web_search_yandex(query: str, search_type: str = "news", max_results: int = 5) -> List[Dict]:
    """
    Поиск через Yandex Search API (fallback при ошибках DuckDuckGo).
    search_type: 'news' или 'web'
    Возвращает список {title, url, date?, text}.
    """
    import requests

    api_key = os.getenv("YANDEX_API_KEY", "")
    folder_id = os.getenv("YANDEX_FOLDER_ID", "")

    if not api_key or not folder_id:
        return []

    try:
        url = "https://search-api.yandex.ru/search"
        headers = {
            "Authorization": f"Api-Key {api_key}",
        }
        params = {
            "query": query,
            "folderId": folder_id,
            "pageSize": max_results,
        }

        if search_type == "news":
            params["filter"] = "news"

        response = requests.get(url, headers=headers, params=params, timeout=8)
        response.raise_for_status()

        data = response.json()
        results = []

        for item in data.get("results", [])[:max_results]:
            result_url = item.get("url", "")
            full_text = _fetch_full_text(result_url)

            results.append({
                "title": item.get("title", ""),
                "url": result_url,
                "date": item.get("publishedDate", "")[:10] if item.get("publishedDate") else "",
                "source": item.get("domain", ""),
                "text": full_text or item.get("snippet", ""),
            })

        return results
    except Exception as e:
        print(f"  [SEARCH] yandex ошибка: {e}")
        return []


def web_search_fresh(query: str, max_results: int = 3) -> List[Dict]:
    """
    Слой 1: свежие новости за последнюю неделю.
    """
    if not _DDGS:
        return []
    for timelimit in ("w", "m"):  # неделя → если пусто, месяц
        try:
            items = list(_DDGS().news(query, max_results=max_results, timelimit=timelimit, region="ru-ru"))
            if not items:
                continue
            results = []
            for item in items:
                url = item.get("url", "")
                full_text = _fetch_full_text(url)
                results.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "date": item.get("date", "")[:10],
                    "source": item.get("source", ""),
                    "text": full_text or item.get("body", ""),
                    "fresh": timelimit == "w",
                })
            return results
        except Exception as e:
            print(f"  [SEARCH] news/{timelimit} ошибка: {e}")
            
    # Fallback to Yandex Search API
    print("  [SEARCH] DuckDuckGo news failed. Trying Yandex Search API...")
    return web_search_yandex(query, search_type="news", max_results=max_results)


def web_search_deep(query: str, max_results: int = 5) -> List[Dict]:
    """
    Слой 2: глубинные источники без ограничения по дате.
    """
    if not _DDGS:
        return []
    try:
        items = list(_DDGS().text(query, max_results=max_results, region="ru-ru"))
        results = []
        for item in items:
            url = item.get("href", "")
            full_text = _fetch_full_text(url)
            results.append({
                "title": item.get("title", ""),
                "url": url,
                "text": full_text or item.get("body", ""),
            })
        return results
    except Exception as e:
        print(f"  [SEARCH] text ошибка: {e}")
        
    # Fallback to Yandex Search API
    print("  [SEARCH] DuckDuckGo text failed. Trying Yandex Search API...")
    return web_search_yandex(query, search_type="web", max_results=max_results)


def format_search_for_llm(fresh: List[Dict], deep: List[Dict]) -> str:
    """Форматирует результаты поиска для передачи в LLM."""
    parts = []

    if fresh:
        parts.append("## СВЕЖИЕ НОВОСТИ (последняя неделя)\n")
        for i, item in enumerate(fresh, 1):
            flag = "🔴 ГОРЯЧАЯ НОВОСТЬ" if item.get("fresh") else "🟡 Свежая"
            parts.append(
                f"### {flag} [{item['date']}] {item['title']}\n"
                f"Источник: {item['source']} | URL: {item['url']}\n\n"
                f"{item['text']}\n"
            )
    else:
        parts.append("## СВЕЖИЕ НОВОСТИ\n⚠️ Новостей за последнюю неделю не найдено.\n")

    if deep:
        parts.append("\n## ГЛУБИННЫЕ ИСТОЧНИКИ (любой период)\n")
        for item in deep:
            parts.append(
                f"### {item['title']}\nURL: {item['url']}\n\n{item['text']}\n"
            )

    return "\n---\n".join(parts)


def format_raw_sources(fresh: List[Dict], deep: List[Dict]) -> str:
    """
    Форматирует сырые источники с порядковыми номерами и уровнем авторитетности.
    """
    parts = []
    idx = 1
    total_chars = 0
    all_items = [
        (item, True) for item in fresh
    ] + [
        (item, False) for item in deep
    ]
    # Tier-1 источники сначала
    all_items.sort(key=lambda x: _source_tier(x[0].get("url", "")))
    for item, is_fresh in all_items:
        text = item.get("text", "").strip()
        if not text:
            continue
        tier = _source_tier(item.get("url", ""))
        text = text[:_TIER_TEXT_LIMIT[tier]]
        date_line = f"Дата: {item.get('date', '')} | " if is_fresh else ""
        part = (
            f"[{idx}] {_TIER_LABEL[tier]} {item.get('title', 'Без заголовка')}\n"
            f"URL: {item.get('url', '')}\n"
            f"{date_line}Уровень: {_TIER_LABEL[tier]}\n\n"
            f"{text}"
        )
        total_chars += len(part)
        if total_chars > _RAW_SOURCES_CAP:
            break
        parts.append(part)
        idx += 1
    return "\n\n---\n\n".join(parts) if parts else "(источники не найдены)"
