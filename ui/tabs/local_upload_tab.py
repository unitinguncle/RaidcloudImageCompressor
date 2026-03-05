"""
ui/tabs/local_upload_tab.py — Local folder upload via immich-go CLI.
Ported and restyled from shitan198u/immich-go-gui.
"""

import os

from PySide6.QtCore    import Qt, QDate
from PySide6.QtGui     import QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QGroupBox, QTextEdit, QCheckBox, QDateEdit,
    QScrollArea, QFrame, QSizePolicy,
)

from core.config         import AppConfig
from core.binary_manager import (
    RunCommandThread, DownloadBinaryThread,
    get_default_binary_path,
)
from ui.theme import (
    ACCENT, TEXT_MUTED, TEXT_SUCCESS, TEXT_ERROR, FONT_MONO, BG_CARD, BORDER,
)


class LocalUploadTab(QWidget):

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config  = config
        self._runner: RunCommandThread | None = None
        self.setAcceptDrops(True)
        self._build_ui()
        self._load()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        title = QLabel("📁  LOCAL FOLDER UPLOAD")
        title.setFont(QFont(FONT_MONO, 16, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Upload any local folder directly to Immich using immich-go with advanced filtering."
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
        v.addWidget(self._build_filter_group())
        v.addWidget(self._build_server_group())
        v.addWidget(self._build_preview_group())
        v.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)
        outer.addWidget(self._build_action_area())

    def _build_source_group(self) -> QGroupBox:
        grp = QGroupBox("SOURCE FOLDER  (drag & drop supported)")
        v = QVBoxLayout(grp)
        v.setSpacing(8)

        row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Select the folder to upload…")
        self.source_edit.textChanged.connect(self._update_preview)
        browse_btn = QPushButton("Browse")
        browse_btn.setProperty("class", "secondary")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse)
        row.addWidget(self.source_edit)
        row.addWidget(browse_btn)
        v.addLayout(row)

        self.drop_hint = QLabel("  ↓  or drag & drop a folder here")
        self.drop_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;")
        v.addWidget(self.drop_hint)
        return grp

    def _build_filter_group(self) -> QGroupBox:
        grp = QGroupBox("FILTERS & OPTIONS")
        form = QFormLayout(grp)
        form.setSpacing(10)

        # Extension filter
        self.ext_edit = QLineEdit()
        self.ext_edit.setPlaceholderText("e.g. jpg,jpeg,png,cr2  (leave blank for all)")
        self.ext_edit.textChanged.connect(self._update_preview)
        form.addRow("Extensions:", self.ext_edit)

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

        self.use_date_cb = QCheckBox("Enable date range filter")
        self.use_date_cb.stateChanged.connect(self._update_preview)
        form.addRow("", self.use_date_cb)

        # Album name
        self.album_edit = QLineEdit()
        self.album_edit.setPlaceholderText("Optional — creates an album with this name")
        self.album_edit.textChanged.connect(self._update_preview)
        form.addRow("Album Name:", self.album_edit)

        # Recursive
        self.recursive_cb = QCheckBox("Scan sub-folders recursively")
        self.recursive_cb.setChecked(True)
        self.recursive_cb.stateChanged.connect(self._update_preview)
        form.addRow("", self.recursive_cb)

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
        self.run_btn = QPushButton("▶  RUN LOCAL UPLOAD")
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
    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", self.config.last_source_folder or ""
        )
        if folder:
            self.source_edit.setText(folder)
            self.config.last_source_folder = folder

    def _build_command(self) -> list[str]:
        binary = self.config.binary_path_override or get_default_binary_path()
        server = self.server_edit.text().strip()
        key    = self.key_edit.text().strip()
        source = self.source_edit.text().strip()

        cmd = [binary, "upload", "--server", server, "--api-key", key]

        exts = [e.strip().lstrip(".") for e in self.ext_edit.text().split(",") if e.strip()]
        for ext in exts:
            cmd += ["--include-extension", ext]

        if self.use_date_cb.isChecked():
            cmd += ["--date-range",
                    f"{self.date_start.date().toString('yyyy-MM-dd')},"
                    f"{self.date_end.date().toString('yyyy-MM-dd')}"]

        album = self.album_edit.text().strip()
        if album:
            cmd += ["--album", album]

        if self.recursive_cb.isChecked():
            cmd.append("--recursive")

        cmd.append(source)
        return cmd

    def _update_preview(self):
        try:
            cmd = self._build_command()
            # Mask API key in display
            display = []
            mask_next = False
            for part in cmd:
                if mask_next:
                    display.append("***")
                    mask_next = False
                elif part == "--api-key":
                    display.append(part)
                    mask_next = True
                else:
                    display.append(part)
            self.preview_edit.setPlainText(" ".join(display))
        except Exception:
            pass

    def _run(self):
        source = self.source_edit.text().strip()
        if not source:
            self._log("⚠ Please select a source folder.", True)
            return
        if not self.server_edit.text().strip() or not self.key_edit.text().strip():
            self._log("⚠ Server URL and API key are required.", True)
            return

        cmd    = self._build_command()
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
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._runner = RunCommandThread(cmd, self)
        self._runner.output_line.connect(self._log)
        self._runner.process_done.connect(self._on_done)
        self._runner.start()

    def _cancel(self):
        if self._runner:
            self._runner.terminate_process()
        self.cancel_btn.setEnabled(False)

    def _on_done(self, rc: int):
        color = TEXT_SUCCESS if rc == 0 else TEXT_ERROR
        msg   = "✓ Upload complete." if rc == 0 else f"✗ Process exited with code {rc}."
        self.log_edit.append(f'<span style="color:{color};font-weight:bold;">{msg}</span>')
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _log(self, msg: str, is_err: bool = False):
        color = TEXT_ERROR if is_err else "#A8BFCA"
        self.log_edit.append(f'<span style="color:{color};">{msg}</span>')

    def _load(self):
        self.server_edit.setText(self.config.server_url)
        self.key_edit.setText(self.config.api_key)
        self._update_preview()
