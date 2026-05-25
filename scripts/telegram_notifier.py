#!/usr/bin/env python3
"""
Telegram Notifier — отправляет уведомления о прогрессе генерации статей.
Требует переменные окружения: TG_BOT_TOKEN, TG_CHAT_ID
"""

import os
import json
import urllib.request
from typing import Optional


def send(text: str, parse_mode: str = "HTML") -> bool:
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        print(f"[TG SKIP — нет токена] {text[:80]}")
        return False

    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[TG ERROR] {e}")
        return False


def step_report(
    step: int,
    agent: str,
    elapsed: float,
    tokens: int,
    success: bool = True,
    error: Optional[str] = None,
) -> bool:
    icon = "✅" if success else "❌"
    text = (
        f"{icon} <b>Шаг {step:02d}</b> — <code>{agent}</code>\n"
        f"⏱ {elapsed:.1f}с | ~{tokens:,} токенов"
    )
    if error:
        text += f"\n⚠️ {error[:200]}"
    return send(text)


def article_start(title: str, topic: str) -> bool:
    return send(f"🚀 <b>Генерация запущена</b>\n📝 {title}\n🔍 {topic}")


def article_done(title: str, slug: str) -> bool:
    return send(f"🎉 <b>Статья готова!</b>\n📝 {title}\n📁 docs/articles/{slug}.md")


def human_review_request(step: int, title: str, preview: str) -> bool:
    return send(
        f"⏸ <b>Шаг {step} — требуется решение</b>\n"
        f"<b>{title}</b>\n\n{preview[:600]}\n\n"
        f"Ответьте: <code>ok</code> — продолжить | <code>stop</code> — остановить"
    )


if __name__ == "__main__":
    print("Тест отправки уведомления...")
    success = send("🔧 <b>Content Factory</b> — тест уведомления ✅")
    print("Отправлено!" if success else "Не отправлено (проверьте TG_BOT_TOKEN и TG_CHAT_ID)")
