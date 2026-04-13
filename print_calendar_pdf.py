"""
print_calendar_pdf.py
=====================
Server-side PDF calendar generator using ReportLab Platypus.
Drop this file next to server.py and import the route function.

Install: pip install reportlab --break-system-packages
"""

import io
import re
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Table, TableStyle, Paragraph, Spacer, KeepTogether, Flowable,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = landscape(letter)   # 792 x 612 pts
MARGIN_TB = 18                        # top/bottom margin pts
MARGIN_LR = 22                        # left/right margin pts
CONTENT_W = PAGE_W - 2 * MARGIN_LR
CONTENT_H = PAGE_H - 2 * MARGIN_TB

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
C_BLACK      = colors.HexColor("#000000")
C_GRID       = colors.HexColor("#aaaaaa")
C_DOW_BG     = colors.HexColor("#222222")
C_DOW_FG     = colors.white
C_OUT_MONTH  = colors.HexColor("#f5f5f5")
C_TODAY_BG   = colors.HexColor("#c0392b")
C_TODAY_FG   = colors.white
C_EVT_TIME   = colors.HexColor("#000000")
C_EVT_LOC    = colors.HexColor("#444444")
C_NOTE       = colors.HexColor("#555555")
C_FOOTER     = colors.HexColor("#888888")
C_LEGEND     = colors.HexColor("#333333")
C_HEADER_SEP = colors.HexColor("#000000")

# ---------------------------------------------------------------------------
# Fonts — uses built-in Helvetica family (no install needed)
# ---------------------------------------------------------------------------
FONT_REGULAR = "Helvetica"
FONT_BOLD    = "Helvetica-Bold"
FONT_ITALIC  = "Helvetica-Oblique"
FONT_BOLDITALIC = "Helvetica-BoldOblique"

FEED_TYPE_PRIORITY = {
    "full": 50,
    "performer": 40,
    "crew": 30,
    "public": 20,
    "custom": 10,
}

# ---------------------------------------------------------------------------
# iCal fetching
# ---------------------------------------------------------------------------
def _fetch_ical(url: str) -> str:
    url = url.replace("webcal://", "https://").replace("webcal:", "https:")
    req = urllib.request.Request(url, headers={"User-Agent": "ProparedDisplay/4.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_dt(line: str):
    """Parse a DTSTART/DTEND line. Returns (datetime|date, is_allday)."""
    colon = line.index(":")
    val = line[colon + 1:].strip()
    if "T" not in val:
        try:
            return date(int(val[0:4]), int(val[4:6]), int(val[6:8])), True
        except Exception:
            return None, True
    try:
        yr, mo, dy = int(val[0:4]), int(val[4:6]), int(val[6:8])
        hr, mn, sc = int(val[9:11]), int(val[11:13]), int(val[13:15]) if len(val) > 13 else 0
        utc = val.endswith("Z")
        return datetime(yr, mo, dy, hr, mn, sc, tzinfo=timezone.utc if utc else None), False
    except Exception:
        return None, False


def parse_ical_for_print(text: str) -> list[dict]:
    """
    Parse iCal into event dicts:
      {title, start, end, allday, location}
    All-day events have date objects; timed events have datetime objects.
    """
    events = []
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

        start, allday = _parse_dt(props["DTSTART"])
        if start is None:
            continue

        end = None
        if "DTEND" in props:
            end, _ = _parse_dt(props["DTEND"])

        # For all-day: iCal DTEND is exclusive — back off one day
        if allday and end and isinstance(end, date) and not isinstance(end, datetime):
            end = end - timedelta(days=1)

        raw_title = props["SUMMARY"].split(":", 1)[1].strip()
        title = (raw_title
                 .replace("\\,", ",").replace("\\n", " ")
                 .replace("\\;", ";").replace("\\:", ":"))

        raw_loc = props.get("LOCATION", "")
        location = ""
        if raw_loc and ":" in raw_loc:
            location = raw_loc.split(":", 1)[1].strip().replace("\\,", ",")

        events.append({
            "title":    title,
            "start":    start,
            "end":      end or start,
            "allday":   allday,
            "location": location,
        })
    return events


def normalize_show_feeds(show: dict) -> list[dict]:
    feeds = show.get("feeds", []) if isinstance(show, dict) else []
    if not isinstance(feeds, list):
        return []
    normalized = []
    for index, feed in enumerate(feeds):
        if not isinstance(feed, dict):
            continue
        url = str(feed.get("url", "")).strip()
        if not url:
            continue
        feed_type = str(feed.get("type", "")).strip().lower() or "custom"
        if feed_type not in FEED_TYPE_PRIORITY:
            feed_type = "custom"
        normalized.append(
            {
                "id": str(feed.get("id", "")).strip() or f"{feed_type}-{index + 1}",
                "type": feed_type,
                "label": str(feed.get("label", "")).strip(),
                "url": url,
                "enabled": bool(feed.get("enabled", True)),
            }
        )
    return normalized


# ---------------------------------------------------------------------------
# Title / location cleaning (mirrors JS logic)
# ---------------------------------------------------------------------------
def clean_title(title: str) -> str:
    tags = re.findall(r'\[([^\]]+)\]', title)
    if not tags:
        return title
    unique = list(dict.fromkeys(t.strip() for t in tags))
    if len(unique) <= 1:
        return re.sub(r'\s*\[[^\]]+\]', '', title).strip()
    return title


def get_tag(title: str) -> str | None:
    m = re.search(r'\[([^\]]+)\]', title)
    return m.group(1).strip() if m else None


def clean_location(loc: str, rules: list[dict]) -> str:
    # Strip parentheticals
    cleaned = re.sub(r'\s*\([^)]*\)', '', loc).strip()
    # Apply location rules
    for rule in rules:
        keywords = [k.strip().lower() for k in rule.get("keywords", "").split(",") if k.strip()]
        if not keywords:
            continue
        if any(kw in cleaned.lower() for kw in keywords):
            return rule.get("replacement", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Calendar grid helpers
# ---------------------------------------------------------------------------
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

def _date_key(d) -> str:
    if isinstance(d, datetime):
        d = d.date() if hasattr(d, 'date') else d
        if isinstance(d, datetime):
            d = d.replace(tzinfo=None).date() if d.tzinfo else d
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    return d.strftime("%Y-%m-%d")


def build_month_weeks(year: int, month: int) -> list[list[date]]:
    """Return list of weeks (each a list of 7 dates) for the month grid."""
    first = date(year, month, 1)
    # Start on Sunday
    grid_start = first - timedelta(days=first.weekday() + 1 if first.weekday() != 6 else 0)
    if first.weekday() == 6:
        grid_start = first
    else:
        grid_start = first - timedelta(days=(first.weekday() + 1) % 7)

    last = date(year, month, monthrange(year, month)[1])
    grid_end = last + timedelta(days=(6 - last.weekday() - 1) % 7)
    # Adjust: grid_end should be Saturday
    days_to_sat = (5 - last.weekday()) % 7  # 5 = Saturday in Mon-based
    # Use isoweekday: Mon=1..Sun=7. We want Sun=0..Sat=6
    last_dow = (last.isoweekday() % 7)  # Sun=0, Mon=1, ..., Sat=6
    grid_end = last + timedelta(days=(6 - last_dow))

    weeks = []
    cur = grid_start
    while cur <= grid_end:
        week = [cur + timedelta(days=i) for i in range(7)]
        weeks.append(week)
        cur += timedelta(days=7)
    return weeks


def group_events_by_day(events: list[dict]) -> dict[str, list[dict]]:
    """Group events by date key, expanding multi-day all-day events."""
    by_day: dict[str, list[dict]] = {}

    def add(key: str, ev: dict):
        if key not in by_day:
            by_day[key] = []
        by_day[key].append(ev)

    for ev in events:
        start = ev["start"]
        end   = ev["end"]

        if ev["allday"]:
            s = start.date() if isinstance(start, datetime) else start
            e = end.date()   if isinstance(end,   datetime) else end
            cur = s
            while cur <= e:
                add(cur.strftime("%Y-%m-%d"), ev)
                cur += timedelta(days=1)
        else:
            # Use local date for keying (handles UTC midnight crossings)
            d = local_date(start)
            add(d.strftime("%Y-%m-%d"), ev)

    # Sort each day's events: all-day first, then by start time
    for key in by_day:
        by_day[key].sort(key=lambda e: (
            0 if e["allday"] else 1,
            e["start"] if isinstance(e["start"], datetime) else datetime.min
        ))
    return by_day


def dedupe_print_events(events: list[dict]) -> list[dict]:
    """Remove exact duplicate print events, preferring higher-priority feed types."""
    by_key: dict[tuple, tuple[int, int, dict]] = {}
    for ev in events:
        start = ev["start"].isoformat() if isinstance(ev["start"], (datetime, date)) else str(ev["start"])
        end = ev["end"].isoformat() if isinstance(ev["end"], (datetime, date)) else str(ev["end"])
        key = (
            ev["title"],
            start,
            end,
            bool(ev.get("allday")),
            ev.get("location", ""),
        )
        priority = int(ev.get("_feed_priority", 0))
        sequence = int(ev.get("_sequence", 0))
        current = by_key.get(key)
        if current is None or priority > current[0] or (priority == current[0] and sequence < current[1]):
            by_key[key] = (priority, sequence, ev)
    deduped = [item[2] for item in sorted(by_key.values(), key=lambda item: item[1])]
    return deduped


class MonthContextMarker(Flowable):
    """Stamp the active month label onto the canvas for continuation headers."""

    def __init__(self, month_label: str):
        super().__init__()
        self.month_label = month_label

    def wrap(self, availWidth, availHeight):
        return 0, 0

    def draw(self):
        self.canv._current_month_label = self.month_label


def fmt_time(dt) -> str:
    if not isinstance(dt, datetime):
        return ""
    # Convert UTC to America/New_York
    if dt.tzinfo is not None:
        import zoneinfo
        dt = dt.astimezone(zoneinfo.ZoneInfo("America/New_York"))
    h, m = dt.hour, dt.minute
    ap = "pm" if h >= 12 else "am"
    h = h % 12 or 12
    return f"{h}:{m:02d}{ap}" if m else f"{h}{ap}"


def local_date(dt) -> date:
    """Get the local date of a datetime, converting from UTC if needed."""
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        import zoneinfo
        dt = dt.astimezone(zoneinfo.ZoneInfo("America/New_York"))
    if isinstance(dt, datetime):
        return dt.date()
    return dt


def _expanded_month_row_heights(
    grid_table: Table,
    content_width: float,
    target_height: float,
    num_weeks: int,
) -> list[float] | None:
    """Expand monthly calendar week rows so quieter months still fill the page."""
    if num_weeks <= 0 or target_height <= 0:
        return None
    grid_table.wrap(content_width, target_height)
    row_heights = list(getattr(grid_table, "_rowHeights", []) or [])
    if len(row_heights) != num_weeks + 1:
        return None
    current_height = sum(row_heights)
    if current_height >= target_height:
        return None
    extra_per_week = (target_height - current_height) / num_weeks
    return [row_heights[0]] + [h + extra_per_week for h in row_heights[1:]]


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------
def build_calendar_pdf(
    show_ids: list[str],
    shows: dict,
    tag_colors: dict,
    location_rules: list[dict],
    start_month: int,
    start_year: int,
    end_month: int,
    end_year: int,
    updated_by: str = "",
    cal_subtitle: str = "",
    custom_notes: dict | None = None,
    multi_show: bool = False,
) -> bytes:
    """
    Generate and return a PDF as bytes.
    """
    buf = io.BytesIO()

    # -- Fetch and merge all events ------------------------------------------
    all_events: list[dict] = []
    sequence = 0
    for show_id in show_ids:
        show = shows.get(show_id, {})
        for feed in normalize_show_feeds(show):
            if not feed.get("enabled", True):
                continue
            url = feed.get("url", "")
            if not url:
                continue
            try:
                text = _fetch_ical(url)
                events = parse_ical_for_print(text)
                priority = FEED_TYPE_PRIORITY.get(feed.get("type", "custom"), FEED_TYPE_PRIORITY["custom"])
                for ev in events:
                    ev["_feed_type"] = feed.get("type", "custom")
                    ev["_feed_label"] = feed.get("label", "")
                    ev["_feed_priority"] = priority
                    ev["_sequence"] = sequence
                    sequence += 1
                all_events.extend(events)
            except Exception as exc:
                pass  # silently skip failed feeds

    custom_notes = custom_notes or {}
    deduped = dedupe_print_events(all_events)
    by_day = group_events_by_day(deduped)

    # -- Header text ----------------------------------------------------------
    titles    = [shows[sid].get("title",   "") for sid in show_ids if sid in shows]
    seasons   = [shows[sid].get("season",  "") for sid in show_ids if sid in shows]
    unique_seasons = list(dict.fromkeys(s for s in seasons if s))

    if not multi_show:
        header_title = titles[0] if titles else ""
        header_sub   = seasons[0] if seasons else ""
    else:
        header_title = " / ".join(unique_seasons) if unique_seasons else " / ".join(titles)
        header_sub   = ""

    cal_sub = cal_subtitle or "Rehearsal Performance Calendar"
    now_str = datetime.now().strftime("%-m/%-d/%y")
    updated = f"Updated {now_str}" + (f" {updated_by}" if updated_by else "")

    # -- Build month range ---------------------------------------------------
    st = start_year * 12 + start_month
    et = end_year   * 12 + end_month
    if et < st:
        st, et = et, st
    month_range = []
    cur = st
    while cur <= et:
        month_range.append((cur % 12, cur // 12))
        cur += 1

    # -- ReportLab document --------------------------------------------------
    doc = BaseDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=MARGIN_LR,
        rightMargin=MARGIN_LR,
        topMargin=MARGIN_TB,
        bottomMargin=MARGIN_TB,
    )

    # -- Paragraph styles ----------------------------------------------------
    def ps(name, font=FONT_REGULAR, size=7, leading=None, color=C_BLACK, align=TA_LEFT, space_before=0, space_after=0):
        return ParagraphStyle(
            name, fontName=font, fontSize=size,
            leading=leading or size * 1.2,
            textColor=color, alignment=align,
            spaceBefore=space_before, spaceAfter=space_after,
        )

    sty_title    = ps("title",  FONT_BOLD,       12, color=C_BLACK,  align=TA_LEFT)
    sty_season   = ps("season", FONT_REGULAR,    10, color=colors.HexColor("#333333"), align=TA_LEFT)
    sty_cal_sub  = ps("calsub", FONT_ITALIC,     12, color=C_BLACK,  align=TA_CENTER)
    sty_subj     = ps("subj",   FONT_REGULAR,     7, color=C_FOOTER, align=TA_CENTER)
    sty_updated  = ps("upd",    FONT_REGULAR,    10, color=colors.HexColor("#444444"), align=TA_RIGHT)
    sty_month    = ps("month",  FONT_BOLD,        22, color=C_BLACK,  align=TA_CENTER, leading=26)
    sty_dow      = ps("dow",    FONT_BOLD,         9, color=C_DOW_FG, align=TA_CENTER)
    sty_datenum  = ps("dnum",   FONT_BOLD,         7, color=C_BLACK)
    sty_datenum_out = ps("dnumout", FONT_BOLD,    7, color=colors.HexColor("#bbbbbb"))
    sty_datenum_today = ps("dnumtod", FONT_BOLD,  7, color=C_TODAY_FG)
    sty_evt_time = ps("evttime", FONT_BOLD,        6, color=C_EVT_TIME)
    sty_evt_title= ps("evttitle",FONT_REGULAR,     6, color=C_BLACK)
    sty_evt_loc  = ps("evtloc",  FONT_ITALIC,      5.5, color=C_EVT_LOC)
    sty_note     = ps("note",    FONT_ITALIC,       5.5, color=C_NOTE)
    sty_legend   = ps("legend",  FONT_BOLD,         6.5, color=C_LEGEND)
    sty_footer   = ps("footer",  FONT_REGULAR,      6, color=C_FOOTER, align=TA_CENTER)
    sty_prefix   = ps("prefix",  FONT_BOLD,         6, color=C_BLACK)

    # -- Two page templates --------------------------------------------------
    # "first": full height frame for month-start pages
    # "cont":  shorter frame (leaves room at top for cont header drawn by callback)
    CONT_HDR_H = 22  # height reserved for cont header in points

    frame_first = Frame(MARGIN_LR, MARGIN_TB, CONTENT_W, CONTENT_H,
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame_cont  = Frame(MARGIN_LR, MARGIN_TB, CONTENT_W, CONTENT_H - CONT_HDR_H,
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def _draw_cont_header(canvas, doc):
        """Draw compact (cont) header at top of continuation pages."""
        canvas.saveState()
        x  = MARGIN_LR
        y  = PAGE_H - MARGIN_TB - 10  # baseline for text
        w  = CONTENT_W
        month_label = getattr(canvas, "_current_month_label", "Month")

        canvas.setFont(FONT_BOLD, 10)
        canvas.drawString(x, y, header_title)

        canvas.setFont(FONT_BOLDITALIC, 10)
        canvas.drawCentredString(x + w / 2, y, f"{month_label} (cont)")

        canvas.setFont(FONT_REGULAR, 9)
        canvas.drawRightString(x + w, y, updated)

        canvas.setStrokeColor(C_HEADER_SEP)
        canvas.setLineWidth(1.5)
        canvas.line(x, y - 4, x + w, y - 4)
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id="first", frames=[frame_first]),
        PageTemplate(id="cont",  frames=[frame_cont], onPage=_draw_cont_header),
    ])

    story = []
    col_w = CONTENT_W / 7

    for page_idx, (month, year) in enumerate(month_range):
        month_num = month + 1

        # Switch to "first" template at each month start (after a page break)
        if page_idx > 0:
            from reportlab.platypus import PageBreak, NextPageTemplate
            story.append(NextPageTemplate("first"))
            story.append(PageBreak())

        month_label = f"{MONTH_NAMES[month]} {year}"

        # After this page, continuation pages use "cont" template
        from reportlab.platypus import NextPageTemplate
        story.append(NextPageTemplate("cont"))
        story.append(MonthContextMarker(month_label))

        # ---- Header -------------------------------------------------------
        header_data = [[
            Paragraph(
                (f'<b>{header_title}</b>' if header_title else '') +
                (f'<br/><font size="10">{header_sub}</font>' if header_sub else ''),
                sty_title
            ),
            [
                Paragraph(f'<i>{cal_sub}</i>', sty_cal_sub),
                Paragraph("SUBJECT TO CHANGE", sty_subj),
            ],
            Paragraph(updated, sty_updated),
        ]]
        header_table = Table(header_data, colWidths=[CONTENT_W*0.33, CONTENT_W*0.34, CONTENT_W*0.33])
        header_table.setStyle(TableStyle([
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("LINEBELOW",     (0,0), (-1,-1), 1.5, C_HEADER_SEP),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("TOPPADDING",    (0,0), (-1,-1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 2))

        # ---- Month label --------------------------------------------------
        month_para = Paragraph(month_label, sty_month)
        story.append(month_para)
        story.append(Spacer(1, 2))

        # ---- Calendar grid: DOW header + week rows ------------------------
        ev_size, loc_size, dnum_size = 7.5, 6.5, 8
        sty_et  = ps(f"et{page_idx}",  FONT_REGULAR, ev_size,  color=C_BLACK,   leading=ev_size*1.35)
        sty_el  = ps(f"el{page_idx}",  FONT_ITALIC,  loc_size, color=C_EVT_LOC, leading=loc_size*1.35)
        sty_dn  = ps(f"dn{page_idx}",  FONT_BOLD,    dnum_size, color=C_BLACK)
        sty_dno = ps(f"dno{page_idx}", FONT_BOLD,    dnum_size, color=colors.HexColor("#bbbbbb"))

        weeks = build_month_weeks(year, month_num)
        num_weeks = len(weeks)

        # Collect tags for legend
        month_tags: set[str] = set()
        for week in weeks:
            for day in week:
                for ev in by_day.get(day.strftime("%Y-%m-%d"), []):
                    t = get_tag(ev["title"])
                    if t:
                        month_tags.add(t)

        # Row 0 = DOW header, rows 1..N = weeks
        grid_data = [[Paragraph(f'<b>{d}</b>', sty_dow) for d in DAY_NAMES]]
        grid_styles = [
            ("GRID",          (0,0), (-1,-1), 0.5, C_GRID),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",    (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ("LEFTPADDING",   (0,0), (-1,-1), 2),
            ("RIGHTPADDING",  (0,0), (-1,-1), 2),
            ("BACKGROUND",    (0,0), (-1,0), C_DOW_BG),
            ("TEXTCOLOR",     (0,0), (-1,0), C_DOW_FG),
            ("ALIGN",         (0,0), (-1,0), "CENTER"),
            ("VALIGN",        (0,0), (-1,0), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,0), 3),
            ("BOTTOMPADDING", (0,0), (-1,0), 3),
        ]

        for row_idx, week in enumerate(weeks):
            tbl_row = row_idx + 1
            row_cells = []
            for col_idx, day in enumerate(week):
                key = day.strftime("%Y-%m-%d")
                in_month = day.month == month_num
                cell_content = []

                date_label = MONTH_NAMES[day.month-1][:3].upper() + " 1" if day.day == 1 else str(day.day)
                cell_content.append(Paragraph(f'<b>{date_label}</b>', sty_dno if not in_month else sty_dn))

                if not in_month:
                    grid_styles.append(("BACKGROUND", (col_idx, tbl_row), (col_idx, tbl_row), C_OUT_MONTH))

                for ev in by_day.get(key, []):
                    tag           = get_tag(ev["title"])
                    display_title = clean_title(ev["title"])
                    display_loc   = clean_location(ev["location"], location_rules) if ev["location"] and not ev["allday"] else ""
                    prefix = f'<b>{tag}:</b> ' if (multi_show and tag) else ''

                    if ev["allday"]:
                        cell_content.append(Paragraph(f'{prefix}<b>{display_title}</b>', sty_et))
                    else:
                        time_str = fmt_time(ev["start"])
                        end_dt = ev["end"]
                        if isinstance(end_dt, datetime) and isinstance(ev["start"], datetime):
                            if local_date(end_dt) == local_date(ev["start"]) and end_dt != ev["start"]:
                                time_str += f"\u2013{fmt_time(end_dt)}"
                        cell_content.append(Paragraph(f'<b>{time_str}</b> {prefix}{display_title}', sty_et))

                    if display_loc:
                        cell_content.append(Paragraph(display_loc, sty_el))

                note = custom_notes.get(key, "")
                if note:
                    cell_content.append(Paragraph(f'<i>{note}</i>', sty_note))

                row_cells.append(cell_content)
            grid_data.append(row_cells)

        legend_present = multi_show and bool(month_tags)
        header_h = header_table.wrap(CONTENT_W, CONTENT_H)[1]
        month_h = month_para.wrap(CONTENT_W, CONTENT_H)[1]
        grid_target_height = CONTENT_H - header_h - month_h - 8 - (20 if legend_present else 0) - 12

        grid_table = Table(grid_data, colWidths=[col_w]*7, repeatRows=1, splitByRow=1)
        grid_table.setStyle(TableStyle(grid_styles))
        row_heights = _expanded_month_row_heights(grid_table, CONTENT_W, grid_target_height, num_weeks)
        if row_heights:
            grid_table = Table(
                grid_data,
                colWidths=[col_w]*7,
                rowHeights=row_heights,
                repeatRows=1,
                splitByRow=1,
            )
            grid_table.setStyle(TableStyle(grid_styles))
        story.append(grid_table)

        # ---- Legend -------------------------------------------------------
        if multi_show and month_tags:
            def _full_name(tag: str) -> str:
                info = tag_colors.get(tag)
                if not info:
                    for k, v in tag_colors.items():
                        if k.lower() == tag.lower():
                            info = v; break
                if isinstance(info, dict) and info.get("fullName") and info["fullName"] != tag:
                    return info["fullName"]
                return ""
            parts = [f"{t} \u2014 {_full_name(t)}" if _full_name(t) else t for t in sorted(month_tags)]
            story.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=C_GRID, spaceAfter=2, spaceBefore=3))
            story.append(Paragraph("   ".join(parts), sty_legend))

        # ---- Footer -------------------------------------------------------
        story.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=C_GRID, spaceAfter=1, spaceBefore=2))
        story.append(Paragraph(f"Page {page_idx+1} of {len(month_range)}", sty_footer))

    doc.build(story)
    buf.seek(0)
    return buf.read()




# ---------------------------------------------------------------------------
# Weekly calendar PDF — time-grid layout (like the room displays)
# Hours down the left, days as columns, events as positioned blocks
# Uses ReportLab canvas directly for pixel-perfect placement
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Weekly calendar PDF — time-grid layout (like the room displays)
# ---------------------------------------------------------------------------
def build_weekly_pdf(
    show_ids: list[str],
    shows: dict,
    tag_colors: dict,
    location_rules: list[dict],
    start_date: str,
    end_date: str,
    updated_by: str = "",
    cal_subtitle: str = "",
    custom_notes: dict | None = None,
    multi_show: bool = False,
    preserve_tags: bool = False,
) -> bytes:
    from datetime import date as Date
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    custom_notes = custom_notes or {}

    # Snap start to Monday (isoweekday: Mon=1, Sun=7)
    sd = Date.fromisoformat(start_date)
    ed = Date.fromisoformat(end_date)
    # isoweekday() Mon=1..Sun=7; days since Monday = isoweekday()-1
    sd = sd - timedelta(days=sd.isoweekday() - 1)

    weeks = []
    cur = sd
    while cur <= ed:
        weeks.append(cur)
        cur += timedelta(days=7)

    # Fetch events
    all_events: list[dict] = []
    sequence = 0
    for show_id in show_ids:
        show = shows.get(show_id, {})
        for feed in normalize_show_feeds(show):
            if not feed.get("enabled", True):
                continue
            url = feed.get("url", "")
            if not url:
                continue
            try:
                text = _fetch_ical(url)
                events = parse_ical_for_print(text)
                priority = FEED_TYPE_PRIORITY.get(feed.get("type", "custom"), FEED_TYPE_PRIORITY["custom"])
                for ev in events:
                    ev["_feed_type"] = feed.get("type", "custom")
                    ev["_feed_label"] = feed.get("label", "")
                    ev["_feed_priority"] = priority
                    ev["_sequence"] = sequence
                    sequence += 1
                all_events.extend(events)
            except Exception:
                pass

    by_day = group_events_by_day(dedupe_print_events(all_events))

    # Header values
    titles    = [shows[sid].get("title",   "") for sid in show_ids if sid in shows]
    seasons   = [shows[sid].get("season",  "") for sid in show_ids if sid in shows]
    unique_seasons = list(dict.fromkeys(s for s in seasons if s))

    if not multi_show:
        header_title = titles[0] if titles else ""
        header_sub   = seasons[0] if seasons else ""
    else:
        header_title = " / ".join(unique_seasons) if unique_seasons else " / ".join(titles)
        header_sub   = ""

    cal_sub  = cal_subtitle or "Rehearsal Performance Calendar"
    now_str  = datetime.now().strftime("%-m/%-d/%y")
    updated  = f"Updated {now_str}" + (f" {updated_by}" if updated_by else "")

    def tag_color_hex(tag: str) -> str:
        if not tag:
            return "#2563c7"
        info = tag_colors.get(tag)
        if not info:
            for k, v in tag_colors.items():
                if k.lower() == tag.lower():
                    info = v; break
        if isinstance(info, dict):
            return info.get("color", "#2563c7")
        if isinstance(info, str):
            return info
        return "#2563c7"

    def full_name(tag: str) -> str:
        info = tag_colors.get(tag)
        if not info:
            for k, v in tag_colors.items():
                if k.lower() == tag.lower():
                    info = v; break
        if isinstance(info, dict) and info.get("fullName") and info["fullName"] != tag:
            return info["fullName"]
        return ""

    # ── Page geometry (landscape letter = 792 x 612 pts) ───────────────────
    PW, PH = PAGE_W, PAGE_H   # 792 x 612

    # Margins
    ML, MR = 14, 8
    MT, MB = 10, 10

    # Fixed-height zones (pts), top-down:
    HDR_H    = 28   # title/subtitle/updated line
    RULE_H   = 2    # thick rule below header
    WEEK_H   = 18   # week label
    DOW_H    = 18   # day-of-week + date number header row
    FOOTER_H = 12
    LEGEND_H = 14 if multi_show else 0

    # Time range
    START_H = 8
    END_H   = 22
    HOURS   = END_H - START_H

    TIME_COL_W = 26   # left column for hour labels
    USABLE_W   = PW - ML - MR - TIME_COL_W
    DAY_W      = USABLE_W / 7

    # grid_top and HPX are recalculated per-week after the allday row is sized
    grid_bottom = MB + FOOTER_H + LEGEND_H

    MONTH_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    DAY_SHORT   = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]   # Mon-Sun order

    c = rl_canvas.Canvas(buf, pagesize=landscape(letter))

    for week_idx, week_mon in enumerate(weeks):
        if week_idx > 0:
            c.showPage()

        week_days = [week_mon + timedelta(days=i) for i in range(7)]  # Mon=0..Sun=6
        week_sun_day = week_days[6]  # Sunday is last

        if week_days[0].month == week_sun_day.month:
            week_label = f"{MONTH_NAMES[week_days[0].month-1]} {week_days[0].day}\u2013{week_sun_day.day}, {week_sun_day.year}"
        else:
            week_label = (f"{MONTH_NAMES[week_days[0].month-1]} {week_days[0].day} \u2013 "
                          f"{MONTH_NAMES[week_sun_day.month-1]} {week_sun_day.day}, {week_sun_day.year}")

        # ── Header (3-column: title left, cal_sub center, updated right) ───
        hdr_y = PH - MT - 10   # baseline for first header line
        c.setFont(FONT_BOLD, 10)
        c.setFillColor(C_BLACK)
        c.drawString(ML, hdr_y, header_title)
        if header_sub:
            c.setFont(FONT_REGULAR, 8)
            c.setFillColor(colors.HexColor("#444444"))
            c.drawString(ML, hdr_y - 11, header_sub)

        c.setFont(FONT_ITALIC, 10)
        c.setFillColor(C_BLACK)
        c.drawCentredString(PW / 2, hdr_y, cal_sub)
        c.setFont(FONT_REGULAR, 6.5)
        c.setFillColor(C_FOOTER)
        c.drawCentredString(PW / 2, hdr_y - 10, "SUBJECT TO CHANGE")

        c.setFont(FONT_REGULAR, 8)
        c.setFillColor(colors.HexColor("#444444"))
        c.drawRightString(PW - MR, hdr_y, updated)

        # Rule below header
        rule_y = PH - MT - HDR_H
        c.setStrokeColor(C_BLACK)
        c.setLineWidth(1.5)
        c.line(ML, rule_y, PW - MR, rule_y)

        # ── Week label ──────────────────────────────────────────────────────
        wk_y = rule_y - WEEK_H + 4
        c.setFont(FONT_BOLD, 13)
        c.setFillColor(C_BLACK)
        c.drawCentredString(PW / 2, wk_y, week_label)

        # ── DOW header row ──────────────────────────────────────────────────
        dow_top = rule_y - WEEK_H         # top of DOW row in canvas coords
        dow_bot = dow_top - DOW_H

        c.setFillColor(C_DOW_BG)
        c.setStrokeColor(C_GRID)
        c.setLineWidth(0.5)
        # Full background including time-col area
        c.rect(ML, dow_bot, TIME_COL_W + USABLE_W, DOW_H, fill=1, stroke=0)

        for col, day in enumerate(week_days):
            x = ML + TIME_COL_W + col * DAY_W
            # Vertical separator
            c.setStrokeColor(colors.HexColor("#555555"))
            c.setLineWidth(0.3)
            if col > 0:
                c.line(x, dow_bot, x, dow_top)
            # Day label
            date_label = f"{DAY_SHORT[col]}  {day.day}"
            if day.day == 1:
                date_label = f"{DAY_SHORT[col]}  {MONTH_SHORT[day.month-1]} {day.day}"
            c.setFillColor(C_DOW_FG)
            c.setFont(FONT_BOLD, 8)
            c.drawCentredString(x + DAY_W / 2, dow_bot + 5, date_label)

        # DOW border
        c.setStrokeColor(C_GRID)
        c.setLineWidth(0.5)
        c.rect(ML + TIME_COL_W, dow_bot, USABLE_W, DOW_H, fill=0, stroke=1)

        # ── All-day strip row ───────────────────────────────────────────────
        # Calculate max all-day events across all days this week
        STRIP_H = 10  # height of each strip
        max_allday = max(
            (len([ev for ev in by_day.get(d.strftime("%Y-%m-%d"), []) if ev["allday"]])
             for d in week_days),
            default=0
        )
        n_strips   = max(max_allday, 1)
        ALLDAY_H   = n_strips * STRIP_H + 2  # +2 for top/bottom padding

        allday_top = dow_bot
        allday_bot = allday_top - ALLDAY_H

        # Light background
        c.setFillColor(colors.HexColor("#f0f0f8"))
        c.rect(ML + TIME_COL_W, allday_bot, USABLE_W, ALLDAY_H, fill=1, stroke=0)

        for col, day in enumerate(week_days):
            x = ML + TIME_COL_W + col * DAY_W
            key = day.strftime("%Y-%m-%d")
            allday_evs = [ev for ev in by_day.get(key, []) if ev["allday"]]

            # Column separator
            c.setStrokeColor(C_GRID)
            c.setLineWidth(0.3)
            c.line(x, allday_bot, x, allday_top)

            # Draw each all-day event as its own strip, stacked top-down
            for strip_idx, ev in enumerate(allday_evs):
                tag   = get_tag(ev["title"])
                hex_c = tag_color_hex(tag) if tag else "#6699cc"
                title = ev["title"] if preserve_tags else clean_title(ev["title"])
                # strip y: start from top of allday row going down
                sy = allday_top - (strip_idx + 1) * STRIP_H
                c.setFillColor(colors.HexColor(hex_c))
                c.rect(x + 1, sy + 1, DAY_W - 2, STRIP_H - 1, fill=1, stroke=0)
                c.setFillColor(C_BLACK)
                c.setFont(FONT_BOLD, 6)
                txt = title
                while c.stringWidth(txt, FONT_BOLD, 6) > DAY_W - 4 and len(txt) > 3:
                    txt = txt[:-1]
                if txt != title:
                    txt = txt[:-1] + "\u2026"
                c.drawString(x + 2, sy + 3, txt)

        # All-day row border
        c.setStrokeColor(C_GRID)
        c.setLineWidth(0.5)
        c.rect(ML + TIME_COL_W, allday_bot, USABLE_W, ALLDAY_H, fill=0, stroke=1)

        # Recalculate grid_top to exactly match allday_bot (accounts for rounding)
        grid_top = allday_bot
        GRID_H   = grid_top - grid_bottom
        HPX      = GRID_H / HOURS

        def h_to_y(hour_float: float) -> float:
            return grid_top - (hour_float - START_H) * HPX

        # ── Hour lines + labels ─────────────────────────────────────────────
        for h in range(HOURS + 1):
            hour = START_H + h
            y = h_to_y(hour)
            # Hour line
            c.setStrokeColor(colors.HexColor("#cccccc"))
            c.setLineWidth(0.3)
            c.line(ML + TIME_COL_W, y, PW - MR, y)
            # Half-hour dashed
            if h < HOURS:
                yh = h_to_y(hour + 0.5)
                c.setDash(2, 3)
                c.setLineWidth(0.2)
                c.line(ML + TIME_COL_W, yh, PW - MR, yh)
                c.setDash()
            # Label
            if h < HOURS:
                label = f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"
                c.setFillColor(colors.HexColor("#6868a0"))
                c.setFont(FONT_REGULAR, 6.5)
                c.drawRightString(ML + TIME_COL_W - 3, y - 3, label)

        # ── Vertical day separators ─────────────────────────────────────────
        c.setStrokeColor(C_GRID)
        c.setLineWidth(0.5)
        for col in range(8):
            x = ML + TIME_COL_W + col * DAY_W
            c.line(x, grid_bottom, x, grid_top)

        # Grid border
        c.setStrokeColor(C_GRID)
        c.setLineWidth(0.8)
        c.rect(ML + TIME_COL_W, grid_bottom, USABLE_W, GRID_H, fill=0, stroke=1)

        # ── Timed events ────────────────────────────────────────────────────
        import zoneinfo
        NY = zoneinfo.ZoneInfo("America/New_York")

        for col, day in enumerate(week_days):
            key = day.strftime("%Y-%m-%d")
            x_col = ML + TIME_COL_W + col * DAY_W

            timed_evs = [ev for ev in by_day.get(key, [])
                         if not ev["allday"] and isinstance(ev["start"], datetime)]

            # Compute local start/end hours for each event
            ev_times = []
            for ev in timed_evs:
                s = ev["start"].astimezone(NY) if ev["start"].tzinfo else ev["start"]
                e = ev["end"]
                if isinstance(e, datetime):
                    e = e.astimezone(NY) if e.tzinfo else e
                else:
                    e = s.replace(hour=s.hour+1, minute=0)
                s_h = max(s.hour + s.minute/60, START_H)
                e_h = min(e.hour + e.minute/60 if isinstance(e, datetime) else s_h+1, END_H)
                if e_h <= s_h: e_h = s_h + 0.5
                ev_times.append((s_h, e_h, s, e, ev))

            # Collision detection — assign slots using greedy interval colouring
            # then determine width based on max concurrent in each event's group
            n = len(ev_times)
            assigned = [0] * n
            order = sorted(range(n), key=lambda i: ev_times[i][0])

            # Greedy slot assignment
            for i in order:
                s_h = ev_times[i][0]
                e_h = ev_times[i][1]
                used = set()
                for j in range(n):
                    if j != i and assigned[j] is not None:
                        js, je = ev_times[j][0], ev_times[j][1]
                        if js < e_h and je > s_h:  # overlaps
                            used.add(assigned[j])
                slot = 0
                while slot in used:
                    slot += 1
                assigned[i] = slot

            # For each event, num_cols = max slot index among all overlapping events + 1
            num_cols = [1] * n
            for i in range(n):
                s_h, e_h = ev_times[i][0], ev_times[i][1]
                max_slot = assigned[i]
                for j in range(n):
                    if ev_times[j][0] < e_h and ev_times[j][1] > s_h:
                        max_slot = max(max_slot, assigned[j])
                num_cols[i] = max_slot + 1

            # Draw events
            for idx, (s_h, e_h, s, e, ev) in enumerate(ev_times):
                slot    = assigned[idx]
                n_cols  = num_cols[idx]
                slot_w  = (DAY_W - 2) / n_cols
                x_ev    = x_col + 1 + slot * slot_w
                w_ev    = slot_w - 1

                y_top = h_to_y(s_h)
                y_bot = h_to_y(e_h)
                bh = max(y_top - y_bot, 5)

                tag = get_tag(ev["title"])
                ev_color = colors.HexColor(tag_color_hex(tag) if tag else "#2563c7")

                c.setFillColor(ev_color)
                c.setStrokeColor(colors.white)
                c.setLineWidth(0.4)
                c.roundRect(x_ev, y_bot, w_ev, bh, 1.5, fill=1, stroke=1)

                # Text inside block
                c.setFillColor(C_BLACK)
                ty = y_top - 6.5

                display_title = ev["title"] if preserve_tags else clean_title(ev["title"])
                prefix = ""
                if tag and not preserve_tags and multi_show:
                    prefix = f"{tag}: "
                time_str = fmt_time(s)
                if isinstance(e, datetime) and local_date(e) == local_date(s) and e > s:
                    time_str += f"\u2013{fmt_time(e)}"

                if bh >= 9:
                    c.setFont(FONT_BOLD, 6)
                    c.drawString(x_ev + 2, ty, time_str)
                    ty -= 7

                if bh >= 16 and ty > y_bot + 2:
                    c.setFont(FONT_REGULAR, 6)
                    txt = prefix + display_title
                    while c.stringWidth(txt, FONT_REGULAR, 6) > w_ev - 4 and len(txt) > 3:
                        txt = txt[:-1]
                    if txt != prefix + display_title:
                        txt = txt[:-1] + "\u2026"
                    c.drawString(x_ev + 2, ty, txt)
                    ty -= 7

                if bh >= 28 and ty > y_bot + 2 and ev.get("location"):
                    loc = clean_location(ev["location"], location_rules)
                    if loc:
                        c.setFont(FONT_ITALIC, 5.5)
                        while c.stringWidth(loc, FONT_ITALIC, 5.5) > w_ev - 4 and len(loc) > 3:
                            loc = loc[:-1]
                        c.drawString(x_ev + 2, ty, loc)

        # ── Legend ──────────────────────────────────────────────────────────
        if multi_show and LEGEND_H > 0:
            week_tags: set[str] = set()
            for day in week_days:
                for ev in by_day.get(day.strftime("%Y-%m-%d"), []):
                    t = get_tag(ev["title"])
                    if t: week_tags.add(t)

            if week_tags:
                leg_y = MB + FOOTER_H + 3
                x_leg = ML + TIME_COL_W
                for tag in sorted(week_tags):
                    fn = full_name(tag)
                    label = f"{tag} \u2014 {fn}" if fn else tag
                    c.setFillColor(colors.HexColor(tag_color_hex(tag)))
                    c.rect(x_leg, leg_y, 8, 8, fill=1, stroke=0)
                    c.setFont(FONT_BOLD, 7)
                    c.setFillColor(C_BLACK)
                    c.drawString(x_leg + 11, leg_y + 1, label)
                    x_leg += c.stringWidth(label, FONT_BOLD, 7) + 22

        # ── Footer ──────────────────────────────────────────────────────────
        c.setStrokeColor(C_GRID)
        c.setLineWidth(0.5)
        c.line(ML, MB + FOOTER_H - 1, PW - MR, MB + FOOTER_H - 1)
        c.setFont(FONT_REGULAR, 6)
        c.setFillColor(C_FOOTER)
        c.drawCentredString(PW / 2, MB + 3,
            f"Week of {week_label}  \u2022  Page {week_idx+1} of {len(weeks)}")

    c.save()
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Room schedule calendar PDF — monthly grid
# Shows all events from room iCal feeds; [TAG] labels kept and colored
# ---------------------------------------------------------------------------
def build_room_calendar_pdf(
    room_ids: list[str],
    rooms: dict,
    tag_colors: dict,
    location_rules: list[dict],
    start_month: int,
    start_year: int,
    end_month: int,
    end_year: int,
    updated_by: str = "",
    cal_subtitle: str = "",
    custom_notes: dict | None = None,
) -> bytes:
    """
    Monthly room schedule PDF.  Events are colored by [TAG] using tag_colors.
    Tags are retained in the display title as a colored prefix.
    """
    buf = io.BytesIO()
    custom_notes = custom_notes or {}

    # -- Fetch events from each room's iCal URL ------------------------------
    all_events: list[dict] = []
    for rid in room_ids:
        room = rooms.get(rid, {})
        url  = room.get("icalUrl", "").strip()
        url  = url.replace("webcal://", "https://").replace("webcal:", "https:")
        if not url:
            continue
        try:
            text = _fetch_ical(url)
            all_events.extend(parse_ical_for_print(text))
        except Exception:
            pass

    deduped = dedupe_print_events(all_events)
    by_day = group_events_by_day(deduped)

    # -- Header text ---------------------------------------------------------
    room_titles = [rooms[rid].get("title", rid) for rid in room_ids if rid in rooms]
    header_title = " / ".join(room_titles)
    cal_sub  = cal_subtitle or "Room Schedule"
    now_str  = datetime.now().strftime("%-m/%-d/%y")
    updated  = f"Updated {now_str}" + (f" {updated_by}" if updated_by else "")

    def _tag_full(tag: str) -> str:
        info = tag_colors.get(tag)
        if not info:
            for k, v in tag_colors.items():
                if k.lower() == tag.lower():
                    info = v; break
        if isinstance(info, dict) and info.get("fullName") and info["fullName"] != tag:
            return info["fullName"]
        return ""

    # -- Month range ---------------------------------------------------------
    st = start_year * 12 + start_month
    et = end_year   * 12 + end_month
    if et < st:
        st, et = et, st
    month_range = []
    cur = st
    while cur <= et:
        month_range.append((cur % 12, cur // 12))
        cur += 1

    # -- ReportLab document --------------------------------------------------
    doc = BaseDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=MARGIN_LR, rightMargin=MARGIN_LR,
        topMargin=MARGIN_TB,  bottomMargin=MARGIN_TB,
    )

    def ps(name, font=FONT_REGULAR, size=7, leading=None, color=C_BLACK,
           align=TA_LEFT, space_before=0, space_after=0):
        return ParagraphStyle(
            name, fontName=font, fontSize=size,
            leading=leading or size * 1.2,
            textColor=color, alignment=align,
            spaceBefore=space_before, spaceAfter=space_after,
        )

    sty_title   = ps("rm_title",   FONT_BOLD,     12, color=C_BLACK,   align=TA_LEFT)
    sty_cal_sub = ps("rm_calsub",  FONT_ITALIC,   12, color=C_BLACK,   align=TA_CENTER)
    sty_subj    = ps("rm_subj",    FONT_REGULAR,   7, color=C_FOOTER,  align=TA_CENTER)
    sty_updated = ps("rm_upd",     FONT_REGULAR,  10, color=colors.HexColor("#444444"), align=TA_RIGHT)
    sty_month   = ps("rm_month",   FONT_BOLD,     22, color=C_BLACK,   align=TA_CENTER, leading=26)
    sty_dow     = ps("rm_dow",     FONT_BOLD,      9, color=C_DOW_FG,  align=TA_CENTER)
    sty_footer  = ps("rm_footer",  FONT_REGULAR,   6, color=C_FOOTER,  align=TA_CENTER)
    sty_legend  = ps("rm_legend",  FONT_BOLD,    6.5, color=C_LEGEND)

    CONT_HDR_H = 22
    frame_first = Frame(MARGIN_LR, MARGIN_TB, CONTENT_W, CONTENT_H,
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame_cont  = Frame(MARGIN_LR, MARGIN_TB, CONTENT_W, CONTENT_H - CONT_HDR_H,
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    def _draw_cont_hdr(canvas, doc):
        canvas.saveState()
        x, y, w = MARGIN_LR, PAGE_H - MARGIN_TB - 10, CONTENT_W
        month_label = getattr(canvas, "_current_month_label", "Month")
        canvas.setFont(FONT_BOLD, 10);       canvas.drawString(x, y, header_title)
        canvas.setFont(FONT_BOLDITALIC, 10); canvas.drawCentredString(x + w/2, y, f"{month_label} (cont)")
        canvas.setFont(FONT_REGULAR, 9);     canvas.drawRightString(x + w, y, updated)
        canvas.setStrokeColor(C_HEADER_SEP); canvas.setLineWidth(1.5)
        canvas.line(x, y - 4, x + w, y - 4)
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id="first", frames=[frame_first]),
        PageTemplate(id="cont",  frames=[frame_cont], onPage=_draw_cont_hdr),
    ])

    story = []
    col_w = CONTENT_W / 7

    for page_idx, (month, year) in enumerate(month_range):
        month_num = month + 1

        if page_idx > 0:
            from reportlab.platypus import PageBreak, NextPageTemplate
            story.append(NextPageTemplate("first"))
            story.append(PageBreak())

        month_label = f"{MONTH_NAMES[month]} {year}"
        from reportlab.platypus import NextPageTemplate
        story.append(NextPageTemplate("cont"))
        story.append(MonthContextMarker(month_label))

        # Header row
        hdr_data = [[
            Paragraph(f'<b>{header_title}</b>', sty_title),
            [Paragraph(f'<i>{cal_sub}</i>', sty_cal_sub),
             Paragraph("SUBJECT TO CHANGE", sty_subj)],
            Paragraph(updated, sty_updated),
        ]]
        hdr_tbl = Table(hdr_data, colWidths=[CONTENT_W*0.33, CONTENT_W*0.34, CONTENT_W*0.33])
        hdr_tbl.setStyle(TableStyle([
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("LINEBELOW",     (0,0), (-1,-1), 1.5, C_HEADER_SEP),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("TOPPADDING",    (0,0), (-1,-1), 0),
        ]))
        story.append(hdr_tbl)
        story.append(Spacer(1, 2))
        month_para = Paragraph(month_label, sty_month)
        story.append(month_para)
        story.append(Spacer(1, 2))

        ev_size, loc_size, dnum_size = 7.5, 6.5, 8
        sty_et  = ps(f"rm_et{page_idx}",  FONT_REGULAR, ev_size,   color=C_BLACK,   leading=ev_size*1.35)
        sty_el  = ps(f"rm_el{page_idx}",  FONT_ITALIC,  loc_size,  color=C_EVT_LOC, leading=loc_size*1.35)
        sty_dn  = ps(f"rm_dn{page_idx}",  FONT_BOLD,    dnum_size, color=C_BLACK)
        sty_dno = ps(f"rm_dno{page_idx}", FONT_BOLD,    dnum_size, color=colors.HexColor("#bbbbbb"))
        sty_note= ps(f"rm_note{page_idx}",FONT_ITALIC,  5.5,       color=C_NOTE)

        weeks = build_month_weeks(year, month_num)

        # Collect tags on this month for legend
        month_tags: set[str] = set()
        for week in weeks:
            for day in week:
                for ev in by_day.get(day.strftime("%Y-%m-%d"), []):
                    t = get_tag(ev["title"])
                    if t:
                        month_tags.add(t)

        grid_data   = [[Paragraph(f'<b>{d}</b>', sty_dow) for d in DAY_NAMES]]
        grid_styles = [
            ("GRID",          (0,0), (-1,-1), 0.5, C_GRID),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",    (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ("LEFTPADDING",   (0,0), (-1,-1), 2),
            ("RIGHTPADDING",  (0,0), (-1,-1), 2),
            ("BACKGROUND",    (0,0), (-1,0),  C_DOW_BG),
            ("TEXTCOLOR",     (0,0), (-1,0),  C_DOW_FG),
            ("ALIGN",         (0,0), (-1,0),  "CENTER"),
            ("VALIGN",        (0,0), (-1,0),  "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,0),  3),
            ("BOTTOMPADDING", (0,0), (-1,0),  3),
        ]

        for row_idx, week in enumerate(weeks):
            tbl_row   = row_idx + 1
            row_cells = []
            for col_idx, day in enumerate(week):
                key       = day.strftime("%Y-%m-%d")
                in_month  = day.month == month_num
                cell_content = []

                date_label = (MONTH_NAMES[day.month-1][:3].upper() + " 1"
                              if day.day == 1 else str(day.day))
                cell_content.append(
                    Paragraph(f'<b>{date_label}</b>', sty_dno if not in_month else sty_dn))

                if not in_month:
                    grid_styles.append(
                        ("BACKGROUND", (col_idx, tbl_row), (col_idx, tbl_row), C_OUT_MONTH))

                for ev in by_day.get(key, []):
                    tag           = get_tag(ev["title"])
                    # Strip [TAG] brackets; show tag as colored prefix
                    display_title = re.sub(r'\s*\[[^\]]+\]', '', ev["title"]).strip()
                    display_loc   = (clean_location(ev["location"], location_rules)
                                     if ev["location"] and not ev["allday"] else "")

                    tag_markup = f'<b>[{tag}]</b> ' if tag else ''

                    if ev["allday"]:
                        cell_content.append(
                            Paragraph(f'{tag_markup}<b>{display_title}</b>', sty_et))
                    else:
                        time_str = fmt_time(ev["start"])
                        end_dt   = ev["end"]
                        if (isinstance(end_dt, datetime) and isinstance(ev["start"], datetime)
                                and local_date(end_dt) == local_date(ev["start"])
                                and end_dt != ev["start"]):
                            time_str += f"\u2013{fmt_time(end_dt)}"
                        cell_content.append(
                            Paragraph(f'<b>{time_str}</b> {tag_markup}{display_title}', sty_et))

                    if display_loc:
                        cell_content.append(Paragraph(display_loc, sty_el))

                note = custom_notes.get(key, "")
                if note:
                    cell_content.append(Paragraph(f'<i>{note}</i>', sty_note))

                row_cells.append(cell_content)
            grid_data.append(row_cells)

        legend_present = bool(month_tags)
        header_h = hdr_tbl.wrap(CONTENT_W, CONTENT_H)[1]
        month_h = month_para.wrap(CONTENT_W, CONTENT_H)[1]
        grid_target_height = CONTENT_H - header_h - month_h - 8 - (20 if legend_present else 0) - 12

        grid_table = Table(grid_data, colWidths=[col_w]*7, repeatRows=1, splitByRow=1)
        grid_table.setStyle(TableStyle(grid_styles))
        row_heights = _expanded_month_row_heights(grid_table, CONTENT_W, grid_target_height, len(weeks))
        if row_heights:
            grid_table = Table(
                grid_data,
                colWidths=[col_w]*7,
                rowHeights=row_heights,
                repeatRows=1,
                splitByRow=1,
            )
            grid_table.setStyle(TableStyle(grid_styles))
        story.append(grid_table)

        # Legend with colored squares
        if month_tags:
            parts = []
            for t in sorted(month_tags):
                fn  = _tag_full(t)
                label = f"{t} \u2014 {fn}" if fn else t
                parts.append(label)
            story.append(HRFlowable(width=CONTENT_W, thickness=0.5,
                                    color=C_GRID, spaceAfter=2, spaceBefore=3))
            story.append(Paragraph("   ".join(parts), sty_legend))

        story.append(HRFlowable(width=CONTENT_W, thickness=0.5,
                                color=C_GRID, spaceAfter=1, spaceBefore=2))
        story.append(Paragraph(f"Page {page_idx+1} of {len(month_range)}", sty_footer))

    doc.build(story)
    buf.seek(0)
    return buf.read()
