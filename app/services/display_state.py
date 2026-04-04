from __future__ import annotations

from datetime import datetime


def format_event_time(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    hour, minute = dt.hour, dt.minute
    suffix = "AM" if hour < 12 else "PM"
    hour = hour % 12 or 12
    return f"{hour}:{minute:02d} {suffix}" if minute else f"{hour} {suffix}"


def naive_local(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.replace(tzinfo=None)


def room_status(ical_cache, rid: str, *, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    events = ical_cache.get_events(rid)
    today = sorted([event for event in events if naive_local(event["start"]).date() == now.date()], key=lambda event: event["start"])

    current = next((event for event in today if naive_local(event["start"]) <= now < naive_local(event["end"])), None)
    future = [event for event in today if naive_local(event["start"]) > now]
    upcoming = future[0] if future else None

    def _event_payload(event) -> dict | None:
        if not event:
            return None
        return {
            "title": event["title"],
            "start": format_event_time(event["start"]),
            "end": format_event_time(event["end"]),
        }

    return {
        "rid": rid,
        "occupied": current is not None,
        "current": _event_payload(current),
        "next": _event_payload(upcoming),
    }


def public_room_config(rid: str, rooms: dict, settings: dict, *, load_tags, logo_path, slide_links) -> dict:
    room = dict(rooms[rid])
    room.update(
        roomId=rid,
        tagColors=load_tags(),
        hasLogo=logo_path(rid).exists(),
        hasSlideshow=bool(slide_links()),
        calDuration=settings.get("calDuration", 60),
        slideDuration=settings.get("slideDuration", 8),
    )
    room.setdefault("startHour", 8)
    room.setdefault("endHour", 22)
    return room
