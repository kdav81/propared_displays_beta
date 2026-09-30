from __future__ import annotations

import hashlib
import hmac
import json
import threading
from pathlib import Path

from .config import (
    CLIENTS_FILE,
    DEFAULT_LOCATION_RULES,
    DEFAULT_SETTINGS,
    DEFAULT_TAGS,
    LOCATION_RULES_FILE,
    MEDIA_LIBRARY_FILE,
    NOTICE_FILE,
    PASSWORD_FILE,
    PRINT_SHOWS_FILE,
    ROOMS_FILE,
    SETTINGS_FILE,
    TAGS_FILE,
)

_file_lock = threading.Lock()


def _load_json(path: Path, default):
    try:
        if path.exists():
            with path.open(encoding="utf-8") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return default() if callable(default) else default


def _save_json(path: Path, data) -> None:
    with _file_lock:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)


def load_rooms() -> dict:
    return _load_json(ROOMS_FILE, dict)


def save_rooms(data: dict) -> None:
    _save_json(ROOMS_FILE, data)


def load_clients() -> dict:
    return _load_json(CLIENTS_FILE, dict)


def save_clients(data: dict) -> None:
    _save_json(CLIENTS_FILE, data)


def load_tags() -> dict:
    tags = _load_json(TAGS_FILE, dict) if TAGS_FILE.exists() else dict(DEFAULT_TAGS)
    for key in list(tags):
        if isinstance(tags[key], str):
            tags[key] = {"color": tags[key], "fullName": key}
    return tags


def save_tags(data: dict) -> None:
    _save_json(TAGS_FILE, data)


def load_settings() -> dict:
    settings = _load_json(SETTINGS_FILE, lambda: dict(DEFAULT_SETTINGS))
    for key, value in DEFAULT_SETTINGS.items():
        settings.setdefault(key, value)
    return settings


def save_settings(data: dict) -> None:
    _save_json(SETTINGS_FILE, data)


def load_media_library() -> list:
    media = _load_json(MEDIA_LIBRARY_FILE, list)
    if not isinstance(media, list):
        return []
    clean = []
    for item in media:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename", "")).strip()
        if not filename:
            continue
        clean.append(
            {
                "id": str(item.get("id", "")).strip() or filename,
                "filename": filename,
                "title": str(item.get("title", "")).strip(),
                "originalName": str(item.get("originalName", "")).strip() or filename,
                "startDate": str(item.get("startDate", "")).strip(),
                "endDate": str(item.get("endDate", "")).strip(),
                "active": bool(item.get("active", True)),
                "uploadedAt": str(item.get("uploadedAt", "")).strip(),
            }
        )
    return clean


def save_media_library(items: list) -> None:
    _save_json(MEDIA_LIBRARY_FILE, items)


def empty_notice() -> dict:
    return {
        "id": "",
        "active": False,
        "message": "",
        "startTime": "",
        "endTime": "",
        "version": 0,
        "createdAt": "",
        "updatedAt": "",
    }


def _notice_id(scope: str, notice: dict) -> str:
    raw = "|".join(
        [
            scope,
            str(notice.get("message", "")),
            str(notice.get("startTime", "")),
            str(notice.get("endTime", "")),
            str(notice.get("version", "")),
            str(notice.get("createdAt", "")),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_notice_item(notice: dict, scope: str) -> dict | None:
    if not isinstance(notice, dict):
        return None
    clean = {**empty_notice(), **notice}
    clean["message"] = str(clean.get("message", "")).strip()
    clean["startTime"] = str(clean.get("startTime", "")).strip()
    clean["endTime"] = str(clean.get("endTime", "")).strip()
    clean["id"] = str(clean.get("id", "")).strip() or _notice_id(scope, clean)
    clean["active"] = bool(clean.get("active", False))
    try:
        clean["version"] = int(clean.get("version", 0))
    except (TypeError, ValueError):
        clean["version"] = 0
    clean["createdAt"] = str(clean.get("createdAt", "")).strip()
    clean["updatedAt"] = str(clean.get("updatedAt", "")).strip()
    if not clean["message"] and not clean["startTime"] and not clean["endTime"] and not clean["active"]:
        return None
    return clean


def _normalize_notice_collection(value, scope: str) -> list[dict]:
    if isinstance(value, list):
        notices = value
    elif isinstance(value, dict):
        notices = [value] if any(key in value for key in empty_notice()) else []
    else:
        notices = []
    clean = []
    seen = set()
    for notice in notices:
        item = _normalize_notice_item(notice, scope)
        if not item or item["id"] in seen:
            continue
        seen.add(item["id"])
        clean.append(item)
    return clean


def load_notice() -> dict:
    data = _load_json(NOTICE_FILE, lambda: {"global": [], "rooms": {}})
    if not isinstance(data, dict):
        return {"global": [], "rooms": {}}

    # Older installs stored the global notice directly at the top level.
    if "global" not in data and any(key in data for key in empty_notice()):
        return {"global": _normalize_notice_collection(data, "global"), "rooms": {}}

    global_notices = data.get("global", [])
    room_notices = data.get("rooms", {})
    clean_rooms = {}
    if isinstance(room_notices, dict):
        for room_id, notices in room_notices.items():
            clean = _normalize_notice_collection(notices, str(room_id))
            if clean:
                clean_rooms[str(room_id)] = clean
    return {
        "global": _normalize_notice_collection(global_notices, "global"),
        "rooms": clean_rooms,
    }


def save_notice(data: dict) -> None:
    _save_json(NOTICE_FILE, data)


def load_print_shows() -> dict:
    return _load_json(PRINT_SHOWS_FILE, dict)


def save_print_shows(data: dict) -> None:
    _save_json(PRINT_SHOWS_FILE, data)


def load_location_rules() -> list:
    return _load_json(LOCATION_RULES_FILE, lambda: list(DEFAULT_LOCATION_RULES))


def save_location_rules(data: list) -> None:
    _save_json(LOCATION_RULES_FILE, data)


def read_password_hash(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""
    except OSError:
        return ""


def write_password(path: Path, password: str) -> None:
    path.write_text(hashlib.sha256(password.encode()).hexdigest(), encoding="utf-8")


def check_password(password: str, path: Path) -> bool:
    stored = read_password_hash(path)
    candidate = hashlib.sha256(password.encode()).hexdigest()
    return bool(stored) and hmac.compare_digest(candidate, stored)
