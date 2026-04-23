#!/usr/bin/env python3
"""
Propared Calendar Displays — Main Server
========================================
Single-file Flask/Waitress server. Handles room displays, admin panel,
print calendar PDF generation, iCal feed caching, and client check-ins.

Design goals:
  - Pi Zero W2 friendly: all iCal parsing happens server-side.
    Clients receive pre-parsed JSON; they never touch raw iCal.
  - Background threads refresh each room's calendar on its own schedule.
  - /api/dashboard-data is a pure in-memory read (< 1 ms).
  - Slideshow images are uploaded and served locally by this server.
  - Persistent secret key so admin sessions survive server restarts.

Directory layout (relative to this file):
  server.py
  rooms.json            persistent room config
  tag_colors.json       tag -> {color, fullName}
  settings.json         global settings (timing, dashboard)
  admin_password.txt    sha256 hex of admin password
  notice.json           active notice banner
  notice_password.txt   sha256 hex of notice password
  secret_key.txt        persistent Flask secret key (auto-created)
  media_library.json    slideshow image metadata
  static/
    logo_<rid>.png      room logos
    slides/             uploaded slideshow images
  backups/              zip backups (auto-created)
  templates/            Jinja2 HTML files
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from print_calendar_pdf import build_calendar_pdf as _build_calendar_pdf
    from print_calendar_pdf import build_weekly_pdf as _build_weekly_pdf
    from print_calendar_pdf import build_room_calendar_pdf as _build_room_calendar_pdf
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

from flask import Flask, Response

from app.config import (
    BACKUP_DIR,
    STATIC_DIR,
    ensure_runtime_dirs,
    load_secret_key,
)
from app.services.display_state import public_room_config, room_status
from app.services.ical import ICalCache, validated_proxy_ical_url
from app.services.media_library import (
    local_slide_links as _local_slide_links,
)
from app.routes.admin_misc import register_admin_misc_routes
from app.routes.display import register_display_routes
from app.routes.media import register_media_routes
from app.routes.notice import register_notice_routes
from app.routes.printing import register_printing_routes
from app.storage import (
    load_clients,
    load_rooms,
    load_settings,
    load_tags,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("propared")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ensure_runtime_dirs()

# ---------------------------------------------------------------------------
# Flask app  (persistent secret key so sessions survive restarts)
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = load_secret_key()
# Trust a single reverse proxy for scheme/host so generated URLs stay HTTPS-safe.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)



# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def logo_path(rid: str) -> Path:
    return STATIC_DIR / f"logo_{rid}.png"


def _to_int(value, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _sync_global_calendar_cache(calendars: list[dict]) -> None:
    global_cal_cache.sync_global_calendars(calendars)


ical_cache = ICalCache(log=log)
global_cal_cache = ICalCache(log=log)


def _boot_clients() -> None:
    """Load persisted client registry into memory."""
    _clients.clear()
    _clients.update(load_clients())


def _boot_ical_cache() -> None:
    """Schedule background refresh for every room and global calendar."""
    ical_cache.boot_room_calendars(load_rooms(), to_int=_to_int)
    _sync_global_calendar_cache(load_settings().get("globalCalendars", []))


def get_slides(force: bool = False) -> list[str]:
    """Return active local slideshow image URLs."""
    return _local_slide_links()


def _room_status(rid: str) -> dict:
    return room_status(ical_cache, rid)


# ---------------------------------------------------------------------------
# Client heartbeat  (in-memory — intentionally not persisted)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Client registry  (keyed by client_id UUID — persistent)
# ---------------------------------------------------------------------------
_clients: dict[str, dict] = {}   # client_id -> {hostname, ip, role, room, last_seen, screenOn, screenOff, scheduleEnabled}

# ---------------------------------------------------------------------------
# Public room config  (rendered into display.html via Jinja2)
# ---------------------------------------------------------------------------
def _public_room_config(rid: str, rooms: dict, settings: dict) -> dict:
    return public_room_config(
        rid,
        rooms,
        settings,
        load_tags=load_tags,
        logo_path=logo_path,
        slide_links=_local_slide_links,
    )


# ===========================================================================
# Routes
# ===========================================================================
register_media_routes(app)
register_notice_routes(app)
register_admin_misc_routes(
    app,
    ical_cache=ical_cache,
    sync_global_calendar_cache=_sync_global_calendar_cache,
    to_int=_to_int,
    log=log,
)
register_printing_routes(
    app,
    pdf_available=_PDF_AVAILABLE,
    build_calendar_pdf=_build_calendar_pdf,
    build_weekly_pdf=_build_weekly_pdf,
    build_room_calendar_pdf=_build_room_calendar_pdf,
    to_int=_to_int,
    log=log,
)
register_display_routes(
    app,
    clients=_clients,
    ical_cache=ical_cache,
    global_cal_cache=global_cal_cache,
    get_slides=get_slides,
    logo_path=logo_path,
    public_room_config=_public_room_config,
    room_status=_room_status,
    sync_global_calendar_cache=_sync_global_calendar_cache,
    to_int=_to_int,
    validated_proxy_ical_url=validated_proxy_ical_url,
)

# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    log.info("Starting Propared Calendar Displays Server v4")
    _boot_clients()         # load persisted client registry
    _boot_ical_cache()      # kick off background iCal refresh threads

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 80))

    try:
        from waitress import serve
        log.info("Starting with waitress on %s:%d", host, port)
        serve(app, host=host, port=port, threads=4)
    except ImportError:
        log.warning("waitress not installed — falling back to Flask dev server")
        app.run(host=host, port=port, debug=False, threaded=True)
