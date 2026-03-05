"""
core/binary_manager.py — Download, update, and invoke the immich-go CLI binary.
Ported and enhanced from shitan198u/immich-go-gui.
"""

import io
import os
import sys
import platform
import zipfile
import tarfile
import requests

from PySide6.QtCore import QThread, Signal


GITHUB_API_URL = "https://api.github.com/repos/simulot/immich-go/releases/latest"


def _get_binary_dir() -> str:
    """Return the directory where the immich-go binary will be stored."""
    return os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), "immich-go"))


def get_binary_filename() -> str:
    return "immich-go.exe" if sys.platform.startswith("win") else "immich-go"


def get_default_binary_path() -> str:
    return os.path.join(_get_binary_dir(), get_binary_filename())


def get_latest_version() -> str | None:
    try:
        r = requests.get(GITHUB_API_URL, timeout=10)
        r.raise_for_status()
        return r.json().get("tag_name")
    except Exception as e:
        print(f"[BinaryManager] Failed to fetch latest version: {e}")
        return None


def get_download_url(version: str) -> str | None:
    os_name = sys.platform
    arch = platform.machine().lower()
    if arch in ("x64", "x86_64", "amd64"):
        arch = "x86_64"

    mapping = {
        ("win32",  "x86_64"): f"immich-go_Windows_x86_64.zip",
        ("win32",  "arm64"):  f"immich-go_Windows_arm64.zip",
        ("darwin", "x86_64"): f"immich-go_Darwin_x86_64.tar.gz",
        ("darwin", "arm64"):  f"immich-go_Darwin_arm64.tar.gz",
        ("linux",  "x86_64"): f"immich-go_Linux_x86_64.tar.gz",
        ("linux",  "arm64"):  f"immich-go_Linux_arm64.tar.gz",
    }
    filename = mapping.get((os_name, arch))
    if not filename:
        return None
    return f"https://github.com/simulot/immich-go/releases/download/{version}/{filename}"


class DownloadBinaryThread(QThread):
    """Downloads and extracts the immich-go binary in a background thread."""

    progress   = Signal(int)          # 0-100
    status_msg = Signal(str)
    finished_ok  = Signal(str)        # emits binary path on success
    finished_err = Signal(str)        # emits error message on failure

    def __init__(self, version: str | None = None, parent=None):
        super().__init__(parent)
        self._version = version

    def run(self):
        try:
            version = self._version or get_latest_version() or "0.22.1"
            self.status_msg.emit(f"Fetching immich-go {version}…")

            download_url = get_download_url(version)
            if not download_url:
                self.finished_err.emit("Unsupported platform — cannot determine download URL.")
                return

            self.status_msg.emit(f"Downloading from GitHub…")
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()

            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            buf = io.BytesIO()

            for chunk in response.iter_content(1024 * 64):
                buf.write(chunk)
                downloaded += len(chunk)
                if total:
                    self.progress.emit(int(downloaded / total * 100))

            self.progress.emit(100)
            self.status_msg.emit("Extracting…")

            binary_dir = _get_binary_dir()
            os.makedirs(binary_dir, exist_ok=True)
            binary_path = os.path.join(binary_dir, get_binary_filename())

            buf.seek(0)
            if download_url.endswith(".zip"):
                with zipfile.ZipFile(buf) as z:
                    for name in z.namelist():
                        base = os.path.basename(name)
                        if base in ("immich-go", "immich-go.exe"):
                            with z.open(name) as src, open(binary_path, "wb") as dst:
                                dst.write(src.read())
                            break
            elif download_url.endswith(".tar.gz"):
                with tarfile.open(fileobj=buf, mode="r:gz") as tar:
                    for member in tar.getmembers():
                        base = os.path.basename(member.name)
                        if base in ("immich-go", "immich-go.exe"):
                            src = tar.extractfile(member)
                            with open(binary_path, "wb") as dst:
                                dst.write(src.read())
                            break

            if not sys.platform.startswith("win"):
                os.chmod(binary_path, 0o755)

            self.status_msg.emit("immich-go ready.")
            self.finished_ok.emit(binary_path)

        except Exception as exc:
            self.finished_err.emit(str(exc))


class RunCommandThread(QThread):
    """Runs an immich-go command and streams its output line by line."""

    output_line  = Signal(str, bool)   # (line, is_stderr)
    process_done = Signal(int)         # return code

    def __init__(self, cmd: list[str], parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self._proc = None

    def run(self):
        import subprocess
        try:
            self._proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in self._proc.stdout:
                self.output_line.emit(line.rstrip(), False)
            rc = self._proc.wait()
            self.process_done.emit(rc)
        except Exception as exc:
            self.output_line.emit(f"[ERROR] {exc}", True)
            self.process_done.emit(-1)

    def terminate_process(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
