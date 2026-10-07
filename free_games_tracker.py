"""
Раздачи из других магазинов (Steam, GOG, Humble и др.) через CheapShark API.
Ключ не нужен. Точной даты окончания у CheapShark нет — честно предупреждаем,
что раздача временная. Ссылки идут через redirect CheapShark (требование API).
"""
import logging
from typing import Optional

import requests

from telegram_api import escape as tg_escape

logger = logging.getLogger(__name__)

CHEAPSHARK_DEALS_URL = "https://www.cheapshark.com/api/1.0/deals"
CHEAPSHARK_REDIRECT = "https://www.cheapshark.com/redirect?dealID={}"

# ⚠️ Впиши реальный контакт (юзернейм канала или email) — требование CheapShark.
USER_AGENT = "tg_geek_bot_yandex/1.0 (contact: ВПИШИ_СВОЙ_КОНТАКТ)"

STORE_NAMES = {
    "1": "Steam", "2": "GamersGate", "3": "GreenManGaming", "7": "GOG",
    "8": "Humble Store", "11": "Fanatical", "15": "GameBillet",
    "21": "IndieGala", "24": "2Game", "27": "Gamesplanet",
    "28": "Gamesload", "29": "WinGameStore", "36": "Epic Games Store",
}


def get_cheapshark_free_games() -> list[dict]:
    params = {"upperPrice": 0, "sortBy": "Recent", "pageSize": 60}
    try:
        r = requests.get(CHEAPSHARK_DEALS_URL, params=params,
                         headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        deals = r.json()
    except Exception as e:
        logger.error(f"CheapShark API error: {e}")
        return []

    games = []
    for d in deals:
        try:
            sale, normal = float(d.get("salePrice", 1)), float(d.get("normalPrice", 0))
        except (TypeError, ValueError):
            continue
        if sale != 0 or normal <= 0:
            continue
        store_id = str(d.get("storeID", ""))
        deal_id = d.get("dealID", "")
        app_id = d.get("steamAppID")
        # картинку берём покрупнее: у Steam-игр есть нормальный header
        img = (f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"
               if app_id and app_id != "0" else d.get("thumb", ""))
        games.append({
            "title": d.get("title", "Неизвестная игра"),
            "store": STORE_NAMES.get(store_id, f"магазин #{store_id}"),
            "normal_price": normal,
            "url": CHEAPSHARK_REDIRECT.format(deal_id) if deal_id else "https://www.cheapshark.com/",
            "image_url": img,
        })
    logger.info(f"🔎 CheapShark: найдено {len(games)} бесплатных раздач")
    return games


def format_cheapshark_post(games: list[dict]) -> Optional[str]:
    if not games:
        return None
    lines = ["🎁 <b>Раздают бесплатно прямо сейчас</b>\n"]
    for g in games[:4]:
        price = f"{g['normal_price']:.2f}".rstrip("0").rstrip(".")
        lines.append(f"🎮 <b>{tg_escape(g['title'])}</b> — {tg_escape(g['store'])}")
        lines.append(f"💰 Обычная цена: ${price}")
        lines.append(f'🔗 <a href="{g["url"]}">Забрать в {tg_escape(g["store"])}</a>\n')
    lines.append("⚠️ Раздачи временные и могут закончиться в любой момент.")
    lines.append("\n#раздача #бесплатно #халява")
    return "\n".join(lines)
