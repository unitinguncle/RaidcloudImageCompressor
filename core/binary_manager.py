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
    """Runs an immich-go command and streams its output dynamically."""

    output_line       = Signal(str, bool)  # (line, is_stderr)
    process_done      = Signal(int)        # return code
    log_file_detected = Signal(str)        # emits path to immich-go's log file

    def __init__(self, cmd: list[str], parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self._proc = None

    def run(self):
        import subprocess
        import os
        import sys
        import re

        kwargs = {}
        # Ensure we can kill the entire process tree on cancellation
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["preexec_fn"] = os.setsid

        _log_pat = re.compile(r"Log file:\s*(.+)")

        try:
            self._proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1, # Line-buffered output
                encoding="utf-8",
                errors="replace",
                **kwargs
            )

            # Iterates dynamically, freeing us from trailing buffer issues
            for line in iter(self._proc.stdout.readline, ""):
                if not line:
                    break
                # Replace carriage returns as immich-go sometimes mixes \r and \n in progress status
                line = line.replace('\r', '\n')
                for subline in line.split('\n'):
                    if subline:
                        subline = subline.strip()
                        # Detect the log file path and emit it for the log tailer
                        m = _log_pat.search(subline)
                        if m:
                            self.log_file_detected.emit(m.group(1).strip())
                        self.output_line.emit(subline, False)

            rc = self._proc.wait()
            self.process_done.emit(rc)
        except Exception as exc:
            self.output_line.emit(f"[ERROR] {exc}", True)
            self.process_done.emit(-1)

    def terminate_process(self):
        import subprocess
        import signal
        import os
        import sys

        if self._proc and self._proc.poll() is None:
            try:
                # Terminate the process group to ensure spawned children are also killed
                if sys.platform.startswith("win"):
                    # For Windows we send CTRL_BREAK to the new process group
                    os.kill(self._proc.pid, signal.CTRL_BREAK_EVENT)
                else:
                    # For Unix we kill the session id equal to process group
                    os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except Exception as exc:
                print(f"[BinaryManager] Failed to kill process tree: {exc}")
                self._proc.terminate() # fallback


class LogFileTailerThread(QThread):
    """Tails an immich-go log file and emits new lines as they are written."""

    new_line = Signal(str)   # emits each new line from the log file

    def __init__(self, log_path: str, parent=None):
        super().__init__(parent)
        self._log_path = log_path
        self._stop = False

    def run(self):
        import time
        # Wait for the file to be created (up to 5 s)
        waited = 0
        while not os.path.exists(self._log_path) and waited < 50:
            time.sleep(0.1)
            waited += 1

        if not os.path.exists(self._log_path):
            return  # file never appeared, give up

        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
                # Read from the beginning so we never miss lines written before the tailer starts
                while not self._stop:
                    line = f.readline()
                    if line:
                        self.new_line.emit(line.rstrip("\r\n"))
                    else:
                        time.sleep(0.05)  # short sleep when no new data
        except Exception as exc:
            self.new_line.emit(f"[LogTailer ERROR] {exc}")

    def stop(self):
        self._stop = True
