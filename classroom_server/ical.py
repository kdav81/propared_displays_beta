from __future__ import annotations

import threading
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from classroom_server.core import STATIC_DIR, log, to_int


def restore_logo_files(archive_names: list[str], zf: zipfile.ZipFile) -> None:
    archived_logos = {
        Path(name).name for name in archive_names
        if name.startswith("static/logo_") and name.endswith(".png")
    }
    for fp in STATIC_DIR.glob("logo_*.png"):
        if fp.name not in archived_logos:
            fp.unlink()
    for logo_name in archived_logos:
        (STATIC_DIR / logo_name).write_bytes(zf.read(f"static/{logo_name}"))


def validated_proxy_ical_url(raw_url: str) -> str | None:
    url = raw_url.strip().replace("webcal://", "https://").replace("webcal:", "https:")
    if not url or len(url) > 2048:
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc or parsed.username or parsed.password:
        return None
    return parsed.geturl()


def parse_dt(line: str) -> datetime | None:
    colon = line.index(":")
    params = line[:colon].upper()
    val = line[colon + 1:].strip()
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
    events: list[dict] = []
    text = text.replace("\r\n ", "").replace("\r\n\t", "")
    text = text.replace("\n ", "").replace("\n\t", "")

    for raw_block in text.split("BEGIN:VEVENT")[1:]:
        end_idx = raw_block.find("END:VEVENT")
        block = raw_block[:end_idx] if end_idx != -1 else raw_block
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
        val = dtstart_line[colon + 1:].strip()
        if "T" in val:
            continue

        def date_str(raw: str) -> str:
            return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"

        start_str = date_str(val)
        end_str = start_str
        if "DTEND" in props:
            dtend_line = props["DTEND"]
            ec = dtend_line.index(":")
            ev = dtend_line[ec + 1:].strip()
            if "T" not in ev:
                from datetime import date, timedelta

                ed = date(int(ev[0:4]), int(ev[4:6]), int(ev[6:8])) - timedelta(days=1)
                end_str = ed.isoformat()

        raw_title = props["SUMMARY"].split(":", 1)[1].strip()
        title = raw_title.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";").replace("\\:", ":")
        events.append({"title": title, "start": start_str, "end": end_str})
    return events


def parse_ical(text: str) -> list[dict]:
    events: list[dict] = []
    text = text.replace("\r\n ", "").replace("\r\n\t", "")
    text = text.replace("\n ", "").replace("\n\t", "")

    for raw_block in text.split("BEGIN:VEVENT")[1:]:
        end_idx = raw_block.find("END:VEVENT")
        block = raw_block[:end_idx] if end_idx != -1 else raw_block
        props: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            base_key = line.split(":")[0].split(";")[0].upper()
            props[base_key] = line

        if "SUMMARY" not in props or "DTSTART" not in props:
            continue

        start = parse_dt(props["DTSTART"])
        if start is None:
            continue
        end = parse_dt(props["DTEND"]) if "DTEND" in props else None
        if end is None:
            end = start

        raw_title = props["SUMMARY"].split(":", 1)[1].strip()
        title = raw_title.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";").replace("\\:", ":")
        events.append({"title": title, "start": start, "end": end})
    return events


class ICalCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._timers: dict[str, threading.Timer] = {}

    def get_events(self, rid: str) -> list[dict]:
        with self._lock:
            return list(self._data.get(rid, {}).get("events", []))

    def get_allday(self, rid: str) -> list[dict]:
        with self._lock:
            return list(self._data.get(rid, {}).get("allday", []))

    def get_meta(self, rid: str) -> dict:
        with self._lock:
            data = self._data.get(rid, {})
            return {"fetched_at": data.get("fetched_at"), "error": data.get("error")}

    def schedule(self, rid: str, ical_url: str, interval_min: int) -> None:
        self._cancel(rid)
        if ical_url:
            self._fetch_then_reschedule(rid, ical_url, interval_min)

    def remove(self, rid: str) -> None:
        self._cancel(rid)
        with self._lock:
            self._data.pop(rid, None)

    def active_ids(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def _cancel(self, rid: str) -> None:
        timer = self._timers.pop(rid, None)
        if timer:
            timer.cancel()

    def _fetch_then_reschedule(self, rid: str, ical_url: str, interval_min: int) -> None:
        self._fetch(rid, ical_url)
        timer = threading.Timer(
            interval_min * 60,
            self._fetch_then_reschedule,
            args=(rid, ical_url, interval_min),
        )
        timer.daemon = True
        timer.start()
        self._timers[rid] = timer

    def _fetch(self, rid: str, ical_url: str) -> None:
        log.info("Fetching iCal for room %s", rid)
        ical_url = ical_url.replace("webcal://", "https://").replace("webcal:", "https:")
        try:
            req = urllib.request.Request(ical_url, headers={"User-Agent": "ClassroomDisplay/4.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                text = response.read().decode("utf-8", errors="replace")
            events = parse_ical(text)
            allday_events = parse_ical_allday(text)
            with self._lock:
                self._data[rid] = {
                    "events": events,
                    "allday": allday_events,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                }
            log.info("Room %s: %d events, %d all-day cached", rid, len(events), len(allday_events))
        except Exception as exc:
            log.warning("Room %s iCal fetch failed: %s", rid, exc)
            with self._lock:
                previous = self._data.get(rid, {"events": [], "fetched_at": None})
                previous["error"] = str(exc)
                self._data[rid] = previous


ical_cache = ICalCache()
global_cal_cache = ICalCache()


def sync_global_calendar_cache(calendars: list[dict]) -> None:
    active_ids = {gc.get("id", "").strip() for gc in calendars if gc.get("id", "").strip()}
    for gc_id in global_cal_cache.active_ids():
        if gc_id not in active_ids:
            global_cal_cache.remove(gc_id)
    for gc in calendars:
        gc_id = gc.get("id", "").strip()
        url = gc.get("url", "").strip()
        if gc_id and url:
            global_cal_cache.schedule(gc_id, url, 60)


def boot_ical_cache(load_rooms, load_settings) -> None:
    for rid, room in load_rooms().items():
        url = room.get("icalUrl", "").strip()
        if url:
            ical_cache.schedule(rid, url, to_int(room.get("refresh"), 5, minimum=1, maximum=1440))
    sync_global_calendar_cache(load_settings().get("globalCalendars", []))

