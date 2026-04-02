from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from classroom_server.core import IMAGE_EXTS, log, slides_cache_path
from classroom_server.storage import load_settings


def get_dropbox_token(settings: dict) -> str:
    refresh_token = settings.get("dropboxRefreshToken", "").strip()
    app_key = settings.get("dropboxAppKey", "").strip()
    app_secret = settings.get("dropboxAppSecret", "").strip()
    if refresh_token and app_key and app_secret:
        try:
            data = urllib.parse.urlencode(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": app_key,
                    "client_secret": app_secret,
                }
            ).encode()
            req = urllib.request.Request(
                "https://api.dropbox.com/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read())["access_token"]
        except Exception as exc:
            log.warning("Dropbox token refresh failed: %s", exc)
    return settings.get("dropboxToken", "").strip()


def fetch_dropbox_images(token: str, folder: str) -> list[str]:
    path = "" if folder.strip() in ("", "/") else folder.strip()
    try:
        req = urllib.request.Request(
            "https://api.dropboxapi.com/2/files/list_folder",
            data=json.dumps({"path": path, "limit": 300}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            entries = json.loads(response.read()).get("entries", [])

        image_paths = [
            entry["path_lower"]
            for entry in entries
            if entry.get(".tag") == "file" and Path(entry["name"]).suffix.lower() in IMAGE_EXTS
        ]
        log.info("Dropbox '%s': %d entries, %d images", path, len(entries), len(image_paths))

        links: list[str] = []
        for image_path in image_paths[:60]:
            try:
                req2 = urllib.request.Request(
                    "https://api.dropboxapi.com/2/files/get_temporary_link",
                    data=json.dumps({"path": image_path}).encode(),
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req2, timeout=10) as response:
                    links.append(json.loads(response.read())["link"])
            except Exception as exc:
                log.warning("Dropbox temp link failed for %s: %s", image_path, exc)
        return links
    except Exception as exc:
        log.warning("Dropbox list_folder failed: %s", exc)
        return []


def get_slides(force: bool = False) -> list[str]:
    cache = slides_cache_path()
    if not force and cache.exists():
        try:
            data = json.loads(cache.read_text())
            if time.time() - data.get("fetchedAt", 0) < 1800 and data.get("links"):
                return data["links"]
        except Exception:
            pass
    settings = load_settings()
    token = get_dropbox_token(settings)
    if not token:
        log.warning("get_slides: no Dropbox token available")
        return []
    links = fetch_dropbox_images(token, settings.get("dropboxFolder", ""))
    if links:
        cache.write_text(json.dumps({"links": links, "fetchedAt": time.time()}))
    else:
        log.warning("get_slides: no images returned from Dropbox")
    return links


def exchange_dropbox_code(code: str, app_key: str, app_secret: str, redirect_uri: str) -> dict:
    try:
        data = urllib.parse.urlencode(
            {
                "code": code,
                "grant_type": "authorization_code",
                "client_id": app_key,
                "client_secret": app_secret,
                "redirect_uri": redirect_uri,
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.dropbox.com/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read())
    except Exception as exc:
        return {"error": str(exc)}

