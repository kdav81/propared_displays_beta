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


if __name__ == "__main__":
    unittest.main()
