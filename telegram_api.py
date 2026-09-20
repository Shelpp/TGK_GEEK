import html
import logging
import requests
from typing import Optional
from config import TG_BOT_TOKEN, TG_CHANNEL_ID

logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"

# Лимиты Telegram Bot API
MAX_MESSAGE_LEN = 4096
MAX_CAPTION_LEN = 1024


def _call(method: str, **kwargs) -> Optional[dict]:
    try:
        r = requests.post(f"{BASE_URL}/{method}", timeout=30, **kwargs)
        data = r.json()
        if not data.get("ok"):
            logger.error(f"TG error [{method}]: {data.get('description')}")
            return None
        return data["result"]
    except Exception as e:
        logger.error(f"TG request failed [{method}]: {e}")
        return None


def _hook_line(text: str, limit: int = MAX_CAPTION_LEN) -> str:
    """Берёт начало текста в пределах лимита — для короткой подписи к фото.
    Итоговая строка ГАРАНТИРОВАННО не длиннее limit символов (иначе Telegram
    отклонит весь запрос ошибкой caption too long)."""
    if len(text) <= limit:
        return text
    suffix = "\n\n(продолжение ниже 👇)"
    budget = limit - len(suffix)
    cut = text[:budget]
    last_break = max(cut.rfind("\n\n"), cut.rfind(". "), cut.rfind("!\n"), cut.rfind("?\n"))
    if last_break > budget * 0.4:
        cut = cut[:last_break + 1]
    result = cut.rstrip() + suffix
    return result[:limit]


# ── Отправка текста ────────────────────────────────────────

def send_message(text: str, chat_id: str = None,
                 parse_mode: str = "HTML") -> Optional[dict]:
    text = text[:MAX_MESSAGE_LEN]
    return _call("sendMessage", json={
        "chat_id":    chat_id or TG_CHANNEL_ID,
        "text":       text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    })


# ── Отправка фото (URL) ────────────────────────────────────

def send_photo_url(image_url: str, caption: str = "",
                   chat_id: str = None) -> Optional[dict]:
    caption = _hook_line(caption)
    return _call("sendPhoto", json={
        "chat_id":    chat_id or TG_CHANNEL_ID,
        "photo":      image_url,
        "caption":    caption,
        "parse_mode": "HTML",
    })


# ── Отправка фото (bytes) ──────────────────────────────────

def send_photo_bytes(image_bytes: bytes, caption: str = "",
                     chat_id: str = None) -> Optional[dict]:
    caption = _hook_line(caption)
    return _call("sendPhoto",
        data={
            "chat_id":    chat_id or TG_CHANNEL_ID,
            "caption":    caption,
            "parse_mode": "HTML",
        },
        files={"photo": ("image.jpg", image_bytes, "image/jpeg")},
    )


# ── Отправка опроса (Telegram Poll) ───────────────────────

def send_poll(question: str, options: list[str],
              chat_id: str = None,
              is_anonymous: bool = True) -> Optional[dict]:
    """Создаёт нативный опрос в канале."""
    return _call("sendPoll", json={
        "chat_id":      chat_id or TG_CHANNEL_ID,
        "question":     question[:300],
        "options":      [o[:100] for o in options][:10],
        "is_anonymous": is_anonymous,
    })


# ── Высокоуровневый publish ────────────────────────────────

def publish_post(text: str,
                 image_url: str   = None,
                 image_bytes: bytes = None) -> bool:
    """
    Публикует пост. Если текст длиннее лимита подписи к фото (1024 симв.),
    отправляет картинку с коротким "крючком", а полный текст — отдельным
    сообщением сразу следом, чтобы Telegram не отклонил пост целиком.
    """
    full_text_needs_followup = bool((image_bytes or image_url) and len(text) > MAX_CAPTION_LEN)

    if image_bytes:
        result = send_photo_bytes(image_bytes, caption=text)
    elif image_url:
        result = send_photo_url(image_url, caption=text)
    else:
        result = send_message(text)

    ok = result is not None

    if ok and full_text_needs_followup:
        follow_up = send_message(text)
        ok = ok and (follow_up is not None)

    logger.info("✅ Опубликовано" if ok else "❌ Ошибка публикации")
    return ok


def publish_quiz_poll(question: str, options: list[str]) -> bool:

    result = send_poll(question, options)
    ok = result is not None
    logger.info("✅ Опрос опубликован" if ok else "❌ Ошибка опроса")
    return ok


# ── Утилита экранирования для текста, который пойдёт в HTML-разметку ──

def escape(text: str) -> str:
    """Экранирует HTML-спецсимволы (&, <, >), чтобы Telegram не падал
    с 'can't parse entities', если в AI-тексте случайно окажутся эти символы."""
    return html.escape(text, quote=False)


# ── Проверка токена ────────────────────────────────────────

def get_me() -> Optional[dict]:
    return _call("getMe")
