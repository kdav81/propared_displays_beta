from __future__ import annotations

import time
import urllib.request
import uuid

from flask import Response, jsonify, make_response, redirect, render_template, request

from app.auth import require_admin
from app.services.media_library import local_slide_items
from app.storage import (
    load_rooms,
    load_settings,
    load_tags,
    save_clients,
    save_rooms,
    save_settings,
    save_tags,
)

SUPPORTED_CLIENT_COMMANDS = {"restart_kiosk"}


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return False


def _normalized_pending_command(value):
    if not isinstance(value, dict):
        return None
    command = str(value.get("command", "")).strip()
    if command not in SUPPORTED_CLIENT_COMMANDS:
        return None
    return {
        "id": str(value.get("id", "")).strip(),
        "command": command,
        "created_at": float(value.get("created_at", 0) or 0),
        "status": str(value.get("status", "pending")).strip() or "pending",
    }


def _ensure_client_defaults(existing: dict, *, hostname: str, ip: str, role: str = "display") -> dict:
    client = dict(existing or {})
    client["hostname"] = hostname
    client["ip"] = ip
    client["role"] = role
    client["last_seen"] = time.time()
    client["assigned_room"] = (
        client.get("assigned_room")
        or client.get("assignedRoom")
        or client.get("room")
        or ""
    )
    client["screenOn"] = str(
        client.get("screenOn")
        or client.get("screen_on")
        or client.get("screen_on_time")
        or "08:00"
    )
    client["screenOff"] = str(
        client.get("screenOff")
        or client.get("screen_off")
        or client.get("screen_off_time")
        or "22:00"
    )
    client["scheduleEnabled"] = _coerce_bool(
        client.get("scheduleEnabled", client.get("schedule_enabled", client.get("SCREEN_SCHEDULE_ENABLED", False)))
    )
    client["pending_command"] = _normalized_pending_command(client.get("pending_command"))
    client["last_command_completed_at"] = float(client.get("last_command_completed_at", 0) or 0)
    client["last_command_id"] = str(client.get("last_command_id", "")).strip()
    return client


def register_display_routes(
    app,
    *,
    clients,
    ical_cache,
    global_cal_cache,
    get_slides,
    logo_path,
    public_room_config,
    room_status,
    sync_global_calendar_cache,
    to_int,
    validated_proxy_ical_url,
) -> None:
    @app.route("/api/health")
    def api_health():
        return jsonify({"ok": True, "rooms": len(load_rooms()), "time": time.time()})

    @app.route("/api/rooms")
    def api_rooms():
        rooms = load_rooms()
        return jsonify(
            [
                {"id": rid, "title": room.get("title", rid)}
                for rid, room in sorted(rooms.items(), key=lambda item: item[1].get("title", ""))
            ]
        )

    @app.route("/api/rooms-print")
    def api_rooms_print():
        rooms = load_rooms()
        return jsonify(
            [
                {"id": rid, "title": room.get("title", rid), "icalUrl": room.get("icalUrl", "")}
                for rid, room in sorted(rooms.items(), key=lambda item: item[1].get("title", ""))
            ]
        )

    @app.route("/api/config/<rid>")
    def api_config(rid):
        rooms = load_rooms()
        if rid not in rooms:
            return jsonify({"error": "Room not found"}), 404
        return jsonify(public_room_config(rid, rooms, load_settings()))

    @app.route("/api/events/<rid>")
    def api_events(rid):
        rooms = load_rooms()
        if rid not in rooms:
            return jsonify({"error": "Room not found"}), 404

        events = ical_cache.get_events(rid)
        meta = ical_cache.get_meta(rid)

        def _dt_str(dt):
            return dt.isoformat() if dt else None

        all_events = [{"title": event["title"], "start": _dt_str(event["start"]), "end": _dt_str(event["end"])} for event in events]
        for global_calendar in load_settings().get("globalCalendars", []):
            gc_id = global_calendar.get("id", "")
            gc_color = global_calendar.get("color", "#555555")
            if not gc_id:
                continue
            for event in global_cal_cache.get_events(gc_id):
                all_events.append(
                    {
                        "title": event["title"],
                        "start": _dt_str(event["start"]),
                        "end": _dt_str(event["end"]),
                        "globalColor": gc_color,
                        "globalOnly": True,
                    }
                )

        all_day_events = []
        for global_calendar in load_settings().get("globalCalendars", []):
            gc_id = global_calendar.get("id", "")
            gc_color = global_calendar.get("color", "#555555")
            if not gc_id:
                continue
            for event in global_cal_cache.get_allday(gc_id):
                all_day_events.append(
                    {
                        "title": event["title"],
                        "start": event["start"],
                        "end": event["end"],
                        "color": gc_color,
                    }
                )

        response = jsonify(
            {
                "events": all_events,
                "allDayEvents": all_day_events,
                "fetched_at": meta["fetched_at"],
                "error": meta["error"],
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/api/dashboard-data")
    def api_dashboard_data():
        settings = load_settings()
        rooms = load_rooms()
        room_ids = [rid for rid in settings.get("dashboardRooms", []) if rid in rooms]
        return jsonify({"rooms": [room_status(rid) for rid in room_ids]})

    @app.route("/api/slides")
    def api_slides():
        force = request.args.get("refresh") == "1"
        return jsonify({"links": get_slides(force=force)})

    @app.route("/api/slides/debug")
    def api_slides_debug():
        local_items = local_slide_items(active_only=False)
        active_local_items = local_slide_items(active_only=True)
        return jsonify(
            {
                "localMediaCount": len(local_items),
                "activeLocalMediaCount": len(active_local_items),
                "localMediaEnabled": bool(active_local_items),
                "sample": [item.get("originalName") for item in active_local_items[:5]],
            }
        )

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

    @app.route("/api/checkin", methods=["POST"])
    def api_checkin():
        data = request.get_json(silent=True) or {}
        client_id = data.get("client_id", "")
        hostname = data.get("hostname", request.remote_addr)
        role = data.get("role", "display")

        if not client_id:
            return jsonify({"ok": False, "error": "missing client_id"}), 400

        existing = clients.get(client_id, {})
        clients[client_id] = _ensure_client_defaults(
            existing,
            hostname=hostname,
            ip=data.get("ip", request.remote_addr),
            role=role,
        )
        save_clients(clients)
        return jsonify({"ok": True})

    @app.route("/api/client-config/<client_id>")
    def api_client_config(client_id):
        hostname = request.args.get("hostname", "unknown")
        ip = request.remote_addr

        if client_id not in clients:
            clients[client_id] = _ensure_client_defaults({}, hostname=hostname, ip=ip)
            save_clients(clients)
        else:
            clients[client_id] = _ensure_client_defaults(clients[client_id], hostname=hostname, ip=ip)
            save_clients(clients)

        config = clients[client_id]
        rid = config.get("assigned_room", "")
        rooms = load_rooms()
        settings = load_settings()

        if rid == "__dashboard__":
            display_url = "/dashboard"
            display_role = "dashboard"
        elif rid and rid in rooms:
            display_url = f"/display?room={rid}"
            display_role = "display"
        else:
            display_url = ""
            display_role = "unassigned"

        return jsonify(
            {
                "client_id": client_id,
                "display_url": display_url,
                "display_role": display_role,
                "assigned_room": rid,
                "screenOn": config.get("screenOn", "08:00"),
                "screenOff": config.get("screenOff", "22:00"),
                "scheduleEnabled": config.get("scheduleEnabled", False),
                "server_url": settings.get("serverUrl", ""),
                "pending_command": config.get("pending_command"),
            }
        )

    @app.route("/admin/clients")
    @require_admin
    def admin_clients_list():
        now = time.time()
        out = []
        for client_id, client in sorted(clients.items(), key=lambda item: item[1].get("hostname", "")):
            client = clients[client_id] = _ensure_client_defaults(
                client,
                hostname=client.get("hostname", client_id[:8]),
                ip=client.get("ip", ""),
                role=client.get("role", "display"),
            )
            rid = client.get("assigned_room", "")
            out.append(
                {
                    "client_id": client_id,
                    "hostname": client.get("hostname", client_id[:8]),
                    "ip": client.get("ip", ""),
                    "online": (now - client.get("last_seen", 0)) < 90,
                    "assigned_room": rid,
                    "screenOn": client.get("screenOn", "08:00"),
                    "screenOff": client.get("screenOff", "22:00"),
                    "scheduleEnabled": client.get("scheduleEnabled", False),
                    "pending_command": client.get("pending_command"),
                }
            )
        return jsonify(out)

    @app.route("/admin/client/<client_id>/assign", methods=["POST"])
    @require_admin
    def admin_client_assign(client_id):
        data = request.get_json(force=True, silent=True) or {}
        if client_id not in clients:
            return jsonify({"error": "Unknown client"}), 404
        clients[client_id]["assigned_room"] = data.get("assigned_room", "")
        clients[client_id]["screenOn"] = data.get("screenOn", "08:00")
        clients[client_id]["screenOff"] = data.get("screenOff", "22:00")
        clients[client_id]["scheduleEnabled"] = bool(data.get("scheduleEnabled", False))
        save_clients(clients)
        return jsonify({"ok": True})

    @app.route("/admin/client/<client_id>/delete", methods=["POST"])
    @require_admin
    def admin_client_delete(client_id):
        clients.pop(client_id, None)
        save_clients(clients)
        return jsonify({"ok": True})

    @app.route("/admin/client/<client_id>/command", methods=["POST"])
    @require_admin
    def admin_client_command(client_id):
        data = request.get_json(force=True, silent=True) or {}
        if client_id not in clients:
            return jsonify({"error": "Unknown client"}), 404
        command = str(data.get("command", "")).strip()
        if command not in SUPPORTED_CLIENT_COMMANDS:
            return jsonify({"error": "Unsupported command"}), 400
        clients[client_id]["pending_command"] = {
            "id": str(uuid.uuid4()),
            "command": command,
            "created_at": time.time(),
            "status": "pending",
        }
        save_clients(clients)
        return jsonify({"ok": True, "pending_command": clients[client_id]["pending_command"]})

    @app.route("/api/client-command/<client_id>/ack", methods=["POST"])
    def api_client_command_ack(client_id):
        data = request.get_json(silent=True) or {}
        client = clients.get(client_id)
        if not client:
            return jsonify({"ok": False, "error": "Unknown client"}), 404
        pending = _normalized_pending_command(client.get("pending_command"))
        if not pending:
            return jsonify({"ok": False, "error": "No pending command"}), 404
        if str(data.get("command_id", "")).strip() != pending.get("id", ""):
            return jsonify({"ok": False, "error": "Command mismatch"}), 409
        client["pending_command"] = None
        client["last_command_id"] = pending["id"]
        client["last_command_completed_at"] = time.time()
        save_clients(clients)
        return jsonify({"ok": True})

    @app.route("/static/logo/<rid>")
    def serve_logo(rid):
        path = logo_path(rid)
        if not path.exists():
            return "", 404
        return app.response_class(
            path.read_bytes(),
            mimetype="image/png",
            headers={"Cache-Control": "no-cache"},
        )

    @app.route("/display")
    def display():
        rid = request.args.get("room", "")
        rooms = load_rooms()
        if not rid or rid not in rooms:
            return render_template("room_not_found.html", rooms=rooms, room_id=rid)
        room = public_room_config(rid, rooms, load_settings())
        response = make_response(
            render_template(
                "display.html",
                room=room,
                server_url=request.host_url.rstrip("/"),
            )
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    @app.route("/slide")
    def slide_view():
        rid = request.args.get("room", "")
        rooms = load_rooms()
        settings = load_settings()
        if rid and rid not in rooms:
            return redirect(f"/display?room={rid}")
        room = {
            "roomId": rid if rid in rooms else "",
            "calDuration": settings.get("calDuration", 60),
            "slideDuration": settings.get("slideDuration", 8),
        }
        return render_template("slide.html", room=room, server_url=request.host_url.rstrip("/"))

    @app.route("/dashboard")
    def dashboard():
        settings = load_settings()
        rooms = load_rooms()
        selected = [(rid, rooms[rid]) for rid in settings.get("dashboardRooms", []) if rid in rooms]
        return render_template(
            "dashboard.html",
            rooms=selected,
            iframe_url=settings.get("dashboardIframeUrl", ""),
            cal_duration=settings.get("dashboardCalDuration", 60),
            slide_duration=settings.get("dashboardSlideDuration", 8),
            server_url=request.host_url.rstrip("/"),
            all_rooms=rooms,
        )

    @app.route("/api/proxy-ical")
    def proxy_ical():
        url = validated_proxy_ical_url(request.args.get("url", ""))
        if not url:
            return Response("Invalid iCal URL", status=400)
        try:
            proxy_request = urllib.request.Request(url, headers={"User-Agent": "ProparedDisplay/1.0"})
            with urllib.request.urlopen(proxy_request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="replace")
            return Response(body, mimetype="text/calendar", headers={"Access-Control-Allow-Origin": "*"})
        except Exception as exc:
            return str(exc), 502

    @app.route("/admin/settings", methods=["POST"])
    @require_admin
    def admin_settings():
        settings = load_settings()
        settings["calDuration"] = to_int(request.form.get("calDuration"), settings["calDuration"], minimum=5, maximum=3600)
        settings["slideDuration"] = to_int(request.form.get("slideDuration"), settings["slideDuration"], minimum=1, maximum=3600)
        save_settings(settings)
        return redirect("/admin")

    @app.route("/admin/dashboard", methods=["POST"])
    @require_admin
    def admin_dashboard_save():
        settings = load_settings()
        settings["dashboardIframeUrl"] = request.form.get("dashboardIframeUrl", "").strip()
        settings["dashboardRooms"] = request.form.getlist("dashboardRooms")
        settings["dashboardCalDuration"] = to_int(request.form.get("dashboardCalDuration"), 60, minimum=5, maximum=3600)
        settings["dashboardSlideDuration"] = to_int(request.form.get("dashboardSlideDuration"), 8, minimum=1, maximum=3600)
        save_settings(settings)
        return redirect("/admin")

    @app.route("/admin/global-calendars", methods=["POST"])
    @require_admin
    def admin_global_calendars():
        data = request.get_json(force=True, silent=True) or {}
        calendars = data.get("globalCalendars", [])
        clean = []
        for calendar in calendars:
            gid = calendar.get("id", "").strip()
            url = calendar.get("url", "").strip()
            if gid and url:
                clean.append(
                    {
                        "id": gid,
                        "name": calendar.get("name", "").strip(),
                        "url": url,
                        "color": calendar.get("color", "#555555").strip(),
                    }
                )
        settings = load_settings()
        settings["globalCalendars"] = clean
        save_settings(settings)
        sync_global_calendar_cache(clean)
        return jsonify({"ok": True})

    @app.route("/admin/room/new", methods=["POST"])
    @require_admin
    def admin_room_new():
        rooms = load_rooms()
        rid = str(uuid.uuid4())[:8]
        ical_url = request.form.get("icalUrl", "").strip()
        rooms[rid] = {
            "title": request.form.get("title", "New Room"),
            "icalUrl": ical_url,
            "refresh": to_int(request.form.get("refresh"), 5, minimum=1, maximum=1440),
            "showSlideshow": request.form.get("showSlideshow") == "1",
            "startHour": to_int(request.form.get("startHour"), 8, minimum=0, maximum=23),
            "endHour": to_int(request.form.get("endHour"), 22, minimum=0, maximum=23),
            "createdAt": time.time(),
        }
        save_rooms(rooms)
        upload = request.files.get("logo")
        if upload and upload.filename:
            upload.save(str(logo_path(rid)))
        if ical_url:
            ical_cache.schedule(rid, ical_url, rooms[rid]["refresh"])
        return redirect("/admin")

    @app.route("/admin/room/<rid>/edit", methods=["POST"])
    @require_admin
    def admin_room_edit(rid):
        rooms = load_rooms()
        if rid not in rooms:
            return redirect("/admin")
        room = rooms[rid]
        room["title"] = request.form.get("title", room.get("title", ""))
        room["icalUrl"] = request.form.get("icalUrl", room.get("icalUrl", "")).strip()
        room["refresh"] = to_int(request.form.get("refresh"), room.get("refresh", 5), minimum=1, maximum=1440)
        room["showSlideshow"] = request.form.get("showSlideshow") == "1"
        room["startHour"] = to_int(request.form.get("startHour"), room.get("startHour", 8), minimum=0, maximum=23)
        room["endHour"] = to_int(request.form.get("endHour"), room.get("endHour", 22), minimum=0, maximum=23)
        save_rooms(rooms)
        upload = request.files.get("logo")
        if upload and upload.filename:
            upload.save(str(logo_path(rid)))
        if request.form.get("removeLogo") == "1":
            path = logo_path(rid)
            if path.exists():
                path.unlink()
        ical_cache.schedule(rid, room["icalUrl"], room["refresh"])
        return redirect("/admin")

    @app.route("/admin/room/<rid>/delete", methods=["POST"])
    @require_admin
    def admin_room_delete(rid):
        rooms = load_rooms()
        if rid in rooms:
            del rooms[rid]
        save_rooms(rooms)
        ical_cache.remove(rid)
        path = logo_path(rid)
        if path.exists():
            path.unlink()
        return redirect("/admin")
