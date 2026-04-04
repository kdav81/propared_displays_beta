from __future__ import annotations

import urllib.parse
from datetime import datetime

from app.config import IMAGE_EXTS, MEDIA_DIR, SITE_LOGO_STEM, STATIC_DIR
from app.storage import load_media_library


def parse_optional_date(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def media_public_url(filename: str) -> str:
    return f"/static/slides/{urllib.parse.quote(filename)}"


def media_is_active(item: dict, today=None) -> bool:
    if not item.get("active", True):
        return False
    today = today or datetime.now().date()
    start_date = parse_optional_date(item.get("startDate", ""))
    end_date = parse_optional_date(item.get("endDate", ""))
    if start_date and today < start_date:
        return False
    if end_date and today > end_date:
        return False
    return True


def media_sort_key(item: dict):
    return (
        item.get("startDate", "9999-12-31") or "9999-12-31",
        item.get("uploadedAt", ""),
        item.get("title", "").lower(),
    )


def local_slide_items(active_only: bool = True) -> list[dict]:
    today = datetime.now().date()
    items = []
    for item in load_media_library():
        path = MEDIA_DIR / item["filename"]
        if not path.exists():
            continue
        if active_only and not media_is_active(item, today):
            continue
        enriched = dict(item)
        enriched["url"] = media_public_url(item["filename"])
        items.append(enriched)
    items.sort(key=media_sort_key)
    return items


def local_slide_links() -> list[str]:
    return [item["url"] for item in local_slide_items(active_only=True)]


def site_logo_path():
    for ext in sorted(IMAGE_EXTS):
        candidate = STATIC_DIR / f"{SITE_LOGO_STEM}{ext}"
        if candidate.exists():
            return candidate
    return None


def site_logo_url() -> str | None:
    path = site_logo_path()
    if not path:
        return None
    return f"/static/{path.name}?v={int(path.stat().st_mtime)}"
