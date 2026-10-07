import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHANNEL_ID = os.getenv("TG_CHANNEL_ID", "")
# Необязательно: @username или ссылка на канал — попадёт в подпись поста.
# Пример: CHANNEL_LINK=https://t.me/my_channel
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
YANDEX_MODEL = "yandexgpt-lite"

# ── RSS: ТОЛЬКО игровые источники ───
# 4pda и habr_gamedev убраны — это железо, софт и инженерные темы.
# Если в логах "📰 <источник>: 0 новостей" — проверь адрес RSS в браузере.
RSS_FEEDS = {
    "dtf_games":  "https://dtf.ru/rss/games",
    "stopgame":   "https://stopgame.ru/rss/news.xml",
    "playground": "https://www.playground.ru/rss/news/",
    "ixbt_games": "https://www.ixbt.com/export/games.rss",
}

# Новости про железо/гаджеты/ИТ отсекаются по этим словам (в заголовке и описании)
OFFTOPIC_KEYWORDS = [
    "видеокарт", "процессор", "смартфон", "iphone", "android", "ноутбук",
    "geforce", "radeon", "ryzen", "intel core", "оперативн", "ssd", "nvme",
    "материнск", "роутер", "wi-fi", "5g", "windows 11", "linux", "ios 1",
    "нейросет", "chatgpt", "искусственн", "биткоин", "криптовалют",
    "электромобил", "tesla", "samsung galaxy", "xiaomi", "техника",
    "драйвер", "прошивк", "программист", "разработчикам по",
]

# ── Расписание ──
POST_SCHEDULE = [
    {"hour": 9,  "minute": 0,  "slot": "morning"},
    {"hour": 13, "minute": 0,  "slot": "midday"},
    {"hour": 18, "minute": 30, "slot": "evening"},
    {"hour": 21, "minute": 30, "slot": "night"},
]

# Только игры
SLOT_CATEGORIES = {
    "morning": ["gaming_news", "game_announce"],
    "midday":  ["game_review", "gaming_news"],
    "evening": ["epic_freebie", "steam_deals"],
    "night":   ["daily_quiz", "game_fact"],
}

CHANNEL_NAME = "Игровые новости"
POST_SIGNATURE = "🎮 Игровые новости"   # подпись в конце каждого поста

POSTED_CACHE_FILE = "posted_cache.json"
MAX_CACHE_SIZE = 1000
