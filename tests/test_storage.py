from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import storage
from app.config import DEFAULT_TAGS


class LoadTagsTest(unittest.TestCase):
    def test_missing_tags_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = storage.TAGS_FILE
            storage.TAGS_FILE = Path(tmp) / "tag_colors.json"
            try:
                self.assertEqual(storage.load_tags(), DEFAULT_TAGS)
            finally:
                storage.TAGS_FILE = original

    def test_existing_tags_file_does_not_restore_removed_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = storage.TAGS_FILE
            storage.TAGS_FILE = Path(tmp) / "tag_colors.json"
            try:
                storage.save_tags(
                    {
                        "Class": {"color": "#2563c7", "fullName": "Class"},
                        "default": {"color": "#2563c7", "fullName": ""},
                    }
                )

                tags = storage.load_tags()

                self.assertNotIn("SPDance", tags)
                self.assertEqual(set(tags), {"Class", "default"})
            finally:
                storage.TAGS_FILE = original

    def test_legacy_string_tags_are_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = storage.TAGS_FILE
            storage.TAGS_FILE = Path(tmp) / "tag_colors.json"
            try:
                storage.save_tags({"Legacy": "#123456"})

                self.assertEqual(
                    storage.load_tags(),
                    {"Legacy": {"color": "#123456", "fullName": "Legacy"}},
                )
            finally:
                storage.TAGS_FILE = original


class LoadNoticeTest(unittest.TestCase):
    def test_legacy_global_notice_is_normalized_to_library_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = storage.NOTICE_FILE
            storage.NOTICE_FILE = Path(tmp) / "notice.json"
            try:
                storage.save_notice(
                    {
                        "active": True,
                        "message": "Legacy message",
                        "startTime": "",
                        "endTime": "",
                        "version": 3,
                    }
                )

                notices = storage.load_notice()

                self.assertEqual(len(notices["global"]), 1)
                self.assertEqual(notices["global"][0]["message"], "Legacy message")
                self.assertEqual(notices["global"][0]["version"], 3)
                self.assertTrue(notices["global"][0]["id"])
                self.assertEqual(notices["rooms"], {})
            finally:
                storage.NOTICE_FILE = original

    def test_empty_legacy_notice_does_not_create_blank_library_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = storage.NOTICE_FILE
            storage.NOTICE_FILE = Path(tmp) / "notice.json"
            try:
                storage.save_notice(storage.empty_notice())

                self.assertEqual(storage.load_notice(), {"global": [], "rooms": {}})
            finally:
                storage.NOTICE_FILE = original


if __name__ == "__main__":
    unittest.main()
