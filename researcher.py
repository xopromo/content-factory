#!/usr/bin/env python3
"""
Universal Research Agent — config-driven
Запуск: python3 researcher.py --config research_configs/chelyabinsk.json
"""

import argparse

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import hashlib


def search_web(query: str, max_results: int = 5, region: str = "ru-ru",
               timelimit: str = None) -> List[Dict[str, str]]:
    """Поиск в DuckDuckGo через пакет ddgs. timelimit: 'h'=час, 'd'=день, 'w'=неделя"""
    try:
        from ddgs import DDGS
        kwargs = {"max_results": max_results, "region": region}
        if timelimit:
            kwargs["timelimit"] = timelimit
        with DDGS() as ddgs:
            results = list(ddgs.text(query, **kwargs))
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


def fetch_article(url: str, max_chars: int = 3000) -> Dict[str, str]:
    """Скачивает статью, возвращает {'text': ..., 'date': ...}"""
    try:
        import requests as req
        import trafilatura
        import htmldate
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        r = req.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return {}
        # Многие ru-сайты объявляют ISO-8859-1 но реально отдают UTF-8
        r.encoding = "utf-8"
        html = r.text
        text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
        date = htmldate.find_date(html) or ""
        return {"text": text[:max_chars], "date": date}
    except Exception as e:
        print(f"  [WARN] fetch_article failed for {url[:60]}: {e}")
        return {}


def fetch_article_text(url: str, max_chars: int = 3000) -> str:
    """Обратная совместимость"""
    return fetch_article(url, max_chars).get("text", "")


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

def is_relevant(text: str, platform: str, platform_keywords: List[str] = None) -> bool:
    """Проверяет что текст относится к теме платформы"""
    text_lower = text.lower()
    keywords = platform_keywords or PLATFORM_KEYWORDS.get(platform, [])
    if not keywords:
        return True  # если ключевых слов нет — пропускаем фильтр
    return any(kw in text_lower for kw in keywords)

def is_irrelevant_summary(summary: str) -> bool:
    """Проверяет, что LLM сам признал контент нерелевантным"""
    markers = ["не имеет отношения", "не относится", "не связан", "не является темой",
               "не про рекламу", "не по теме", "данная статья не"]
    summary_lower = summary.lower()
    return any(m in summary_lower for m in markers)


def extract_insights_from_search(results: List[Dict[str, str]], platform: str, topic: str,
                                 platform_keywords: List[str] = None) -> List[Dict[str, str]]:
    """Извлекает структурированные инсайты из результатов поиска."""
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

        if not is_relevant(title + " " + body, platform, platform_keywords):
            print(f"  [SKIP] Not relevant to {platform}: {title[:60]}")
            continue

        snippet = body[:300]

        # Пробуем получить полный текст и дату публикации
        article = fetch_article(href) if href else {}
        article_text = article.get("text", "")
        source_published_at = article.get("date", "")

        if article_text and is_mostly_russian(article_text):
            llm_summary = summarize_with_llm(title, article_text, platform)
            if llm_summary and is_irrelevant_summary(llm_summary):
                print(f"  [SKIP] LLM marked irrelevant: {title[:60]}")
                continue
            print(f"  [OK] Full article + LLM summary{' date:'+source_published_at if source_published_at else ''}: {title[:50]}")
        else:
            llm_summary = ""
            print(f"  [OK] Snippet fallback: {title[:50]}")

        content = llm_summary if llm_summary else snippet

        insights.append({
            "title": title[:80] if title else topic,
            "content": content,
            "snippet": snippet,
            "summary": llm_summary,
            "source_published_at": source_published_at,
            "source_url": href,
        })
    return insights


class ResearchAgent:
    """Universal config-driven research agent"""

    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.project_root = Path(__file__).parent
        output_dir = self.project_root / self.config["output_dir"]
        self.research_dir = output_dir
        self.logs_dir    = output_dir / "logs"
        self.insights_dir = output_dir / "insights"

        self.research_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.insights_dir.mkdir(exist_ok=True)

        self.seen_urls_file = self.insights_dir / "seen_urls.json"
        self.seen_urls = self._load_seen_urls()

        self.session_id = self._generate_session_id()
        self.log_file = self.logs_dir / f"session_{self.session_id}.json"
        self.session_log = {
            "session_id": self.session_id,
            "started_at": datetime.now().isoformat(),
            "config": self.config["name"],
            "research_targets": [p["name"] for p in self.config["platforms"]],
            "log_entries": [],
            "insights": [],
            "statistics": {
                "sources_analyzed": 0,
                "insights_found": 0,
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
                    snippet: str = "", summary: str = "",
                    source_published_at: str = ""):
        insight = {
            "id": len(self.session_log["insights"]) + 1,
            "platform": platform,
            "title": title,
            "content": content,
            "snippet": snippet,
            "summary": summary,
            "source_published_at": source_published_at,
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

    def _search_and_add(self, platform: str, queries: List[Dict], default_confidence: int = 7,
                        region: str = "ru-ru", platform_keywords: List[str] = None,
                        timelimit: str = None):
        """Общий метод: поиск по запросам и добавление инсайтов"""
        total = 0
        for item in queries:
            query = item["query"]
            category = item["category"]
            self.log_action(f"Searching: {query}", {"platform": platform})

            results = search_web(query, max_results=3, region=region, timelimit=timelimit)
            self.session_log["statistics"]["sources_analyzed"] += len(results)

            raw_insights = extract_insights_from_search(
                results, platform, query, platform_keywords=platform_keywords
            )
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
                    source_published_at=ins.get("source_published_at", ""),
                )
                if url_key:
                    self.seen_urls.add(url_key)
                total += 1

        return total

    def run_all_platforms(self):
        timelimit = self.config.get("timelimit")  # 'h', 'd', 'w' или None
        for platform_cfg in self.config["platforms"]:
            name       = platform_cfg["name"]
            queries    = platform_cfg["queries"]
            confidence = platform_cfg.get("confidence", 7)
            keywords   = platform_cfg.get("relevance_keywords", [])

            self.log_action(f"Starting {name} research", {"platform": name})
            count = self._search_and_add(
                name, queries,
                default_confidence=confidence,
                platform_keywords=keywords,
                timelimit=timelimit,
            )
            self.log_action(f"{name} research completed", {"insights_added": count}, status="success")

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
        from datetime import timezone, timedelta
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

        # Фильтр по свежести: если в конфиге есть schedule_hours — оставляем только свежие
        schedule_hours = self.config.get("schedule_hours")
        if schedule_hours:
            cutoff = datetime.now() - timedelta(hours=schedule_hours * 2)
            cutoff_str = cutoff.date().isoformat()
            filtered = []
            for ins in all_insights:
                pub = ins.get("source_published_at", "")
                disc = ins.get("discovered_at", "")[:10]
                date_str = pub if pub else disc
                if date_str >= cutoff_str:
                    filtered.append(ins)
                else:
                    print(f"  [OLD] Skipping stale insight ({date_str}): {ins.get('title','')[:50]}")
            print(f"  [FILTER] Freshness: {len(filtered)}/{len(all_insights)} kept (cutoff {cutoff_str})")
            all_insights = filtered

        # Дедупликация + фильтры: язык, релевантность, LLM-маркер нерелевантности
        seen = set()
        unique_insights = []
        for ins in all_insights:
            title   = ins.get("title", "")
            content = ins.get("content", "")
            snippet = ins.get("snippet", "")
            summary = ins.get("summary", "")
            platform = ins.get("platform", "")

            if not is_mostly_russian(title + " " + content):
                continue
            if not is_relevant(title + " " + content + " " + snippet, platform):
                continue
            if summary and is_irrelevant_summary(summary):
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
        print(f"🚀 RESEARCH AGENT — {self.config['name']}")
        print("="*60 + "\n")

        self.log_action("Agent initialized", {
            "session_id": self.session_id,
            "config": self.config["name"],
            "platforms": [p["name"] for p in self.config["platforms"]],
        })

        self.run_all_platforms()

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="research_configs/traffic.json",
                        help="Path to research config JSON")
    args = parser.parse_args()
    agent = ResearchAgent(args.config)
    agent.run()
