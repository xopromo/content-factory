#!/usr/bin/env python3
"""Backfill source publication dates for existing research insights."""

from __future__ import annotations

import json
from pathlib import Path

from research_dates import resolve_publication_date


def enrich_insight(insight: dict) -> bool:
    current_value = insight.get("source_published_at")
    if current_value:
        return False

    resolved = resolve_publication_date(
        content=insight.get("content", ""),
        source_url=insight.get("source_url", ""),
    )
    if not resolved:
        return False

    insight["source_published_at"] = resolved
    return True


def process_file(path: Path) -> tuple[int, int]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    changed = 0
    total = 0

    if isinstance(payload, list):
        for insight in payload:
            total += 1
            changed += int(enrich_insight(insight))
    elif isinstance(payload, dict) and isinstance(payload.get("insights"), list):
        for insight in payload["insights"]:
            total += 1
            changed += int(enrich_insight(insight))
    else:
        return 0, 0

    if changed:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    return total, changed


def main() -> None:
    root = Path(__file__).parent / "docs" / "research" / "insights"
    files = sorted(root.glob("insights_*.json")) + [root / "index.json"]

    total_items = 0
    total_changed = 0

    for path in files:
        if not path.exists():
            continue
        processed, changed = process_file(path)
        total_items += processed
        total_changed += changed
        print(f"{path.name}: processed={processed}, updated={changed}")

    print(f"Done. processed={total_items}, updated={total_changed}")


if __name__ == "__main__":
    main()
