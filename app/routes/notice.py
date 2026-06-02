from __future__ import annotations

from datetime import datetime

from flask import Response, jsonify, redirect, render_template, request

from app.config import NOTICE_PASSWORD_FILE
from app.storage import (
    check_password,
    empty_notice,
    load_notice,
    load_rooms,
    read_password_hash,
    save_notice,
    write_password,
)


def _active_notice(notice: dict, now: str) -> dict | None:
    if not notice.get("active") or not notice.get("message", "").strip():
        return None
    start = notice.get("startTime", "")
    end = notice.get("endTime", "")
    if (not start or now >= start) and (not end or now <= end):
        return notice
    return None


def register_notice_routes(app) -> None:
    @app.route("/api/notice")
    def api_notice():
        notices = load_notice()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        room_id = request.args.get("room", "").strip()
        notice = _active_notice(notices["global"], now)
        if not notice and room_id:
            notice = _active_notice(notices["rooms"].get(room_id, {}), now)
        if notice:
            return jsonify(
                {
                    "active": True,
                    "message": notice.get("message", ""),
                    "version": notice.get("version", 0),
                }
            )
        return jsonify({"active": False})

    @app.route("/notice", methods=["GET", "POST"])
    def notice_page():
        setup_needed = not read_password_hash(NOTICE_PASSWORD_FILE)
        msg = ""
        notices = load_notice()
        rooms = load_rooms()
        selected = request.values.get("scope", "global").strip()
        if selected != "global" and selected not in rooms:
            selected = "global"

        if request.method == "POST":
            action = request.form.get("action")

            if action == "set_password":
                pw = request.form.get("password", "").strip()
                if pw:
                    write_password(NOTICE_PASSWORD_FILE, pw)
                return redirect("/notice")

            auth = request.authorization
            if not auth or not check_password(auth.password, NOTICE_PASSWORD_FILE):
                return Response(
                    "Notice access required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Notice Board"'},
                )
            if action == "save":
                notice = notices["global"] if selected == "global" else notices["rooms"].get(selected, empty_notice())
                notice["message"] = request.form.get("message", "").strip()
                notice["startTime"] = request.form.get("startTime", "").strip()
                notice["endTime"] = request.form.get("endTime", "").strip()
                notice["active"] = request.form.get("active") == "1"
                notice["version"] = int(notice.get("version", 0)) + 1
                if selected == "global":
                    notices["global"] = notice
                else:
                    notices["rooms"][selected] = notice
                save_notice(notices)
                msg = "Notice saved."
            elif action == "clear":
                if selected == "global":
                    notices["global"] = empty_notice()
                else:
                    notices["rooms"].pop(selected, None)
                save_notice(notices)
                msg = "Notice cleared."
        else:
            auth = request.authorization
            if not setup_needed and (not auth or not check_password(auth.password, NOTICE_PASSWORD_FILE)):
                return Response(
                    "Notice access required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Notice Board"'},
                )

        notice = notices["global"] if selected == "global" else notices["rooms"].get(selected, empty_notice())
        return render_template(
            "notice.html",
            n=notice,
            msg=msg,
            rooms=rooms,
            selected=selected,
            setup_needed=setup_needed,
        )
