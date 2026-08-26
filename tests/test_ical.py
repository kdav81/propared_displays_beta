import unittest

from app.services.ical import parse_ical


class ICalParserTests(unittest.TestCase):
    def test_parse_ical_extracts_propared_details(self):
        text = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260827T133500Z
DTEND:20260827T145524Z
SUMMARY:DANC 202-010 [Class]
DESCRIPTION:---STATUS---\\nConfirmed\\n\\n---LOCATION---\\n208 [Dance Studio] (HGY)\\n\\n---DETAILS---\\nBallet I\\n\\n---CATEGORIES---\\nClass\\, DANC Class\\n
LOCATION:208 [Dance Studio] (HGY)
UID:3818996@propared.com
END:VEVENT
END:VCALENDAR
"""

        events = parse_ical(text)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "DANC 202-010 [Class]")
        self.assertEqual(events[0]["details"], "Ballet I")
        self.assertEqual(events[0]["start"].isoformat(), "2026-08-27T13:35:00+00:00")


if __name__ == "__main__":
    unittest.main()
