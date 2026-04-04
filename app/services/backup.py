from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from app.config import BACKUP_DIR, BASE, MEDIA_DIR, STATIC_DIR

BACKUP_JSON_FILES = (
    "rooms.json",
    "tag_colors.json",
    "settings.json",
    "notice.json",
    "notice_password.txt",
    "print_shows.json",
    "location_rules.json",
    "media_library.json",
)


def restore_logo_files(archive_names: list[str], zf: zipfile.ZipFile) -> None:
    archived_logos = {
        Path(name).name for name in archive_names if name.startswith("static/logo_") and name.endswith(".png")
    }
    for fp in STATIC_DIR.glob("logo_*.png"):
        if fp.name not in archived_logos:
            fp.unlink()
    for logo_name in archived_logos:
        (STATIC_DIR / logo_name).write_bytes(zf.read(f"static/{logo_name}"))


def restore_slide_files(archive_names: list[str], zf: zipfile.ZipFile) -> None:
    archived_slides = {
        Path(name).name for name in archive_names if name.startswith("static/slides/") and not name.endswith("/")
    }
    for fp in MEDIA_DIR.iterdir():
        if fp.is_file() and fp.name not in archived_slides:
            fp.unlink()
    for slide_name in archived_slides:
        (MEDIA_DIR / slide_name).write_bytes(zf.read(f"static/slides/{slide_name}"))


def make_backup_zip(room_ids: list[str]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in BACKUP_JSON_FILES:
            path = BASE / fname
            if path.exists():
                zf.write(path, fname)
        if STATIC_DIR.is_dir():
            for fn in STATIC_DIR.iterdir():
                if fn.name.startswith("logo_") and fn.suffix == ".png":
                    zf.write(fn, f"static/{fn.name}")
        if MEDIA_DIR.is_dir():
            for fn in MEDIA_DIR.iterdir():
                if fn.is_file():
                    zf.write(fn, f"static/slides/{fn.name}")
        manifest = {
            "version": 4,
            "createdAt": datetime.now().isoformat(),
            "rooms": room_ids,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    buf.seek(0)
    return buf


def restore_backup_archive(uploaded_bytes: bytes) -> None:
    buf = io.BytesIO(uploaded_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        for fname in BACKUP_JSON_FILES:
            if fname in names:
                (BASE / fname).write_bytes(zf.read(fname))
        restore_logo_files(names, zf)
        restore_slide_files(names, zf)


def save_backup_copy(filename: str, data: bytes) -> None:
    (BACKUP_DIR / filename).write_bytes(data)
