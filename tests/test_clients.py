from __future__ import annotations

import unittest
from importlib.util import find_spec
from unittest.mock import patch

if find_spec("flask") is None:
    raise unittest.SkipTest("Flask is not installed in this test environment")

from app.routes.display import _ensure_client_defaults


class ClientPresenceTests(unittest.TestCase):
    def test_normalizing_client_does_not_refresh_last_seen(self):
        client = _ensure_client_defaults(
            {"last_seen": 123.0},
            hostname="display-1",
            ip="10.0.0.10",
        )

        self.assertEqual(client["last_seen"], 123.0)

    def test_heartbeat_refreshes_last_seen_when_requested(self):
        with patch("app.routes.display.time.time", return_value=456.0):
            client = _ensure_client_defaults(
                {"last_seen": 123.0},
                hostname="display-1",
                ip="10.0.0.10",
                update_last_seen=True,
            )

        self.assertEqual(client["last_seen"], 456.0)


if __name__ == "__main__":
    unittest.main()
