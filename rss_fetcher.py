

import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import requests

from config import RSS_FEEDS

logger = logging.getLogger(__name__)


def _fetch_feed(url: str, max_age_hours: int = 48) -> list[dict]:

    try:

        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        items  = []

        for entry in feed.entries[:20]:
            # Парсим дату
            pub = entry.get("published_parsed") or entry.get("updated_parsed")
            if pub:
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue

            title   = entry.get("title", "").strip()
            summary = entry.get("summary", "")[:500].strip()
            link    = entry.get("link", "")

            # Убираем HTML-теги из summary
            import re
            summary = re.sub(r"<[^>]+>", "", summary).strip()

            if title:
                items.append({
                    "title":   title,
                    "summary": summary,
                    "link":    link,
                    "source":  feed.feed.get("title", ""),
                })

        return items

    except Exception as e:
        logger.warning(f"RSS ошибка {url}: {e}")
        return []


def get_latest_news(count: int = 5) -> list[dict]:

    all_items = []
    for name, url in RSS_FEEDS.items():
        items = _fetch_feed(url)
        all_items.extend(items)
        if items:
            logger.info(f"📰 {name}: {len(items)} новостей")


    random.shuffle(all_items)
    return all_items[:count]


def format_news_for_prompt(news: list[dict]) -> str:

    if not news:
        return ""

    lines = ["Свежие игровые новости (используй одну из них для поста):"]
    for i, n in enumerate(news, 1):
        lines.append(f"\n{i}. {n['title']}")
        if n["summary"]:
            lines.append(f"   {n['summary'][:200]}")
        if n["link"]:
            lines.append(f"   Источник: {n['link']}")

    return "\n".join(lines)


def get_news_context() -> str:

    news = get_latest_news(count=5)
    if not news:
        logger.warning("RSS: новости не получены, будем без контекста")
        return ""
    return format_news_for_prompt(news)
