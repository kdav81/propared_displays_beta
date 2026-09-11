from __future__ import annotations

import unittest
from datetime import date
from importlib.util import find_spec

if find_spec("reportlab") is None:
    raise unittest.SkipTest("ReportLab is not installed in this test environment")

from print_calendar_pdf import _short_mdy


class PrintCalendarPdfTests(unittest.TestCase):
    def test_short_mdy_is_platform_portable(self):
        self.assertEqual(_short_mdy(date(2026, 9, 11)), "9/11/26")


if __name__ == "__main__":
    unittest.main()
