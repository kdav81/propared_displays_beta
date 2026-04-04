from __future__ import annotations

from datetime import datetime
from pathlib import Path
import urllib.parse

from flask import Response, jsonify, redirect, render_template, request, send_file

from app.auth import require_admin
from app.config import BACKUP_DIR, NOTICE_PASSWORD_FILE, PASSWORD_FILE
from app.services.backup import make_backup_zip, restore_backup_archive
from app.services.media_library import site_logo_url
from app.storage import (
    check_password,
    load_rooms,
    load_settings,
    load_tags,
    read_password_hash,
    write_password,
)


def register_admin_misc_routes(app, *, ical_cache, sync_global_calendar_cache, to_int, log) -> None:
    @app.route("/")
    def home():
        return render_template("home.html", site_logo_url=site_logo_url())

    @app.route("/admin/setup", methods=["GET", "POST"])
    def admin_setup():
        if read_password_hash(PASSWORD_FILE):
            return redirect("/admin")
        error = None
        if request.method == "POST":
            pw = request.form.get("password", "").strip()
            pw2 = request.form.get("password2", "").strip()
            if len(pw) < 6:
                error = "Password must be at least 6 characters."
            elif pw != pw2:
                error = "Passwords do not match."
            else:
                write_password(PASSWORD_FILE, pw)
                return redirect("/admin")
        return render_template("admin_setup.html", error=error)

    @app.route("/admin")
    @require_admin
    def admin():
        return render_template(
            "admin.html",
            rooms=load_rooms(),
            tag_colors=load_tags(),
            settings=load_settings(),
        )

    @app.route("/admin/backup")
    @require_admin
    def admin_backup():
        buf = make_backup_zip(list(load_rooms().keys()))
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"propared-backup-{ts}.zip"
        (BACKUP_DIR / filename).write_bytes(buf.read())
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/zip")

    @app.route("/admin/backup/list")
    @require_admin
    def admin_backup_list():
        backups = []
        if BACKUP_DIR.is_dir():
            for fp in sorted(BACKUP_DIR.glob("*.zip"), reverse=True):
                backups.append({"name": fp.name, "size": fp.stat().st_size, "mtime": fp.stat().st_mtime})
        return jsonify(backups)

    @app.route("/admin/backup/download/<filename>")
    @require_admin
    def admin_backup_download(filename):
        fp = BACKUP_DIR / Path(filename).name
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
            restore_backup_archive(f.read())
            restored_rooms = load_rooms()
            restored_settings = load_settings()
            for rid in list(ical_cache._data):
                if rid not in restored_rooms:
                    ical_cache.remove(rid)
            for rid, room in restored_rooms.items():
                url = room.get("icalUrl", "").strip()
                if url:
                    ical_cache.schedule(rid, url, to_int(room.get("refresh"), 5, minimum=1, maximum=1440))
            sync_global_calendar_cache(restored_settings.get("globalCalendars", []))
            return redirect("/admin?restored=1")
        except Exception as exc:
            log.error("Restore failed: %s", exc)
            return redirect("/admin?restore_error=" + urllib.parse.quote(str(exc)))
