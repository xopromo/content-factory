#!/usr/bin/env python3
"""Utilities for extracting publication dates from snippets and source pages."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Optional

import requests


MONTHS_EN = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

MONTHS_RU = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def _to_iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return datetime(year, month, day).isoformat()
    except ValueError:
        return None


def normalize_iso_date(value: str) -> Optional[str]:
    if not value:
        return None

    cleaned = html.unescape(value).strip().replace("Z", "+00:00")
    cleaned = cleaned.replace(" UTC", "").replace(" GMT", "")

    try:
        return datetime.fromisoformat(cleaned).isoformat()
    except ValueError:
        pass

    date_only = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", cleaned)
    if date_only:
        return _to_iso(int(date_only.group(1)), int(date_only.group(2)), int(date_only.group(3)))

    return None


def extract_date_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    normalized = html.unescape(text)

    iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", normalized)
    if iso_match:
        return _to_iso(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))

    en_match = re.search(
        r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s*(20\d{2})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if en_match:
        month = MONTHS_EN.get(en_match.group(1).lower())
        if month:
            return _to_iso(int(en_match.group(3)), month, int(en_match.group(2)))

    ru_match = re.search(
        r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(20\d{2})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if ru_match:
        month = MONTHS_RU.get(ru_match.group(2).lower())
        if month:
            return _to_iso(int(ru_match.group(3)), month, int(ru_match.group(1)))

    return None


def _meta_candidates(html_text: str) -> list[str]:
    patterns = [
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']publish_date["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']pubdate["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']date["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+itemprop=["\']datePublished["\'][^>]+content=["\']([^"\']+)["\']',
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'"dateCreated"\s*:\s*"([^"]+)"',
        r'"uploadDate"\s*:\s*"([^"]+)"',
    ]
    candidates: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, html_text, flags=re.IGNORECASE):
            candidates.append(match)
    return candidates


def fetch_source_publication_date(url: str, timeout: int = 12) -> Optional[str]:
    if not url:
        return None

    try:
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return None

    html_text = response.text

    for candidate in _meta_candidates(html_text):
        iso_value = normalize_iso_date(candidate)
        if iso_value:
            return iso_value

        parsed_from_text = extract_date_from_text(candidate)
        if parsed_from_text:
            return parsed_from_text

    json_ld_blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in json_ld_blocks:
        try:
            payload = json.loads(html.unescape(block.strip()))
        except Exception:
            continue

        for key in ("datePublished", "dateCreated", "uploadDate"):
            iso_value = _find_jsonld_date(payload, key)
            if iso_value:
                return iso_value

    return extract_date_from_text(html_text[:5000])


def _find_jsonld_date(payload: object, key: str) -> Optional[str]:
    if isinstance(payload, dict):
        if key in payload:
            raw = payload.get(key)
            if isinstance(raw, str):
                iso_value = normalize_iso_date(raw) or extract_date_from_text(raw)
                if iso_value:
                    return iso_value
        for value in payload.values():
            found = _find_jsonld_date(value, key)
            if found:
                return found

    if isinstance(payload, list):
        for item in payload:
            found = _find_jsonld_date(item, key)
            if found:
                return found

    return None


def resolve_publication_date(content: str = "", source_url: str = "") -> Optional[str]:
    snippet_date = extract_date_from_text(content)
    if snippet_date:
        return snippet_date
    return fetch_source_publication_date(source_url)
