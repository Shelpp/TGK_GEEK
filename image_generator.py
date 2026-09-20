
import base64
import logging
import random
import time
from urllib.parse import quote
from typing import Optional

import requests

from config import YANDEX_API_KEY, YANDEX_FOLDER_ID, IMAGE_PROBABILITY

logger = logging.getLogger(__name__)



POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

POLLINATIONS_STYLES = [
    "cinematic lighting, ultra detailed, 4k",
    "digital art, vibrant colors, sharp",
    "concept art, professional, high quality",
    "neon cyberpunk aesthetic, dramatic",
]


def _pollinations(image_query: str) -> Optional[bytes]:
    """Генерирует картинку через Pollinations.ai — без ключей."""
    style   = random.choice(POLLINATIONS_STYLES)
    prompt  = f"{image_query}, {style}"
    encoded = quote(prompt)
    url     = POLLINATIONS_URL.format(prompt=encoded) + "?width=1024&height=1024&nologo=true"

    try:
        logger.info(f"🎨 Pollinations.ai: «{image_query[:50]}»")
        r = requests.get(url, timeout=60)
        r.raise_for_status()

        # Убеждаемся что вернулась картинка, а не HTML
        ct = r.headers.get("content-type", "")
        if ct.startswith("image"):
            logger.info("✅ Картинка от Pollinations.ai")
            return r.content
        else:
            logger.warning(f"Pollinations вернул не картинку: {ct}")
            return None

    except Exception as e:
        logger.error(f"Pollinations ошибка: {e}")
        return None



YANDEX_ART_URL   = "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
YANDEX_OP_URL    = "https://llm.api.cloud.yandex.net/operations/{}"


def _yandex_art(image_query: str) -> Optional[bytes]:

    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        return None

    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type":  "application/json",
        "x-folder-id":   YANDEX_FOLDER_ID,
    }
    payload = {
        "modelUri": f"art://{YANDEX_FOLDER_ID}/yandex-art/latest",
        "generationOptions": {
            "seed":        random.randint(1, 9_999_999),
            "aspectRatio": {"widthRatio": 1, "heightRatio": 1},
        },
        "messages": [{
            "weight": "1",
            "text":   f"{image_query}, высокое качество, детализация",
        }],
    }

    try:
        logger.info(f"  YandexART: «{image_query[:50]}»")


        r = requests.post(YANDEX_ART_URL, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        operation_id = r.json().get("id")
        if not operation_id:
            return None


        for _ in range(20):
            time.sleep(3)
            op   = requests.get(YANDEX_OP_URL.format(operation_id), headers=headers, timeout=15)
            data = op.json()

            if data.get("done"):
                b64 = data.get("response", {}).get("image", "")
                if b64:
                    logger.info("✅ Картинка от YandexART")
                    return base64.b64decode(b64)
                return None

        logger.warning("YandexART: timeout")
        return None

    except Exception as e:
        logger.error(f"YandexART ошибка: {e}")
        return None


# ── Основная функция ──

def get_image(image_query: str, needs_image: bool) -> Optional[bytes]:

    if not needs_image and random.random() > IMAGE_PROBABILITY:
        return None

    return _pollinations(image_query) or _yandex_art(image_query)
