#!/usr/bin/env python3
"""
Knowledge Search — быстрый семантический поиск по базе знаний.
Использует ripgrep для точного поиска + скоринг релевантности.
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"

CONTEXT_LINES = 5  # строк вокруг найденного фрагмента


def rg_search(query: str, path: Path) -> list[dict]:
    """Ищет query в файлах через ripgrep, возвращает фрагменты с контекстом."""
    if not path.exists():
        return []
    result = subprocess.run(
        [
            "rg", "--json", "-i",
            "--context", str(CONTEXT_LINES),
            "--max-count", "5",
            query, str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):
        return fallback_grep(query, path)

    fragments = []
    current: dict | None = None

    for line in result.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get("type") == "begin":
            current = {"file": obj["data"]["path"]["text"], "lines": []}
        elif obj.get("type") == "match" and current is not None:
            current["lines"].append(obj["data"]["lines"]["text"])
        elif obj.get("type") == "context" and current is not None:
            current["lines"].append(obj["data"]["lines"]["text"])
        elif obj.get("type") == "end" and current is not None:
            fragments.append({
                "file": current["file"],
                "text": "".join(current["lines"]),
            })
            current = None

    return fragments


def fallback_grep(query: str, path: Path) -> list[dict]:
    """Запасной вариант через Python-grep если ripgrep недоступен."""
    fragments = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for fpath in path.rglob("*.md"):
        lines = fpath.read_text(encoding="utf-8", errors="ignore").splitlines()
        for i, line in enumerate(lines):
            if pattern.search(line):
                start = max(0, i - CONTEXT_LINES)
                end = min(len(lines), i + CONTEXT_LINES + 1)
                fragments.append({
                    "file": str(fpath),
                    "text": "\n".join(lines[start:end]),
                })
                if len(fragments) >= 10:
                    return fragments
    return fragments


def score_fragment(fragment: dict, keywords: list[str]) -> float:
    """Скоринг релевантности: количество найденных ключевых слов."""
    text = fragment["text"].lower()
    return sum(1 for kw in keywords if kw.lower() in text)


def search(query: str, top_k: int = 5) -> list[dict]:
    """
    Основной метод поиска.
    Возвращает top_k наиболее релевантных фрагментов из knowledge/.
    """
    keywords = [w for w in query.split() if len(w) > 3]
    fragments = rg_search(query, KNOWLEDGE_DIR)

    for kw in keywords[:3]:
        if kw != query:
            fragments.extend(rg_search(kw, KNOWLEDGE_DIR))

    seen = set()
    unique = []
    for f in fragments:
        key = f["text"][:100]
        if key not in seen:
            seen.add(key)
            unique.append(f)

    scored = sorted(unique, key=lambda f: score_fragment(f, keywords), reverse=True)
    return scored[:top_k]


def format_pack(results: list[dict]) -> str:
    """Форматирует результаты в компактный контекстный пакет для субагентов."""
    if not results:
        return "(база знаний не содержит релевантных фрагментов)"
    lines = ["## Контекстный пакет из базы знаний\n"]
    for i, r in enumerate(results, 1):
        source = Path(r["file"]).name
        lines.append(f"### Фрагмент {i} (источник: {source})\n```\n{r['text'].strip()}\n```\n")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python knowledge_search.py 'поисковый запрос'")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    results = search(query)
    print(format_pack(results))
