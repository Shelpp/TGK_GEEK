import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──
TG_BOT_TOKEN  = os.getenv("TG_BOT_TOKEN", "")
TG_CHANNEL_ID = os.getenv("TG_CHANNEL_ID", "")

YANDEX_API_KEY   = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")


YANDEX_MODEL = "yandexgpt-lite"

# ── RSS-источники игровых новостей ───
# ВАЖНО: rss_fetcher устойчив к неработающим фидам (просто пропускает их
# и не роняет бота), но я не могу проверить их доступность живьём из
# этого окружения — сети до этих доменов у меня нет. Если через пару дней
# в логах будет "📰 <источник>: 0 новостей" для конкретного источника —
# либо RSS-адрес сайта поменялся, либо источник сменил движок. Проверь
# вручную в браузере и поправь адрес в этом словаре.
RSS_FEEDS = {
    "dtf_games":   "https://dtf.ru/rss/games",
    "stopgame":    "https://stopgame.ru/rss/news.xml",
    "4pda":        "https://4pda.to/feed/",
    "ixbt_games":  "https://www.ixbt.com/export/games.rss",
    "playground":  "https://www.playground.ru/rss/news/",
    "kanobu":      "https://kanobu.ru/rss/",
    "habr_gamedev":"https://habr.com/ru/rss/hub/gamedev/all/?fl=ru",
}

# ── Расписание ──
POST_SCHEDULE = [
    {"hour": 9, "minute": 0,  "slot": "morning"},
    {"hour": 13, "minute": 0,  "slot": "midday"},
    {"hour": 18, "minute": 30, "slot": "evening"},
    {"hour": 21, "minute": 30,  "slot": "night"},
]

SLOT_CATEGORIES = {
    "morning": ["gaming_news", "tech_news", "game_announce"],
    "midday":  ["marketplace_find", "game_review", "gadget_review"],
    "evening": ["epic_freebie", "steam_deals", "geek_gadget"],
    "night":   ["daily_quiz", "geek_fact", "anime_pick", "movie_pick"],
}

MARKETPLACES = ["Wildberries", "Ozon", "Яндекс Маркет"]

GEEK_PRODUCT_TAGS = [
    "механическая клавиатура", "игровая мышь", "RGB гаджет",
    "аниме фигурка", "настольная игра", "геймпад",
    "игровая гарнитура", "стриминг оборудование", "ретро консоль",
    "коллекционная фигурка", "VR очки", "LED подсветка",
    "портативная консоль", "DIY Arduino", "гик мерч",
]

CHANNEL_NAME      = "Игры и Гик-новости"
IMAGE_PROBABILITY = 0.45
POSTED_CACHE_FILE = "posted_cache.json"
MAX_CACHE_SIZE    = 1000
