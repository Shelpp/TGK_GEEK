
import json
import logging
import random
import time
from typing import Optional

import requests

from config import (
    YANDEX_API_KEY, YANDEX_FOLDER_ID, YANDEX_MODEL,
    GEEK_PRODUCT_TAGS, MARKETPLACES,
)
from rss_fetcher import get_news_context
from telegram_api import escape as tg_escape

logger = logging.getLogger(__name__)

YANDEX_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# ── Системный промпт ───────────────────────────────────────
SYSTEM = """Ты — редактор Telegram-канала «Игры и Гик-новости».
Пишешь живые, цепляющие посты для геймеров и гиков на русском языке.
Твоя цель — чтобы пост дочитывали до конца, сохраняли и комментировали.

Правила:
• ПЕРВАЯ СТРОКА — самое важное. Именно она видна в превью уведомления и в
  списке чата, до того как пользователь откроет пост. Она должна цеплять
  за 1 секунду: конкретный факт, цифра, интрига или вопрос. Никогда не
  начинай с общих фраз вроде "Сегодня хотим рассказать" или "Новость дня".
• Длина: 180–350 слов. Не больше, не меньше.
• Тон: дружелюбный, экспертный, чуть дерзкий. Как старший друг-гик, а не
  пресс-релиз.
• Структура: заголовок-крючок с эмодзи → суть в 1-2 предложениях →
  конкретная деталь/цифра/сравнение → мнение или инсайт → вопрос к читателю.
• Короткие абзацы (1-3 строки) — это Telegram, читают с телефона.
• Никаких шаблонных фраз: «как вы знаете», «стоит отметить», «это очень
  важно», «в мире технологий».
• Всегда конкретика: названия игр, цифры, цены в рублях, даты. Если точных
  данных нет в предоставленном контексте — пиши обобщённо, не выдумывай
  цифры и факты, которые выдаёшь за подтверждённые.
• Только эмодзи и переносы строк — никаких # в середине текста и никаких **.
• Заканчивай ОДНИМ из двух: вопросом, который легко и быстро ответить в
  комментариях («А вы уже..?», «Согласны?», «Что выберете?») ИЛИ фразой
  «Сохрани, чтобы не потерять 🔖».
• В последней строке (отдельной) добавь 2-3 релевантных хэштега строчными
  буквами без пробелов внутри, например: #геймдев #скидки #anime — только
  по теме конкретного поста, не универсальный список.
• Только русский язык."""


def _call_yandex(system: str, user: str, temperature: float = 0.8) -> Optional[str]:
    """Делает запрос к YandexGPT API и возвращает текст ответа."""
    model_uri = f"gpt://{YANDEX_FOLDER_ID}/{YANDEX_MODEL}/latest"

    payload = {
        "modelUri": model_uri,
        "completionOptions": {
            "stream":      False,
            "temperature": temperature,
            "maxTokens":   2000,
        },
        "messages": [
            {"role": "system", "text": system},
            {"role": "user",   "text": user},
        ],
    }
    headers = {
        "Authorization":    f"Api-Key {YANDEX_API_KEY}",
        "Content-Type":     "application/json",
        "x-folder-id":      YANDEX_FOLDER_ID,
    }

    for attempt in range(3):
        try:
            r = requests.post(YANDEX_URL, json=payload, headers=headers, timeout=60)


            if r.status_code == 429:
                wait = 65 * (attempt + 1)
                logger.warning(f"YandexGPT rate limit, жду {wait}с...")
                time.sleep(wait)
                continue

            r.raise_for_status()
            data = r.json()
            text = data["result"]["alternatives"][0]["message"]["text"]
            return text.strip()

        except requests.HTTPError as e:
            logger.error(f"YandexGPT HTTP {r.status_code}: {r.text[:200]}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"YandexGPT попытка {attempt+1}: {e}")
            time.sleep(10)

    return None


# ── Промпты по рубрикам ──

def _get_prompt(category: str) -> tuple[str, str]:


    if category in ("gaming_news", "game_announce", "tech_news"):
        # Для новостей подгружаем RSS-контекст
        news_ctx = get_news_context()
        base = {
            "gaming_news":   "Выбери одну из новостей ниже и напиши живой пост о ней. Добавь своё мнение.",
            "game_announce": "Выбери анонс игры из новостей ниже и напиши пост. Жанр, платформы, дата, почему ждать.",
            "tech_news":     "Выбери технологическую новость из списка ниже и напиши пост для геймера/гика.",
        }[category]

        user = f"{base}\n\n{news_ctx}" if news_ctx else (
            base + "\n\nНапиши пост о любой актуальной новости игровой индустрии которую знаешь."
        )
        return SYSTEM, user

    prompts = {
        "game_review": (
            SYSTEM,
            "Напиши мини-обзор одной популярной игры (2023–2025). "
            "Жанр, платформы, плюсы, минусы, кому зайдёт. Живое мнение без оценок."
        ),
        "gadget_review": (
            SYSTEM,
            "Напиши обзор одного интересного гик-гаджета 2024–2025: "
            "клавиатура, мышь, гарнитура, контроллер или похожее. "
            "Что умеет, цена в рублях, где купить в России."
        ),
        "geek_gadget": (
            SYSTEM,
            "Расскажи о необычном гик-гаджете с изюминкой — не банальные наушники. "
            "Цена в рублях, где купить, зачем вообще нужно."
        ),
        "marketplace_find": _marketplace_prompt(),
        "epic_freebie": (
            SYSTEM,
            "Напиши общий пост про формат бесплатных раздач в Epic Games Store: "
            "как часто бывают раздачи, как не пропустить, как включить уведомления "
            "в приложении Epic Games. НЕ называй конкретные игры и даты раздач — "
            "у тебя нет актуальных данных, а неверная информация о временной акции "
            "введёт подписчиков в заблуждение. Заверши призывом подписаться на "
            "уведомления Epic, чтобы не пропускать раздачи."
        ),
        "steam_deals": (
            SYSTEM,
            "Напиши пост о топ-3 горячих скидках в Steam. "
            "Для каждой: название, жанр, % скидки, цена со скидкой в рублях. "
            "Выбирай хорошие игры со скидкой >50%."
        ),
        "daily_quiz": (
            SYSTEM + "\n\nДополнительно: после текста поста добавь викторину в формате:\n"
            "ВОПРОС: [вопрос]\nА) ...\nБ) ...\nВ) ...\nГ) ...\nОТВЕТ: [буква и объяснение]\n\n"
            "Используй только широко известные, легко проверяемые факты (даты выхода "
            "культовых игр, рекорды продаж, известные разработчики/студии). Если не "
            "уверен в точности факта на 100% — выбери другой, более очевидный вопрос. "
            "Лучше простой достоверный вопрос, чем эффектный, но сомнительный.",
            "Напиши короткий вступительный текст (2–3 предложения) и викторину "
            "по теме игр, кино или технологий. Вопрос должен быть интересным, "
            "но с однозначно верным и общеизвестным ответом. Попроси написать "
            "ответ в комментарии."
        ),
        "geek_fact": (
            SYSTEM,
            "Расскажи один удивительный факт из мира игр, технологий или поп-культуры. "
            "Что-то, что захочется переслать другу. Только реальные факты."
        ),
        "anime_pick": (
            SYSTEM,
            "Порекомендуй одно аниме для геймера/гика — 2023–2025 или недооценённая классика. "
            "Жанр, количество серий, где смотреть в России, почему зайдёт."
        ),
        "movie_pick": (
            SYSTEM,
            "Порекомендуй фильм или сериал для гика — фантастика, киберпанк, игровая тема. "
            "Из 2023–2025 или недооценённая классика. Где смотреть в России."
        ),
    }
    return prompts.get(category, (SYSTEM, "Напиши интересный пост об играх или технологиях для гиков."))


def _marketplace_prompt() -> tuple[str, str]:
    mp  = random.choice(MARKETPLACES)
    tag = random.choice(GEEK_PRODUCT_TAGS)
    return (
        SYSTEM,
        f"Напиши пост-находку о конкретном товаре категории «{tag}» с {mp}. "
        f"Придумай реальный пример: название, характеристики, цена в рублях (актуальная 2025), "
        f"рейтинг, почему это крутая покупка для гика. Скажи честно — стоит ли брать. "
        f"В конце: «Ищите на {mp}: [название товара]»"
    )


# ── Основная функция ──

def generate_post(category: str) -> dict:
    logger.info(f"🤖 YandexGPT генерирует [{category}]...")

    system, user = _get_prompt(category)
    text = _call_yandex(system, user)

    if not text:
        logger.error(f"YandexGPT не ответил для [{category}], fallback")
        return _fallback(category)

    # Экранируем спецсимволы HTML (&, <, >), чтобы Telegram не отклонил
    # пост ошибкой "can't parse entities", если модель случайно вставит
    # такой символ (например, "5 < 10" или "Cyberpunk 2077 & DLC").
    text = tg_escape(text)

    image_query = _build_image_query(category)
    needs_image = category in (
        "gaming_news", "game_announce", "game_review",
        "gadget_review", "geek_gadget", "marketplace_find",
        "anime_pick", "movie_pick",
    )

    # Викторина
    is_poll   = category == "daily_quiz"
    poll_data = _extract_poll(text) if is_poll else None

    logger.info(f"✅ [{category}] готово ({len(text)} симв.)")
    return {
        "text":        text,
        "category":    category,
        "image_query": image_query,
        "needs_image": needs_image,
        "is_poll":     is_poll,
        "poll_data":   poll_data,
    }


def _build_image_query(category: str) -> str:
    queries = {
        "gaming_news":     "video game news 2025 gaming",
        "game_announce":   "new video game announcement epic cinematic",
        "tech_news":       "gaming technology GPU gadget 2025",
        "game_review":     "video game screenshot gameplay",
        "gadget_review":   "mechanical keyboard gaming mouse RGB",
        "geek_gadget":     "cool geek gadget neon tech",
        "marketplace_find":"gaming product buy online",
        "epic_freebie":    "epic games store free game",
        "steam_deals":     "steam sale discount gaming",
        "daily_quiz":      "gaming quiz trivia neon",
        "geek_fact":       "mind blowing tech fact science",
        "anime_pick":      "anime art illustration 2024",
        "movie_pick":      "sci-fi movie cinematic poster",
    }
    return queries.get(category, "gaming geek neon 2025")


def _extract_poll(text: str) -> Optional[dict]:
    # text уже экранирован для HTML (send_message), но нативный Telegram-опрос
    # (sendPoll) не рендерит HTML-разметку — поэтому вопрос/варианты нужно
    # вернуть в "сыром" виде, разэкранировав спецсимволы обратно.
    import html as _html
    question, options = "", []
    for line in text.split("\n"):
        line = line.strip()
        if line.upper().startswith("ВОПРОС:"):
            question = line.split(":", 1)[1].strip()
        elif line.startswith(("А)", "Б)", "В)", "Г)")):
            options.append(line[2:].strip())
    if question and len(options) >= 2:
        question = _html.unescape(question)[:300]
        options  = [_html.unescape(o) for o in options][:4]
        return {"question": question, "options": options}
    return None


def _fallback(category: str) -> dict:
    return {
        "text": (
            "🎮 Технические работы — скоро вернёмся!\n\n"
            "А пока: во что играете прямо сейчас? 👇"
        ),
        "category":    category,
        "image_query": "gaming setup neon",
        "needs_image": False,
        "is_poll":     False,
        "poll_data":   None,
    }
