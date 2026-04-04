from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from flask import Response, jsonify, redirect, render_template, request
from werkzeug.utils import secure_filename

from app.auth import require_shared_media_auth
from app.config import IMAGE_EXTS, MEDIA_DIR, NOTICE_PASSWORD_FILE, SITE_LOGO_STEM, STATIC_DIR
from app.services.media_library import (
    local_slide_items,
    media_public_url,
    parse_optional_date,
    site_logo_path,
    site_logo_url,
)
from app.storage import (
    check_password,
    load_media_library,
    load_settings,
    read_password_hash,
    save_media_library,
    write_password,
)


def register_media_routes(app) -> None:
    def _delete_site_logo() -> None:
        for ext in IMAGE_EXTS:
            candidate = STATIC_DIR / f"{SITE_LOGO_STEM}{ext}"
            if candidate.exists():
                candidate.unlink()

    def _save_site_logo(upload):
        original_name = Path(upload.filename).name
        ext = Path(original_name).suffix.lower()
        if ext not in IMAGE_EXTS:
            return "Unsupported image type"
        _delete_site_logo()
        upload.save(STATIC_DIR / f"{SITE_LOGO_STEM}{ext}")
        return None

    @app.route("/api/media")
    @require_shared_media_auth
    def api_media_list():
        return jsonify(local_slide_items(active_only=False))

    @app.route("/api/media/upload", methods=["POST"])
    @require_shared_media_auth
    def api_media_upload():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return Response("No file uploaded", status=400)

        original_name = Path(upload.filename).name
        ext = Path(original_name).suffix.lower()
        if ext not in IMAGE_EXTS:
            return Response("Unsupported image type", status=400)

        safe_name = secure_filename(Path(original_name).stem) or "slide"
        filename = f"{uuid.uuid4().hex[:12]}-{safe_name}{ext}"
        dest = MEDIA_DIR / filename
        start_date = request.form.get("startDate", "").strip()
        end_date = request.form.get("endDate", "").strip()
        start_dt = parse_optional_date(start_date)
        end_dt = parse_optional_date(end_date)
        if start_date and start_dt is None:
            return Response("Invalid start date", status=400)
        if end_date and end_dt is None:
            return Response("Invalid end date", status=400)
        if start_dt and end_dt and end_dt < start_dt:
            return Response("End date cannot be earlier than start date", status=400)

        upload.save(dest)

        items = load_media_library()
        item = {
            "id": uuid.uuid4().hex[:12],
            "filename": filename,
            "title": request.form.get("title", "").strip() or Path(original_name).stem,
            "originalName": original_name,
            "startDate": start_date,
            "endDate": end_date,
            "active": request.form.get("active", "1") != "0",
            "uploadedAt": datetime.now().isoformat(),
        }
        items.append(item)
        save_media_library(items)
        return jsonify({"ok": True, "item": dict(item, url=media_public_url(filename))})

    @app.route("/api/media/<media_id>", methods=["PUT", "POST"])
    @require_shared_media_auth
    def api_media_update(media_id):
        data = request.get_json(force=True, silent=True) or {}
        items = load_media_library()
        for item in items:
            if item["id"] != media_id:
                continue
            start_date = str(data.get("startDate", item.get("startDate", ""))).strip()
            end_date = str(data.get("endDate", item.get("endDate", ""))).strip()
            start_dt = parse_optional_date(start_date)
            end_dt = parse_optional_date(end_date)
            if start_date and start_dt is None:
                return Response("Invalid start date", status=400)
            if end_date and end_dt is None:
                return Response("Invalid end date", status=400)
            if start_dt and end_dt and end_dt < start_dt:
                return Response("End date cannot be earlier than start date", status=400)
            item["title"] = str(data.get("title", item.get("title", ""))).strip()
            item["startDate"] = start_date
            item["endDate"] = end_date
            item["active"] = bool(data.get("active", item.get("active", True)))
            save_media_library(items)
            return jsonify({"ok": True})
        return Response("Not found", status=404)

    @app.route("/api/media/<media_id>", methods=["DELETE"])
    @require_shared_media_auth
    def api_media_delete(media_id):
        items = load_media_library()
        kept = []
        deleted = None
        for item in items:
            if item["id"] == media_id and deleted is None:
                deleted = item
                continue
            kept.append(item)
        if deleted is None:
            return Response("Not found", status=404)
        path = MEDIA_DIR / deleted["filename"]
        if path.exists():
            path.unlink()
        save_media_library(kept)
        return jsonify({"ok": True})

    @app.route("/media-admin", methods=["GET", "POST"])
    def media_admin():
        setup_needed = not read_password_hash(NOTICE_PASSWORD_FILE)
        if request.method == "POST" and setup_needed:
            if request.form.get("action") == "set_password":
                pw = request.form.get("password", "").strip()
                if pw:
                    write_password(NOTICE_PASSWORD_FILE, pw)
                return redirect("/media-admin")
        elif not setup_needed:
            auth = request.authorization
            if not auth or not check_password(auth.password, NOTICE_PASSWORD_FILE):
                return Response(
                    "Shared media access required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Notice Board"'},
                )
            action = request.form.get("action")
            if action == "upload_site_logo":
                upload = request.files.get("siteLogo")
                if not upload or not upload.filename:
                    return redirect("/media-admin?site_logo_error=Please+choose+an+image")
                error = _save_site_logo(upload)
                if error:
                    return redirect("/media-admin?site_logo_error=" + error.replace(" ", "+"))
                return redirect("/media-admin?site_logo_updated=1")
            if action == "delete_site_logo":
                _delete_site_logo()
                return redirect("/media-admin?site_logo_deleted=1")
        return render_template(
            "media_admin.html",
            settings=load_settings(),
            setup_needed=setup_needed,
            site_logo_url=site_logo_url(),
        )
