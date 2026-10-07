

import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import requests
import logging
import random
import re
from datetime import datetime, timezone, timedelta

import feedparser
import requests

from config import RSS_FEEDS, OFFTOPIC_KEYWORDS
from post_cache import was_seen

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (compatible; GeekBot/1.0)"}


def _is_offtopic(title: str, summary: str) -> bool:
    t = f"{title} {summary}".lower()
    return any(k in t for k in OFFTOPIC_KEYWORDS)


def _entry_image(entry) -> str:
    """Ищет картинку новости в самом RSS."""
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key, []) or []:
            if m.get("url"):
                return m["url"]
    for enc in entry.get("enclosures", []) or []:
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    for l in entry.get("links", []) or []:
        if l.get("type", "").startswith("image") and l.get("href"):
            return l["href"]
    html = entry.get("summary", "") or ""
    for c in entry.get("content", []) or []:
        html += c.get("value", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    return m.group(1) if m else ""


def fetch_og_image(url: str) -> str:
    """Если в RSS картинки нет — берём og:image со страницы новости."""
    try:
        r = requests.get(url, headers=UA, timeout=15)
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r.text) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', r.text)
        return m.group(1) if m else ""
    except Exception as e:
        logger.warning(f"og:image не получен: {e}")
        return ""


def _fetch_feed(url: str, max_age_hours: int = 48) -> list[dict]:
    try:
        feed = feedparser.parse(url, request_headers=UA)
        if feed.bozo and not feed.entries:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        items = []
        for entry in feed.entries[:25]:
            pub = entry.get("published_parsed") or entry.get("updated_parsed")
            if pub and datetime(*pub[:6], tzinfo=timezone.utc) < cutoff:
                continue
            title = entry.get("title", "").strip()
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")[:700]).strip()
            link = entry.get("link", "")
            if not title or not link or _is_offtopic(title, summary):
                continue
            items.append({
                "title": title, "summary": summary, "link": link,
                "image": _entry_image(entry),
                "source": feed.feed.get("title", ""),
            })
        return items
    except Exception as e:
        logger.warning(f"RSS ошибка {url}: {e}")
        return []


def get_fresh_news() -> dict | None:
    """Одна свежая игровая новость, которую ещё не публиковали."""
    pool = []
    for name, url in RSS_FEEDS.items():
        items = _fetch_feed(url)
        if items:
            logger.info(f"📰 {name}: {len(items)} новостей")
        pool.extend(items)
    pool = [n for n in pool if not was_seen("news:" + n["link"])]
    if not pool:
        return None
    random.shuffle(pool)
    # предпочитаем новости, у которых уже есть картинка
    pool.sort(key=lambda n: 0 if n["image"] else 1)
    item = pool[0]
    if not item["image"]:
        item["image"] = fetch_og_image(item["link"])
    return item
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
