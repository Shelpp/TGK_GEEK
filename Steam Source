"""
Реальные данные об играх из Steam (без ключей): скидки, новинки, анонсы.
Отсюда берём название, цену в рублях, картинку и ссылку на страницу игры.
"""
import logging
import random
import re
from typing import Optional

import requests

from post_cache import was_seen

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (compatible; GeekBot/1.0)"}

FEATURED = "https://store.steampowered.com/api/featuredcategories?cc=ru&l=russian"
DETAILS = "https://store.steampowered.com/api/appdetails?appids={}&cc=ru&l=russian"
STORE = "https://store.steampowered.com/app/{}/"
HEADER = "https://cdn.akamai.steamstatic.com/steam/apps/{}/header.jpg"
HERO = "https://cdn.akamai.steamstatic.com/steam/apps/{}/library_hero.jpg"


def _featured() -> dict:
    try:
        r = requests.get(FEATURED, headers=UA, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Steam featured error: {e}")
        return {}


def _items(block: str) -> list[dict]:
    data = _featured().get(block, {})
    return data.get("items", []) if isinstance(data, dict) else []


def get_details(appid: int) -> Optional[dict]:
    try:
        r = requests.get(DETAILS.format(appid), headers=UA, timeout=20)
        d = r.json().get(str(appid), {})
        if not d.get("success"):
            return None
        return d["data"]
    except Exception as e:
        logger.warning(f"Steam appdetails {appid}: {e}")
        return None


def _money(v) -> str:
    return f"{int(v) / 100:.0f} ₽" if v is not None else ""


def _build(appid: int, base: dict, kind: str) -> dict:
    d = get_details(appid) or {}
    price = d.get("price_overview") or {}
    genres = ", ".join(g["description"] for g in d.get("genres", [])[:3])
    desc = re.sub(r"<[^>]+>", "", d.get("short_description", "") or "")
    title = d.get("name") or base.get("name", "")
    return {
        "appid": appid,
        "title": title,
        "description": desc[:400],
        "genres": genres,
        "release": (d.get("release_date") or {}).get("date", ""),
        "discount": price.get("discount_percent", base.get("discount_percent", 0)),
        "old_price": price.get("initial_formatted") or _money(base.get("original_price")),
        "new_price": price.get("final_formatted") or _money(base.get("final_price")),
        "is_free": d.get("is_free", False),
        "developers": ", ".join(d.get("developers", [])[:2]),
        "url": STORE.format(appid),
        "image_url": d.get("header_image") or HEADER.format(appid),
        "kind": kind,
    }


def pick_game(kind: str) -> Optional[dict]:
    """
    kind: 'deal' — игра со скидкой, 'review' — популярная игра (топ продаж),
          'announce' — скоро выйдет / новинка.
    Возвращает реальные данные игры, о которой ещё не писали.
    """
    block = {"deal": "specials", "review": "top_sellers", "announce": "coming_soon"}[kind]
    items = [i for i in _items(block) if i.get("id") and i.get("name")]
    if kind == "deal":
        items = [i for i in items if (i.get("discount_percent") or 0) >= 40]
        items.sort(key=lambda i: -(i.get("discount_percent") or 0))
        items = items[:12]
    items = [i for i in items if not was_seen(f"steam:{kind}:{i['id']}")]
    if not items:
        return None
    base = random.choice(items[:8])
    game = _build(int(base["id"]), base, kind)
    game["seen_key"] = f"steam:{kind}:{base['id']}"
    return game
