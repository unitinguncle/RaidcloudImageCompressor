"""
ui/tabs/google_takeout_tab.py — Upload Google Takeout archives to Immich.
Ported and restyled from shitan198u/immich-go-gui.
"""

import os
import sys

from PySide6.QtCore    import Qt, QDate, QTimer
from PySide6.QtGui     import QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QGroupBox, QTextEdit, QCheckBox, QDateEdit,
    QScrollArea, QFrame, QComboBox, QSizePolicy, QProgressBar
)

from core.config         import AppConfig
from core.binary_manager import (
    RunCommandThread, DownloadBinaryThread, LogFileTailerThread,
    get_default_binary_path,
)
from ui.theme import (
    ACCENT, TEXT_MUTED, TEXT_SUCCESS, TEXT_ERROR, FONT_MONO, BG_CARD, BORDER,
)
import re


class GoogleTakeoutTab(QWidget):

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config   = config
        self._runner: RunCommandThread | None = None
        self._tailer: LogFileTailerThread | None = None
        self._spin_idx      = 0
        self._net_sent_prev = 0
        self._net_recv_prev = 0
        # Heartbeat timer drives spinner + network speed
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(500)
        self._heartbeat.timeout.connect(self._heartbeat_tick)
        self.setAcceptDrops(True)
        self._build_ui()
        self._load()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        title = QLabel("🌐  GOOGLE TAKEOUT UPLOAD")
        title.setFont(QFont(FONT_MONO, 16, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Import photos from a Google Takeout archive (zip or folder) using immich-go."
        )
        subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setSpacing(14)
        v.setContentsMargins(0, 0, 8, 0)

        v.addWidget(self._build_source_group())
        v.addWidget(self._build_options_group())
        v.addWidget(self._build_server_group())
        v.addWidget(self._build_preview_group())
        v.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)
        outer.addWidget(self._build_action_area())

    def _build_source_group(self) -> QGroupBox:
        grp = QGroupBox("TAKEOUT SOURCE  (drag & drop supported)")
        v = QVBoxLayout(grp)
        v.setSpacing(8)

        row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Path to Takeout .zip file or extracted folder…")
        self.source_edit.textChanged.connect(self._update_preview)
        zip_btn = QPushButton("Select ZIP")
        zip_btn.setProperty("class", "secondary")
        zip_btn.clicked.connect(self._browse_zip)
        folder_btn = QPushButton("Select Folder")
        folder_btn.setProperty("class", "secondary")
        folder_btn.clicked.connect(self._browse_folder)
        row.addWidget(self.source_edit)
        row.addWidget(zip_btn)
        row.addWidget(folder_btn)
        v.addLayout(row)

        self.drop_hint = QLabel("  ↓  or drag & drop a zip / folder here")
        self.drop_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;")
        v.addWidget(self.drop_hint)
        return grp

    def _build_options_group(self) -> QGroupBox:
        grp = QGroupBox("OPTIONS")
        form = QFormLayout(grp)
        form.setSpacing(10)

        # Date range
        date_row = QHBoxLayout()
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setDate(QDate(2000, 1, 1))
        self.date_start.dateChanged.connect(self._update_preview)
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDate(QDate.currentDate())
        self.date_end.dateChanged.connect(self._update_preview)
        lbl_to = QLabel("to")
        lbl_to.setStyleSheet(f"color: {TEXT_MUTED};")
        date_row.addWidget(self.date_start)
        date_row.addWidget(lbl_to)
        date_row.addWidget(self.date_end)
        date_row.addStretch()
        form.addRow("Date Range:", date_row)

        self.use_date_range = QCheckBox("Enable date range filter")
        self.use_date_range.stateChanged.connect(self._update_preview)
        form.addRow("", self.use_date_range)

        self.album_cb = QCheckBox("Group by albums from Takeout metadata")
        self.album_cb.setChecked(True)
        self.album_cb.stateChanged.connect(self._update_preview)
        form.addRow("Albums:", self.album_cb)

        self.create_album_edit = QLineEdit()
        self.create_album_edit.setPlaceholderText("Optional album name override")
        self.create_album_edit.textChanged.connect(self._update_preview)
        form.addRow("Album Name:", self.create_album_edit)

        return grp

    def _build_server_group(self) -> QGroupBox:
        grp = QGroupBox("SERVER  (auto-filled from Settings)")
        form = QFormLayout(grp)
        form.setSpacing(10)

        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("https://your-immich-server.com")
        self.server_edit.textChanged.connect(self._update_preview)
        form.addRow("Server URL:", self.server_edit)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("API Key")
        self.key_edit.textChanged.connect(self._update_preview)
        form.addRow("API Key:", self.key_edit)

        return grp

    def _build_preview_group(self) -> QGroupBox:
        grp = QGroupBox("COMMAND PREVIEW")
        v = QVBoxLayout(grp)
        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFixedHeight(60)
        self.preview_edit.setStyleSheet(f"font-family: '{FONT_MONO}'; font-size: 11px;")
        v.addWidget(self.preview_edit)
        return grp

    def _build_action_area(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {BG_CARD}; border-radius: 8px;")
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("▶  RUN GOOGLE TAKEOUT UPLOAD")
        self.run_btn.setFixedHeight(38)
        self.run_btn.setFont(QFont(FONT_MONO, 11, QFont.Bold))
        self.run_btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 #1A8ED4); color:#000; border-radius:6px; }}"
            f"QPushButton:hover {{ background:#1A8ED4; color:#fff; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
        )
        self.run_btn.clicked.connect(self._run)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setProperty("class", "danger")
        self.cancel_btn.setFixedHeight(38)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)

        btn_row.addWidget(self.run_btn, 3)
        btn_row.addWidget(self.cancel_btn, 1)
        v.addLayout(btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ border: none; background: #2A2A2A; border-radius: 4px; }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
        """)
        self.progress_bar.hide()
        v.addWidget(self.progress_bar)

        self.progress_labels = QLabel("")
        self.progress_labels.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.progress_labels.hide()
        v.addWidget(self.progress_labels)

        self.speed_label = QLabel("")
        self.speed_label.setStyleSheet("color: #4FC3F7; font-size: 11px; font-family: monospace;")
        self.speed_label.hide()
        v.addWidget(self.speed_label)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFixedHeight(130)
        self.log_edit.setPlaceholderText("immich-go output will appear here…")
        v.addWidget(self.log_edit)

        return w

    # ── Drag & Drop ───────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self.source_edit.setText(urls[0].toLocalFile())
        self._update_preview()

    # ── Logic ─────────────────────────────────────────────────────────────────
    def _browse_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Google Takeout ZIP", "", "ZIP Files (*.zip);;All Files (*)"
        )
        if path:
            self.source_edit.setText(path)
            self.config.last_takeout_path = path

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Google Takeout Folder", self.config.last_takeout_path or ""
        )
        if folder:
            self.source_edit.setText(folder)
            self.config.last_takeout_path = folder

    def _build_command(self) -> list[str]:
        binary = self.config.binary_path_override or get_default_binary_path()
        server = self.server_edit.text().strip()
        key    = self.key_edit.text().strip()
        source = self.source_edit.text().strip()

        cmd = [binary, "upload", "from-google-photos",
               "--server", server, "--api-key", key, "--pause-immich-jobs=false",
               "--no-ui", "--on-errors", "continue"]

        if self.use_date_range.isChecked():
            cmd += ["--date-range",
                    f"{self.date_start.date().toString('yyyy-MM-dd')},"
                    f"{self.date_end.date().toString('yyyy-MM-dd')}"]

        if not self.album_cb.isChecked():
            cmd.append("--no-albums")

        album_name = self.create_album_edit.text().strip()
        if album_name:
            cmd += ["--album", album_name]

        cmd.append(source)
        return cmd

    def _update_preview(self):
        try:
            cmd = self._build_command()
            safe = [c if "api-key" not in str(prev) else "***"
                    for prev, c in zip([""] + cmd, cmd)]
            self.preview_edit.setPlainText(" ".join(safe))
        except Exception:
            pass

    def _run(self):
        cmd = self._build_command()
        source = self.source_edit.text().strip()
        if not source:
            self._log("⚠ Please select a Takeout source.", True)
            return
        if not self.server_edit.text().strip() or not self.key_edit.text().strip():
            self._log("⚠ Server URL and API key are required.", True)
            return

        binary = cmd[0]
        if not os.path.isfile(binary):
            self._log("immich-go binary not found — downloading…")
            self._download_binary(cmd)
            return

        self._execute(cmd)

    def _download_binary(self, cmd_after: list[str]):
        self.run_btn.setEnabled(False)
        dl = DownloadBinaryThread(parent=self)
        dl.status_msg.connect(self._log)
        dl.progress.connect(lambda p: self._log(f"Download: {p}%") if p % 20 == 0 else None)
        def _on_ok(_path):
            self.run_btn.setEnabled(True)
            self._execute(cmd_after)
        def _on_err(msg):
            self.run_btn.setEnabled(True)
            self._log(f"Download failed: {msg}", True)
        dl.finished_ok.connect(_on_ok)
        dl.finished_err.connect(_on_err)
        dl.start()

    def _execute(self, cmd: list[str]):
        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_labels.setText("Starting process...")
        self.progress_labels.show()
        # Reset progress counters
        self._cnt_found = 0
        self._cnt_uploaded = 0
        self._cnt_errors = 0
        self._cnt_dupes = 0
        self._prev_uploaded = -1
        self._prev_errors = -1
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._runner = RunCommandThread(cmd, self)
        self._runner.output_line.connect(self._log)
        self._runner.log_file_detected.connect(self._start_log_tailer)
        self._runner.process_done.connect(self._on_done)
        self._runner.start()
        # Kick off heartbeat for spinner + speed
        try:
            import psutil
            c = psutil.net_io_counters()
            self._net_sent_prev = c.bytes_sent
            self._net_recv_prev = c.bytes_recv
        except Exception:
            self._net_sent_prev = self._net_recv_prev = 0
        self.speed_label.show()
        self._heartbeat.start()

    def _start_log_tailer(self, log_path: str):
        """Start tailing the immich-go log file and pipe its lines to _log."""
        if self._tailer:
            self._tailer.stop()
            self._tailer.wait()
        self._tailer = LogFileTailerThread(log_path, self)
        self._tailer.new_line.connect(lambda line: self._log(line, False))
        self._tailer.start()

    def _cancel(self):
        if self._runner:
            self._runner.terminate_process()
        if self._tailer:
            self._tailer.stop()
        self._heartbeat.stop()
        self.speed_label.hide()
        self.cancel_btn.setEnabled(False)

    def _on_done(self, rc: int):
        self._heartbeat.stop()
        self.speed_label.hide()
        color = TEXT_SUCCESS if rc == 0 else TEXT_ERROR
        msg   = "✓ Upload complete." if rc == 0 else f"✗ Process exited with code {rc}."
        self.log_edit.append(f'<span style="color:{color};font-weight:bold;">{msg}</span>')
        self.progress_bar.setValue(100 if rc == 0 else self.progress_bar.value())
        if self._tailer:
            self._tailer.stop()
            self._tailer = None
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    _SPINNER = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]

    def _heartbeat_tick(self):
        """Called every 500 ms while upload is running. Animates spinner & shows net speed."""
        # Spinner
        spin = self._SPINNER[self._spin_idx % len(self._SPINNER)]
        self._spin_idx += 1

        # Network speed via psutil
        up_str = dn_str = "--"
        try:
            import psutil
            c = psutil.net_io_counters()
            sent_delta = c.bytes_sent - self._net_sent_prev
            recv_delta = c.bytes_recv - self._net_recv_prev
            self._net_sent_prev = c.bytes_sent
            self._net_recv_prev = c.bytes_recv
            # Convert bytes/0.5s to KB/s or MB/s
            def _fmt(bps):
                bps = bps * 2  # per 500ms interval → per second
                if bps >= 1_048_576:
                    return f"{bps/1_048_576:.1f} MB/s"
                elif bps >= 1024:
                    return f"{bps/1024:.0f} KB/s"
                return f"{bps} B/s"
            up_str = _fmt(sent_delta)
            dn_str = _fmt(recv_delta)
        except Exception:
            pass

        self.speed_label.setText(f"{spin}  ↑ Upload: {up_str}   ↓ Download: {dn_str}")

    # TUI summary line still written to stdout even with --no-ui:
    # e.g. "Immich read 100%, Assets found: 4829, Upload errors: 0, Uploaded 0"
    _PAT_TUI = re.compile(
        r"Assets found:\s*(\d+),\s*Upload errors:\s*(\d+),\s*Uploaded\s*(\d+)"
    )
    # Real new-upload confirmation lines
    _PAT_UPLOAD = re.compile(r"INF uploaded\b", re.IGNORECASE)
    # Duplicate / already-on-server lines
    _PAT_DUPE = re.compile(
        r"(?:INF server has duplicate|WRN discarded local duplicate|INF local duplicate)"
    )

    def _log(self, msg: str, is_err: bool = False):
        color = TEXT_ERROR if is_err else "#A8BFCA"

        # Primary source of truth: TUI summary line written to stdout
        m = self._PAT_TUI.search(msg)
        if m:
            total    = int(m.group(1))
            err_cnt  = int(m.group(2))
            uploaded = int(m.group(3))
            if total > 0:
                processed = self._cnt_dupes + uploaded + err_cnt
                pct = min(int(processed / total * 100), 100)
                self.progress_bar.setValue(pct)
            self.progress_labels.setText(
                f"Total: {total}  │  Uploaded: {uploaded}  │  Duplicates: {self._cnt_dupes}  │  Errors: {err_cnt}"
            )
            # Only show this line in the text box when something materially changed
            if uploaded != self._prev_uploaded or err_cnt != self._prev_errors:
                self._prev_uploaded = uploaded
                self._prev_errors   = err_cnt
                summary = f"[Progress] Total: {total} │ Uploaded: {uploaded} │ Duplicates: {self._cnt_dupes} │ Errors: {err_cnt}"
                self.log_edit.append(f'<span style="color:#6EC6E6;">{summary}</span>')
            return

        # Count duplicate events for the Duplicates counter
        if self._PAT_DUPE.search(msg):
            self._cnt_dupes += 1

        # Show all log lines in the text box
        self.log_edit.append(f'<span style="color:{color};">{msg}</span>')

    def _load(self):
        self.server_edit.setText(self.config.server_url)
        self.key_edit.setText(self.config.api_key)
        self._update_preview()
