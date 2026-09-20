"""
Telegram Geek Bot — главный файл.
Запуск: python main.py
Тест:   python main.py --now [категория]
"""

import logging
import random
import signal
import sys
import time
from datetime import datetime
import pytz
import schedule

from config import (
    POST_SCHEDULE, SLOT_CATEGORIES,
    TG_BOT_TOKEN, TG_CHANNEL_ID, YANDEX_API_KEY,
)
import telegram_api as tg
from content_generator import generate_post
from epic_tracker import get_free_games, format_epic_post
from free_games_tracker import get_cheapshark_free_games, format_cheapshark_post
from marketplace_finder import find_marketplace_product, format_marketplace_post
from image_generator import get_image
from post_cache import (
    record_post, get_last_categories,
    was_epic_posted, mark_epic_posted, get_stats,
)

# ── Логирование ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")
MSK = pytz.timezone("Europe/Moscow")


# ── Выбор категории ────────────────────────────────────────

def pick_category(slot: str) -> str:
    """Выбирает рубрику для слота, избегая недавних повторов."""
    candidates    = SLOT_CATEGORIES.get(slot, ["gaming_news"])
    last          = get_last_categories(6)
    fresh         = [c for c in candidates if c not in last]
    pool          = fresh if fresh else candidates
    return random.choice(pool)


# ── Публикация одного поста ────────────────────────────────

def publish_post(slot: str = "morning", forced_category: str = None):
    category = forced_category or pick_category(slot)
    now      = datetime.now(MSK).strftime("%H:%M")
    logger.info(f"═══ Пост [{slot}] [{category}] в {now} МСК ═══")

    # ── Особые рубрики: маркетплейс и Epic ────────────────
    if category == "marketplace_find":
        _publish_marketplace()
        return

    if category == "epic_freebie":
        _publish_epic()
        return

    # ── Стандартный AI-пост ────────────────────────────────
    post = generate_post(category)
    text = post["text"]

    # Если это викторина — публикуем poll + текст
    if post.get("is_poll") and post.get("poll_data"):
        pd = post["poll_data"]
        poll_ok = tg.publish_quiz_poll(pd["question"], pd["options"])
        # Текст викторины отправляем отдельно (пояснение + ответ)
        msg_ok = tg.send_message(text) is not None
        if poll_ok and msg_ok:
            record_post(category, text)
        else:
            logger.error(f"Викторина [{category}] опубликована не полностью — в кэш не записываю")
        return

    # Картинка
    img = get_image(post["image_query"], post["needs_image"])
    ok = tg.publish_post(text, image_bytes=img)
    if ok:
        record_post(category, text)
    else:
        logger.error(f"Пост [{category}] не опубликован — в кэш не записываю")

    stats = get_stats()
    logger.info(f"📊 Всего постов: {stats['total']}")


def _publish_marketplace():
    """Публикует гайд по выбору гик-товара (без выдуманных цен/рейтингов)."""
    product = find_marketplace_product()
    if not product:
        logger.warning("Маркетплейс-гайд: не удалось сгенерировать, fallback")
        post = generate_post("gadget_review")
        ok = tg.publish_post(post["text"])
        if ok:
            record_post("gadget_review", post["text"])
        return

    text = format_marketplace_post(product)
    # Картинку не генерируем для этой рубрики — нет реального фото товара
    ok = tg.send_message(text) is not None
    if ok:
        record_post("marketplace_find", product.get("tag", ""))
    else:
        logger.error("Маркетплейс-гайд не опубликован — в кэш не записываю")


def _publish_epic():
    """Публикует пост о текущих бесплатных раздачах: сначала официальный
    Epic API (точные даты окончания), затем CheapShark — остальные магазины
    (Steam, GOG, Humble и др.), у которых нет точной даты, но есть сам факт
    раздачи. Дубли между источниками (Epic попадает и в CheapShark) убираются."""
    epic_games = get_free_games()
    epic_titles_lower = {g["title"].lower() for g in epic_games}

    cheapshark_games = get_cheapshark_free_games()
    cheapshark_games = [g for g in cheapshark_games if g["title"].lower() not in epic_titles_lower]

    new_epic       = [g for g in epic_games if not was_epic_posted(g["title"])]
    new_cheapshark = [g for g in cheapshark_games if not was_epic_posted(g["title"])]

    if not new_epic and not new_cheapshark:
        logger.info("Раздач нет или все уже анонсированы, fallback на steam_deals")
        post = generate_post("steam_deals")
        img  = get_image(post["image_query"], post["needs_image"])
        ok = tg.publish_post(post["text"], image_bytes=img)
        if ok:
            record_post("steam_deals", post["text"])
        return

    parts = []
    if new_epic:
        parts.append(format_epic_post(new_epic))
    if new_cheapshark:
        parts.append(format_cheapshark_post(new_cheapshark))
    text = "\n\n".join(p for p in parts if p)

    img_url = (new_epic[0].get("image_url") if new_epic else None) \
        or (new_cheapshark[0].get("image_url") if new_cheapshark else None) \
        or ""

    # publish_post сам разрулит лимит подписи (1024 симв.) и дошлёт остаток
    # отдельным сообщением, если раздач в посте несколько и текст длинный.
    ok = tg.publish_post(text, image_url=img_url) if img_url else tg.publish_post(text)

    if ok:
        for g in new_epic + new_cheapshark:
            mark_epic_posted(g["title"])
        first_title = new_epic[0]["title"] if new_epic else new_cheapshark[0]["title"]
        record_post("epic_freebie", first_title)
    else:
        logger.error("Пост про раздачи не опубликован — в кэш не записываю")


# ── Расписание ─────────────────────────────────────────────

def setup_schedule():
    for entry in POST_SCHEDULE:
        h, m, slot = entry["hour"], entry["minute"], entry["slot"]
        time_str    = f"{h:02d}:{m:02d}"
        schedule.every().day.at(time_str, MSK).do(publish_post, slot=slot)
        logger.info(f"📅 [{slot}] → {time_str} МСК")

    logger.info(f"⏭  Следующий пост: {schedule.next_run()}")


# ── Проверка конфига ───────────────────────────────────────

def check_config():
    errors = []
    if not TG_BOT_TOKEN:
        errors.append("TG_BOT_TOKEN не задан (@BotFather → /newbot)")
    if not TG_CHANNEL_ID:
        errors.append("TG_CHANNEL_ID не задан")
    if not YANDEX_API_KEY:
        errors.append("YANDEX_API_KEY не задан")
    if errors:
        for e in errors:
            logger.error(f"❌ {e}")
        sys.exit(1)

    me = tg.get_me()
    if me:
        logger.info(f"✅ Telegram бот: @{me.get('username', '?')}")
    else:
        logger.warning("⚠️  Не удалось проверить токен Telegram")


# ── Точка входа ────────────────────────────────────────────

def main():
    logger.info("🎮 Telegram Geek Bot стартует!")
    logger.info("=" * 50)

    signal.signal(signal.SIGINT,  lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    check_config()

    # Режим --now [категория]
    if "--now" in sys.argv:
        idx = sys.argv.index("--now")
        cat = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        slot = "morning"
        logger.info(f"⚡ Немедленная публикация: {cat or 'авто'}")
        publish_post(slot=slot, forced_category=cat)
        return

    stats = get_stats()
    logger.info(f"📊 Постов в базе: {stats['total']}")

    setup_schedule()
    logger.info("🚀 Бот работает! 4 поста в день.")
    logger.info("   --now gaming_news  — опубликовать сейчас")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
