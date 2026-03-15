"""
core/uploader.py — Immich REST API uploader QThread.
Uploads a list of local files directly to an Immich server using its API.
"""

import os
import mimetypes
import requests
import concurrent.futures

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

        # Keep workers reasonable (e.g. 5-10) to not hammer the server network layer too violently.
        max_workers = min(10, os.cpu_count() or 4)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # We map futures to file_paths so we can track errors back to filename
            futures = {}
            for file_path in self.files:
                fut = executor.submit(self._upload_worker, file_path, upload_url, headers)
                futures[fut] = file_path

            completed = 0
            for future in concurrent.futures.as_completed(futures):
                if self._cancel:
                    self.log.emit("Upload cancelled by user.", False)
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                    
                file_path = futures[future]
                filename = os.path.basename(file_path)

                try:
                    result_label, log_warn_err = future.result()
                    self.file_done.emit(filename, result_label)
                    if log_warn_err:
                        self.log.emit(log_warn_err[0], log_warn_err[1])
                except Exception as exc:
                    self.file_done.emit(filename, "FAILED")
                    self.log.emit(f"[ERROR] {filename}: {exc}", True)

                completed += 1
                self.progress.emit(int(completed / total * 100))

        self.finished.emit()

    def _upload_worker(self, file_path: str, upload_url: str, headers: dict) -> tuple[str, tuple[str, bool] | None]:
        """
        Worker thread function.
        Returns -> (result_label_str, (log_msg_str, is_err_bool) | None)
        """
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
                        "fileCreatedAt": _file_created_iso(file_path),
                        "fileModifiedAt": _file_created_iso(file_path),
                        "isFavorite":    "false",
                    },
                    timeout=120,
                )

            if resp.status_code in (200, 201):
                return ("uploaded", None)
            elif resp.status_code == 409:
                return ("duplicate (skipped)", None)
            else:
                return (f"error {resp.status_code}", (f"[WARN] {filename}: HTTP {resp.status_code} — {resp.text[:80]}", True))

        except Exception as exc:
            return ("FAILED", (f"[ERROR] {filename}: {exc}", True))


def _file_created_iso(path: str) -> str:
    """
    Return the file's creation time as an ISO-8601 string.
    - macOS:   st_birthtime  (true creation time)
    - Windows: st_ctime      (creation time on NTFS)
    - Linux:   st_mtime      (no creation time available, fall back to mtime)
    """
    import datetime
    import sys
    stat = os.stat(path)
    if sys.platform == "darwin":
        ts = getattr(stat, "st_birthtime", stat.st_mtime)
    elif sys.platform.startswith("win"):
        ts = stat.st_ctime          # st_ctime = creation time on Windows NTFS
    else:
        ts = stat.st_mtime          # Linux fallback
    return datetime.datetime.fromtimestamp(ts).isoformat()



class ConnectionTestThread(QThread):
    """
    Runs UploaderThread.test_connection() off the main thread so the UI
    never freezes while waiting for a server response.

    Signals:
        result(ok: bool, message: str)
    """

    result = Signal(bool, str)

    def __init__(self, server_url: str, api_key: str, timeout: int = 10, parent=None):
        super().__init__(parent)
        self._url     = server_url
        self._key     = api_key
        self._timeout = timeout

    def run(self):
        ok, msg = UploaderThread.test_connection(self._url, self._key, self._timeout)
        self.result.emit(ok, msg)

