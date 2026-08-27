from datetime import datetime, timedelta
import unittest

from app.services.display_state import room_status


class FakeICalCache:
    def __init__(self, events):
        self._events = events

    def get_events(self, rid):
        return self._events


class RoomStatusTests(unittest.TestCase):
    def test_room_status_includes_event_details(self):
        now = datetime(2026, 8, 27, 9, 0)
        events = [
            {
                "title": "DANC 202-010 [Class]",
                "details": "Ballet I",
                "start": now + timedelta(hours=1),
                "end": now + timedelta(hours=2),
            }
        ]

        status = room_status(FakeICalCache(events), "hgy208", now=now)

        self.assertEqual(status["next"]["title"], "DANC 202-010 [Class]")
        self.assertEqual(status["next"]["details"], "Ballet I")


if __name__ == "__main__":
    unittest.main()
