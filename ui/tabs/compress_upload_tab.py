"""
ui/tabs/compress_upload_tab.py — "Compress & Upload" flagship tab.
Compresses images locally then optionally uploads to Immich via REST API.
"""

import os

from PySide6.QtCore    import Qt, QTimer
from PySide6.QtGui     import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QGroupBox, QProgressBar, QTextEdit, QCheckBox,
    QRadioButton, QButtonGroup, QSlider, QSizePolicy,
    QScrollArea, QFrame,
)

from core.compressor import CompressorThread, estimate_compressed_size, VALID_IMAGE_EXTENSIONS
from core.uploader   import UploaderThread
from core.config     import AppConfig
from ui.theme        import (
    ACCENT, BG_CARD, BG_INPUT, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, TEXT_SUCCESS, TEXT_ERROR, TEXT_WARNING,
    FONT_MONO, BORDER,
)


def _bytes_to_human(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


class CompressUploadTab(QWidget):

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._compressor: CompressorThread | None = None
        self._uploader:   UploaderThread   | None = None
        self._compressed_files: list[str] = []

        self._build_ui()
        self._load_from_config()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12)
        root.setSpacing(10)

        # ── Page title ──
        title_row = QHBoxLayout()
        title = QLabel("⚡  COMPRESS  &  UPLOAD")
        title.setFont(QFont(FONT_MONO, 14, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px;")
        title_row.addWidget(title)
        title_row.addStretch()
        subtitle = QLabel("Compress locally → upload to Immich")
        subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        title_row.addWidget(subtitle)
        root.addLayout(title_row)

        # ── Scrollable main content (two columns) ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content_v = QVBoxLayout(content)
        content_v.setContentsMargins(0, 0, 6, 0)
        content_v.setSpacing(10)

        # Two-column row
        cols = QHBoxLayout()
        cols.setSpacing(14)
        cols.addLayout(self._build_left_column(), 52)
        cols.addLayout(self._build_right_column(), 48)
        content_v.addLayout(cols)
        content_v.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # ── Action area (always visible at bottom) ──
        root.addWidget(self._build_action_area())

    def _build_left_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(10)

        # ── Source folder ──
        grp_src = QGroupBox("SOURCE FOLDER")
        src_v = QVBoxLayout(grp_src)
        src_v.setSpacing(6)

        row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Select a folder containing your images…")
        self.source_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse")
        browse_btn.setProperty("class", "secondary")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_source)
        row.addWidget(self.source_edit)
        row.addWidget(browse_btn)
        src_v.addLayout(row)

        info_row = QHBoxLayout()
        self.file_count_lbl = QLabel("No folder selected")
        self.file_count_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.est_size_lbl = QLabel("")
        self.est_size_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 11px; font-family: '{FONT_MONO}';")
        info_row.addWidget(self.file_count_lbl)
        info_row.addStretch()
        info_row.addWidget(self.est_size_lbl)
        src_v.addLayout(info_row)
        col.addWidget(grp_src)

        # ── Output folder ──
        grp_out = QGroupBox("OUTPUT FOLDER")
        out_h = QHBoxLayout(grp_out)
        out_h.setContentsMargins(10, 6, 10, 10)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Defaults to <source>/_compressed")
        out_btn = QPushButton("Browse")
        out_btn.setProperty("class", "secondary")
        out_btn.setFixedWidth(80)
        out_btn.clicked.connect(self._browse_output)
        out_h.addWidget(self.output_edit)
        out_h.addWidget(out_btn)
        col.addWidget(grp_out)

        # ── Format ──
        grp_fmt = QGroupBox("OUTPUT FORMAT & QUALITY")
        fmt_v = QVBoxLayout(grp_fmt)
        fmt_v.setSpacing(8)

        # Radio row
        radio_row = QHBoxLayout()
        self.fmt_jpeg = QRadioButton("JPEG")
        self.fmt_png  = QRadioButton("PNG")
        self.fmt_jpeg.setChecked(True)
        self._fmt_group = QButtonGroup()
        self._fmt_group.addButton(self.fmt_jpeg)
        self._fmt_group.addButton(self.fmt_png)
        self.fmt_jpeg.toggled.connect(self._update_format_visibility)
        radio_row.addWidget(self.fmt_jpeg)
        radio_row.addWidget(self.fmt_png)
        radio_row.addStretch()
        fmt_v.addLayout(radio_row)

        # JPEG quality
        self.jpeg_quality_lbl = QLabel("JPEG Quality: 85")
        self.jpeg_quality_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.jpeg_slider = QSlider(Qt.Horizontal)
        self.jpeg_slider.setRange(10, 95)
        self.jpeg_slider.setValue(85)
        self.jpeg_slider.valueChanged.connect(
            lambda v: self.jpeg_quality_lbl.setText(f"JPEG Quality: {v}")
        )
        fmt_v.addWidget(self.jpeg_quality_lbl)
        fmt_v.addWidget(self.jpeg_slider)

        # PNG compression
        self.png_compress_lbl = QLabel("PNG Compression Level: 6")
        self.png_compress_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.png_slider = QSlider(Qt.Horizontal)
        self.png_slider.setRange(0, 9)
        self.png_slider.setValue(6)
        self.png_slider.valueChanged.connect(
            lambda v: self.png_compress_lbl.setText(f"PNG Compression Level: {v}")
        )
        fmt_v.addWidget(self.png_compress_lbl)
        fmt_v.addWidget(self.png_slider)

        # EXIF checkbox
        self.preserve_exif_cb = QCheckBox("Preserve EXIF metadata")
        self.preserve_exif_cb.setChecked(True)
        fmt_v.addWidget(self.preserve_exif_cb)

        col.addWidget(grp_fmt)
        self._update_format_visibility()
        return col

    def _build_right_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(10)

        # ── Upload toggle ──
        grp_upload = QGroupBox("UPLOAD TO IMMICH")
        up_v = QVBoxLayout(grp_upload)
        up_v.setSpacing(8)

        # Toggle radios
        radio_row = QHBoxLayout()
        self.upload_yes = QRadioButton("Yes — upload after compress")
        self.upload_no  = QRadioButton("No — compress only")
        self.upload_no.setChecked(True)
        self._upload_group = QButtonGroup()
        self._upload_group.addButton(self.upload_yes)
        self._upload_group.addButton(self.upload_no)
        self.upload_yes.toggled.connect(self._toggle_upload_fields)
        radio_row.addWidget(self.upload_yes)
        radio_row.addWidget(self.upload_no)
        up_v.addLayout(radio_row)

        # Server URL
        self.server_url_lbl = QLabel("Server URL")
        self.server_url_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.server_url_edit = QLineEdit()
        self.server_url_edit.setPlaceholderText("https://your-immich-server.com")
        up_v.addWidget(self.server_url_lbl)
        up_v.addWidget(self.server_url_edit)

        # API Key
        self.api_key_lbl = QLabel("API Key")
        self.api_key_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        api_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Paste your Immich API key…")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setProperty("class", "secondary")
        self.show_key_btn.setFixedWidth(56)
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.toggled.connect(
            lambda on: (
                self.api_key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password),
                self.show_key_btn.setText("Hide" if on else "Show"),
            )
        )
        api_row.addWidget(self.api_key_edit)
        api_row.addWidget(self.show_key_btn)
        up_v.addWidget(self.api_key_lbl)
        up_v.addLayout(api_row)

        # Test connection
        test_row = QHBoxLayout()
        self.test_conn_btn = QPushButton("Test Connection")
        self.test_conn_btn.setProperty("class", "secondary")
        self.test_conn_btn.setFixedHeight(30)
        self.test_conn_btn.clicked.connect(self._test_connection)
        test_row.addWidget(self.test_conn_btn)
        test_row.addStretch()
        up_v.addLayout(test_row)

        self.conn_status_lbl = QLabel("")
        self.conn_status_lbl.setStyleSheet(f"font-size: 11px; font-family: '{FONT_MONO}';")
        up_v.addWidget(self.conn_status_lbl)

        col.addWidget(grp_upload)

        # ── Session summary ──
        grp_sum = QGroupBox("SESSION SUMMARY")
        sum_grid = QGridLayout(grp_sum)
        sum_grid.setColumnStretch(1, 1)
        sum_grid.setVerticalSpacing(6)

        self._sum_total    = self._make_summary_row(sum_grid, 0, "Total files")
        self._sum_success  = self._make_summary_row(sum_grid, 1, "Compressed OK")
        self._sum_failed   = self._make_summary_row(sum_grid, 2, "Failed")
        self._sum_uploaded = self._make_summary_row(sum_grid, 3, "Uploaded")
        self._sum_skipped  = self._make_summary_row(sum_grid, 4, "Skipped (dup)")
        col.addWidget(grp_sum)
        col.addStretch()

        self._toggle_upload_fields()
        return col

    def _make_summary_row(self, grid: QGridLayout, row: int, label: str) -> QLabel:
        key = QLabel(label)
        key.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        val = QLabel("—")
        val.setStyleSheet(f"color: {ACCENT}; font-family: '{FONT_MONO}'; font-size: 11px;")
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid.addWidget(key, row, 0)
        grid.addWidget(val, row, 1)
        return val

    def _build_action_area(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet(f"background: {BG_CARD}; border-radius: 8px;")
        v = QVBoxLayout(container)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(8)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(16)
        v.addWidget(self.progress_bar)

        # Buttons row
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("▶  COMPRESS & UPLOAD")
        self.run_btn.setFixedHeight(38)
        self.run_btn.setFont(QFont(FONT_MONO, 11, QFont.Bold))
        self.run_btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 #1A8ED4); color: #000; border-radius: 6px; }}"
            f"QPushButton:hover {{ background: #1A8ED4; color: #fff; }}"
            f"QPushButton:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}"
        )
        self.run_btn.clicked.connect(self._start)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setProperty("class", "danger")
        self.cancel_btn.setFixedHeight(38)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)

        btn_row.addWidget(self.run_btn, 3)
        btn_row.addWidget(self.cancel_btn, 1)
        v.addLayout(btn_row)

        # Log area
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFixedHeight(110)
        self.log_edit.setPlaceholderText("Activity log will appear here…")
        v.addWidget(self.log_edit)

        return container

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _browse_source(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Source Folder", self.config.last_source_folder or ""
        )
        if folder:
            self.source_edit.setText(folder)
            self.config.last_source_folder = folder
            self._scan_folder(folder)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self.config.last_output_folder or ""
        )
        if folder:
            self.output_edit.setText(folder)
            self.config.last_output_folder = folder

    def _scan_folder(self, folder: str):
        count = sum(
            1 for root, _, names in os.walk(folder)
            for n in names
            if os.path.splitext(n)[1].lower() in VALID_IMAGE_EXTENSIONS
        )
        self.file_count_lbl.setText(f"{count} image(s) found")
        self._sum_total.setText(str(count))
        self.est_size_lbl.setText("Estimating…")

        fmt = "JPEG" if self.fmt_jpeg.isChecked() else "PNG"
        jq  = self.jpeg_slider.value()
        pc  = self.png_slider.value()

        def _do_estimate():
            est, _ = estimate_compressed_size(folder, fmt, jq, pc)
            self.est_size_lbl.setText(f"≈ {_bytes_to_human(est)} compressed")

        QTimer.singleShot(50, _do_estimate)

    def _update_format_visibility(self):
        is_jpeg = self.fmt_jpeg.isChecked()
        self.jpeg_quality_lbl.setVisible(is_jpeg)
        self.jpeg_slider.setVisible(is_jpeg)
        self.png_compress_lbl.setVisible(not is_jpeg)
        self.png_slider.setVisible(not is_jpeg)

    def _toggle_upload_fields(self):
        enabled = self.upload_yes.isChecked()
        for w in (self.server_url_lbl, self.server_url_edit,
                  self.api_key_lbl, self.api_key_edit,
                  self.show_key_btn, self.test_conn_btn, self.conn_status_lbl):
            w.setEnabled(enabled)

    def _test_connection(self):
        url = self.server_url_edit.text().strip()
        key = self.api_key_edit.text().strip()
        if not url or not key:
            self.conn_status_lbl.setStyleSheet(f"color: {TEXT_WARNING}; font-size: 11px;")
            self.conn_status_lbl.setText("Enter URL and key first.")
            return
        self.conn_status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.conn_status_lbl.setText("Testing…")

        ok, msg = UploaderThread.test_connection(url, key)
        color = TEXT_SUCCESS if ok else TEXT_ERROR
        self.conn_status_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-family: '{FONT_MONO}';")
        self.conn_status_lbl.setText(msg)

        if ok:
            self.config.server_url = url
            self.config.api_key    = key

    def _log(self, msg: str, is_err: bool = False):
        color = TEXT_ERROR if is_err else TEXT_SECONDARY
        self.log_edit.append(f'<span style="color:{color};">{msg}</span>')

    def _start(self):
        source = self.source_edit.text().strip()
        if not source or not os.path.isdir(source):
            self._log("⚠ Please select a valid source folder.", True)
            return

        output = self.output_edit.text().strip() or os.path.join(source, "_compressed")
        fmt    = "JPEG" if self.fmt_jpeg.isChecked() else "PNG"
        jq     = self.jpeg_slider.value()
        pc     = self.png_slider.value()
        exif   = self.preserve_exif_cb.isChecked()

        self.config.output_format     = fmt
        self.config.jpeg_quality      = jq
        self.config.png_compression   = pc
        self.config.preserve_exif     = exif
        self.config.last_output_folder = output
        self.config.sync()

        self._compressed_files = []
        self._ok_count   = 0
        self._fail_count = 0
        self._up_count   = 0
        self._skip_count = 0

        self.progress_bar.setValue(0)
        self.log_edit.clear()
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._log(f"Starting compression → {output}")

        self._compressor = CompressorThread(source, output, fmt, jq, pc, exif, self)
        self._compressor.progress.connect(self._on_compress_progress)
        self._compressor.file_done.connect(self._on_compress_file)
        self._compressor.finished.connect(self._on_compress_done)
        self._compressor.start()

    def _cancel(self):
        if self._compressor and self._compressor.isRunning():
            self._compressor.cancel()
        if self._uploader and self._uploader.isRunning():
            self._uploader.cancel()
        self.cancel_btn.setEnabled(False)

    def _on_compress_progress(self, pct: int):
        self.progress_bar.setValue(pct)

    def _on_compress_file(self, filename: str, ok: bool, msg: str):
        if ok:
            self._ok_count += 1
            out_dir = (self.output_edit.text().strip() or
                       os.path.join(self.source_edit.text(), "_compressed"))
            self._compressed_files.append(os.path.join(out_dir, msg.lstrip("→ ").strip()))
            self._log(f"✓ {filename}  {msg}")
        else:
            self._fail_count += 1
            self._log(f"✗ {filename}: {msg}", True)

        self._sum_success.setText(str(self._ok_count))
        self._sum_failed.setText(str(self._fail_count))

    def _on_compress_done(self):
        self.progress_bar.setValue(100)
        self._log(f"Compression done. {self._ok_count} OK, {self._fail_count} failed.")

        if self.upload_yes.isChecked() and self._compressed_files:
            url = self.server_url_edit.text().strip()
            key = self.api_key_edit.text().strip()
            if not url or not key:
                self._log("⚠ Upload enabled but server URL / API key is missing.", True)
                self._finish()
                return
            self._log(f"Starting upload of {len(self._compressed_files)} file(s)…")
            self.progress_bar.setValue(0)
            self._uploader = UploaderThread(self._compressed_files, url, key, self)
            self._uploader.progress.connect(self.progress_bar.setValue)
            self._uploader.file_done.connect(self._on_upload_file)
            self._uploader.log.connect(self._log)
            self._uploader.finished.connect(self._on_upload_done)
            self._uploader.start()
        else:
            self._finish()

    def _on_upload_file(self, filename: str, status: str):
        if "uploaded" in status:
            self._up_count += 1
        elif "duplicate" in status:
            self._skip_count += 1
        self._log(f"↑ {filename} — {status}")
        self._sum_uploaded.setText(str(self._up_count))
        self._sum_skipped.setText(str(self._skip_count))

    def _on_upload_done(self):
        self._log(f"Upload complete. {self._up_count} uploaded, {self._skip_count} skipped.")
        self._finish()

    def _finish(self):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)

    def _load_from_config(self):
        self.server_url_edit.setText(self.config.server_url)
        self.api_key_edit.setText(self.config.api_key)
        self.jpeg_slider.setValue(self.config.jpeg_quality)
        self.png_slider.setValue(self.config.png_compression)
        self.preserve_exif_cb.setChecked(self.config.preserve_exif)
        if self.config.output_format == "PNG":
            self.fmt_png.setChecked(True)
        else:
            self.fmt_jpeg.setChecked(True)
        self._update_format_visibility()
