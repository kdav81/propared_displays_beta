from __future__ import annotations

import logging
import secrets
from pathlib import Path

from flask import Flask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("classroom")

BASE = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE / "cache"
STATIC_DIR = BASE / "static"
BACKUP_DIR = BASE / "backups"

for _directory in (CACHE_DIR, STATIC_DIR, BACKUP_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

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
    "dropboxToken": "",
    "dropboxAppKey": "",
    "dropboxAppSecret": "",
    "dropboxRefreshToken": "",
    "dropboxFolder": "/slideshow",
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


def _load_secret_key() -> str:
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(key)
    return key


app = Flask(__name__)
app.secret_key = _load_secret_key()


def logo_path(rid: str) -> Path:
    return STATIC_DIR / f"logo_{rid}.png"


def slides_cache_path() -> Path:
    return CACHE_DIR / "slides.json"


def to_int(value, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result

