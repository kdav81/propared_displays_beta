from __future__ import annotations

import unittest
import re
import tempfile
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

if find_spec("flask") is None:
    raise unittest.SkipTest("Flask is not installed in this test environment")

from flask import Flask

from app.routes import printing as printing_routes
from app.config import EXPECTED_CLIENT_VERSION
from app.routes import display as display_routes
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
        self.assertTrue(_client_supports_update("10.09"))
        self.assertTrue(_client_supports_update("10.10"))
        self.assertTrue(_client_supports_update("10.11"))
        self.assertTrue(_client_supports_update("10.12"))
        self.assertTrue(_client_supports_update("10.13"))

    def test_update_all_queues_only_eligible_outdated_clients(self):
        clients = {
            "eligible": {"hostname": "eligible", "ip": "10.0.0.1", "clientVersion": "10.12"},
            "current": {"hostname": "current", "ip": "10.0.0.2", "clientVersion": EXPECTED_CLIENT_VERSION},
            "manual": {"hostname": "manual", "ip": "10.0.0.3", "clientVersion": "0.1.0"},
            "pending": {
                "hostname": "pending",
                "ip": "10.0.0.4",
                "clientVersion": "10.12",
                "pending_command": {
                    "id": "existing-command",
                    "command": "restart_kiosk",
                    "created_at": 1,
                    "status": "pending",
                },
            },
        }
        app = Flask(__name__)

        original_require_admin = display_routes.require_admin
        display_routes.require_admin = lambda func: func
        try:
            display_routes.register_display_routes(
                app,
                clients=clients,
                ical_cache=None,
                global_cal_cache=None,
                get_slides=lambda force=False: [],
                logo_path=lambda rid: None,
                public_room_config=lambda rid, rooms, settings: {},
                room_status=lambda rid: {},
                sync_global_calendar_cache=lambda calendars: None,
                to_int=lambda value, default, minimum=None, maximum=None: default,
                validated_proxy_ical_url=lambda url: "",
            )
        finally:
            display_routes.require_admin = original_require_admin

        response = app.test_client().post("/admin/clients/update-all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "ok": True,
                "queued": 1,
                "skippedCurrent": 1,
                "skippedManual": 1,
                "skippedPending": 1,
            },
        )
        self.assertEqual(clients["eligible"]["pending_command"]["command"], "update_client")
        self.assertEqual(clients["pending"]["pending_command"]["id"], "existing-command")

    def test_client_version_file_matches_installer_constant(self):
        root = Path(__file__).resolve().parents[1]
        expected = (root / "CLIENT_VERSION").read_text(encoding="utf-8").strip()
        installer = (root / "install-client.sh").read_text(encoding="utf-8")
        match = re.search(r'^INSTALLER_CLIENT_VERSION="([^"]+)"', installer, re.MULTILINE)

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), expected)

    def test_print_show_order_requires_print_admin_auth(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.auth.PRINT_ADMIN_PASSWORD_FILE",
            Path(tmp) / "print_admin_password.txt",
        ):
            app = Flask(__name__)
            printing_routes.register_printing_routes(
                app,
                pdf_available=False,
                build_calendar_pdf=None,
                build_weekly_pdf=None,
                build_room_calendar_pdf=None,
                to_int=lambda value, default, minimum=None, maximum=None: default,
                log=None,
            )

            response = app.test_client().post("/api/print-shows/order", json={"order": []})

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
