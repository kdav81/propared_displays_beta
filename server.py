#!/usr/bin/env python3
"""
Propared Calendar Displays Server
========================
Single-file Flask server for Pi-based room display kiosks.

Design goals:
  - Pi Zero W2 friendly: all iCal parsing happens server-side.
    Clients receive pre-parsed JSON; they never touch raw iCal.
  - Background threads refresh each room's calendar on its own schedule.
  - /api/dashboard-data is a pure in-memory read (< 1 ms).
  - Dropbox photos are cached for 30 min; links refreshed as needed.
  - Persistent secret key so admin sessions survive server restarts.

Directory layout (relative to this file):
  server.py
  rooms.json            persistent room config
  tag_colors.json       tag -> {color, fullName}
  settings.json         global settings (Dropbox, timing, dashboard)
  admin_password.txt    sha256 hex of admin password
  notice.json           active notice banner
  notice_password.txt   sha256 hex of notice password
  secret_key.txt        persistent Flask secret key (auto-created)
  static/
    logo_<rid>.png      room logos
  cache/
    slides.json         cached Dropbox photo links
  backups/              zip backups (auto-created)
  templates/            Jinja2 HTML files
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from print_calendar_pdf import build_calendar_pdf as _build_calendar_pdf
    from print_calendar_pdf import build_weekly_pdf as _build_weekly_pdf
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

from flask import (
    Flask, Response, jsonify, make_response, redirect,
    render_template, request, send_file,
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
BASE       = Path(__file__).parent
CACHE_DIR  = BASE / "cache"
STATIC_DIR = BASE / "static"
BACKUP_DIR = BASE / "backups"

for _d in (CACHE_DIR, STATIC_DIR, BACKUP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

ROOMS_FILE           = BASE / "rooms.json"
CLIENTS_FILE         = BASE / "clients.json"   # persistent client registry
TAGS_FILE            = BASE / "tag_colors.json"
SETTINGS_FILE        = BASE / "settings.json"
PASSWORD_FILE        = BASE / "admin_password.txt"
NOTICE_FILE          = BASE / "notice.json"
NOTICE_PASSWORD_FILE = BASE / "notice_password.txt"
SECRET_KEY_FILE      = BASE / "secret_key.txt"
PRINT_SHOWS_FILE     = BASE / "print_shows.json"
LOCATION_RULES_FILE  = BASE / "location_rules.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# ---------------------------------------------------------------------------
# Flask app  (persistent secret key so sessions survive restarts)
# ---------------------------------------------------------------------------
def _load_secret_key() -> str:
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(key)
    return key

app = Flask(__name__)
app.secret_key = _load_secret_key()

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TAGS: dict = {
    "Class":     {"color": "#2563c7", "fullName": "Class"},
    "SPDance":   {"color": "#16213e", "fullName": "Spring Dance Concert"},
    "Rehearsal": {"color": "#7b2d8b", "fullName": "Rehearsal"},
    "ND":        {"color": "#c0392b", "fullName": "Notre Dame"},
    "Hold":      {"color": "#555555", "fullName": "Hold"},
    "default":   {"color": "#2563c7", "fullName": ""},
}

DEFAULT_SETTINGS: dict = {
    "dropboxToken":           "",
    "dropboxAppKey":          "",
    "dropboxAppSecret":       "",
    "dropboxRefreshToken":    "",
    "dropboxFolder":          "/slideshow",
    "slideDuration":          8,
    "calDuration":            60,
    "dashboardIframeUrl":     "",
    "dashboardRooms":         [],
    "dashboardCalDuration":   60,
    "dashboardSlideDuration": 8,
    "globalCalendars":        [],
}

# ---------------------------------------------------------------------------
# JSON persistence helpers
# ---------------------------------------------------------------------------
_file_lock = threading.Lock()


def _load_json(path: Path, default):
    try:
        if path.exists():
            with path.open() as f:
                return json.load(f)
    except Exception as exc:
        log.warning("Failed to load %s: %s", path.name, exc)
    return default() if callable(default) else default


def _save_json(path: Path, data) -> None:
    with _file_lock:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)


def load_rooms() -> dict:
    return _load_json(ROOMS_FILE, dict)


def save_rooms(r: dict) -> None:
    _save_json(ROOMS_FILE, r)


def load_tags() -> dict:
    tc = _load_json(TAGS_FILE, lambda: dict(DEFAULT_TAGS))
    # Migrate bare colour strings from old format
    for k in list(tc):
        if isinstance(tc[k], str):
            tc[k] = {"color": tc[k], "fullName": k}
    for k, v in DEFAULT_TAGS.items():
        tc.setdefault(k, v)
    return tc


def save_tags(tc: dict) -> None:
    _save_json(TAGS_FILE, tc)


def load_settings() -> dict:
    s = _load_json(SETTINGS_FILE, lambda: dict(DEFAULT_SETTINGS))
    for k, v in DEFAULT_SETTINGS.items():
        s.setdefault(k, v)
    return s


def save_settings(s: dict) -> None:
    _save_json(SETTINGS_FILE, s)


def load_notice() -> dict:
    return _load_json(NOTICE_FILE, lambda: {
        "active": False, "message": "", "startTime": "", "endTime": "", "version": 0,
    })


def save_notice(n: dict) -> None:
    _save_json(NOTICE_FILE, n)


def load_print_shows() -> dict:
    return _load_json(PRINT_SHOWS_FILE, dict)


def save_print_shows(shows: dict) -> None:
    _save_json(PRINT_SHOWS_FILE, shows)


DEFAULT_LOCATION_RULES = [
    {
        "keywords":    "thompson theatre, dressing rooms, green room",
        "replacement": "Thompson Theatre",
    },
]


def load_location_rules() -> list:
    if LOCATION_RULES_FILE.exists():
        try:
            return json.loads(LOCATION_RULES_FILE.read_text())
        except Exception:
            pass
    return list(DEFAULT_LOCATION_RULES)


def save_location_rules(rules: list) -> None:
    _save_json(LOCATION_RULES_FILE, rules)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _read_pw_file(path: Path) -> str:
    try:
        return path.read_text().strip() if path.exists() else ""
    except Exception:
        return ""


def _write_pw_file(path: Path, pw: str) -> None:
    path.write_text(hashlib.sha256(pw.encode()).hexdigest())


def _check_pw(pw: str, path: Path) -> bool:
    stored = _read_pw_file(path)
    return bool(stored) and hashlib.sha256(pw.encode()).hexdigest() == stored


def require_admin(f):
    import functools

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _read_pw_file(PASSWORD_FILE):
            return redirect("/admin/setup")
        auth = request.authorization
        if not auth or not _check_pw(auth.password, PASSWORD_FILE):
            return Response(
                "Admin access required.", 401,
                {"WWW-Authenticate": 'Basic realm="Propared Calendar Displays Admin"'},
            )
        return f(*args, **kwargs)

    return decorated


def require_notice_auth(f):
    import functools

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not _check_pw(auth.password, NOTICE_PASSWORD_FILE):
            return Response(
                "Notice access required.", 401,
                {"WWW-Authenticate": 'Basic realm="Notice Board"'},
            )
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def logo_path(rid: str) -> Path:
    return STATIC_DIR / f"logo_{rid}.png"


def slides_cache_path() -> Path:
    return CACHE_DIR / "slides.json"


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


def _restore_logo_files(archive_names: list[str], zf: zipfile.ZipFile) -> None:
    archived_logos = {
        Path(name).name for name in archive_names
        if name.startswith("static/logo_") and name.endswith(".png")
    }
    for fp in STATIC_DIR.glob("logo_*.png"):
        if fp.name not in archived_logos:
            fp.unlink()
    for logo_name in archived_logos:
        (STATIC_DIR / logo_name).write_bytes(zf.read(f"static/{logo_name}"))


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


# ---------------------------------------------------------------------------
# Dropbox helpers
# ---------------------------------------------------------------------------
def _get_dropbox_token(s: dict) -> str:
    """Return a valid Dropbox access token, using the refresh token when available."""
    rt  = s.get("dropboxRefreshToken", "").strip()
    ak  = s.get("dropboxAppKey",       "").strip()
    ase = s.get("dropboxAppSecret",    "").strip()
    if rt and ak and ase:
        try:
            data = urllib.parse.urlencode({
                "grant_type":    "refresh_token",
                "refresh_token": rt,
                "client_id":     ak,
                "client_secret": ase,
            }).encode()
            req = urllib.request.Request(
                "https://api.dropbox.com/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())["access_token"]
        except Exception as exc:
            log.warning("Dropbox token refresh failed: %s", exc)
    return s.get("dropboxToken", "").strip()


def _fetch_dropbox_images(token: str, folder: str) -> list[str]:
    """Return temporary download links for up to 60 images in the Dropbox folder."""
    path = "" if folder.strip() in ("", "/") else folder.strip()
    try:
        req = urllib.request.Request(
            "https://api.dropboxapi.com/2/files/list_folder",
            data=json.dumps({"path": path, "limit": 300}).encode(),
            headers={
                "Authorization":  f"Bearer {token}",
                "Content-Type":   "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            entries = json.loads(r.read()).get("entries", [])

        image_paths = [
            e["path_lower"] for e in entries
            if e.get(".tag") == "file"
            and Path(e["name"]).suffix.lower() in IMAGE_EXTS
        ]
        log.info("Dropbox '%s': %d entries, %d images", path, len(entries), len(image_paths))

        links: list[str] = []
        for p in image_paths[:60]:
            try:
                req2 = urllib.request.Request(
                    "https://api.dropboxapi.com/2/files/get_temporary_link",
                    data=json.dumps({"path": p}).encode(),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type":  "application/json",
                    },
                )
                with urllib.request.urlopen(req2, timeout=10) as r2:
                    links.append(json.loads(r2.read())["link"])
            except Exception as exc:
                log.warning("Dropbox temp link failed for %s: %s", p, exc)
        return links
    except Exception as exc:
        log.warning("Dropbox list_folder failed: %s", exc)
        return []


def get_slides(force: bool = False) -> list[str]:
    """Return cached Dropbox photo links, refreshing if stale (> 30 min) or forced."""
    cache = slides_cache_path()
    if not force and cache.exists():
        try:
            data = json.loads(cache.read_text())
            if time.time() - data.get("fetchedAt", 0) < 1800 and data.get("links"):
                return data["links"]
        except Exception:
            pass
    s     = load_settings()
    token = _get_dropbox_token(s)
    if not token:
        log.warning("get_slides: no Dropbox token available")
        return []
    links = _fetch_dropbox_images(token, s.get("dropboxFolder", ""))
    if links:
        cache.write_text(json.dumps({"links": links, "fetchedAt": time.time()}))
    else:
        log.warning("get_slides: no images returned from Dropbox")
    return links


def _exchange_dropbox_code(code: str, app_key: str, app_secret: str, redirect_uri: str) -> dict:
    try:
        data = urllib.parse.urlencode({
            "code":          code,
            "grant_type":    "authorization_code",
            "client_id":     app_key,
            "client_secret": app_secret,
            "redirect_uri":  redirect_uri,
        }).encode()
        req = urllib.request.Request(
            "https://api.dropbox.com/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as exc:
        return {"error": str(exc)}


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
def load_clients() -> dict:
    return _load_json(CLIENTS_FILE, dict)

def save_clients(data: dict) -> None:
    _save_json(CLIENTS_FILE, data)

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
        hasSlideshow = bool(settings.get("dropboxToken") or settings.get("dropboxRefreshToken")),
        calDuration  = settings.get("calDuration",  60),
        slideDuration = settings.get("slideDuration", 8),
    )
    r.setdefault("startHour", 8)
    r.setdefault("endHour",   22)
    return r


# ===========================================================================
# Routes
# ===========================================================================

# ── Health ──────────────────────────────────────────────────────────────────

@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "rooms": len(load_rooms()), "time": time.time()})


# ── Room list ────────────────────────────────────────────────────────────────

@app.route("/api/rooms")
def api_rooms():
    rooms = load_rooms()
    return jsonify([
        {"id": rid, "title": r.get("title", rid)}
        for rid, r in sorted(rooms.items(), key=lambda x: x[1].get("title", ""))
    ])


# ── Room config ──────────────────────────────────────────────────────────────

@app.route("/api/config/<rid>")
def api_config(rid):
    rooms = load_rooms()
    if rid not in rooms:
        return jsonify({"error": "Room not found"}), 404
    return jsonify(_public_room_config(rid, rooms, load_settings()))


# ── Events — pre-parsed JSON ─────────────────────────────────────────────────

@app.route("/api/events/<rid>")
def api_events(rid):
    """
    Pre-parsed event list for one room.  Clients never touch raw iCal.

    Response:
    {
      "events": [
        {"title": "Class [Class]", "start": "2025-01-15T09:00:00", "end": "2025-01-15T10:30:00"}
      ],
      "fetched_at": "2025-01-15T13:00:00+00:00",
      "error": null
    }

    Dates are ISO-8601. UTC datetimes include +00:00; floating (TZID) datetimes are naive.
    """
    rooms = load_rooms()
    if rid not in rooms:
        return jsonify({"error": "Room not found"}), 404

    events = ical_cache.get_events(rid)
    meta   = ical_cache.get_meta(rid)

    def _dt_str(dt):
        return dt.isoformat() if dt else None

    # Room events
    all_events = [
        {"title": e["title"], "start": _dt_str(e["start"]), "end": _dt_str(e["end"])}
        for e in events
    ]
    # Merge global calendar events — tagged with globalColor and globalOnly
    # so the client can colour them correctly and exclude from sidebar
    for gc in load_settings().get("globalCalendars", []):
        gc_id    = gc.get("id", "")
        gc_color = gc.get("color", "#555555")
        if not gc_id:
            continue
        for e in global_cal_cache.get_events(gc_id):
            all_events.append({
                "title":       e["title"],
                "start":       _dt_str(e["start"]),
                "end":         _dt_str(e["end"]),
                "globalColor": gc_color,
                "globalOnly":  True,
            })

    # Collect all-day events from global calendars
    all_day_events = []
    for gc in load_settings().get("globalCalendars", []):
        gc_id    = gc.get("id", "")
        gc_color = gc.get("color", "#555555")
        if not gc_id:
            continue
        for e in global_cal_cache.get_allday(gc_id):
            all_day_events.append({
                "title": e["title"],
                "start": e["start"],   # "YYYY-MM-DD"
                "end":   e["end"],     # "YYYY-MM-DD"
                "color": gc_color,
            })

    payload = {
        "events":       all_events,
        "allDayEvents": all_day_events,
        "fetched_at":   meta["fetched_at"],
        "error":        meta["error"],
    }
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── Dashboard data — pre-computed room status ─────────────────────────────────

@app.route("/api/dashboard-data")
def api_dashboard_data():
    """
    Occupied / available status for all dashboard rooms.
    Pure in-memory read — sub-millisecond on any Pi.

    Response:
    {
      "rooms": [
        {
          "rid":      "abc12345",
          "occupied": true,
          "current":  {"title": "Spring Rehearsal", "start": "2 PM", "end": "5 PM"},
          "next":     {"title": "Class [Class]",     "start": "6 PM", "end": "7:30 PM"}
        }
      ]
    }
    """
    s     = load_settings()
    rooms = load_rooms()
    rids  = [rid for rid in s.get("dashboardRooms", []) if rid in rooms]
    return jsonify({"rooms": [_room_status(rid) for rid in rids]})


# ── Slides ───────────────────────────────────────────────────────────────────

@app.route("/api/slides")
def api_slides():
    force = request.args.get("refresh") == "1"
    return jsonify({"links": get_slides(force=force)})


@app.route("/api/slides/debug")
def api_slides_debug():
    s      = load_settings()
    token  = _get_dropbox_token(s)
    folder = s.get("dropboxFolder", "").strip()
    path   = "" if folder in ("", "/") else folder
    result = {
        "hasToken":        bool(token),
        "folder":          folder,
        "folderPath":      path,
        "hasAppKey":       bool(s.get("dropboxAppKey")),
        "hasRefreshToken": bool(s.get("dropboxRefreshToken")),
    }
    if token:
        try:
            req = urllib.request.Request(
                "https://api.dropboxapi.com/2/files/list_folder",
                data=json.dumps({"path": path, "limit": 10}).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read())
            result.update(
                ok      = True,
                entries = len(resp.get("entries", [])),
                sample  = [e["name"] for e in resp.get("entries", [])[:5]],
            )
        except Exception as exc:
            result.update(ok=False, error=str(exc))
    return jsonify(result)


# ── Tag colours ──────────────────────────────────────────────────────────────

@app.route("/api/tag-colors", methods=["GET"])
def api_tag_colors_get():
    return jsonify(load_tags())


@app.route("/api/tag-colors", methods=["POST"])
@require_admin
def api_tag_colors_post():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON"}), 400
    save_tags(data)
    return jsonify({"ok": True})


# ── Notice ───────────────────────────────────────────────────────────────────

@app.route("/api/notice")
def api_notice():
    n   = load_notice()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not n.get("active"):
        return jsonify({"active": False})
    start = n.get("startTime", "")
    end   = n.get("endTime",   "")
    if (not start or now >= start) and (not end or now <= end):
        return jsonify({
            "active":  True,
            "message": n.get("message", ""),
            "version": n.get("version", 0),
        })
    return jsonify({"active": False})


@app.route("/api/notice/push", methods=["POST"])
@require_notice_auth
def api_notice_push():
    n = load_notice()
    n["version"] = n.get("version", 0) + 1
    save_notice(n)
    return jsonify({"ok": True})

@app.route('/print-calendar')
def print_calendar():
    return render_template('print_calendar.html')


@app.route('/print-admin')
def print_admin():
    return render_template('print_admin.html')


@app.route('/api/print-shows', methods=['GET'])
def api_print_shows_get():
    return jsonify(load_print_shows())


@app.route('/api/print-shows', methods=['POST'])
def api_print_shows_post():
    data = request.get_json(force=True, silent=True) or {}
    shows = load_print_shows()
    new_id = str(uuid.uuid4())[:8]
    shows[new_id] = data
    save_print_shows(shows)
    return jsonify({'id': new_id})


@app.route('/api/print-shows/<show_id>', methods=['PUT'])
def api_print_shows_put(show_id):
    data = request.get_json(force=True, silent=True) or {}
    shows = load_print_shows()
    if show_id not in shows:
        return Response('Not found', status=404)
    shows[show_id] = data
    save_print_shows(shows)
    return jsonify({'id': show_id})


@app.route('/api/print-shows/<show_id>', methods=['DELETE'])
def api_print_shows_delete(show_id):
    shows = load_print_shows()
    shows.pop(show_id, None)
    save_print_shows(shows)
    return jsonify({'ok': True})


# ── Location rules API ────────────────────────────────────────────────────────

@app.route('/api/location-rules', methods=['GET'])
def api_location_rules_get():
    return jsonify(load_location_rules())


@app.route('/api/location-rules', methods=['POST'])
def api_location_rules_post():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, list):
        return Response('Expected a JSON array', status=400)
    clean = [
        {'keywords': str(r.get('keywords', '')).strip(),
         'replacement': str(r.get('replacement', '')).strip()}
        for r in data
        if r.get('keywords') and r.get('replacement')
    ]
    save_location_rules(clean)
    return jsonify({'ok': True, 'count': len(clean)})


# ── Print Calendar PDF ────────────────────────────────────────────────────────

@app.route('/api/generate-calendar-pdf', methods=['POST'])
def api_generate_calendar_pdf():
    if not _PDF_AVAILABLE:
        return Response(
            'ReportLab not installed. Run: ~/propared-display/venv/bin/pip install reportlab',
            status=500
        )
    data         = request.get_json(force=True, silent=True) or {}
    show_ids     = data.get('showIds', [])
    cal_type     = data.get('calType', 'monthly')
    updated_by   = data.get('updatedBy', '').strip()
    cal_subtitle = data.get('calSubtitle', 'Rehearsal Performance Calendar').strip()
    custom_notes = data.get('customNotes', {})
    multi_show   = bool(data.get('multiShow', len(show_ids) > 1))
    shows          = load_print_shows()
    tag_colors     = load_tags()
    location_rules = load_location_rules() if data.get('applyLocationRules', True) else []

    try:
        if cal_type == 'weekly':
            pdf_bytes = _build_weekly_pdf(
                show_ids       = show_ids,
                shows          = shows,
                tag_colors     = tag_colors,
                location_rules = location_rules,
                start_date     = data.get('startDate', ''),
                end_date       = data.get('endDate',   ''),
                updated_by     = updated_by,
                cal_subtitle   = cal_subtitle,
                custom_notes   = custom_notes,
                multi_show     = multi_show,
            )
        else:
            pdf_bytes = _build_calendar_pdf(
                show_ids       = show_ids,
                shows          = shows,
                tag_colors     = tag_colors,
                location_rules = location_rules,
                start_month    = _to_int(data.get('startMonth'), 0, minimum=0, maximum=12),
                start_year     = _to_int(data.get('startYear'), 2026, minimum=2000, maximum=2100),
                end_month      = _to_int(data.get('endMonth'), 0, minimum=0, maximum=12),
                end_year       = _to_int(data.get('endYear'), 2026, minimum=2000, maximum=2100),
                updated_by     = updated_by,
                cal_subtitle   = cal_subtitle,
                custom_notes   = custom_notes,
                multi_show     = multi_show,
            )
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': 'attachment; filename=calendar.pdf',
                'Content-Length': str(len(pdf_bytes)),
            }
        )
    except Exception as exc:
        log.error('PDF generation failed: %s', exc)
        return Response(f'PDF generation failed: {exc}', status=500)

@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    data      = request.get_json(silent=True) or {}
    client_id = data.get("client_id", "")
    hostname  = data.get("hostname", request.remote_addr)
    role      = data.get("role", "display")

    if not client_id:
        return jsonify({"ok": False, "error": "missing client_id"}), 400

    existing = _clients.get(client_id, {})
    _clients[client_id] = {
        "hostname":        hostname,
        "ip":              data.get("ip", request.remote_addr),
        "role":            role,
        "last_seen":       time.time(),
        # Preserve admin-assigned config
        "assigned_room":   existing.get("assigned_room", ""),
        "screenOn":        existing.get("screenOn", "08:00"),
        "screenOff":       existing.get("screenOff", "22:00"),
        "scheduleEnabled": existing.get("scheduleEnabled", False),
    }
    save_clients(_clients)
    return jsonify({"ok": True})


@app.route("/api/client-config/<client_id>")
def api_client_config(client_id):
    """
    Called by Pi clients at boot to get their room assignment and schedule.
    Auto-registers unknown clients. Returns config or empty assignment.
    """
    hostname  = request.args.get("hostname", "unknown")
    ip        = request.remote_addr

    existing = _clients.get(client_id, {})
    if client_id not in _clients:
        # First contact — register with no assignment
        _clients[client_id] = {
            "hostname":        hostname,
            "ip":              ip,
            "role":            "display",
            "last_seen":       time.time(),
            "assigned_room":   "",
            "screenOn":        "08:00",
            "screenOff":       "22:00",
            "scheduleEnabled": False,
        }
        save_clients(_clients)
    else:
        # Update last seen / hostname / ip
        _clients[client_id]["last_seen"] = time.time()
        _clients[client_id]["hostname"]  = hostname
        _clients[client_id]["ip"]        = ip
        save_clients(_clients)

    cfg     = _clients[client_id]
    rid     = cfg.get("assigned_room", "")
    rooms   = load_rooms()
    s       = load_settings()

    if rid == "__dashboard__":
        display_url  = "/dashboard"
        display_role = "dashboard"
    elif rid and rid in rooms:
        display_url  = f"/display?room={rid}"
        display_role = "display"
    else:
        display_url  = ""
        display_role = "unassigned"

    return jsonify({
        "client_id":       client_id,
        "display_url":     display_url,
        "display_role":    display_role,
        "assigned_room":   rid,
        "screenOn":        cfg.get("screenOn",  "08:00"),
        "screenOff":       cfg.get("screenOff", "22:00"),
        "scheduleEnabled": cfg.get("scheduleEnabled", False),
        "server_url":      s.get("serverUrl", ""),
    })


@app.route("/admin/clients")
@require_admin
def admin_clients_list():
    now   = time.time()
    rooms = load_rooms()
    out   = []
    for client_id, c in sorted(_clients.items(), key=lambda x: x[1].get("hostname","")):
        rid = c.get("assigned_room", "")
        out.append({
            "client_id":       client_id,
            "hostname":        c.get("hostname", client_id[:8]),
            "ip":              c.get("ip", ""),
            "online":          (now - c.get("last_seen", 0)) < 90,
            "assigned_room":   rid,
            "screenOn":        c.get("screenOn",  "08:00"),
            "screenOff":       c.get("screenOff", "22:00"),
            "scheduleEnabled": c.get("scheduleEnabled", False),
        })
    return jsonify(out)


@app.route("/admin/client/<client_id>/assign", methods=["POST"])
@require_admin
def admin_client_assign(client_id):
    """Assign a room and schedule to a client from the admin panel.""";
    data = request.get_json(force=True, silent=True) or {}
    if client_id not in _clients:
        return jsonify({"error": "Unknown client"}), 404
    _clients[client_id]["assigned_room"]   = data.get("assigned_room", "")
    _clients[client_id]["screenOn"]        = data.get("screenOn",  "08:00")
    _clients[client_id]["screenOff"]       = data.get("screenOff", "22:00")
    _clients[client_id]["scheduleEnabled"] = bool(data.get("scheduleEnabled", False))
    save_clients(_clients)
    return jsonify({"ok": True})


@app.route("/admin/client/<client_id>/delete", methods=["POST"])
@require_admin
def admin_client_delete(client_id):
    _clients.pop(client_id, None)
    save_clients(_clients)
    return jsonify({"ok": True})


# ── Logo ─────────────────────────────────────────────────────────────────────

@app.route("/static/logo/<rid>")
def serve_logo(rid):
    p = logo_path(rid)
    if not p.exists():
        return "", 404
    return app.response_class(
        p.read_bytes(),
        mimetype="image/png",
        headers={"Cache-Control": "no-cache"},
    )


# ── Display pages ─────────────────────────────────────────────────────────────

@app.route("/display")
def display():
    rid   = request.args.get("room", "")
    rooms = load_rooms()
    if not rid or rid not in rooms:
        return render_template("room_not_found.html", rooms=rooms, room_id=rid)
    room = _public_room_config(rid, rooms, load_settings())
    resp = make_response(render_template(
        "display.html",
        room       = room,
        server_url = request.host_url.rstrip("/"),
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/slide")
def slide_view():
    rid   = request.args.get("room", "")
    rooms = load_rooms()
    if not rid or rid not in rooms:
        return redirect(f"/display?room={rid}")
    s = load_settings()
    room = {
        "roomId":        rid,
        "calDuration":   s.get("calDuration",   60),
        "slideDuration": s.get("slideDuration",  8),
    }
    return render_template("slide.html", room=room, server_url=request.host_url.rstrip("/"))


@app.route("/dashboard")
def dashboard():
    s     = load_settings()
    rooms = load_rooms()
    selected = [
        (rid, rooms[rid])
        for rid in s.get("dashboardRooms", [])
        if rid in rooms
    ]
    return render_template(
        "dashboard.html",
        rooms          = selected,
        iframe_url     = s.get("dashboardIframeUrl", ""),
        cal_duration   = s.get("dashboardCalDuration",   60),
        slide_duration = s.get("dashboardSlideDuration",  8),
        server_url     = request.host_url.rstrip("/"),
        all_rooms      = rooms,
    )






@app.route('/api/proxy-ical')
def proxy_ical():
    url = _validated_proxy_ical_url(request.args.get("url", ""))
    if not url:
        return Response("Invalid iCal URL", status=400)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ProparedDisplay/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8', errors='replace')
        return Response(body, mimetype='text/calendar',
            headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return (str(e), 502)



# ── Notice page ───────────────────────────────────────────────────────────────

@app.route("/notice", methods=["GET", "POST"])
def notice_page():
    setup_needed = not _read_pw_file(NOTICE_PASSWORD_FILE)
    msg = ""
    n   = load_notice()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "set_password":
            pw = request.form.get("password", "").strip()
            if pw:
                _write_pw_file(NOTICE_PASSWORD_FILE, pw)
            return redirect("/notice")

        # All other actions require auth
        auth = request.authorization
        if not auth or not _check_pw(auth.password, NOTICE_PASSWORD_FILE):
            return Response(
                "Notice access required.", 401,
                {"WWW-Authenticate": 'Basic realm="Notice Board"'},
            )
        if action == "save":
            n["message"]   = request.form.get("message", "").strip()
            n["startTime"] = request.form.get("startTime", "").strip()
            n["endTime"]   = request.form.get("endTime",   "").strip()
            n["active"]    = request.form.get("active") == "1"
            save_notice(n)
            msg = "Notice saved."
        elif action == "clear":
            n = {"active": False, "message": "", "startTime": "", "endTime": "", "version": 0}
            save_notice(n)
            msg = "Notice cleared."

    else:  # GET
        auth = request.authorization
        if not setup_needed and (not auth or not _check_pw(auth.password, NOTICE_PASSWORD_FILE)):
            return Response(
                "Notice access required.", 401,
                {"WWW-Authenticate": 'Basic realm="Notice Board"'},
            )

    return render_template("notice.html", n=n, msg=msg, setup_needed=setup_needed)


# ── Admin: setup ──────────────────────────────────────────────────────────────

@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    if _read_pw_file(PASSWORD_FILE):
        return redirect("/admin")
    error = None
    if request.method == "POST":
        pw  = request.form.get("password",  "").strip()
        pw2 = request.form.get("password2", "").strip()
        if len(pw) < 6:
            error = "Password must be at least 6 characters."
        elif pw != pw2:
            error = "Passwords do not match."
        else:
            _write_pw_file(PASSWORD_FILE, pw)
            return redirect("/admin")
    return render_template("admin_setup.html", error=error)


# ── Admin: main ───────────────────────────────────────────────────────────────

@app.route("/admin")
@require_admin
def admin():
    s = load_settings()
    return render_template(
        "admin.html",
        rooms             = load_rooms(),
        tag_colors        = load_tags(),
        settings          = s,
        dropbox_connected = bool(s.get("dropboxRefreshToken") or s.get("dropboxToken")),
        flash_dropbox     = request.args.get("dropbox"),
        flash_error       = request.args.get("dropbox_error"),
    )


# ── Admin: global settings ────────────────────────────────────────────────────

@app.route("/admin/settings", methods=["POST"])
@require_admin
def admin_settings():
    s = load_settings()
    s["dropboxFolder"] = request.form.get("dropboxFolder", s["dropboxFolder"]).strip()
    s["calDuration"]   = _to_int(request.form.get("calDuration"), s["calDuration"], minimum=5, maximum=3600)
    s["slideDuration"] = _to_int(request.form.get("slideDuration"), s["slideDuration"], minimum=1, maximum=3600)
    for key in ("dropboxToken", "dropboxAppKey", "dropboxAppSecret", "dropboxRefreshToken"):
        val = request.form.get(key, "").strip()
        if val:
            s[key] = val
    save_settings(s)
    cache = slides_cache_path()
    if cache.exists():
        cache.unlink()
    return redirect("/admin")


# ── Admin: Dropbox OAuth ──────────────────────────────────────────────────────

@app.route("/admin/dropbox/exchange", methods=["POST"])
@require_admin
def admin_dropbox_exchange():
    code = request.form.get("code", "").strip()
    if not code:
        return redirect("/admin?dropbox_error=No+code+provided")
    s          = load_settings()
    app_key    = s.get("dropboxAppKey",    "").strip()
    app_secret = s.get("dropboxAppSecret", "").strip()
    if not app_key or not app_secret:
        return redirect("/admin?dropbox_error=Save+App+Key+and+Secret+first")
    result = _exchange_dropbox_code(code, app_key, app_secret, "http://localhost/dropbox-auth")
    if "access_token" in result:
        s["dropboxToken"]        = result["access_token"]
        s["dropboxRefreshToken"] = result.get("refresh_token", "")
        save_settings(s)
        cache = slides_cache_path()
        if cache.exists():
            cache.unlink()
        return redirect("/admin?dropbox=connected")
    err = result.get("error_description") or result.get("error", "Unknown error")
    return redirect("/admin?dropbox_error=" + urllib.parse.quote(str(err)))


# ── Admin: dashboard settings ─────────────────────────────────────────────────

@app.route("/admin/dashboard", methods=["POST"])
@require_admin
def admin_dashboard_save():
    s = load_settings()
    s["dashboardIframeUrl"]    = request.form.get("dashboardIframeUrl", "").strip()
    s["dashboardRooms"]        = request.form.getlist("dashboardRooms")
    s["dashboardCalDuration"]  = _to_int(request.form.get("dashboardCalDuration"), 60, minimum=5, maximum=3600)
    s["dashboardSlideDuration"] = _to_int(request.form.get("dashboardSlideDuration"), 8, minimum=1, maximum=3600)
    save_settings(s)
    return redirect("/admin")


# ── Admin: global calendars ──────────────────────────────────────────

@app.route("/admin/global-calendars", methods=["POST"])
@require_admin
def admin_global_calendars():
    data  = request.get_json(force=True, silent=True) or {}
    cals  = data.get("globalCalendars", [])
    clean = []
    for gc in cals:
        gid = gc.get("id", "").strip()
        url = gc.get("url", "").strip()
        if gid and url:
            clean.append({
                "id":    gid,
                "name":  gc.get("name", "").strip(),
                "url":   url,
                "color": gc.get("color", "#555555").strip(),
            })
    s = load_settings()
    s["globalCalendars"] = clean
    save_settings(s)
    _sync_global_calendar_cache(clean)
    return jsonify({"ok": True})


# ── Admin: room management ────────────────────────────────────────────────────

@app.route("/admin/room/new", methods=["POST"])
@require_admin
def admin_room_new():
    rooms = load_rooms()
    rid   = str(uuid.uuid4())[:8]
    ical  = request.form.get("icalUrl", "").strip()
    rooms[rid] = {
        "title":        request.form.get("title", "New Room"),
        "icalUrl":      ical,
        "refresh":      _to_int(request.form.get("refresh"), 5, minimum=1, maximum=1440),
        "showSlideshow": request.form.get("showSlideshow") == "1",
        "startHour":    _to_int(request.form.get("startHour"), 8, minimum=0, maximum=23),
        "endHour":      _to_int(request.form.get("endHour"), 22, minimum=0, maximum=23),
        "createdAt":    time.time(),
    }
    save_rooms(rooms)
    f = request.files.get("logo")
    if f and f.filename:
        f.save(str(logo_path(rid)))
    if ical:
        ical_cache.schedule(rid, ical, rooms[rid]["refresh"])
    return redirect("/admin")


@app.route("/admin/room/<rid>/edit", methods=["POST"])
@require_admin
def admin_room_edit(rid):
    rooms = load_rooms()
    if rid not in rooms:
        return redirect("/admin")
    r = rooms[rid]
    r["title"]         = request.form.get("title",   r.get("title", ""))
    r["icalUrl"]       = request.form.get("icalUrl", r.get("icalUrl", "")).strip()
    r["refresh"]       = _to_int(request.form.get("refresh"), r.get("refresh", 5), minimum=1, maximum=1440)
    r["showSlideshow"] = request.form.get("showSlideshow") == "1"
    r["startHour"]     = _to_int(request.form.get("startHour"), r.get("startHour", 8), minimum=0, maximum=23)
    r["endHour"]       = _to_int(request.form.get("endHour"), r.get("endHour", 22), minimum=0, maximum=23)
    save_rooms(rooms)
    f = request.files.get("logo")
    if f and f.filename:
        f.save(str(logo_path(rid)))
    if request.form.get("removeLogo") == "1":
        p = logo_path(rid)
        if p.exists():
            p.unlink()
    # Restart background refresh with updated URL / interval
    ical_cache.schedule(rid, r["icalUrl"], r["refresh"])
    return redirect("/admin")


@app.route("/admin/room/<rid>/delete", methods=["POST"])
@require_admin
def admin_room_delete(rid):
    rooms = load_rooms()
    if rid in rooms:
        del rooms[rid]
    save_rooms(rooms)
    ical_cache.remove(rid)
    p = logo_path(rid)
    if p.exists():
        p.unlink()
    return redirect("/admin")


# ── Admin: backup & restore ───────────────────────────────────────────────────

def _make_backup_zip() -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in (
            "rooms.json", "tag_colors.json", "settings.json",
            "notice.json", "print_shows.json", "location_rules.json",
        ):
            p = BASE / fname
            if p.exists():
                zf.write(p, fname)
        if STATIC_DIR.is_dir():
            for fn in STATIC_DIR.iterdir():
                if fn.name.startswith("logo_") and fn.suffix == ".png":
                    zf.write(fn, f"static/{fn.name}")
        manifest = {
            "version":   4,
            "createdAt": datetime.now().isoformat(),
            "rooms":     list(load_rooms().keys()),
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    buf.seek(0)
    return buf


@app.route("/admin/backup")
@require_admin
def admin_backup():
    buf = _make_backup_zip()
    ts  = datetime.now().strftime("%Y%m%d-%H%M%S")
    fn  = f"propared-backup-{ts}.zip"
    (BACKUP_DIR / fn).write_bytes(buf.read())
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=fn, mimetype="application/zip")


@app.route("/admin/backup/list")
@require_admin
def admin_backup_list():
    backups = []
    if BACKUP_DIR.is_dir():
        for fp in sorted(BACKUP_DIR.glob("*.zip"), reverse=True):
            backups.append({
                "name":  fp.name,
                "size":  fp.stat().st_size,
                "mtime": fp.stat().st_mtime,
            })
    return jsonify(backups)


@app.route("/admin/backup/download/<filename>")
@require_admin
def admin_backup_download(filename):
    fp = BACKUP_DIR / Path(filename).name   # Path.name prevents traversal
    if not fp.exists():
        return Response("Not found", 404)
    return send_file(fp, as_attachment=True, download_name=fp.name, mimetype="application/zip")


@app.route("/admin/backup/delete/<filename>", methods=["POST"])
@require_admin
def admin_backup_delete(filename):
    fp = BACKUP_DIR / Path(filename).name
    if fp.exists():
        fp.unlink()
    return redirect("/admin#backup")


@app.route("/admin/restore", methods=["POST"])
@require_admin
def admin_restore():
    f = request.files.get("backup")
    if not f or not f.filename.endswith(".zip"):
        return redirect("/admin?restore_error=Please+upload+a+valid+.zip+file")
    try:
        buf = io.BytesIO(f.read())
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
            for fname in (
                "rooms.json", "tag_colors.json", "settings.json",
                "notice.json", "print_shows.json", "location_rules.json",
            ):
                if fname in names:
                    (BASE / fname).write_bytes(zf.read(fname))
            _restore_logo_files(names, zf)
        restored_rooms = load_rooms()
        restored_settings = load_settings()
        for rid in list(ical_cache._data):
            if rid not in restored_rooms:
                ical_cache.remove(rid)
        # Restart iCal refresh for restored rooms
        for rid, room in restored_rooms.items():
            url = room.get("icalUrl", "").strip()
            if url:
                ical_cache.schedule(rid, url, _to_int(room.get("refresh"), 5, minimum=1, maximum=1440))
        _sync_global_calendar_cache(restored_settings.get("globalCalendars", []))
        return redirect("/admin?restored=1")
    except Exception as exc:
        log.error("Restore failed: %s", exc)
        return redirect("/admin?restore_error=" + urllib.parse.quote(str(exc)))

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
