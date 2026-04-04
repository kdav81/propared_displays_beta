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
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

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
    active_ids = {gc.get("id", "").strip() for gc in calendars if gc.get("id", "").strip()}
    for gc_id in list(global_cal_cache._data):
        if gc_id not in active_ids:
            global_cal_cache.remove(gc_id)
    for gc in calendars:
        gc_id = gc.get("id", "").strip()
        url = gc.get("url", "").strip()
        if gc_id and url:
            global_cal_cache.schedule(gc_id, url, 60)


def _validated_proxy_ical_url(raw_url: str) -> str | None:
    url = raw_url.strip().replace("webcal://", "https://").replace("webcal:", "https:")
    if not url or len(url) > 2048:
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc or parsed.username or parsed.password:
        return None
    return parsed.geturl()


# ---------------------------------------------------------------------------
# iCal parser  (pure stdlib — zero external dependencies)
# ---------------------------------------------------------------------------
def _parse_dt(line: str) -> datetime | None:
    """
    Parse a DTSTART / DTEND property line (already unfolded) into a datetime.
    Returns None for all-day (VALUE=DATE) values — those events are skipped.

    Handles:
      DTSTART:20240901T090000Z           (UTC)
      DTSTART;TZID=America/New_York:20240901T090000   (local — treated as floating)
      DTSTART;VALUE=DATE:20240901        (all-day — returns None)
    """
    colon = line.index(":")
    params = line[:colon].upper()
    val    = line[colon + 1:].strip()

    # All-day: skip
    if "T" not in val:
        return None
    if "VALUE=DATE" in params and "T" not in val:
        return None

    try:
        yr = int(val[0:4])
        mo = int(val[4:6])
        dy = int(val[6:8])
        hr = int(val[9:11])
        mn = int(val[11:13])
        sc = int(val[13:15]) if len(val) > 13 and val[13:15].isdigit() else 0
        utc = val.endswith("Z")
        return datetime(yr, mo, dy, hr, mn, sc, tzinfo=timezone.utc if utc else None)
    except (ValueError, IndexError):
        return None


def parse_ical_allday(text: str) -> list[dict]:
    """
    Parse iCal text and return ONLY all-day events as date strings.
      {"title": str, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    """
    events: list[dict] = []
    text = text.replace("\r\n ", "").replace("\r\n\t", "")
    text = text.replace("\n ", "").replace("\n\t", "")

    for raw_block in text.split("BEGIN:VEVENT")[1:]:
        end_idx = raw_block.find("END:VEVENT")
        block   = raw_block[:end_idx] if end_idx != -1 else raw_block
        props: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            base_key = line.split(":")[0].split(";")[0].upper()
            props[base_key] = line

        if "SUMMARY" not in props or "DTSTART" not in props:
            continue

        dtstart_line = props["DTSTART"]
        colon = dtstart_line.index(":")
        val   = dtstart_line[colon + 1:].strip()
        # Only process all-day events (no T in value)
        if "T" in val:
            continue

        def _date_str(v: str) -> str:
            return f"{v[0:4]}-{v[4:6]}-{v[6:8]}"

        start_str = _date_str(val)
        end_str   = start_str
        if "DTEND" in props:
            dtend_line = props["DTEND"]
            ec = dtend_line.index(":")
            ev = dtend_line[ec + 1:].strip()
            if "T" not in ev:
                # iCal DTEND for all-day is exclusive, subtract 1 day
                from datetime import date, timedelta
                ed = date(int(ev[0:4]), int(ev[4:6]), int(ev[6:8])) - timedelta(days=1)
                end_str = ed.isoformat()

        raw_title = props["SUMMARY"].split(":", 1)[1].strip()
        title = (raw_title
                 .replace("\\,", ",")
                 .replace("\\n", " ")
                 .replace("\\;", ";")
                 .replace("\\:", ":"))
        events.append({"title": title, "start": start_str, "end": end_str})
    return events


def parse_ical(text: str) -> list[dict]:
    """
    Parse iCal text into a list of event dicts:
      {"title": str, "start": datetime, "end": datetime}
    All-day events are skipped.
    """
    events: list[dict] = []

    # Unfold RFC 5545 continuation lines
    text = text.replace("\r\n ", "").replace("\r\n\t", "")
    text = text.replace("\n ", "").replace("\n\t", "")

    for raw_block in text.split("BEGIN:VEVENT")[1:]:
        end_idx = raw_block.find("END:VEVENT")
        block   = raw_block[:end_idx] if end_idx != -1 else raw_block

        # Build a property map: base-key -> full line (for _parse_dt)
        props: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            base_key = line.split(":")[0].split(";")[0].upper()
            props[base_key] = line

        if "SUMMARY" not in props or "DTSTART" not in props:
            continue

        start = _parse_dt(props["DTSTART"])
        if start is None:
            continue  # skip all-day events

        end = _parse_dt(props["DTEND"]) if "DTEND" in props else None
        if end is None:
            end = start

        raw_title = props["SUMMARY"].split(":", 1)[1].strip()
        title = (raw_title
                 .replace("\\,", ",")
                 .replace("\\n", " ")
                 .replace("\\;", ";")
                 .replace("\\:", ":"))

        events.append({"title": title, "start": start, "end": end})

    return events


# ---------------------------------------------------------------------------
# iCal background cache  (one refresh timer per room)
# ---------------------------------------------------------------------------
class _ICalCache:
    """
    Keeps a parsed event list for every room, refreshed in the background.

    Reads are lock-free via Python's GIL on simple dict/list access.
    Writes hold a lock only during the brief dict update.
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._data:   dict[str, dict]          = {}  # rid -> cache entry
        self._timers: dict[str, threading.Timer] = {}

    # ── Public ──────────────────────────────────────────────────

    def get_events(self, rid: str) -> list[dict]:
        with self._lock:
            return list(self._data.get(rid, {}).get("events", []))

    def get_allday(self, rid: str) -> list[dict]:
        with self._lock:
            return list(self._data.get(rid, {}).get("allday", []))

    def get_meta(self, rid: str) -> dict:
        with self._lock:
            d = self._data.get(rid, {})
            return {"fetched_at": d.get("fetched_at"), "error": d.get("error")}

    def schedule(self, rid: str, ical_url: str, interval_min: int) -> None:
        """Start (or restart) background refresh for a room."""
        self._cancel(rid)
        if ical_url:
            self._fetch_then_reschedule(rid, ical_url, interval_min)

    def remove(self, rid: str) -> None:
        self._cancel(rid)
        with self._lock:
            self._data.pop(rid, None)

    # ── Internal ────────────────────────────────────────────────

    def _cancel(self, rid: str) -> None:
        t = self._timers.pop(rid, None)
        if t:
            t.cancel()

    def _fetch_then_reschedule(self, rid: str, ical_url: str, interval_min: int) -> None:
        self._fetch(rid, ical_url)
        t = threading.Timer(
            interval_min * 60,
            self._fetch_then_reschedule,
            args=(rid, ical_url, interval_min),
        )
        t.daemon = True
        t.start()
        self._timers[rid] = t

    def _fetch(self, rid: str, ical_url: str) -> None:
        log.info("Fetching iCal for room %s", rid)
        # webcal:// is identical to https:// — Python's urllib doesn't handle it
        ical_url = ical_url.replace("webcal://", "https://").replace("webcal:", "https:")
        try:
            req = urllib.request.Request(
                ical_url,
                headers={"User-Agent": "ProparedDisplay/4.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                text = r.read().decode("utf-8", errors="replace")
            events     = parse_ical(text)
            allday_evs = parse_ical_allday(text)
            with self._lock:
                self._data[rid] = {
                    "events":     events,
                    "allday":     allday_evs,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "error":      None,
                }
            log.info("Room %s: %d events, %d all-day cached", rid, len(events), len(allday_evs))
        except Exception as exc:
            log.warning("Room %s iCal fetch failed: %s", rid, exc)
            with self._lock:
                prev = self._data.get(rid, {"events": [], "fetched_at": None})
                prev["error"] = str(exc)
                self._data[rid] = prev


ical_cache = _ICalCache()
global_cal_cache = _ICalCache()  # separate cache for global calendars, 60 min refresh


def _boot_clients() -> None:
    """Load persisted client registry into memory."""
    global _clients
    _clients = load_clients()


def _boot_ical_cache() -> None:
    """Schedule background refresh for every room and global calendar."""
    for rid, room in load_rooms().items():
        url = room.get("icalUrl", "").strip()
        if url:
            ical_cache.schedule(rid, url, _to_int(room.get("refresh"), 5, minimum=1, maximum=1440))
    _sync_global_calendar_cache(load_settings().get("globalCalendars", []))


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
    validated_proxy_ical_url=_validated_proxy_ical_url,
)


def get_slides(force: bool = False) -> list[str]:
    """Return active local slideshow image URLs."""
    return _local_slide_links()


# ---------------------------------------------------------------------------
# Room status helpers
# ---------------------------------------------------------------------------
def _fmt_time(dt: datetime) -> str:
    """Format datetime as '9:30 AM' or '2 PM', always in local server time."""
    # Convert UTC-aware datetimes to local time before formatting
    if dt.tzinfo is not None:
        dt = dt.astimezone()   # converts to local timezone (server's tz = EDT)
    h, m = dt.hour, dt.minute
    ap   = "AM" if h < 12 else "PM"
    h    = h % 12 or 12
    return f"{h}:{m:02d} {ap}" if m else f"{h} {ap}"


def _naive(dt: datetime) -> datetime:
    """Convert to local time and strip timezone for comparison against datetime.now()."""
    if dt.tzinfo is not None:
        dt = dt.astimezone()   # convert UTC -> local
    return dt.replace(tzinfo=None)


def _room_status(rid: str) -> dict:
    """
    Compute the current occupied/available status for one room.
    Pure in-memory — reads from ical_cache with no I/O.
    """
    now    = datetime.now()
    events = ical_cache.get_events(rid)

    today = sorted(
        [e for e in events if _naive(e["start"]).date() == now.date()],
        key=lambda e: e["start"],
    )

    current = next(
        (e for e in today if _naive(e["start"]) <= now < _naive(e["end"])),
        None,
    )
    future = [e for e in today if _naive(e["start"]) > now]
    nxt    = future[0] if future else None

    def _ev(e) -> dict | None:
        if not e:
            return None
        return {
            "title": e["title"],
            "start": _fmt_time(e["start"]),
            "end":   _fmt_time(e["end"]),
        }

    return {
        "rid":      rid,
        "occupied": current is not None,
        "current":  _ev(current),
        "next":     _ev(nxt),
    }


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
    r = dict(rooms[rid])
    r.update(
        roomId       = rid,
        tagColors    = load_tags(),
        hasLogo      = logo_path(rid).exists(),
        hasSlideshow = bool(_local_slide_links()),
        calDuration  = settings.get("calDuration",  60),
        slideDuration = settings.get("slideDuration", 8),
    )
    r.setdefault("startHour", 8)
    r.setdefault("endHour",   22)
    return r


# ===========================================================================
# Routes
# ===========================================================================

# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    log.info("Starting Propared Calendar Displays Server v4")
    _boot_clients()         # load persisted client registry
    _boot_ical_cache()      # kick off background iCal refresh threads

    port = int(os.environ.get("PORT", 80))

    try:
        from waitress import serve
        log.info("Starting with waitress on port %d", port)
        serve(app, host="0.0.0.0", port=port, threads=4)
    except ImportError:
        log.warning("waitress not installed — falling back to Flask dev server")
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
