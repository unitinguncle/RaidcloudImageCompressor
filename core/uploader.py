"""
core/uploader.py — Immich REST API uploader QThread.
Uploads a list of local files directly to an Immich server using its API.
"""

import os
import mimetypes
import requests

from PySide6.QtCore import QThread, Signal


class UploaderThread(QThread):
    """
    Uploads files to Immich via POST /api/assets.

    Signals:
        progress(int)                    — 0-100 overall %
        file_done(filename, status_str)  — per-file result label
        log(str, bool)                   — (message, is_error)
        finished()
    """

    progress  = Signal(int)
    file_done = Signal(str, str)   # filename, status
    log       = Signal(str, bool)
    finished  = Signal()

    def __init__(
        self,
        files: list[str],
        server_url: str,
        api_key: str,
        parent=None,
    ):
        super().__init__(parent)
        self.files      = files
        self.server_url = server_url.rstrip("/")
        self.api_key    = api_key
        self._cancel    = False

    def cancel(self):
        self._cancel = True

    # ── Public helper: test connectivity ─────────────────────────────────────
    @staticmethod
    def test_connection(server_url: str, api_key: str, timeout: int = 10) -> tuple[bool, str]:
        """Returns (ok, message)."""
        url = server_url.rstrip("/") + "/api/server/about"
        try:
            r = requests.get(
                url,
                headers={"x-api-key": api_key},
                timeout=timeout,
            )
            if r.status_code == 200:
                data = r.json()
                version = data.get("version", "unknown")
                return True, f"Connected ✓  (Immich {version})"
            else:
                return False, f"HTTP {r.status_code}: {r.text[:120]}"
        except requests.exceptions.ConnectionError:
            return False, "Connection refused — check server URL."
        except requests.exceptions.Timeout:
            return False, "Connection timed out."
        except Exception as exc:
            return False, str(exc)

    # ── Main thread logic ─────────────────────────────────────────────────────
    def run(self):
        total = len(self.files)
        if total == 0:
            self.finished.emit()
            return

        upload_url = f"{self.server_url}/api/assets"
        headers = {"x-api-key": self.api_key}

        for idx, file_path in enumerate(self.files):
            if self._cancel:
                self.log.emit("Upload cancelled by user.", False)
                break

            filename = os.path.basename(file_path)
            mime, _ = mimetypes.guess_type(file_path)
            if not mime:
                mime = "application/octet-stream"

            try:
                with open(file_path, "rb") as f:
                    resp = requests.post(
                        upload_url,
                        headers=headers,
                        files={"assetData": (filename, f, mime)},
                        data={
                            "deviceAssetId": filename,
                            "deviceId":      "RaidCloudImmichSuite",
                            "fileCreatedAt": _file_mtime_iso(file_path),
                            "fileModifiedAt": _file_mtime_iso(file_path),
                            "isFavorite":    "false",
                        },
                        timeout=120,
                    )

                if resp.status_code in (200, 201):
                    self.file_done.emit(filename, "uploaded")
                elif resp.status_code == 409:
                    self.file_done.emit(filename, "duplicate (skipped)")
                else:
                    self.file_done.emit(filename, f"error {resp.status_code}")
                    self.log.emit(
                        f"[WARN] {filename}: HTTP {resp.status_code} — {resp.text[:80]}",
                        True,
                    )

            except Exception as exc:
                self.file_done.emit(filename, "FAILED")
                self.log.emit(f"[ERROR] {filename}: {exc}", True)

            self.progress.emit(int((idx + 1) / total * 100))

        self.finished.emit()


def _file_mtime_iso(path: str) -> str:
    """Return the file's mtime as an ISO-8601 string."""
    import datetime
    mtime = os.path.getmtime(path)
    return datetime.datetime.fromtimestamp(mtime).isoformat()
