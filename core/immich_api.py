"""
core/immich_api.py — Synchronous Immich REST API client.

Used from QThread workers; never call from the main/GUI thread directly.
Covers album management, asset upload, sharing, and shared-link generation.
"""

import os
import mimetypes
import datetime
import requests
from typing import Optional


class ImmichApiError(Exception):
    """Raised when an Immich API call returns a non-2xx response."""


class ImmichApi:
    """Thin synchronous wrapper around the Immich REST API (v1)."""

    def __init__(self, server_url: str, api_key: str, timeout: int = 120):
        self.base = server_url.rstrip("/")
        self._headers = {"x-api-key": api_key, "Accept": "application/json"}
        self.timeout = timeout

    # ── Internal HTTP helpers ─────────────────────────────────────────────────

    def _get(self, path: str, **kwargs):
        r = requests.get(
            f"{self.base}{path}", headers=self._headers, timeout=self.timeout, **kwargs
        )
        self._raise(r)
        return r.json()

    def _post(self, path: str, json=None, **kwargs):
        r = requests.post(
            f"{self.base}{path}",
            headers=self._headers,
            json=json,
            timeout=self.timeout,
            **kwargs,
        )
        self._raise(r)
        return r.json()

    def _put(self, path: str, json=None, **kwargs):
        r = requests.put(
            f"{self.base}{path}",
            headers=self._headers,
            json=json,
            timeout=self.timeout,
            **kwargs,
        )
        self._raise(r)
        return r.json()

    @staticmethod
    def _raise(r: requests.Response):
        if r.status_code not in (200, 201):
            raise ImmichApiError(f"HTTP {r.status_code} — {r.text[:200]}")

    # ── Connectivity ──────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """Quick ping. Returns (ok, human-readable message)."""
        try:
            data = self._get("/api/server/about")
            version = data.get("version", "?")
            return True, f"Connected ✓  (Immich {version})"
        except ImmichApiError as e:
            return False, str(e)
        except requests.exceptions.ConnectionError:
            return False, "Connection refused — check server URL."
        except requests.exceptions.Timeout:
            return False, "Connection timed out."
        except Exception as e:
            return False, str(e)

    # ── Albums ────────────────────────────────────────────────────────────────

    def list_albums(self) -> list[dict]:
        """Return [{id, name}] for every album owned by the API-key user."""
        data = self._get("/api/albums")
        return [{"id": a["id"], "name": a.get("albumName", "")} for a in data]

    def create_album(self, name: str, description: str = "") -> str:
        """Create a new album and return its UUID."""
        data = self._post(
            "/api/albums",
            json={"albumName": name, "description": description},
        )
        return data["id"]

    def add_assets_to_album(self, album_id: str, asset_ids: list[str]) -> None:
        """Bulk-add asset UUIDs to an existing album."""
        if not asset_ids:
            return
        self._put(f"/api/albums/{album_id}/assets", json={"ids": asset_ids})

    def share_album_with_users(
        self,
        album_id: str,
        user_ids: list[str],
        role: str = "viewer",
    ) -> None:
        """Share an album with internal Immich users by UUID list."""
        self._put(
            f"/api/albums/{album_id}/users",
            json={
                "albumUsers": [{"userId": uid, "role": role} for uid in user_ids]
            },
        )

    def create_shared_link(self, album_id: str) -> str:
        """
        Create a public shared link for an album.
        Returns the full shareable URL.
        """
        data = self._post(
            "/api/shared-links",
            json={
                "type": "ALBUM",
                "albumId": album_id,
                "allowDownload": True,
                "allowUpload": False,
                "showMetadata": True,
            },
        )
        token = data.get("key") or data.get("id", "")
        return f"{self.base}/share/{token}"

    # ── Assets ────────────────────────────────────────────────────────────────

    def upload_asset(self, file_path: str) -> str:
        """
        Upload a single file to Immich.
        Returns the asset UUID (new or existing on 409 duplicate).
        Raises ImmichApiError on hard failures.
        """
        filename = os.path.basename(file_path)
        mime, _ = mimetypes.guess_type(file_path)
        if not mime:
            mime = "application/octet-stream"

        stat = os.stat(file_path)
        ts = _file_created_iso(file_path)

        with open(file_path, "rb") as fh:
            resp = requests.post(
                f"{self.base}/api/assets",
                headers={"x-api-key": self._headers["x-api-key"]},
                files={"assetData": (filename, fh, mime)},
                data={
                    "deviceAssetId": f"{filename}-{int(stat.st_mtime)}",
                    "deviceId": "RaidCloudSmartAlbum",
                    "fileCreatedAt": ts,
                    "fileModifiedAt": ts,
                    "isFavorite": "false",
                },
                timeout=self.timeout,
            )

        if resp.status_code in (200, 201):
            return resp.json().get("id", "")
        elif resp.status_code == 409:
            # Duplicate — the asset already exists; try to extract its id
            try:
                return resp.json().get("id", "")
            except Exception:
                return ""
        else:
            raise ImmichApiError(
                f"Upload failed HTTP {resp.status_code} — {resp.text[:200]}"
            )


# ── Utility ───────────────────────────────────────────────────────────────────

def _file_created_iso(path: str) -> str:
    """Return the file's true creation/birth time as ISO-8601."""
    import sys

    stat = os.stat(path)
    if sys.platform == "darwin":
        ts = getattr(stat, "st_birthtime", stat.st_mtime)
    elif sys.platform.startswith("win"):
        ts = stat.st_ctime
    else:
        ts = stat.st_mtime
    return datetime.datetime.fromtimestamp(ts).isoformat()
