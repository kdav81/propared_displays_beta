from __future__ import annotations

import uuid
from datetime import datetime

from flask import Response, jsonify, redirect, render_template, request

from app.auth import require_notice_auth
from app.config import NOTICE_PASSWORD_FILE
from app.storage import (
    check_password,
    load_notice,
    load_rooms,
    read_password_hash,
    save_notice,
    write_password,
)


NOTICE_TIME_FORMAT = "%Y-%m-%d %H:%M"


def _parse_notice_time(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, NOTICE_TIME_FORMAT)
    except ValueError:
        return None


def _active_notice(notice: dict, now: datetime) -> bool:
    if not notice.get("active") or not notice.get("message", "").strip():
        return False
    start = _parse_notice_time(notice.get("startTime", ""))
    end = _parse_notice_time(notice.get("endTime", ""))
    if notice.get("startTime") and start is None:
        return False
    if notice.get("endTime") and end is None:
        return False
    return (not start or now >= start) and (not end or now <= end)


def _notice_sort_key(notice: dict):
    return (
        notice.get("updatedAt", ""),
        notice.get("createdAt", ""),
        int(notice.get("version", 0)),
    )


def _current_notice(notices: list[dict], now: datetime) -> dict | None:
    active = [notice for notice in notices if _active_notice(notice, now)]
    if not active:
        return None
    return sorted(active, key=_notice_sort_key, reverse=True)[0]


def _all_notice_items(notices: dict, rooms: dict) -> list[dict]:
    now = datetime.now()
    items = []
    for notice in notices.get("global", []):
        item = dict(notice)
        item["scope"] = "global"
        item["scopeLabel"] = "Global Notice - all rooms"
        item["visibleNow"] = _active_notice(item, now)
        items.append(item)
    for room_id, room_notices in notices.get("rooms", {}).items():
        for notice in room_notices:
            item = dict(notice)
            item["scope"] = room_id
            item["scopeLabel"] = rooms.get(room_id, {}).get("title", room_id)
            item["visibleNow"] = _active_notice(item, now)
            items.append(item)
    items.sort(key=lambda item: (item.get("updatedAt", ""), item.get("createdAt", "")), reverse=True)
    return items


def _find_notice(notices: dict, notice_id: str):
    for notice in notices.get("global", []):
        if notice.get("id") == notice_id:
            return notices["global"], notice
    for room_notices in notices.get("rooms", {}).values():
        for notice in room_notices:
            if notice.get("id") == notice_id:
                return room_notices, notice
    return None, None


def _validate_payload(data: dict, rooms: dict):
    scope = str(data.get("scope", "global")).strip() or "global"
    if scope != "global" and scope not in rooms:
        return None, "Choose a valid room."
    message = str(data.get("message", "")).strip()
    if not message:
        return None, "Message is required."
    start_time = str(data.get("startTime", "")).strip()
    end_time = str(data.get("endTime", "")).strip()
    start_dt = _parse_notice_time(start_time)
    end_dt = _parse_notice_time(end_time)
    if start_time and start_dt is None:
        return None, "Invalid start date/time."
    if end_time and end_dt is None:
        return None, "Invalid end date/time."
    if start_dt and end_dt and end_dt < start_dt:
        return None, "End date/time cannot be earlier than start date/time."
    return {
        "scope": scope,
        "message": message,
        "startTime": start_time,
        "endTime": end_time,
        "active": bool(data.get("active", True)),
    }, None


def register_notice_routes(app) -> None:
    @app.route("/api/notice")
    def api_notice():
        notices = load_notice()
        now = datetime.now()
        room_id = request.args.get("room", "").strip()
        notice = _current_notice(notices.get("global", []), now)
        if not notice and room_id:
            notice = _current_notice(notices.get("rooms", {}).get(room_id, []), now)
        if notice:
            return jsonify(
                {
                    "active": True,
                    "message": notice.get("message", ""),
                    "version": notice.get("version", 0),
                }
            )
        return jsonify({"active": False})

    @app.route("/api/notices")
    @require_notice_auth
    def api_notices_list():
        return jsonify(_all_notice_items(load_notice(), load_rooms()))

    @app.route("/api/notices", methods=["POST"])
    @require_notice_auth
    def api_notices_create():
        data = request.get_json(force=True, silent=True) or {}
        rooms = load_rooms()
        payload, error = _validate_payload(data, rooms)
        if error:
            return Response(error, status=400)
        now = datetime.now().isoformat(timespec="seconds")
        notice = {
            "id": uuid.uuid4().hex[:12],
            "message": payload["message"],
            "startTime": payload["startTime"],
            "endTime": payload["endTime"],
            "active": payload["active"],
            "version": 1,
            "createdAt": now,
            "updatedAt": now,
        }
        notices = load_notice()
        if payload["scope"] == "global":
            notices["global"].append(notice)
        else:
            notices["rooms"].setdefault(payload["scope"], []).append(notice)
        save_notice(notices)
        return jsonify({"ok": True, "notice": notice})

    @app.route("/api/notices/<notice_id>", methods=["PUT", "POST"])
    @require_notice_auth
    def api_notices_update(notice_id):
        data = request.get_json(force=True, silent=True) or {}
        rooms = load_rooms()
        payload, error = _validate_payload(data, rooms)
        if error:
            return Response(error, status=400)

        notices = load_notice()
        source, notice = _find_notice(notices, notice_id)
        if notice is None:
            return Response("Not found", status=404)

        source.remove(notice)
        notice["message"] = payload["message"]
        notice["startTime"] = payload["startTime"]
        notice["endTime"] = payload["endTime"]
        notice["active"] = payload["active"]
        notice["version"] = int(notice.get("version", 0)) + 1
        notice["updatedAt"] = datetime.now().isoformat(timespec="seconds")
        if payload["scope"] == "global":
            notices["global"].append(notice)
        else:
            notices["rooms"].setdefault(payload["scope"], []).append(notice)
        notices["rooms"] = {room_id: items for room_id, items in notices["rooms"].items() if items}
        save_notice(notices)
        return jsonify({"ok": True})

    @app.route("/api/notices/<notice_id>", methods=["DELETE"])
    @require_notice_auth
    def api_notices_delete(notice_id):
        notices = load_notice()
        source, notice = _find_notice(notices, notice_id)
        if notice is None:
            return Response("Not found", status=404)
        source.remove(notice)
        notices["rooms"] = {room_id: items for room_id, items in notices["rooms"].items() if items}
        save_notice(notices)
        return jsonify({"ok": True})

    @app.route("/notice", methods=["GET", "POST"])
    def notice_page():
        setup_needed = not read_password_hash(NOTICE_PASSWORD_FILE)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "set_password":
                auth = request.authorization
                if not setup_needed and (not auth or not check_password(auth.password, NOTICE_PASSWORD_FILE)):
                    return Response(
                        "Notice access required.",
                        401,
                        {"WWW-Authenticate": 'Basic realm="Notice Board"'},
                    )
                pw = request.form.get("password", "").strip()
                if pw:
                    write_password(NOTICE_PASSWORD_FILE, pw)
                return redirect("/notice")

        auth = request.authorization
        if not setup_needed and (not auth or not check_password(auth.password, NOTICE_PASSWORD_FILE)):
            return Response(
                "Notice access required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Notice Board"'},
            )

        return render_template(
            "notice.html",
            rooms=load_rooms(),
            setup_needed=setup_needed,
        )
