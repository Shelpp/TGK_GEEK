"""
Дополнительный источник раздач — CheapShark API (www.cheapshark.com).

Бесплатный, без ключа и без регистрации. Отслеживает 30+ магазинов
(Steam, GOG, Humble Store, Fanatical, Epic Games Store и др.) и отдаёт
игры, у которых текущая цена 0 — то есть временную раздачу.

ВАЖНОЕ ОТЛИЧИЕ от официального Epic API (epic_tracker.py): у CheapShark
НЕТ данных о точной дате/времени окончания раздачи — только то, что игра
бесплатна ПРЯМО СЕЙЧАС. Поэтому здесь мы не пишем конкретную дату (как
делали раньше для выдуманных раздач), а честно предупреждаем, что раздача
временная и может закончиться в любой момент.

Условия использования API (см. https://apidocs.cheapshark.com/):
- запросы бесплатны, ключ не нужен, но обязателен описательный User-Agent
  с контактом — иначе есть риск блокировки при частых запросах;
- ссылки на раздачу нужно давать через их redirect (это бесплатно для нас
  и так работает их модель монетизации — не убирай эту ссылку на "прямую").
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

CHEAPSHARK_DEALS_URL = "https://www.cheapshark.com/api/1.0/deals"
CHEAPSHARK_REDIRECT  = "https://www.cheapshark.com/redirect?dealID={}"

# ⚠️ ВПИШИ СЮДА РЕАЛЬНЫЙ КОНТАКТ (юзернейм канала, email) — это требование
# CheapShark API, без адекватного User-Agent запросы могут начать банить.
USER_AGENT = "tg_geek_bot_yandex/1.0 (contact: ВПИШИ_СВОЙ_КОНТАКТ)"

STORE_NAMES = {
    "1": "Steam", "2": "GamersGate", "3": "GreenManGaming", "7": "GOG",
    "8": "Humble Store", "11": "Fanatical", "15": "GameBillet",
    "21": "IndieGala", "24": "2Game", "27": "Gamesplanet",
    "28": "Gamesload", "29": "WinGameStore", "36": "Epic Games Store",
}


def get_cheapshark_free_games() -> list[dict]:
    """
    Возвращает список игр, которые СЕЙЧАС можно получить бесплатно
    (salePrice == 0) на любом отслеживаемом CheapShark магазине.
    Игры, у которых normal_price тоже 0 (вечно-бесплатные F2P), отсекаются —
    нас интересуют именно временные раздачи обычно платных игр.
    """
    params = {"upperPrice": 0, "sortBy": "Recent", "pageSize": 60}
    headers = {"User-Agent": USER_AGENT}

    try:
        r = requests.get(CHEAPSHARK_DEALS_URL, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        deals = r.json()
    except Exception as e:
        logger.error(f"CheapShark API error: {e}")
        return []

    free_games = []
    for d in deals:
        try:
            sale_price   = float(d.get("salePrice", 1))
            normal_price = float(d.get("normalPrice", 0))
        except (TypeError, ValueError):
            continue

        if sale_price != 0 or normal_price <= 0:
            continue

        store_id   = str(d.get("storeID", ""))
        store_name = STORE_NAMES.get(store_id, f"магазин #{store_id}")
        deal_id    = d.get("dealID", "")

        free_games.append({
            "title":        d.get("title", "Неизвестная игра"),
            "store":        store_name,
            "normal_price": normal_price,
            "url":          CHEAPSHARK_REDIRECT.format(deal_id) if deal_id else "https://www.cheapshark.com/",
            "image_url":    d.get("thumb", ""),
        })

    logger.info(f"🔎 CheapShark: найдено {len(free_games)} бесплатных раздач")
    return free_games


def format_cheapshark_post(games: list[dict]) -> Optional[str]:
    from telegram_api import escape as tg_escape

    if not games:
        return None

    lines = ["🎁 <b>РАЗДАЮТ БЕСПЛАТНО прямо сейчас!</b>\n"]
    for g in games[:5]:  # не больше 5 за раз, чтобы пост не раздувался
        title = tg_escape(g["title"])
        store = tg_escape(g["store"])
        price = f"{g['normal_price']:.2f}".rstrip("0").rstrip(".")
        lines.append(f"🎮 <b>{title}</b> — {store}")
        lines.append(f"   💰 Обычная цена: ${price}")
        lines.append(f"   🔗 {g['url']}\n")

    lines.append("⚠️ Раздачи временные и могут закончиться в любой момент — не тяните с загрузкой!")
    lines.append("Сохрани чтобы не забыть 🔖")
    lines.append("\n#халява #раздача #скидки")
    return "\n".join(lines)
