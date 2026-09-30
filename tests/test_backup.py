from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from app.services import backup


class BackupServiceTest(unittest.TestCase):
    def test_backup_includes_media_gallery_notices_slides_and_site_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_base = backup.BASE
            original_static = backup.STATIC_DIR
            original_media = backup.MEDIA_DIR
            try:
                backup.BASE = root
                backup.STATIC_DIR = root / "static"
                backup.MEDIA_DIR = backup.STATIC_DIR / "slides"
                backup.MEDIA_DIR.mkdir(parents=True)
                (root / "notice.json").write_text('{"global": [], "rooms": {}}', encoding="utf-8")
                (root / "media_library.json").write_text("[]", encoding="utf-8")
                (backup.MEDIA_DIR / "slide.png").write_bytes(b"slide")
                (backup.STATIC_DIR / "site_logo.png").write_bytes(b"logo")

                archive = backup.make_backup_zip(["room1"])

                with zipfile.ZipFile(archive) as zf:
                    names = set(zf.namelist())
                self.assertIn("notice.json", names)
                self.assertIn("media_library.json", names)
                self.assertIn("static/slides/slide.png", names)
                self.assertIn("static/site_logo.png", names)
            finally:
                backup.BASE = original_base
                backup.STATIC_DIR = original_static
                backup.MEDIA_DIR = original_media

    def test_restore_replaces_site_logo_from_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            static_dir = root / "static"
            static_dir.mkdir()
            (static_dir / "site_logo.jpg").write_bytes(b"old")
            archive_path = root / "backup.zip"
            with zipfile.ZipFile(archive_path, "w") as zf:
                zf.writestr("static/site_logo.png", b"new")

            original_static = backup.STATIC_DIR
            try:
                backup.STATIC_DIR = static_dir
                with zipfile.ZipFile(archive_path) as zf:
                    backup.restore_site_logo_files(zf.namelist(), zf)

                self.assertFalse((static_dir / "site_logo.jpg").exists())
                self.assertEqual((static_dir / "site_logo.png").read_bytes(), b"new")
            finally:
                backup.STATIC_DIR = original_static


if __name__ == "__main__":
    unittest.main()
