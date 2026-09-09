from __future__ import annotations

import unittest
from importlib.util import find_spec
from unittest.mock import patch

if find_spec("flask") is None:
    raise unittest.SkipTest("Flask is not installed in this test environment")

from app.routes.display import SUPPORTED_CLIENT_COMMANDS, _client_supports_update, _ensure_client_defaults


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

    def test_client_version_is_normalized_from_legacy_key(self):
        client = _ensure_client_defaults(
            {"client_version": "0.1.0"},
            hostname="display-1",
            ip="10.0.0.10",
        )

        self.assertEqual(client["clientVersion"], "0.1.0")

    def test_update_client_command_is_supported(self):
        self.assertIn("update_client", SUPPORTED_CLIENT_COMMANDS)

    def test_update_requires_self_updater_version(self):
        self.assertFalse(_client_supports_update(""))
        self.assertFalse(_client_supports_update("0.1.0"))
        self.assertTrue(_client_supports_update("0.1.1"))


if __name__ == "__main__":
    unittest.main()
