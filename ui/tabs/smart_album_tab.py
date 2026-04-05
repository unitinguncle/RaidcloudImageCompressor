"""
ui/tabs/smart_album_tab.py — Smart Album Upload tab.

Orchestrates uploading photos to:
  • Immich (owner account, into a named shared album)
  • RustFS on Unraid (S3 bucket, same album-named prefix)
  • CompreFace (face indexing, stored in local SQLite)
"""

import os

from PySide6.QtCore    import Qt, QTimer, QThread, Signal
from PySide6.QtGui     import QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QGroupBox, QTextEdit, QCheckBox, QRadioButton,
    QButtonGroup, QProgressBar, QScrollArea, QFrame,
    QSizePolicy, QComboBox, QListWidget, QListWidgetItem,
    QSplitter, QMessageBox, QApplication,
)

from core.config              import AppConfig
from core.face_db             import FaceDB
from core.album_orchestrator  import AlbumOrchestrator
from core.immich_api          import ImmichApi
from ui.theme import (
    ACCENT, ACCENT_DARK, BG_CARD, BG_INPUT, BORDER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_SUCCESS,
    TEXT_ERROR, TEXT_WARNING, FONT_MONO, FONT_UI,
)


class _AlbumLoaderThread(QThread):
    """Background thread: fetch existing album list from Immich."""
    loaded = Signal(list)   # list of {id, name}
    error  = Signal(str)

    def __init__(self, server_url, api_key, parent=None):
        super().__init__(parent)
        self._url = server_url
        self._key = api_key

    def run(self):
        try:
            api     = ImmichApi(self._url, self._key)
            albums  = api.list_albums()
            self.loaded.emit(albums)
        except Exception as exc:
            self.error.emit(str(exc))


class SmartAlbumTab(QWidget):
    """Smart Album Upload tab — combines Immich + RustFS + CompreFace."""

    def __init__(self, config: AppConfig, face_db: FaceDB, parent=None):
        super().__init__(parent)
        self.config    = config
        self.face_db   = face_db
        self._files:  list[str] = []
        self._albums: list[dict] = []          # cached Immich album list
        self._orchestrator: AlbumOrchestrator | None = None
        self._album_loader: _AlbumLoaderThread | None = None
        self._shared_link   = ""
        self._album_id      = ""

        self.setAcceptDrops(True)
        self._build_ui()
        self._load_from_config()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # Title
        title = QLabel("🎞  SMART ALBUM UPLOAD")
        title.setFont(QFont(FONT_MONO, 15, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Create a shared album → upload to Immich + RustFS → index faces with CompreFace."
        )
        subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        outer.addWidget(subtitle)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setSpacing(12)
        v.setContentsMargins(0, 0, 8, 0)

        v.addWidget(self._build_album_group())
        v.addWidget(self._build_files_group())
        v.addWidget(self._build_destinations_group())
        v.addWidget(self._build_sharing_group())
        v.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        outer.addWidget(self._build_action_area())

    # ── Group boxes ───────────────────────────────────────────────────────────

    def _build_album_group(self) -> QGroupBox:
        grp = QGroupBox("ALBUM SETUP")
        form = QFormLayout(grp)
        form.setSpacing(10)

        # Toggle: new vs existing
        radio_row = QHBoxLayout()
        self.radio_new      = QRadioButton("Create new")
        self.radio_existing = QRadioButton("Use existing")
        self.radio_new.setChecked(True)
        self._album_mode_grp = QButtonGroup()
        self._album_mode_grp.addButton(self.radio_new)
        self._album_mode_grp.addButton(self.radio_existing)
        self.radio_new.toggled.connect(self._toggle_album_fields)
        radio_row.addWidget(self.radio_new)
        radio_row.addWidget(self.radio_existing)
        radio_row.addStretch()
        form.addRow("Mode:", radio_row)

        # New album name
        self.album_name_edit = QLineEdit()
        self.album_name_edit.setPlaceholderText("e.g.  Wedding 2025")
        form.addRow("Album name:", self.album_name_edit)

        # Existing album picker
        picker_row = QHBoxLayout()
        self.album_combo = QComboBox()
        self.album_combo.setEnabled(False)
        self.album_combo.addItem("— select an album —")
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setProperty("class", "secondary")
        refresh_btn.setFixedWidth(90)
        refresh_btn.clicked.connect(self._load_albums)
        picker_row.addWidget(self.album_combo, 1)
        picker_row.addWidget(refresh_btn)
        form.addRow("Existing:", picker_row)

        self.album_status_lbl = QLabel("")
        self.album_status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        form.addRow("", self.album_status_lbl)

        self._toggle_album_fields()
        return grp

    def _build_files_group(self) -> QGroupBox:
        grp = QGroupBox("FILE SELECTION  (drag & drop supported)")
        v = QVBoxLayout(grp)
        v.setSpacing(8)

        # Drop zone hint
        self.drop_hint = QLabel("  ↓  Drag & drop files or a folder here, or use the buttons below")
        self.drop_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f"border: 1px dashed {BORDER}; border-radius: 6px; padding: 12px;"
        )
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setMinimumHeight(52)
        v.addWidget(self.drop_hint)

        btn_row = QHBoxLayout()
        add_files_btn  = QPushButton("+ Add Files")
        add_files_btn.setProperty("class", "secondary")
        add_folder_btn = QPushButton("📁 Add Folder")
        add_folder_btn.setProperty("class", "secondary")
        self.clear_btn = QPushButton("✕ Clear")
        self.clear_btn.setProperty("class", "danger")
        self.clear_btn.setEnabled(False)
        add_files_btn.clicked.connect(self._add_files)
        add_folder_btn.clicked.connect(self._add_folder)
        self.clear_btn.clicked.connect(self._clear_files)
        btn_row.addWidget(add_files_btn)
        btn_row.addWidget(add_folder_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.clear_btn)
        v.addLayout(btn_row)

        # File count badge + list
        self.file_count_lbl = QLabel("No files selected")
        self.file_count_lbl.setStyleSheet(f"color: {ACCENT}; font-family: '{FONT_MONO}'; font-size: 11px; font-weight: bold;")
        v.addWidget(self.file_count_lbl)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(100)
        self.file_list.setStyleSheet(
            f"QListWidget {{ background: {BG_INPUT}; border: 1px solid {BORDER}; "
            f"border-radius: 5px; font-size: 11px; font-family: '{FONT_MONO}'; }}"
        )
        v.addWidget(self.file_list)
        return grp

    def _build_destinations_group(self) -> QGroupBox:
        grp = QGroupBox("UPLOAD DESTINATIONS")
        v = QVBoxLayout(grp)
        v.setSpacing(8)

        self.dest_immich_cb = QCheckBox("☁  Upload to Immich  (owner account + shared album)")
        self.dest_immich_cb.setChecked(True)
        self.dest_rustfs_cb = QCheckBox("🗄  Upload to RustFS on Unraid  (S3 object storage)")
        self.dest_rustfs_cb.setChecked(True)
        self.dest_cf_cb     = QCheckBox("👤  Index faces with CompreFace")
        self.dest_cf_cb.setChecked(True)
        v.addWidget(self.dest_immich_cb)
        v.addWidget(self.dest_rustfs_cb)
        v.addWidget(self.dest_cf_cb)

        # CompreFace similarity threshold (shown when CompreFace checked)
        sim_row = QHBoxLayout()
        sim_lbl = QLabel("    Similarity threshold:")
        sim_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.sim_edit = QLineEdit()
        self.sim_edit.setText("0.85")
        self.sim_edit.setFixedWidth(60)
        self.sim_edit.setToolTip("0.0 – 1.0  (higher = stricter matching)")
        sim_row.addWidget(sim_lbl)
        sim_row.addWidget(self.sim_edit)
        sim_row.addStretch()
        v.addLayout(sim_row)

        return grp

    def _build_sharing_group(self) -> QGroupBox:
        grp = QGroupBox("IMMICH SHARING")
        v = QVBoxLayout(grp)
        v.setSpacing(8)

        radio_row = QHBoxLayout()
        self.share_link_rb  = QRadioButton("Generate public shared link")
        self.share_users_rb = QRadioButton("Share with Immich users (by UUID)")
        self.share_none_rb  = QRadioButton("No sharing")
        self.share_link_rb.setChecked(True)
        self._share_grp = QButtonGroup()
        for rb in (self.share_link_rb, self.share_users_rb, self.share_none_rb):
            self._share_grp.addButton(rb)
        self.share_link_rb.toggled.connect(self._toggle_share_fields)
        self.share_users_rb.toggled.connect(self._toggle_share_fields)
        for w in (self.share_link_rb, self.share_users_rb, self.share_none_rb):
            radio_row.addWidget(w)
        radio_row.addStretch()
        v.addLayout(radio_row)

        self.user_ids_edit = QTextEdit()
        self.user_ids_edit.setPlaceholderText("One Immich user UUID per line…")
        self.user_ids_edit.setFixedHeight(64)
        self.user_ids_edit.setEnabled(False)
        v.addWidget(self.user_ids_edit)

        return grp

    def _build_action_area(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {BG_CARD}; border-radius: 8px;")
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        # Phase label
        self.phase_lbl = QLabel("Ready")
        self.phase_lbl.setStyleSheet(
            f"color: {ACCENT}; font-family: '{FONT_MONO}'; font-size: 12px; font-weight: bold;"
        )
        v.addWidget(self.phase_lbl)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ border: none; background: #2A2A2A; border-radius: 4px; }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
        """)
        self.progress_bar.hide()
        v.addWidget(self.progress_bar)

        # Buttons
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("▶  RUN SMART UPLOAD")
        self.run_btn.setFixedHeight(38)
        self.run_btn.setFont(QFont(FONT_MONO, 11, QFont.Bold))
        self.run_btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 {ACCENT_DARK}); color:#000; border-radius:6px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; color:#fff; }}"
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

        # Results strip (hidden until complete)
        self.results_frame = QFrame()
        self.results_frame.setStyleSheet(
            f"background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px;"
        )
        results_v = QVBoxLayout(self.results_frame)
        results_v.setContentsMargins(10, 6, 10, 6)
        results_v.setSpacing(4)

        link_row = QHBoxLayout()
        self.link_lbl = QLabel("Shared link: —")
        self.link_lbl.setStyleSheet(f"color: {TEXT_SUCCESS}; font-size: 11px; font-family: '{FONT_MONO}';")
        self.copy_link_btn = QPushButton("📋 Copy")
        self.copy_link_btn.setProperty("class", "secondary")
        self.copy_link_btn.setFixedHeight(26)
        self.copy_link_btn.setFixedWidth(70)
        self.copy_link_btn.clicked.connect(self._copy_link)
        link_row.addWidget(self.link_lbl, 1)
        link_row.addWidget(self.copy_link_btn)
        results_v.addLayout(link_row)

        self.face_stats_lbl = QLabel("Face stats: —")
        self.face_stats_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        results_v.addWidget(self.face_stats_lbl)

        self.results_frame.hide()
        v.addWidget(self.results_frame)

        # Log
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(130)
        self.log_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_edit.setPlaceholderText("Upload activity will appear here…")
        v.addWidget(self.log_edit)

        return w

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self._add_dir(path)
            elif os.path.isfile(path):
                self._add_path(path)
        self._refresh_file_ui()

    # ── File management ───────────────────────────────────────────────────────

    _IMAGE_EXTS = {
        ".jpg", ".jpeg", ".png", ".heic", ".heif",
        ".tiff", ".tif", ".bmp", ".webp", ".gif", ".cr2", ".nef",
    }

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", self.config.last_source_folder or "",
            "Images (*.jpg *.jpeg *.png *.heic *.heif *.tiff *.bmp *.webp *.gif *.cr2 *.nef);;All files (*)"
        )
        for p in paths:
            self._add_path(p)
        self._refresh_file_ui()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", self.config.last_source_folder or ""
        )
        if folder:
            self.config.last_source_folder = folder
            self._add_dir(folder)
            self._refresh_file_ui()

    def _add_dir(self, folder: str):
        for root, _, names in os.walk(folder):
            for name in names:
                if os.path.splitext(name)[1].lower() in self._IMAGE_EXTS:
                    self._add_path(os.path.join(root, name))

    def _add_path(self, path: str):
        if path not in self._files:
            self._files.append(path)

    def _clear_files(self):
        self._files.clear()
        self._refresh_file_ui()

    def _refresh_file_ui(self):
        n = len(self._files)
        self.file_count_lbl.setText(
            f"{n} file(s) selected" if n else "No files selected"
        )
        self.clear_btn.setEnabled(bool(self._files))
        self.file_list.clear()
        # Show at most 200 entries to keep the list snappy
        for fp in self._files[:200]:
            self.file_list.addItem(os.path.basename(fp))
        if n > 200:
            self.file_list.addItem(f"… and {n - 200} more")

    # ── Album loading ─────────────────────────────────────────────────────────

    def _load_albums(self):
        url = self.config.server_url
        key = self.config.api_key
        if not url or not key:
            self.album_status_lbl.setStyleSheet(f"color: {TEXT_WARNING}; font-size: 11px;")
            self.album_status_lbl.setText("Configure Immich URL & API key in Settings first.")
            return
        self.album_status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.album_status_lbl.setText("Loading albums…")

        self._album_loader = _AlbumLoaderThread(url, key, self)
        self._album_loader.loaded.connect(self._on_albums_loaded)
        self._album_loader.error.connect(
            lambda e: (
                self.album_status_lbl.setStyleSheet(f"color: {TEXT_ERROR}; font-size: 11px;"),
                self.album_status_lbl.setText(f"Error: {e}"),
            )
        )
        self._album_loader.start()

    def _on_albums_loaded(self, albums: list):
        self._albums = albums
        self.album_combo.clear()
        self.album_combo.addItem("— select an album —", "")
        for a in albums:
            self.album_combo.addItem(a["name"], a["id"])
        self.album_status_lbl.setStyleSheet(f"color: {TEXT_SUCCESS}; font-size: 11px;")
        self.album_status_lbl.setText(f"{len(albums)} album(s) loaded.")

    # ── Toggle helpers ────────────────────────────────────────────────────────

    def _toggle_album_fields(self):
        new_mode = self.radio_new.isChecked()
        self.album_name_edit.setEnabled(new_mode)
        self.album_combo.setEnabled(not new_mode)

    def _toggle_share_fields(self):
        self.user_ids_edit.setEnabled(self.share_users_rb.isChecked())

    # ── Run / Cancel ──────────────────────────────────────────────────────────

    def _run(self):
        if not self._files:
            self._log("⚠ No files selected.", True)
            return

        # Album name / id
        if self.radio_new.isChecked():
            album_name = self.album_name_edit.text().strip()
            if not album_name:
                self._log("⚠ Please enter an album name.", True)
                return
            existing_id = ""
        else:
            idx = self.album_combo.currentIndex()
            existing_id = self.album_combo.itemData(idx) or ""
            album_name  = self.album_combo.currentText()
            if not existing_id:
                self._log("⚠ Please select an existing album.", True)
                return

        # Sharing
        if self.share_link_rb.isChecked():
            sharing_mode = "link"
            user_ids = []
        elif self.share_users_rb.isChecked():
            sharing_mode = "users"
            user_ids = [
                u.strip()
                for u in self.user_ids_edit.toPlainText().splitlines()
                if u.strip()
            ]
        else:
            sharing_mode = "none"
            user_ids = []

        # Similarity threshold
        try:
            sim = float(self.sim_edit.text())
            sim = max(0.0, min(1.0, sim))
        except ValueError:
            sim = 0.85

        # Prepare UI
        self.log_edit.clear()
        self.results_frame.hide()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.phase_lbl.setText("Preparing…")
        self._shared_link = ""
        self._album_id    = ""

        self._orchestrator = AlbumOrchestrator(
            files              = self._files,
            album_name         = album_name,
            immich_url         = self.config.server_url,
            immich_key         = self.config.api_key,
            use_immich         = self.dest_immich_cb.isChecked(),
            existing_album_id  = existing_id,
            sharing_mode       = sharing_mode,
            share_user_ids     = user_ids,
            rustfs_endpoint    = self.config.rustfs_endpoint,
            rustfs_access_key  = self.config.rustfs_access_key,
            rustfs_secret_key  = self.config.rustfs_secret_key,
            rustfs_bucket      = self.config.rustfs_bucket,
            use_rustfs         = self.dest_rustfs_cb.isChecked(),
            compreface_url     = self.config.compreface_url,
            compreface_api_key = self.config.compreface_api_key,
            use_compreface     = self.dest_cf_cb.isChecked(),
            sim_threshold      = sim,
            face_db            = self.face_db,
            parent             = self,
        )
        self._orchestrator.phase_changed.connect(self.phase_lbl.setText)
        self._orchestrator.progress.connect(self.progress_bar.setValue)
        self._orchestrator.file_done.connect(
            lambda fn, st: self._log(f"  {fn}  →  {st}")
        )
        self._orchestrator.album_created.connect(self._on_album_created)
        self._orchestrator.shared_link_ready.connect(self._on_shared_link)
        self._orchestrator.log.connect(self._log)
        self._orchestrator.finished.connect(self._on_done)
        self._orchestrator.start()

    def _cancel(self):
        if self._orchestrator:
            self._orchestrator.cancel()
        self.cancel_btn.setEnabled(False)

    def _on_album_created(self, album_id: str, name: str):
        self._album_id = album_id
        self._log(f"Album ready: '{name}'  (id: {album_id[:8]}…)")

    def _on_shared_link(self, url: str):
        self._shared_link = url
        self.link_lbl.setText(f"Shared link: {url}")
        self.results_frame.show()

    def _on_done(self):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)

        # Face stats
        if self._orchestrator and self.dest_cf_cb.isChecked():
            album_name = (
                self.album_name_edit.text().strip()
                if self.radio_new.isChecked()
                else self.album_combo.currentText()
            )
            try:
                st = self.face_db.stats(album_name)
                self.face_stats_lbl.setText(
                    f"Faces: {st['total']} indexed  │  "
                    f"{st['identified']} identified  │  "
                    f"{st['unknown']} unknown  │  "
                    f"{st['subjects']} subjects"
                )
                self.results_frame.show()
            except Exception:
                pass

        self._log(
            f'<span style="color:{TEXT_SUCCESS}; font-weight:bold;">✅  Upload complete.</span>',
            html=True,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _copy_link(self):
        if self._shared_link:
            QApplication.clipboard().setText(self._shared_link)
            self.copy_link_btn.setText("✓ Copied")
            QTimer.singleShot(2000, lambda: self.copy_link_btn.setText("📋 Copy"))

    def _log(self, msg: str, is_err: bool = False, *, html: bool = False):
        if html:
            self.log_edit.append(msg)
        else:
            color = TEXT_ERROR if is_err else TEXT_SECONDARY
            self.log_edit.append(f'<span style="color:{color};">{msg}</span>')

    def _load_from_config(self):
        """Reload server fields from config (called by main window after Settings save)."""
        pass  # fields are read at run-time from self.config
