from __future__ import annotations

import secrets
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE / "cache"
STATIC_DIR = BASE / "static"
BACKUP_DIR = BASE / "backups"
MEDIA_DIR = STATIC_DIR / "slides"

ROOMS_FILE = BASE / "rooms.json"
CLIENTS_FILE = BASE / "clients.json"
TAGS_FILE = BASE / "tag_colors.json"
SETTINGS_FILE = BASE / "settings.json"
PASSWORD_FILE = BASE / "admin_password.txt"
NOTICE_FILE = BASE / "notice.json"
NOTICE_PASSWORD_FILE = BASE / "notice_password.txt"
SECRET_KEY_FILE = BASE / "secret_key.txt"
PRINT_SHOWS_FILE = BASE / "print_shows.json"
LOCATION_RULES_FILE = BASE / "location_rules.json"
MEDIA_LIBRARY_FILE = BASE / "media_library.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

DEFAULT_TAGS: dict = {
    "Class": {"color": "#2563c7", "fullName": "Class"},
    "SPDance": {"color": "#16213e", "fullName": "Spring Dance Concert"},
    "Rehearsal": {"color": "#7b2d8b", "fullName": "Rehearsal"},
    "ND": {"color": "#c0392b", "fullName": "Notre Dame"},
    "Hold": {"color": "#555555", "fullName": "Hold"},
    "default": {"color": "#2563c7", "fullName": ""},
}

DEFAULT_SETTINGS: dict = {
    "slideDuration": 8,
    "calDuration": 60,
    "dashboardIframeUrl": "",
    "dashboardRooms": [],
    "dashboardCalDuration": 60,
    "dashboardSlideDuration": 8,
    "globalCalendars": [],
}

DEFAULT_LOCATION_RULES = [
    {
        "keywords": "thompson theatre, dressing rooms, green room",
        "replacement": "Thompson Theatre",
    },
]


def ensure_runtime_dirs() -> None:
    for directory in (CACHE_DIR, STATIC_DIR, BACKUP_DIR, MEDIA_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_secret_key() -> str:
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(key)
    return key

