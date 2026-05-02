#!/usr/bin/env python3
"""
🚀 Traffic Specialist Research Agent
Агент-исследователь для изучения стратегий таргетированной рекламы
VK, Threads, Яндекс Директ

Собирает лайфхаки, лучшие практики и ведет подробные логи исследований
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import hashlib


def search_web(query: str, max_results: int = 5, region: str = "ru-ru") -> List[Dict[str, str]]:
    """Поиск в DuckDuckGo через пакет ddgs"""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region=region))
        return results
    except Exception as e:
        print(f"  [WARN] DuckDuckGo search failed for '{query}': {e}")
        return []


def normalize_url(url: str) -> str:
    """Нормализует URL для сравнения — убирает схему, www и trailing slash"""
    url = url.lower().strip()
    for prefix in ("https://", "http://", "www."):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url.rstrip("/")


def is_mostly_russian(text: str) -> bool:
    """Проверяет, что текст преимущественно на русском языке"""
    if not text:
        return False
    cyrillic = sum(1 for c in text if 'Ѐ' <= c <= 'ӿ')
    letters  = sum(1 for c in text if c.isalpha())
    return letters > 0 and cyrillic / letters >= 0.4


def fetch_article_text(url: str, max_chars: int = 3000) -> str:
    """Скачивает и извлекает чистый текст статьи через requests + trafilatura"""
    try:
        import requests as req
        import trafilatura
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        r = req.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return ""
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False)
        if not text:
            return ""
        return text[:max_chars]
    except Exception as e:
        print(f"  [WARN] fetch_article failed for {url[:60]}: {e}")
        return ""


def summarize_with_llm(title: str, article_text: str, platform: str) -> str:
    """Summarizes article via free LLMs: Gemini → Groq → Mistral → Cerebras"""
    LLM_PROVIDERS = [
        {
            "name": "Gemini",
            "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            "key_env": "GEMINI_KEY",
            "is_gemini": True,
        },
        {
            "name": "Groq",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "model": "llama-3.3-70b-versatile",
            "key_env": "GROQ_KEY",
        },
        {
            "name": "Mistral",
            "url": "https://api.mistral.ai/v1/chat/completions",
            "model": "mistral-small-latest",
            "key_env": "MISTRAL_KEY",
        },
        {
            "name": "Cerebras",
            "url": "https://api.cerebras.ai/v1/chat/completions",
            "model": "llama3.1-8b",
            "key_env": "CEREBRAS_KEY",
        },
    ]

    prompt = (
        f"Ты эксперт по digital-маркетингу. Прочитай статью и напиши саммари на русском языке "
        f"(3-5 предложений) — только конкретные инсайты и практические советы по теме {platform}. "
        f"Без воды.\n\nЗаголовок: {title}\n\nТекст:\n{article_text}"
    )

    try:
        import requests as req
    except ImportError:
        return ""

    for p in LLM_PROVIDERS:
        api_key = os.getenv(p["key_env"], "")
        if not api_key:
            key_file = os.path.expanduser(f"~/.{p['key_env'].lower().replace('_key','')}_key")
            try:
                api_key = open(key_file).read().strip()
            except Exception:
                pass
        if not api_key:
            print(f"  [SKIP] {p['name']}: no key")
            continue
        try:
            if p.get("is_gemini"):
                resp = req.post(
                    f"{p['url']}?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"maxOutputTokens": 400, "temperature": 0.4}},
                    timeout=20,
                )
            else:
                resp = req.post(
                    p["url"],
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": p["model"],
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 400, "temperature": 0.4},
                    timeout=20,
                )

            if resp.status_code == 200:
                if p.get("is_gemini"):
                    result = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                else:
                    result = resp.json()["choices"][0]["message"]["content"].strip()
                print(f"  [LLM] {p['name']} OK")
                return clean_summary(result)

            print(f"  [WARN] {p['name']}: HTTP {resp.status_code}, trying next...")
        except Exception as e:
            print(f"  [WARN] {p['name']} failed: {e}, trying next...")

    return ""


def clean_summary(text: str) -> str:
    """Убирает markdown-разметку, нумерацию, заголовки типа Саммари, длинные тире"""
    # Убираем заголовки типа "**Саммари...:**" или "## Саммари"
    text = re.sub(r'(?mi)^[*#\s]*саммари[^:\n]*[:\n]+', '', text)
    # Убираем **жирный** → просто текст
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # Убираем *курсив*
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # Убираем нумерацию строк "1. ", "2. "
    text = re.sub(r'(?m)^\d+\.\s+', '', text)
    # Длинные тире → дефис
    text = text.replace('—', '-').replace('–', '-')
    # Убираем markdown-заголовки ## ### и т.д.
    text = re.sub(r'(?m)^#{1,6}\s+', '', text)
    # Схлопываем множественные пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


PLATFORM_KEYWORDS = {
    "VK": ["вконтакте", "вк", "vk", "таргет", "реклам", "продвижен", "аудитори", "vk ads", "таргетинг"],
    "Threads": ["threads", "мета", "meta", "продвижен", "контент", "охват", "подписчик", "алгоритм"],
    "Yandex Direct": ["яндекс", "директ", "direct", "контекстн", "ставк", "ключев", "wordstat", "объявлен"],
}

def is_relevant(text: str, platform: str) -> bool:
    """Проверяет что текст относится к теме платформы"""
    text_lower = text.lower()
    keywords = PLATFORM_KEYWORDS.get(platform, [])
    return any(kw in text_lower for kw in keywords)

def is_irrelevant_summary(summary: str) -> bool:
    """Проверяет, что LLM сам признал контент нерелевантным"""
    markers = ["не имеет отношения", "не относится", "не связан", "не является темой",
               "не про рекламу", "не по теме", "данная статья не"]
    summary_lower = summary.lower()
    return any(m in summary_lower for m in markers)


def extract_insights_from_search(results: List[Dict[str, str]], platform: str, topic: str) -> List[Dict[str, str]]:
    """Извлекает структурированные инсайты из результатов поиска.
    Для каждого результата пытается скачать полный текст и сделать LLM-саммари."""
    insights = []
    for r in results:
        title = r.get("title", "").strip()
        body = r.get("body", "").strip()
        href = r.get("href", "")
        if not body:
            continue
        if not is_mostly_russian(title + " " + body):
            print(f"  [SKIP] Non-Russian content: {title[:60]}")
            continue

        # Фильтр по релевантности — сниппет должен содержать ключевые слова платформы
        if not is_relevant(title + " " + body, platform):
            print(f"  [SKIP] Not relevant to {platform}: {title[:60]}")
            continue

        snippet = body[:300]

        # Пробуем получить полный текст статьи и сделать LLM-саммари
        article_text = fetch_article_text(href) if href else ""
        if article_text and is_mostly_russian(article_text):
            llm_summary = summarize_with_llm(title, article_text, platform)
            # Если LLM сам говорит что статья нерелевантна — пропускаем
            if llm_summary and is_irrelevant_summary(llm_summary):
                print(f"  [SKIP] LLM marked irrelevant: {title[:60]}")
                continue
            print(f"  [OK] Full article + LLM summary: {title[:50]}")
        else:
            llm_summary = ""
            print(f"  [OK] Snippet fallback: {title[:50]}")

        # content = саммари если есть, иначе сниппет
        content = llm_summary if llm_summary else snippet

        insights.append({
            "title": title[:80] if title else topic,
            "content": content,
            "snippet": snippet,
            "summary": llm_summary,
            "source_url": href,
        })
    return insights


class TrafficResearchAgent:
    """Агент-исследователь для изучения стратегий трафика"""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.docs_dir = self.project_root / "docs"
        self.research_dir = self.docs_dir / "research"
        self.logs_dir = self.research_dir / "logs"
        self.insights_dir = self.research_dir / "insights"

        self.research_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.insights_dir.mkdir(exist_ok=True)

        self.seen_urls_file = self.insights_dir / "seen_urls.json"
        self.seen_urls = self._load_seen_urls()

        self.session_id = self._generate_session_id()
        self.log_file = self.logs_dir / f"session_{self.session_id}.json"
        self.session_log = {
            "session_id": self.session_id,
            "started_at": datetime.now().isoformat(),
            "platform": "local",
            "research_targets": ["VK", "Threads", "Yandex Direct"],
            "log_entries": [],
            "insights": [],
            "statistics": {
                "sources_analyzed": 0,
                "insights_found": 0,
                "research_hours": 0
            }
        }

    def _load_seen_urls(self) -> set:
        """Загружает список уже виденных URL из файла"""
        if self.seen_urls_file.exists():
            try:
                data = json.loads(self.seen_urls_file.read_text(encoding="utf-8"))
                return set(data.get("urls", []))
            except Exception:
                return set()
        return set()

    def _save_seen_urls(self):
        """Сохраняет список виденных URL на диск"""
        self.seen_urls_file.write_text(
            json.dumps({"urls": sorted(self.seen_urls)}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _generate_session_id(self) -> str:
        timestamp = datetime.now().isoformat()
        return hashlib.md5(timestamp.encode()).hexdigest()[:8]

    def log_action(self, action: str, details: Dict[str, Any], status: str = "info"):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "status": status,
            "details": details
        }
        self.session_log["log_entries"].append(entry)
        print(f"[{status.upper()}] {action}")
        if details:
            print(f"  → {json.dumps(details, ensure_ascii=False, indent=2)}")

    def add_insight(self, platform: str, title: str, content: str,
                    category: str, confidence: int = 7,
                    source_url: Optional[str] = None,
                    snippet: str = "", summary: str = ""):
        insight = {
            "id": len(self.session_log["insights"]) + 1,
            "platform": platform,
            "title": title,
            "content": content,
            "snippet": snippet,
            "summary": summary,
            "category": category,
            "confidence": confidence,
            "discovered_at": datetime.now().isoformat(),
            "tags": self._extract_tags(title + " " + content),
            "source_url": source_url or "",
        }
        self.session_log["insights"].append(insight)
        self.session_log["statistics"]["insights_found"] += 1

        self.log_action(
            f"New insight discovered: {platform}",
            {"title": title, "category": category, "confidence": f"{confidence}/10"},
            status="success"
        )

    def _extract_tags(self, text: str) -> List[str]:
        keywords = [
            "targeting", "audience", "budget", "conversion", "cpc", "cpm",
            "impression", "engagement", "roi", "traffic", "optimization",
            "strategy", "niche", "retargeting", "lookalike", "pixel"
        ]
        text_lower = text.lower()
        return [kw for kw in keywords if kw in text_lower]

    def _search_and_add(self, platform: str, queries: List[Dict], default_confidence: int = 7, region: str = "ru-ru"):
        """Общий метод: поиск по запросам и добавление инсайтов"""
        total = 0
        for item in queries:
            query = item["query"]
            category = item["category"]
            self.log_action(f"Searching: {query}", {"platform": platform})

            results = search_web(query, max_results=3, region=region)
            self.session_log["statistics"]["sources_analyzed"] += len(results)

            raw_insights = extract_insights_from_search(results, platform, query)
            for ins in raw_insights:
                url = ins.get("source_url", "")
                url_key = normalize_url(url) if url else ""
                if url_key and url_key in self.seen_urls:
                    print(f"  [SKIP] Already seen: {url[:60]}")
                    continue
                self.add_insight(
                    platform=platform,
                    title=ins["title"],
                    content=ins["content"],
                    category=category,
                    confidence=default_confidence,
                    source_url=url,
                    snippet=ins.get("snippet", ""),
                    summary=ins.get("summary", ""),
                )
                if url_key:
                    self.seen_urls.add(url_key)
                total += 1

        return total

    def research_vk(self):
        self.log_action("Starting VK research", {"platform": "VK"})

        queries = [
            {"query": "ВКонтакте таргетинг лайфхаки 2026 эффективность аудитории", "category": "targeting"},
            {"query": "ВК реклама оптимизация бюджета ROI стратегия 2026", "category": "budget_optimization"},
            {"query": "ВКонтакте реклама время публикации объявлений лучшее", "category": "timing"},
            {"query": "VK Ads новые фишки обновления 2026", "category": "updates"},
            {"query": "ВК таргет ошибки новичков как избежать", "category": "mistakes"},
        ]

        count = self._search_and_add("VK", queries, default_confidence=7)
        self.log_action("VK research completed", {"insights_added": count}, status="success")

    def research_threads(self):
        self.log_action("Starting Threads research", {"platform": "Threads"})

        queries = [
            {"query": "Threads соцсеть Meta продвижение стратегия 2026 охват -ВКонтакте -вк", "category": "content_strategy"},
            {"query": "Threads app хэштеги алгоритм охват 2026 -вконтакте", "category": "discovery"},
            {"query": "Threads Instagram Meta монетизация рост аудитории маркетинг", "category": "monetization"},
            {"query": "Threads соцсеть вирусный контент что работает -ВК -вконтакте", "category": "viral"},
        ]

        count = self._search_and_add("Threads", queries, default_confidence=7)
        self.log_action("Threads research completed", {"insights_added": count}, status="success")

    def research_yandex_direct(self):
        self.log_action("Starting Yandex Direct research", {"platform": "Yandex Direct"})

        queries = [
            {"query": "Яндекс Директ ключевые слова Wordstat лайфхаки 2026", "category": "keywords"},
            {"query": "Яндекс Директ стратегия ставок оптимизация CPC 2026", "category": "bidding"},
            {"query": "Яндекс Директ минус-слова фильтрация примеры", "category": "filtering"},
            {"query": "Яндекс Директ расширения объявлений CTR увеличение", "category": "optimization"},
            {"query": "Яндекс Директ новинки обновления 2026", "category": "updates"},
        ]

        count = self._search_and_add("Yandex Direct", queries, default_confidence=8)
        self.log_action("Yandex Direct research completed", {"insights_added": count}, status="success")

    def generate_summary(self) -> Dict[str, Any]:
        self.log_action("Generating research summary", {})

        by_platform: Dict[str, list] = {}
        by_category: Dict[str, list] = {}
        for insight in self.session_log["insights"]:
            by_platform.setdefault(insight["platform"], []).append(insight)
            by_category.setdefault(insight["category"], []).append(insight)

        summary = {
            "total_insights": len(self.session_log["insights"]),
            "insights_by_platform": {p: len(i) for p, i in by_platform.items()},
            "insights_by_category": {c: len(i) for c, i in by_category.items()},
            "top_categories": sorted(by_category.items(),
                                     key=lambda x: len(x[1]),
                                     reverse=True)[:5]
        }

        self.log_action("Summary generated", summary, status="success")
        return summary

    def save_session(self):
        self.session_log["ended_at"] = datetime.now().isoformat()

        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.session_log, f, ensure_ascii=False, indent=2)

        self.log_action(f"Session saved", {
            "file": str(self.log_file),
            "total_entries": len(self.session_log["log_entries"]),
            "total_insights": len(self.session_log["insights"])
        }, status="success")

        insights_file = self.insights_dir / f"insights_{self.session_id}.json"
        with open(insights_file, 'w', encoding='utf-8') as f:
            json.dump(self.session_log["insights"], f, ensure_ascii=False, indent=2)

        self._save_seen_urls()
        self._update_insights_index()

    def _update_insights_index(self):
        all_insights = []

        for insight_file in sorted(self.insights_dir.glob("insights_*.json")):
            try:
                with open(insight_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_insights.extend(data)
                    else:
                        all_insights.append(data)
            except Exception as e:
                print(f"Error reading {insight_file}: {e}")

        # Дедупликация по URL (primary) и title+platform (fallback)
        # + фильтр: только русскоязычный контент
        seen = set()
        unique_insights = []
        for ins in all_insights:
            text = ins.get("title", "") + " " + ins.get("content", "")
            if not is_mostly_russian(text):
                continue
            url_key = normalize_url(ins.get("source_url", ""))
            title_key = (ins.get("platform", ""), ins.get("title", "")[:60])
            key = url_key if url_key else str(title_key)
            if key not in seen:
                seen.add(key)
                unique_insights.append(ins)

        index_file = self.insights_dir / "index.json"
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump({
                "total_insights": len(unique_insights),
                "last_updated": datetime.now().isoformat(),
                "insights": unique_insights
            }, f, ensure_ascii=False, indent=2)

    def run(self):
        print("\n" + "="*60)
        print("🚀 TRAFFIC SPECIALIST RESEARCH AGENT")
        print("="*60 + "\n")

        self.log_action("Agent initialized", {
            "session_id": self.session_id,
            "target_platforms": ["VK", "Threads", "Yandex Direct"]
        })

        self.research_vk()
        self.research_threads()
        self.research_yandex_direct()

        summary = self.generate_summary()
        self.save_session()

        print("\n" + "="*60)
        print("✅ RESEARCH COMPLETED")
        print("="*60)
        print(f"\n📊 Results Summary:")
        print(f"  Total insights found: {summary['total_insights']}")
        print(f"  Insights by platform: {summary['insights_by_platform']}")
        print(f"  Insights by category: {summary['insights_by_category']}")
        print(f"\n📁 Logs saved to: {self.log_file}")
        print(f"📁 Insights saved to: {self.insights_dir}")
        print("\n")


if __name__ == "__main__":
    agent = TrafficResearchAgent()
    agent.run()
