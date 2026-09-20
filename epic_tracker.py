"""
Трекер бесплатных игр Epic Games Store.
"""

import logging
import requests
from datetime import datetime, timezone
from typing import Optional

from telegram_api import escape as tg_escape

logger = logging.getLogger(__name__)

EPIC_API = (
    "https://store-site-backend-static.ak.epicgames.com"
    "/freeGamesPromotions?locale=ru&country=RU&allowCountries=RU"
)
EPIC_STORE = "https://store.epicgames.com/ru/p/"


def get_free_games() -> list[dict]:

    try:
        r = requests.get(EPIC_API, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        games_raw = (
            r.json()
            .get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
        )
    except Exception as e:
        logger.error(f"Epic API error: {e}")
        return []

    now  = datetime.now(timezone.utc)
    free = []

    for g in games_raw:
        promos = g.get("promotions") or {}
        offers = promos.get("promotionalOffers", [])

        for offer_group in offers:
            for offer in offer_group.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage", 100) != 0:
                    continue

                start = _parse_dt(offer.get("startDate"))
                end   = _parse_dt(offer.get("endDate"))

                if not (start and end and start <= now <= end):
                    continue

                slug = (g.get("productSlug") or "").split("/")[0]
                price_info = (
                    g.get("price", {})
                    .get("totalPrice", {})
                    .get("fmtPrice", {})
                    .get("originalPrice", "бесплатно")
                )

                # Обложка
                img_url = ""
                for img in g.get("keyImages", []):
                    if img.get("type") in ("DieselStoreFrontWide", "OfferImageWide",
                                           "Thumbnail"):
                        img_url = img.get("url", "")
                        break

                free.append({
                    "title":          g.get("title", "Неизвестная игра"),
                    "description":    (g.get("description") or "")[:200],
                    "url":            EPIC_STORE + slug if slug else "https://store.epicgames.com/ru",
                    "original_price": price_info,
                    "end_date":       end.strftime("%d.%m.%Y %H:%M UTC"),
                    "image_url":      img_url,
                })

    return free


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def format_epic_post(games: list[dict]) -> Optional[str]:

    if not games:
        return None

    lines = ["🎁 <b>ХАЛЯВА в Epic Games Store!</b>\n"]
    for g in games:
        title = tg_escape(g["title"])
        desc  = tg_escape(g["description"]) if g["description"] else ""
        price = tg_escape(str(g["original_price"]))
        lines.append(f"🎮 <b>{title}</b>")
        if desc:
            lines.append(f"   {desc}")
        lines.append(f"   💰 Обычная цена: {price}")
        lines.append(f"   ⏰ До: {g['end_date']}")
        lines.append(f"   🔗 {g['url']}\n")

    lines.append("🔥 Забирайте пока не закончилась халява!")
    lines.append("Сохрани чтобы не забыть 🔖")
    lines.append("\n#epicgames #халява #раздача")
    return "\n".join(lines)
