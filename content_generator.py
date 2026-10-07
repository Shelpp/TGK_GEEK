import html as _html
import logging
import time
from typing import Optional

import requests

from config import YANDEX_API_KEY, YANDEX_FOLDER_ID, YANDEX_MODEL
from rss_fetcher import get_fresh_news
from steam_source import pick_game
from telegram_api import prepare_ai_text

logger = logging.getLogger(__name__)

YANDEX_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# ── Системный промпт ───────────────────────────────────────

SYSTEM = """Ты — редактор Telegram-канала «Игровые новости». Канал ТОЛЬКО про видеоигры.
Пишешь живые, цепляющие посты для геймеров на русском языке.

Тематика: видеоигры, игровая индустрия, релизы, анонсы, скидки, раздачи, киберспорт.
ЗАПРЕЩЕНО писать про: железо и комплектующие, смартфоны, ноутбуки, программирование,
ИИ и нейросети, инженерные и IT-новости, аниме, кино, гаджеты. Если в данных такое
встретилось — не используй.

Правила:
• ПЕРВАЯ СТРОКА — цепляющий заголовок с одним эмодзи, выдели его **жирным**. Конкретный
  факт, цифра или интрига. Без фраз вроде «Сегодня расскажем» и «Новость дня».
• Объём: 450–750 символов. Строго не больше — текст должен помещаться в подпись к картинке.
• Тон: дружелюбный, экспертный, чуть дерзкий — как старший друг-геймер, не пресс-релиз.
• Структура: заголовок → суть в 1–2 предложениях → важная деталь или цифра → твоё мнение
  → короткий вопрос читателю.
• Короткие абзацы (1–3 строки), между абзацами пустая строка.
• Ключевые названия игр и цифры можно выделять **жирным** — но не больше 3–4 раз за пост.
• Никаких шаблонов: «как вы знаете», «стоит отметить», «в мире технологий».
• ТОЛЬКО факты из предоставленных данных. Не выдумывай цены, даты, оценки и характеристики.
  Если данных не хватает — пиши обобщённо.
• НЕ вставляй ссылки и URL — ссылку добавит система.
• Заканчивай коротким вопросом, на который легко ответить в комментариях.
• Последняя строка отдельно: 2–3 хэштега строчными буквами, например: #игры #steam #скидки
• Только русский язык."""


def _call_yandex(system: str, user: str, temperature: float = 0.7) -> Optional[str]:
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/{YANDEX_MODEL}/latest",
        "completionOptions": {"stream": False, "temperature": temperature, "maxTokens": 1200},
        "messages": [
            {"role": "system", "text": system},
            {"role": "user", "text": user},
        ],
    }
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json",
        "x-folder-id": YANDEX_FOLDER_ID,
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
            return r.json()["result"]["alternatives"][0]["message"]["text"].strip()
        except requests.HTTPError:
            logger.error(f"YandexGPT HTTP {r.status_code}: {r.text[:200]}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"YandexGPT попытка {attempt + 1}: {e}")
            time.sleep(10)
    return None


# ── Факты об игре для промпта ──

def _game_facts(g: dict) -> str:
    lines = [f"Название: {g['title']}"]
    if g.get("genres"):
        lines.append(f"Жанр: {g['genres']}")
    if g.get("developers"):
        lines.append(f"Разработчик: {g['developers']}")
    if g.get("release"):
        lines.append(f"Дата выхода: {g['release']}")
    if g.get("discount"):
        lines.append(f"Скидка: -{g['discount']}%, было {g['old_price']}, стало {g['new_price']} (Steam, Россия)")
    elif g.get("new_price"):
        lines.append(f"Цена в Steam: {g['new_price']}")
    if g.get("description"):
        lines.append(f"Описание: {g['description']}")
    return "\n".join(lines)


def _result(text: str, category: str, title: str, **kw) -> dict:
    return {
        "text": text, "category": category, "title": title,
        "image_url": kw.get("image_url", ""),
        "link": kw.get("link", ""), "link_label": kw.get("link_label", "Подробнее"),
        "seen_key": kw.get("seen_key", ""),
        "is_poll": kw.get("is_poll", False), "poll_data": kw.get("poll_data"),
    }


# ── Генерация по рубрикам ──

def generate_post(category: str) -> Optional[dict]:
    logger.info(f"🤖 YandexGPT генерирует [{category}]...")

    # 1. Новости — реальная новость из RSS, её картинка и ссылка
    if category == "gaming_news":
        n = get_fresh_news()
        if not n:
            logger.warning("Свежих игровых новостей нет")
            return None
        user = (f"Напиши пост об этой новости. Не придумывай деталей сверх данных.\n\n"
                f"Заголовок: {n['title']}\nКратко: {n['summary']}")
        raw = _call_yandex(SYSTEM, user)
        if not raw:
            return None
        return _result(prepare_ai_text(raw), category, n["title"], image_url=n["image"],
                       link=n["link"], link_label=f"Источник: {n['source'] or 'читать полностью'}",
                       seen_key="news:" + n["link"])

    # 2. Игры из Steam — реальные данные, обложка и ссылка на страницу игры
    if category in ("steam_deals", "game_review", "game_announce"):
        kind = {"steam_deals": "deal", "game_review": "review", "game_announce": "announce"}[category]
        g = pick_game(kind)
        if not g:
            logger.warning(f"Steam: нет новых игр для [{category}]")
            return None
        task = {
            "deal": "Напиши пост о скидке на эту игру: почему стоит взять, кому зайдёт. Цены — строго из данных.",
            "review": "Напиши мини-обзор этой игры: суть, за что любят, кому зайдёт. Без выдуманных оценок.",
            "announce": "Напиши пост-анонс этой игры: жанр, дата выхода, почему её ждать.",
        }[kind]
        raw = _call_yandex(SYSTEM, f"{task}\n\nДанные:\n{_game_facts(g)}")
        if not raw:
            return None
        title = g["title"] if kind != "deal" else f"{g['title']}: скидка {g['discount']}%"
        return _result(prepare_ai_text(raw), category, title, image_url=g["image_url"],
                       link=g["url"], link_label="Страница игры в Steam", seen_key=g["seen_key"])

    # 3. Факт и викторина — без источника
    if category == "game_fact":
        raw = _call_yandex(SYSTEM, "Расскажи один удивительный и ПРОВЕРЕННЫЙ факт из истории или "
                                   "разработки известной видеоигры. Такой, что захочется переслать другу. "
                                   "Если не уверен в точности — выбери другой, более известный факт.")
        if not raw:
            return None
        return _result(prepare_ai_text(raw), category, "Знали ли вы? Факт из мира игр")

    if category == "daily_quiz":
        system = SYSTEM + (
            "\n\nДополнительно: после вступления добавь викторину строго в формате:\n"
            "ВОПРОС: [вопрос]\nА) ...\nБ) ...\nВ) ...\nГ) ...\nОТВЕТ: [буква и короткое объяснение]\n"
            "Только широко известные и легко проверяемые факты о видеоиграх. "
            "Лучше простой достоверный вопрос, чем эффектный, но сомнительный.")
        raw = _call_yandex(system, "Напиши короткое вступление (1–2 предложения) и викторину по видеоиграм. "
                                   "Попроси написать ответ в комментариях.")
        if not raw:
            return None
        poll = _extract_poll(raw)
        if not poll:
            logger.warning("Не удалось разобрать викторину")
            return None
        # в текст поста идут вступление и ответ, сам вопрос — в нативном опросе
        text_raw = "\n".join(l for l in raw.split("\n")
                             if not l.strip().upper().startswith("ВОПРОС:")
                             and not l.strip().startswith(("А)", "Б)", "В)", "Г)")))
        return _result(prepare_ai_text(text_raw), category, "Игровая викторина",
                       is_poll=True, poll_data=poll)

    logger.error(f"Неизвестная рубрика: {category}")
    return None


def _extract_poll(text: str) -> Optional[dict]:
    question, options = "", []
    for line in text.split("\n"):
        line = line.strip().lstrip("*_ ").replace("**", "")
        if line.upper().startswith("ВОПРОС:"):
            question = line.split(":", 1)[1].strip()
        elif line.startswith(("А)", "Б)", "В)", "Г)")):
            options.append(line[2:].strip())
    if question and len(options) >= 2:
        return {"question": _html.unescape(question)[:300],
                "options": [_html.unescape(o) for o in options][:4]}
    return None
