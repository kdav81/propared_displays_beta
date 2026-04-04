from __future__ import annotations

import hashlib
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
            with path.open() as f:
                return json.load(f)
    except Exception:
        pass
    return default() if callable(default) else default


def _save_json(path: Path, data) -> None:
    with _file_lock:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
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
    tags = _load_json(TAGS_FILE, lambda: dict(DEFAULT_TAGS))
    for key in list(tags):
        if isinstance(tags[key], str):
            tags[key] = {"color": tags[key], "fullName": key}
    for key, value in DEFAULT_TAGS.items():
        tags.setdefault(key, value)
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


def load_notice() -> dict:
    return _load_json(
        NOTICE_FILE,
        lambda: {"active": False, "message": "", "startTime": "", "endTime": "", "version": 0},
    )


def save_notice(data: dict) -> None:
    _save_json(NOTICE_FILE, data)


def load_print_shows() -> dict:
    return _load_json(PRINT_SHOWS_FILE, dict)


def save_print_shows(data: dict) -> None:
    _save_json(PRINT_SHOWS_FILE, data)


def load_location_rules() -> list:
    if LOCATION_RULES_FILE.exists():
        try:
            return json.loads(LOCATION_RULES_FILE.read_text())
        except Exception:
            pass
    return list(DEFAULT_LOCATION_RULES)


def save_location_rules(data: list) -> None:
    _save_json(LOCATION_RULES_FILE, data)


def read_password_hash(path: Path) -> str:
    try:
        return path.read_text().strip() if path.exists() else ""
    except Exception:
        return ""


def write_password(path: Path, password: str) -> None:
    path.write_text(hashlib.sha256(password.encode()).hexdigest())


def check_password(password: str, path: Path) -> bool:
    stored = read_password_hash(path)
    return bool(stored) and hashlib.sha256(password.encode()).hexdigest() == stored

