from __future__ import annotations

try:
    from print_calendar_pdf import build_calendar_pdf, build_weekly_pdf

    PDF_AVAILABLE = True
except ImportError:
    build_calendar_pdf = None
    build_weekly_pdf = None
    PDF_AVAILABLE = False

