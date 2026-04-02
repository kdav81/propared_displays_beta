from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from classroom_server.core import (
    CLIENTS_FILE,
    DEFAULT_LOCATION_RULES,
    DEFAULT_SETTINGS,
    DEFAULT_TAGS,
    LOCATION_RULES_FILE,
    NOTICE_FILE,
    NOTICE_PASSWORD_FILE,
    PASSWORD_FILE,
    PRINT_SHOWS_FILE,
    ROOMS_FILE,
    SETTINGS_FILE,
    TAGS_FILE,
    log,
)

_file_lock = threading.Lock()


def _load_json(path: Path, default):
    try:
        if path.exists():
            with path.open() as handle:
                return json.load(handle)
    except Exception as exc:
        log.warning("Failed to load %s: %s", path.name, exc)
    return default() if callable(default) else default


def _save_json(path: Path, data) -> None:
    with _file_lock:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as handle:
            json.dump(data, handle, indent=2)
        tmp.replace(path)


def load_rooms() -> dict:
    return _load_json(ROOMS_FILE, dict)


def save_rooms(data: dict) -> None:
    _save_json(ROOMS_FILE, data)


def load_tags() -> dict:
    tag_colors = _load_json(TAGS_FILE, lambda: dict(DEFAULT_TAGS))
    for key in list(tag_colors):
        if isinstance(tag_colors[key], str):
            tag_colors[key] = {"color": tag_colors[key], "fullName": key}
    for key, value in DEFAULT_TAGS.items():
        tag_colors.setdefault(key, value)
    return tag_colors


def save_tags(data: dict) -> None:
    _save_json(TAGS_FILE, data)


def load_settings() -> dict:
    settings = _load_json(SETTINGS_FILE, lambda: dict(DEFAULT_SETTINGS))
    for key, value in DEFAULT_SETTINGS.items():
        settings.setdefault(key, value)
    return settings


def save_settings(data: dict) -> None:
    _save_json(SETTINGS_FILE, data)


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


def load_clients() -> dict:
    return _load_json(CLIENTS_FILE, dict)


def save_clients(data: dict) -> None:
    _save_json(CLIENTS_FILE, data)


def read_pw_file(path: Path) -> str:
    try:
        return path.read_text().strip() if path.exists() else ""
    except Exception:
        return ""


def write_pw_file(path: Path, password: str) -> None:
    path.write_text(hashlib.sha256(password.encode()).hexdigest())


def check_pw(password: str, path: Path) -> bool:
    stored = read_pw_file(path)
    return bool(stored) and hashlib.sha256(password.encode()).hexdigest() == stored


def admin_password_set() -> bool:
    return bool(read_pw_file(PASSWORD_FILE))


def notice_password_set() -> bool:
    return bool(read_pw_file(NOTICE_PASSWORD_FILE))

