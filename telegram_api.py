import html
import logging
import re
from typing import Optional

import requests

from config import TG_BOT_TOKEN, TG_CHANNEL_ID, CHANNEL_LINK, POST_SIGNATURE

logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"

# Лимиты Telegram Bot API (считаются по ВИДИМЫМ символам, без тегов)
MAX_MESSAGE_LEN = 4096
MAX_CAPTION_LEN = 1024


# ═══════════════════════════════════════════════════════════
#  Форматирование: markdown → HTML Telegram
# ═══════════════════════════════════════════════════════════

def escape(text: str) -> str:
    """Экранирует &, <, > — чтобы Telegram не падал с 'can't parse entities'."""
    return html.escape(text, quote=False)


def md_to_html(text: str) -> str:
    """
    Превращает markdown от нейросети в HTML-разметку Telegram.
    ВАЖНО: на вход подаётся УЖЕ экранированный текст (escape()).

      **жирный** / __жирный__  → <b>
      *курсив*                 → <i>
      `код`                    → <code>
      # Заголовок              → <b>Заголовок</b>
      [текст](url)             → <a href="url">текст</a>
      * пункт / - пункт        → • пункт
    Хэштеги (#игры) не затрагиваются — заголовком считается только "# " с пробелом.
    """
    # ссылки [текст](url)
    text = re.sub(
        r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
        lambda m: f'<a href="{m.group(2).replace(chr(34), "%22")}">{m.group(1)}</a>',
        text,
    )
    # заголовки "# Текст"
    text = re.sub(r"^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*$", r"<b>\1</b>", text, flags=re.M)
    # маркеры списков в начале строки
    text = re.sub(r"^[ \t]*[\*\-][ \t]+(?=\S)", "• ", text, flags=re.M)
    # жирный
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"<b>\1</b>", text)
    # курсив
    text = re.sub(r"(?<![\*\w])\*(?=[^\s\*])([^\n\*]+?)(?<=[^\s\*])\*(?![\*\w])", r"<i>\1</i>", text)
    # код
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    # недопарные звёздочки — убираем, чтобы не торчали в тексте
    text = text.replace("**", "").replace("*", "")
    return text


def prepare_ai_text(raw: str) -> str:
    """Сырой текст нейросети → безопасный HTML для Telegram."""
    return md_to_html(escape(raw.strip()))


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"</?[a-zA-Z][^>]*>", "", text))


def visible_len(text: str) -> int:
    return len(_strip_tags(text))


_HASHTAG_LINE = re.compile(r"^(?:\s*#[\w\d_]+)+\s*$", re.U)


def finalize_post(body: str, link: str = None, link_label: str = "Подробнее") -> str:
    """
    Собирает итоговый пост:
        текст
        🔗 ссылка (под текстом)
        #хэштеги
        🎮 Игровые новости   ← подпись в конце каждого поста
    """
    body = body.strip()

    # Вынимаем завершающую строку с хэштегами, чтобы подпись шла после ссылки
    hashtags = ""
    lines = body.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and _HASHTAG_LINE.match(lines[-1]):
        hashtags = lines.pop().strip()
    body = "\n".join(lines).rstrip()

    parts = [body]
    if link:
        safe = link.replace('"', "%22")
        parts.append(f'🔗 <a href="{safe}">{escape(link_label)}</a>')

    footer = []
    if hashtags:
        footer.append(hashtags)
    sig = f"<b>{escape(POST_SIGNATURE)}</b>"
    if CHANNEL_LINK:
        sig += f' · <a href="{CHANNEL_LINK}">подписаться</a>'
    footer.append(sig)
    parts.append("\n".join(footer))

    return "\n\n".join(p for p in parts if p)


# ═══════════════════════════════════════════════════════════
#  Низкоуровневые вызовы
# ═══════════════════════════════════════════════════════════

def _call(method: str, **kwargs) -> Optional[dict]:
    try:
        r = requests.post(f"{BASE_URL}/{method}", timeout=60, **kwargs)
        data = r.json()
        if not data.get("ok"):
            logger.error(f"TG error [{method}]: {data.get('description')}")
            return {"_error": data.get("description", "")}
        return data["result"]
    except Exception as e:
        logger.error(f"TG request failed [{method}]: {e}")
        return None


def _is_parse_error(result: Optional[dict]) -> bool:
    return bool(result) and "_error" in result and "parse entities" in result["_error"].lower()


def _ok(result: Optional[dict]) -> bool:
    return result is not None and "_error" not in result


def send_message(text: str, chat_id: str = None, parse_mode: str = "HTML",
                 preview: bool = False) -> Optional[dict]:
    payload = {
        "chat_id": chat_id or TG_CHANNEL_ID,
        "text": text[:MAX_MESSAGE_LEN],
        "parse_mode": parse_mode,
        "disable_web_page_preview": not preview,
    }
    res = _call("sendMessage", json=payload)
    if _is_parse_error(res):
        logger.warning("Ошибка разметки — повторяю без форматирования")
        payload.pop("parse_mode")
        payload["text"] = _strip_tags(text)[:MAX_MESSAGE_LEN]
        res = _call("sendMessage", json=payload)
    return res if _ok(res) else None


def send_photo_bytes(image_bytes: bytes, caption: str = "",
                     chat_id: str = None) -> Optional[dict]:
    data = {"chat_id": chat_id or TG_CHANNEL_ID}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    files = {"photo": ("cover.jpg", image_bytes, "image/jpeg")}
    res = _call("sendPhoto", data=data, files=files)
    if _is_parse_error(res):
        data.pop("parse_mode", None)
        data["caption"] = _strip_tags(caption)
        res = _call("sendPhoto", data=data, files=files)
    return res if _ok(res) else None


def send_poll(question: str, options: list[str], chat_id: str = None,
              is_anonymous: bool = True) -> Optional[dict]:
    res = _call("sendPoll", json={
        "chat_id": chat_id or TG_CHANNEL_ID,
        "question": question[:300],
        "options": [o[:100] for o in options][:10],
        "is_anonymous": is_anonymous,
    })
    return res if _ok(res) else None


# ═══════════════════════════════════════════════════════════
#  Высокоуровневый publish
# ═══════════════════════════════════════════════════════════

def publish_post(text: str, image_bytes: bytes = None) -> bool:
    """
    Публикует готовый HTML-текст.
      • Нет картинки → обычное сообщение.
      • Картинка + текст ≤ 1024 видимых символов → ОДИН пост: фото с подписью.
      • Картинка + длинный текст → фото без подписи, сразу следом полный текст
        (без дублирования, как было раньше).
    """
    if not image_bytes:
        ok = send_message(text) is not None
    elif visible_len(text) <= MAX_CAPTION_LEN:
        ok = send_photo_bytes(image_bytes, caption=text) is not None
    else:
        ok = send_photo_bytes(image_bytes) is not None
        if ok:
            ok = send_message(text) is not None

    logger.info("✅ Опубликовано" if ok else "❌ Ошибка публикации")
    return ok


def publish_quiz_poll(question: str, options: list[str]) -> bool:
    ok = send_poll(question, options) is not None
    logger.info("✅ Опрос опубликован" if ok else "❌ Ошибка опроса")
    return ok


def get_me() -> Optional[dict]:
    res = _call("getMe")
    return res if _ok(res) else None
