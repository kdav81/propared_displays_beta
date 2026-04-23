from __future__ import annotations

from datetime import datetime

from flask import Response, jsonify, redirect, render_template, request

from app.config import NOTICE_PASSWORD_FILE
from app.storage import (
    check_password,
    load_notice,
    read_password_hash,
    save_notice,
    write_password,
)


def register_notice_routes(app) -> None:
    @app.route("/api/notice")
    def api_notice():
        notice = load_notice()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not notice.get("active"):
            return jsonify({"active": False})
        start = notice.get("startTime", "")
        end = notice.get("endTime", "")
        if (not start or now >= start) and (not end or now <= end):
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
        notice = load_notice()

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
                notice["message"] = request.form.get("message", "").strip()
                notice["startTime"] = request.form.get("startTime", "").strip()
                notice["endTime"] = request.form.get("endTime", "").strip()
                notice["active"] = request.form.get("active") == "1"
                save_notice(notice)
                msg = "Notice saved."
            elif action == "clear":
                notice = {"active": False, "message": "", "startTime": "", "endTime": "", "version": 0}
                save_notice(notice)
                msg = "Notice cleared."
        else:
            auth = request.authorization
            if not setup_needed and (not auth or not check_password(auth.password, NOTICE_PASSWORD_FILE)):
                return Response(
                    "Notice access required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Notice Board"'},
                )

        return render_template("notice.html", n=notice, msg=msg, setup_needed=setup_needed)
