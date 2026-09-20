import json, os, logging
from datetime import datetime
from collections import Counter
from config import POSTED_CACHE_FILE, MAX_CACHE_SIZE

logger = logging.getLogger(__name__)

def _load() -> dict:
    if not os.path.exists(POSTED_CACHE_FILE):
        return {"posts": [], "categories": [], "epic_seen": []}
    try:
        with open(POSTED_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posts": [], "categories": [], "epic_seen": []}

def _save(data: dict):
    try:
        with open(POSTED_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Cache save error: {e}")

def record_post(category: str, snippet: str = ""):
    d = _load()
    d["posts"].append({"ts": datetime.now().isoformat(),
                       "category": category, "snippet": snippet[:80]})
    d["categories"].append(category)
    if len(d["posts"]) > MAX_CACHE_SIZE:
        d["posts"] = d["posts"][-MAX_CACHE_SIZE:]
        d["categories"] = d["categories"][-MAX_CACHE_SIZE:]
    _save(d)

def get_last_categories(n: int = 8) -> list[str]:
    return _load().get("categories", [])[-n:]

def was_epic_posted(title: str) -> bool:
    return title in _load().get("epic_seen", [])

def mark_epic_posted(title: str):
    d = _load()
    seen = d.get("epic_seen", [])
    if title not in seen:
        seen.append(title)
        d["epic_seen"] = seen[-50:]
        _save(d)

def get_stats() -> dict:
    d = _load()
    return {
        "total": len(d.get("posts", [])),
        "by_category": dict(Counter(d.get("categories", []))),
        "last": d["posts"][-1]["ts"] if d.get("posts") else None,
    }
