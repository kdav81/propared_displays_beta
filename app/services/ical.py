from __future__ import annotations

import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone


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


def _parse_dt(line: str) -> datetime | None:
    colon = line.index(":")
    params = line[:colon].upper()
    value = line[colon + 1 :].strip()

    if "T" not in value:
        return None
    if "VALUE=DATE" in params and "T" not in value:
        return None

    try:
        year = int(value[0:4])
        month = int(value[4:6])
        day = int(value[6:8])
        hour = int(value[9:11])
        minute = int(value[11:13])
        second = int(value[13:15]) if len(value) > 13 and value[13:15].isdigit() else 0
        is_utc = value.endswith("Z")
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc if is_utc else None)
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
        value = dtstart_line[colon + 1 :].strip()
        if "T" in value:
            continue

        def _date_str(raw: str) -> str:
            return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"

        start_str = _date_str(value)
        end_str = start_str
        if "DTEND" in props:
            from datetime import date, timedelta

            dtend_line = props["DTEND"]
            end_colon = dtend_line.index(":")
            end_value = dtend_line[end_colon + 1 :].strip()
            if "T" not in end_value:
                end_date = date(int(end_value[0:4]), int(end_value[4:6]), int(end_value[6:8])) - timedelta(days=1)
                end_str = end_date.isoformat()

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

        start = _parse_dt(props["DTSTART"])
        if start is None:
            continue

        end = _parse_dt(props["DTEND"]) if "DTEND" in props else None
        if end is None:
            end = start

        raw_title = props["SUMMARY"].split(":", 1)[1].strip()
        title = raw_title.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";").replace("\\:", ":")
        events.append({"title": title, "start": start, "end": end})

    return events


class ICalCache:
    def __init__(self, *, log):
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._log = log

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

    def sync_global_calendars(self, calendars: list[dict]) -> None:
        active_ids = {calendar.get("id", "").strip() for calendar in calendars if calendar.get("id", "").strip()}
        for calendar_id in list(self._data):
            if calendar_id not in active_ids:
                self.remove(calendar_id)
        for calendar in calendars:
            calendar_id = calendar.get("id", "").strip()
            url = calendar.get("url", "").strip()
            if calendar_id and url:
                self.schedule(calendar_id, url, 60)

    def boot_room_calendars(self, rooms: dict, *, to_int) -> None:
        for rid, room in rooms.items():
            url = room.get("icalUrl", "").strip()
            if url:
                self.schedule(rid, url, to_int(room.get("refresh"), 5, minimum=1, maximum=1440))

    def _cancel(self, rid: str) -> None:
        timer = self._timers.pop(rid, None)
        if timer:
            timer.cancel()

    def _fetch_then_reschedule(self, rid: str, ical_url: str, interval_min: int) -> None:
        self._fetch(rid, ical_url)
        timer = threading.Timer(interval_min * 60, self._fetch_then_reschedule, args=(rid, ical_url, interval_min))
        timer.daemon = True
        timer.start()
        self._timers[rid] = timer

    def _fetch(self, rid: str, ical_url: str) -> None:
        self._log.info("Fetching iCal for room %s", rid)
        normalized_url = ical_url.replace("webcal://", "https://").replace("webcal:", "https:")
        try:
            request = urllib.request.Request(normalized_url, headers={"User-Agent": "ProparedDisplay/4.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
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
            self._log.info("Room %s: %d events, %d all-day cached", rid, len(events), len(allday_events))
        except Exception as exc:
            self._log.warning("Room %s iCal fetch failed: %s", rid, exc)
            with self._lock:
                previous = self._data.get(rid, {"events": [], "fetched_at": None})
                previous["error"] = str(exc)
                self._data[rid] = previous
