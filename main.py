"""
Telegram Geek Bot (игровой канал) — главный файл.
Запуск: python main.py        Тест: python main.py --now [категория]
Категории: gaming_news game_announce game_review steam_deals epic_freebie game_fact daily_quiz
"""
import logging
import random
import signal
import sys
import time
from datetime import datetime

import pytz
import schedule

from config import (POST_SCHEDULE, SLOT_CATEGORIES,
                    TG_BOT_TOKEN, TG_CHANNEL_ID, YANDEX_API_KEY)
import telegram_api as tg
from content_generator import generate_post
from epic_tracker import get_free_games, format_epic_post
from free_games_tracker import get_cheapshark_free_games, format_cheapshark_post
from image_generator import build_cover
from post_cache import (record_post, get_last_categories, was_epic_posted,
                        mark_epic_posted, mark_seen, get_stats)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler("bot.log", encoding="utf-8")],
)
logger = logging.getLogger("main")
MSK = pytz.timezone("Europe/Moscow")

# Если у рубрики нет свежих данных — запасные рубрики (тоже только про игры)
FALLBACKS = ["game_fact", "game_review", "gaming_news"]


def pick_category(slot: str) -> str:
    candidates = SLOT_CATEGORIES.get(slot, ["gaming_news"])
    last = get_last_categories(6)
    fresh = [c for c in candidates if c not in last]
    return random.choice(fresh or candidates)


def _publish_generated(category: str) -> bool:
    post = generate_post(category)
    if not post:
        return False

    # Викторина: нативный опрос + текст с подписью, без обложки
    if post["is_poll"] and post["poll_data"]:
        pd = post["poll_data"]
        poll_ok = tg.publish_quiz_poll(pd["question"], pd["options"])
        text = tg.finalize_post(post["text"])
        msg_ok = tg.send_message(text) is not None
        if poll_ok and msg_ok:
            record_post(category, post["text"])
            return True
        logger.error("Викторина опубликована не полностью — в кэш не пишу")
        return False

    text = tg.finalize_post(post["text"], post["link"], post["link_label"])
    cover = build_cover(post["title"], category, post["image_url"])
    if tg.publish_post(text, image_bytes=cover):
        record_post(category, post["title"])
        if post["seen_key"]:
            mark_seen(post["seen_key"])
        return True
    logger.error(f"Пост [{category}] не опубликован — в кэш не пишу")
    return False


def _publish_epic() -> bool:
    """Раздачи: официальный Epic API + CheapShark (остальные магазины)."""
    epic = get_free_games()
    epic_titles = {g["title"].lower() for g in epic}
    others = [g for g in get_cheapshark_free_games() if g["title"].lower() not in epic_titles]

    new_epic = [g for g in epic if not was_epic_posted(g["title"])]
    new_other = [g for g in others if not was_epic_posted(g["title"])]
    if not new_epic and not new_other:
        logger.info("Новых раздач нет")
        return False

    parts = [p for p in (format_epic_post(new_epic) if new_epic else None,
                         format_cheapshark_post(new_other) if new_other else None) if p]
    # у склеенных частей хэштеги в середине — оставляем только финальные
    text = tg.finalize_post("\n\n".join(parts))

    first = (new_epic or new_other)[0]
    title = f"Бесплатно: {first['title']}" + (f" и ещё {len(new_epic + new_other) - 1}"
                                              if len(new_epic + new_other) > 1 else "")
    cover = build_cover(title, "epic_freebie", first.get("image_url", ""))

    if tg.publish_post(text, image_bytes=cover):
        for g in new_epic + new_other:
            mark_epic_posted(g["title"])
        record_post("epic_freebie", first["title"])
        return True
    logger.error("Пост про раздачи не опубликован — в кэш не пишу")
    return False


def publish_post(slot: str = "morning", forced_category: str = None):
    category = forced_category or pick_category(slot)
    now = datetime.now(MSK).strftime("%H:%M")
    logger.info(f"═══ Пост [{slot}] [{category}] в {now} МСК ═══")

    ok = _publish_epic() if category == "epic_freebie" else _publish_generated(category)

    if not ok and not forced_category:
        for fb in random.sample(FALLBACKS, len(FALLBACKS)):
            if fb == category:
                continue
            logger.info(f"↩️ Запасная рубрика: {fb}")
            if _publish_generated(fb):
                break

    logger.info(f"📊 Всего постов: {get_stats()['total']}")


def setup_schedule():
    for e in POST_SCHEDULE:
        t = f"{e['hour']:02d}:{e['minute']:02d}"
        schedule.every().day.at(t, MSK).do(publish_post, slot=e["slot"])
        logger.info(f"📅 [{e['slot']}] → {t} МСК")
    logger.info(f"⏭ Следующий пост: {schedule.next_run()}")


def check_config():
    errors = []
    if not TG_BOT_TOKEN:
        errors.append("TG_BOT_TOKEN не задан")
    if not TG_CHANNEL_ID:
        errors.append("TG_CHANNEL_ID не задан")
    if not YANDEX_API_KEY:
        errors.append("YANDEX_API_KEY не задан")
    if errors:
        for e in errors:
            logger.error(f"❌ {e}")
        sys.exit(1)
    me = tg.get_me()
    logger.info(f"✅ Telegram бот: @{me.get('username', '?')}" if me
                else "⚠️ Не удалось проверить токен Telegram")


def main():
    logger.info("🎮 Telegram Geek Bot стартует!")
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    check_config()

    if "--now" in sys.argv:
        i = sys.argv.index("--now")
        publish_post(slot="morning", forced_category=sys.argv[i + 1] if i + 1 < len(sys.argv) else None)
        return

    logger.info(f"📊 Постов в базе: {get_stats()['total']}")
    setup_schedule()
    logger.info("🚀 Бот работает! 4 поста в день.")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
