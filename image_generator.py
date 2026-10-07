"""
Обложки для постов в стиле «крупный заголовок на тёмной подложке» (как у Kod.ru):
  • если у новости/игры есть своя картинка — она идёт фоном на всю обложку,
    поверх — тёмный градиент, плашка рубрики и крупный жирный заголовок;
  • если картинки нет — аккуратный тёмный фон с геометрией в цвете рубрики.
Никакой нейросетевой генерации: никаких случайных «странных» картинок.
"""
import io
import logging
import os
import re
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

W, H = 1280, 720
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [
    os.path.join(BASE_DIR, "fonts"),
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
]
HEADLINE_FONT = ["DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
LABEL_FONT = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]

# рубрика → (текст плашки, акцентный цвет, цвета фона без картинки)
STYLES = {
    "gaming_news":   ("НОВОСТИ",       (255, 205, 0),   ((18, 20, 34), (44, 30, 80))),
    "game_announce": ("АНОНС",         (140, 110, 255), ((14, 16, 36), (52, 28, 96))),
    "game_review":   ("ОБЗОР",         (0, 214, 180),   ((10, 24, 30), (14, 66, 70))),
    "steam_deals":   ("СКИДКИ",        (255, 84, 112),  ((26, 14, 24), (84, 22, 54))),
    "epic_freebie":  ("БЕСПЛАТНО",     (70, 230, 130),  ((10, 26, 22), (16, 70, 50))),
    "game_fact":     ("ФАКТ",          (255, 150, 40),  ((26, 18, 12), (90, 48, 14))),
    "daily_quiz":    ("ВИКТОРИНА",     (80, 190, 255),  ((10, 18, 34), (16, 52, 96))),
}
DEFAULT_STYLE = ("ИГРЫ", (255, 205, 0), ((18, 20, 34), (44, 30, 80)))

CHANNEL_MARK = "ИГРОВЫЕ НОВОСТИ"


# ── вспомогательное ────────────────────────────────────────

def _font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    logger.warning("Шрифт с кириллицей не найден — положи .ttf в папку fonts/")
    return ImageFont.load_default()


_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U00002B00-\U00002BFF\U00002190-\U000021FF]+"
)


def clean_title(text: str, limit: int = 78) -> str:
    """Из первой строки поста делает чистый заголовок для обложки."""
    first = next((l for l in text.split("\n") if l.strip()), "")
    first = re.sub(r"<[^>]+>", "", first)
    first = re.sub(r"&amp;", "&", first)
    first = re.sub(r"&lt;|&gt;|&quot;", "", first)
    first = _EMOJI.sub("", first)
    first = re.sub(r"#\w+", "", first)
    first = re.sub(r"[*_`]+", "", first)
    first = re.sub(r"\s+", " ", first).strip(" -–—:•")
    if len(first) > limit:
        cut = first[:limit]
        sp = cut.rfind(" ")
        first = (cut[:sp] if sp > limit * 0.5 else cut).rstrip(" ,.:;-–—") + "…"
    return first or "Игровые новости"


def download_image(url: str, max_bytes: int = 8_000_000) -> Optional[bytes]:
    """Скачивает картинку по ссылке. Возвращает None, если это не картинка."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image"):
            return None
        data = r.raw.read(max_bytes + 1, decode_content=True)
        if len(data) > max_bytes or len(data) < 2000:
            return None
        Image.open(io.BytesIO(data)).verify()
        return data
    except Exception as e:
        logger.warning(f"Не удалось скачать картинку {url[:80]}: {e}")
        return None


def _cover_crop(img: Image.Image) -> Image.Image:
    """Масштаб с обрезкой до W×H. Маленькие картинки (Steam 460×215) растягиваются
    поверх размытой копии, чтобы не было мыла на весь экран."""
    img = img.convert("RGB")
    scale = max(W / img.width, H / img.height)
    bg = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H))

    if img.width < 900:  # низкое разрешение → блюр-фон + чёткий оригинал по центру
        bg = bg.filter(ImageFilter.GaussianBlur(28))
        fit = min((W - 240) / img.width, 300 / img.height)
        fg = img.resize((int(img.width * fit), int(img.height * fit)), Image.LANCZOS)
        shadow = Image.new("RGBA", (fg.width + 60, fg.height + 60), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((30, 30, fg.width + 30, fg.height + 30), 22, fill=(0, 0, 0, 150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        x, y = (W - fg.width) // 2, 112
        bg = bg.convert("RGBA")
        bg.alpha_composite(shadow, (x - 30, y - 20))
        mask = Image.new("L", fg.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, fg.width, fg.height), 18, fill=255)
        bg.paste(fg, (x, y), mask)
        return bg.convert("RGB")
    return bg


def _gradient_bg(c1, c2) -> Image.Image:
    """Диагональный градиент + мягкая геометрия."""
    base = Image.new("RGB", (W, H), c1)
    top = Image.new("RGB", (W, H), c2)
    mask = Image.linear_gradient("L").rotate(35, expand=True).resize((W, H))
    base = Image.composite(top, base, mask)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.ellipse((W - 520, -260, W + 160, 420), fill=(255, 255, 255, 14))
    d.ellipse((W - 340, 120, W + 260, 720), outline=(255, 255, 255, 30), width=3)
    for i in range(7):
        x = 760 + i * 70
        d.line((x, H, x + 260, 0), fill=(255, 255, 255, 12), width=2)
    return Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")


def _wrap(draw, text, font, max_w) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_title(draw, text, max_w, max_lines=3):
    for size in range(68, 38, -2):
        font = _font(HEADLINE_FONT, size)
        lines = _wrap(draw, text, font, max_w)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_w for l in lines):
            return font, lines, size
    font = _font(HEADLINE_FONT, 38)
    return font, _wrap(draw, text, font, max_w)[:max_lines], 38


# ── главная функция ────────────────────────────────────────

def make_cover(title: str, category: str = "gaming_news",
               source_image: Optional[bytes] = None) -> bytes:
    label, accent, (c1, c2) = STYLES.get(category, DEFAULT_STYLE)

    if source_image:
        try:
            canvas = _cover_crop(Image.open(io.BytesIO(source_image)))
        except Exception as e:
            logger.warning(f"Битая картинка-источник: {e}")
            canvas = _gradient_bg(c1, c2)
    else:
        canvas = _gradient_bg(c1, c2)

    # тёмная подложка под текст: снизу вверх + лёгкое общее затемнение
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = ov.load()
    for y in range(H):
        t = y / H
        a = int(40 + 215 * max(0.0, (t - 0.28) / 0.72) ** 1.35)
        for x in range(W):
            px[x, y] = (6, 8, 16, min(a, 238))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), ov)

    d = ImageDraw.Draw(canvas)
    pad = 64

    # плашка рубрики
    lf = _font(LABEL_FONT, 26)
    tw = d.textlength(label, font=lf)
    d.rounded_rectangle((pad, pad - 6, pad + tw + 44, pad + 52), 12, fill=accent)
    d.text((pad + 22, pad + 23), label, font=lf, fill=(14, 16, 24), anchor="lm")

    # метка канала справа сверху
    mf = _font(LABEL_FONT, 22)
    d.text((W - pad, pad + 23), CHANNEL_MARK, font=mf, fill=(255, 255, 255, 215), anchor="rm")

    # заголовок
    title = clean_title(title)
    font, lines, size = _fit_title(d, title, W - pad * 2 - 20)
    lh = int(size * 1.13)
    block_h = lh * len(lines)
    bottom = H - pad - 16
    y = bottom - block_h
    d.rectangle((pad, y - 30, pad + 120, y - 22), fill=accent)   # акцентная черта
    for i, line in enumerate(lines):
        d.text((pad + 2, y + i * lh + 3), line, font=font, fill=(0, 0, 0, 120))   # тень
        d.text((pad, y + i * lh), line, font=font, fill=(255, 255, 255))

    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue()


def build_cover(text: str, category: str, image_url: str = "",
                title: str = "") -> bytes:
    """Удобная обёртка: скачивает картинку-источник (если есть) и рисует обложку."""
    src = download_image(image_url) if image_url else None
    return make_cover(title or text, category, src)
