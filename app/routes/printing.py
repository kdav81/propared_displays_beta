from __future__ import annotations

import uuid

from flask import Response, jsonify, render_template, request

from app.storage import (
    load_location_rules,
    load_print_shows,
    load_rooms,
    load_tags,
    save_location_rules,
    save_print_shows,
)


FEED_TYPE_CHOICES = {"full", "performer", "crew", "public", "custom"}


def _normalize_feed(feed: dict, index: int) -> dict | None:
    if not isinstance(feed, dict):
        return None
    url = str(feed.get("url", "")).strip()
    if not url:
        return None
    feed_type = str(feed.get("type", "")).strip().lower() or "custom"
    if feed_type not in FEED_TYPE_CHOICES:
        feed_type = "custom"
    label = str(feed.get("label", "")).strip()
    return {
        "id": str(feed.get("id", "")).strip() or f"{feed_type}-{index + 1}",
        "type": feed_type,
        "label": label,
        "url": url,
        "enabled": bool(feed.get("enabled", True)),
    }


def _normalize_show(show: dict) -> dict:
    if not isinstance(show, dict):
        show = {}
    raw_feeds = show.get("feeds", [])
    if not isinstance(raw_feeds, list):
        raw_feeds = []
    feeds = []
    for index, feed in enumerate(raw_feeds):
        normalized = _normalize_feed(feed, index)
        if normalized:
            feeds.append(normalized)
    return {
        "title": str(show.get("title", "")).strip(),
        "shortTitle": str(show.get("shortTitle", "")).strip(),
        "season": str(show.get("season", "")).strip(),
        "shortTag": str(show.get("shortTag", "")).strip(),
        "feeds": feeds,
    }


def _normalized_show_map(shows: dict) -> dict:
    return {show_id: _normalize_show(show) for show_id, show in shows.items()}


def register_printing_routes(
    app,
    *,
    pdf_available,
    build_calendar_pdf,
    build_weekly_pdf,
    build_room_calendar_pdf,
    to_int,
    log,
) -> None:
    @app.route("/print-calendar")
    def print_calendar():
        return render_template("print_calendar.html")

    @app.route("/print-admin")
    def print_admin():
        return render_template("print_admin.html")

    @app.route("/api/print-shows", methods=["GET"])
    def api_print_shows_get():
        return jsonify(_normalized_show_map(load_print_shows()))

    @app.route("/api/print-shows", methods=["POST"])
    def api_print_shows_post():
        data = request.get_json(force=True, silent=True) or {}
        shows = load_print_shows()
        new_id = str(uuid.uuid4())[:8]
        shows[new_id] = _normalize_show(data)
        save_print_shows(shows)
        return jsonify({"id": new_id})

    @app.route("/api/print-shows/<show_id>", methods=["PUT"])
    def api_print_shows_put(show_id):
        data = request.get_json(force=True, silent=True) or {}
        shows = load_print_shows()
        if show_id not in shows:
            return Response("Not found", status=404)
        shows[show_id] = _normalize_show(data)
        save_print_shows(shows)
        return jsonify({"id": show_id})

    @app.route("/api/print-shows/<show_id>", methods=["DELETE"])
    def api_print_shows_delete(show_id):
        shows = load_print_shows()
        shows.pop(show_id, None)
        save_print_shows(shows)
        return jsonify({"ok": True})

    @app.route("/api/location-rules", methods=["GET"])
    def api_location_rules_get():
        return jsonify(load_location_rules())

    @app.route("/api/location-rules", methods=["POST"])
    def api_location_rules_post():
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, list):
            return Response("Expected a JSON array", status=400)
        clean = [
            {
                "keywords": str(rule.get("keywords", "")).strip(),
                "replacement": str(rule.get("replacement", "")).strip(),
            }
            for rule in data
            if rule.get("keywords") and rule.get("replacement")
        ]
        save_location_rules(clean)
        return jsonify({"ok": True, "count": len(clean)})

    @app.route("/api/generate-calendar-pdf", methods=["POST"])
    def api_generate_calendar_pdf():
        if not pdf_available:
            return Response(
                "ReportLab not installed. Run: ~/propared-display/venv/bin/pip install reportlab",
                status=500,
            )
        data = request.get_json(force=True, silent=True) or {}
        cal_type = data.get("calType", "monthly")
        cal_source = data.get("calSource", "productions")
        updated_by = data.get("updatedBy", "").strip()
        cal_subtitle = data.get("calSubtitle", "").strip()
        custom_notes = data.get("customNotes", {})
        tag_colors = load_tags()
        location_rules = load_location_rules() if data.get("applyLocationRules", True) else []

        try:
            if cal_source == "rooms":
                room_ids = data.get("roomIds", [])
                rooms = load_rooms()
                subtitle = cal_subtitle or "Room Schedule"

                if cal_type == "weekly":
                    fake_shows: dict = {}
                    for rid in room_ids:
                        room = rooms.get(rid, {})
                        url = room.get("icalUrl", "").replace("webcal://", "https://").replace("webcal:", "https:")
                        fake_shows[rid] = {
                            "title": room.get("title", rid),
                            "season": "",
                            "shortTag": "",
                            "feeds": [{"url": url, "label": room.get("title", rid)}],
                        }
                    pdf_bytes = build_weekly_pdf(
                        show_ids=room_ids,
                        shows=fake_shows,
                        tag_colors=tag_colors,
                        location_rules=location_rules,
                        start_date=data.get("startDate", ""),
                        end_date=data.get("endDate", ""),
                        updated_by=updated_by,
                        cal_subtitle=subtitle,
                        custom_notes=custom_notes,
                        multi_show=len(room_ids) > 1,
                        preserve_tags=True,
                    )
                else:
                    pdf_bytes = build_room_calendar_pdf(
                        room_ids=room_ids,
                        rooms=rooms,
                        tag_colors=tag_colors,
                        location_rules=location_rules,
                        start_month=to_int(data.get("startMonth"), 0, minimum=0, maximum=12),
                        start_year=to_int(data.get("startYear"), 2026, minimum=2000, maximum=2100),
                        end_month=to_int(data.get("endMonth"), 0, minimum=0, maximum=12),
                        end_year=to_int(data.get("endYear"), 2026, minimum=2000, maximum=2100),
                        updated_by=updated_by,
                        cal_subtitle=subtitle,
                        custom_notes=custom_notes,
                    )
            else:
                show_ids = data.get("showIds", [])
                multi_show = bool(data.get("multiShow", len(show_ids) > 1))
                shows = _normalized_show_map(load_print_shows())
                subtitle = cal_subtitle or "Rehearsal Performance Calendar"

                if cal_type == "weekly":
                    pdf_bytes = build_weekly_pdf(
                        show_ids=show_ids,
                        shows=shows,
                        tag_colors=tag_colors,
                        location_rules=location_rules,
                        start_date=data.get("startDate", ""),
                        end_date=data.get("endDate", ""),
                        updated_by=updated_by,
                        cal_subtitle=subtitle,
                        custom_notes=custom_notes,
                        multi_show=multi_show,
                    )
                else:
                    pdf_bytes = build_calendar_pdf(
                        show_ids=show_ids,
                        shows=shows,
                        tag_colors=tag_colors,
                        location_rules=location_rules,
                        start_month=to_int(data.get("startMonth"), 0, minimum=0, maximum=12),
                        start_year=to_int(data.get("startYear"), 2026, minimum=2000, maximum=2100),
                        end_month=to_int(data.get("endMonth"), 0, minimum=0, maximum=12),
                        end_year=to_int(data.get("endYear"), 2026, minimum=2000, maximum=2100),
                        updated_by=updated_by,
                        cal_subtitle=subtitle,
                        custom_notes=custom_notes,
                        multi_show=multi_show,
                    )

            return Response(
                pdf_bytes,
                mimetype="application/pdf",
                headers={
                    "Content-Disposition": "attachment; filename=calendar.pdf",
                    "Content-Length": str(len(pdf_bytes)),
                },
            )
        except Exception as exc:
            log.error("PDF generation failed: %s", exc)
            return Response(f"PDF generation failed: {exc}", status=500)
