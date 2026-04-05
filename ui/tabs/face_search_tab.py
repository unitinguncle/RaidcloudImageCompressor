"""
ui/tabs/face_search_tab.py — Face Search tab.

Lets any user:
  1. Pick an indexed album from the local SQLite face DB.
  2. Drop or browse a probe photo of themselves.
  3. Run CompreFace recognition against that album's indexed subjects.
  4. Browse a grid of matched photos with similarity scores.
  5. Rename unknown subjects to real names.
"""

import os

from PySide6.QtCore    import Qt, QThread, Signal, QSize, QTimer
from PySide6.QtGui     import QFont, QPixmap, QDragEnterEvent, QDropEvent, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFileDialog, QGroupBox, QScrollArea, QFrame,
    QGridLayout, QSizePolicy, QTextEdit, QListWidget,
    QListWidgetItem, QInputDialog, QMessageBox, QApplication,
    QSplitter,
)

from core.config             import AppConfig
from core.face_db            import FaceDB
from core.compreface_client  import ComprefaceClient
from ui.theme import (
    ACCENT, ACCENT_DARK, BG_CARD, BG_INPUT, BORDER, BG_DARK,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_SUCCESS,
    TEXT_ERROR, TEXT_WARNING, FONT_MONO, FONT_UI,
)


# ── Background worker ─────────────────────────────────────────────────────────

class _RecognizeThread(QThread):
    """Runs CompreFace recognition off the GUI thread."""
    result  = Signal(str, float)   # (subject, similarity)
    no_match = Signal()
    error   = Signal(str)

    def __init__(self, cf_url, cf_key, image_path, sim_threshold, parent=None):
        super().__init__(parent)
        self._url    = cf_url
        self._key    = cf_key
        self._path   = image_path
        self._thresh = sim_threshold

    def run(self):
        try:
            client = ComprefaceClient(
                self._url, self._key, sim_threshold=self._thresh
            )
            match = client.best_match(self._path)
            if match:
                self.result.emit(match[0], match[1])
            else:
                self.no_match.emit()
        except Exception as exc:
            self.error.emit(str(exc))


# ── Thumbnail card ────────────────────────────────────────────────────────────

class _ThumbCard(QFrame):
    """A compact thumbnail card for one face-search result."""

    _THUMB_SIZE = 140

    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self.record = record
        self.setFixedSize(self._THUMB_SIZE + 16, self._THUMB_SIZE + 52)
        self.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; }}"
            f"QFrame:hover {{ border-color: {ACCENT}; }}"
        )

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # Thumbnail
        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(self._THUMB_SIZE, self._THUMB_SIZE)
        thumb_lbl.setAlignment(Qt.AlignCenter)
        thumb_lbl.setStyleSheet(f"background: {BG_INPUT}; border-radius: 4px;")

        # Try loading a cached thumbnail, fall back to placeholder
        thumb_path = record.get("thumb_path", "")
        if thumb_path and os.path.isfile(thumb_path):
            pix = QPixmap(thumb_path).scaled(
                self._THUMB_SIZE, self._THUMB_SIZE,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            thumb_lbl.setPixmap(pix)
        else:
            thumb_lbl.setText("🖼")
            thumb_lbl.setStyleSheet(
                f"font-size: 36px; background: {BG_INPUT}; border-radius: 4px;"
            )
        v.addWidget(thumb_lbl)

        # Filename label
        name_lbl = QLabel(record.get("filename", ""))
        name_lbl.setWordWrap(False)
        name_lbl.setStyleSheet(f"font-size: 9px; color: {TEXT_SECONDARY}; font-family: '{FONT_MONO}';")
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setMaximumWidth(self._THUMB_SIZE + 4)
        v.addWidget(name_lbl)

        # Similarity badge
        sim = record.get("similarity")
        if sim is not None:
            pct = int(sim * 100)
            color = TEXT_SUCCESS if pct >= 90 else (TEXT_WARNING if pct >= 75 else TEXT_ERROR)
            sim_lbl = QLabel(f"{pct}% match")
            sim_lbl.setAlignment(Qt.AlignCenter)
            sim_lbl.setStyleSheet(
                f"color: {color}; font-size: 9px; font-weight: bold; font-family: '{FONT_MONO}';"
            )
            v.addWidget(sim_lbl)


# ── Main tab ──────────────────────────────────────────────────────────────────

class FaceSearchTab(QWidget):
    """Face Search tab: probe a photo → see all matching images from an album."""

    def __init__(self, config: AppConfig, face_db: FaceDB, parent=None):
        super().__init__(parent)
        self.config     = config
        self.face_db    = face_db
        self._probe_path = ""
        self._recognizer: _RecognizeThread | None = None

        self.setAcceptDrops(True)
        self._build_ui()
        self._refresh_albums()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # Title
        title = QLabel("🔍  FACE SEARCH")
        title.setFont(QFont(FONT_MONO, 15, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Drop a photo of a person → find all their images in the selected album."
        )
        subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        outer.addWidget(subtitle)

        # Horizontal splitter: left = controls, right = results grid
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {BORDER}; }}")

        # ── Left panel ──────────────────────────────────────────────────────
        left = QWidget()
        left.setMaximumWidth(300)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(12)

        lv.addWidget(self._build_album_selector())
        lv.addWidget(self._build_probe_group())
        lv.addWidget(self._build_subject_mgmt_group())
        lv.addStretch()

        splitter.addWidget(left)

        # ── Right panel (results) ────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(8)

        self.results_lbl = QLabel("Results will appear here after a search.")
        self.results_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        rv.addWidget(self.results_lbl)

        # Scrollable grid
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setFrameShape(QFrame.NoFrame)
        self.results_container = QWidget()
        self.results_grid = QGridLayout(self.results_container)
        self.results_grid.setSpacing(10)
        self.results_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.results_scroll.setWidget(self.results_container)
        rv.addWidget(self.results_scroll, 1)

        splitter.addWidget(right)
        splitter.setSizes([280, 700])
        outer.addWidget(splitter, 1)

    def _build_album_selector(self) -> QGroupBox:
        grp = QGroupBox("SELECT ALBUM")
        v = QVBoxLayout(grp)
        v.setSpacing(8)

        row = QHBoxLayout()
        self.album_combo = QComboBox()
        self.album_combo.currentIndexChanged.connect(self._on_album_changed)
        refresh_btn = QPushButton("↻")
        refresh_btn.setProperty("class", "secondary")
        refresh_btn.setFixedWidth(34)
        refresh_btn.setToolTip("Refresh album list from database")
        refresh_btn.clicked.connect(self._refresh_albums)
        row.addWidget(self.album_combo, 1)
        row.addWidget(refresh_btn)
        v.addLayout(row)

        self.album_stats_lbl = QLabel("")
        self.album_stats_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-family: '{FONT_MONO}';")
        v.addWidget(self.album_stats_lbl)
        return grp

    def _build_probe_group(self) -> QGroupBox:
        grp = QGroupBox("PROBE PHOTO")
        v = QVBoxLayout(grp)
        v.setSpacing(8)

        # Drop zone
        self.probe_lbl = QLabel("Drop a photo here\nor click Browse")
        self.probe_lbl.setAlignment(Qt.AlignCenter)
        self.probe_lbl.setMinimumHeight(120)
        self.probe_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;"
            f"border: 2px dashed {BORDER}; border-radius: 8px;"
        )
        self.probe_lbl.setAcceptDrops(False)  # parent handles drag events
        v.addWidget(self.probe_lbl)

        browse_btn = QPushButton("📷 Browse Photo")
        browse_btn.setProperty("class", "secondary")
        browse_btn.clicked.connect(self._browse_probe)
        v.addWidget(browse_btn)

        self.probe_path_lbl = QLabel("")
        self.probe_path_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-family: '{FONT_MONO}';")
        self.probe_path_lbl.setWordWrap(True)
        v.addWidget(self.probe_path_lbl)

        self.search_btn = QPushButton("🔍  SEARCH FACES")
        self.search_btn.setFixedHeight(36)
        self.search_btn.setFont(QFont(FONT_MONO, 10, QFont.Bold))
        self.search_btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 {ACCENT_DARK}); color:#000; border-radius:6px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; color:#fff; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
        )
        self.search_btn.clicked.connect(self._run_search)
        self.search_btn.setEnabled(False)
        v.addWidget(self.search_btn)

        self.search_status_lbl = QLabel("")
        self.search_status_lbl.setStyleSheet(f"font-size: 11px; font-family: '{FONT_MONO}';")
        v.addWidget(self.search_status_lbl)

        return grp

    def _build_subject_mgmt_group(self) -> QGroupBox:
        grp = QGroupBox("SUBJECT MANAGEMENT")
        v = QVBoxLayout(grp)
        v.setSpacing(6)

        info = QLabel("Rename unknown subjects:")
        info.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        v.addWidget(info)

        self.subject_list = QListWidget()
        self.subject_list.setMaximumHeight(110)
        self.subject_list.setStyleSheet(
            f"QListWidget {{ background: {BG_INPUT}; border: 1px solid {BORDER}; "
            f"border-radius: 5px; font-size: 11px; font-family: '{FONT_MONO}'; }}"
            f"QListWidget::item:selected {{ background: {ACCENT_DARK}; }}"
        )
        v.addWidget(self.subject_list)

        rename_btn = QPushButton("✏  Rename Selected")
        rename_btn.setProperty("class", "secondary")
        rename_btn.setFixedHeight(30)
        rename_btn.clicked.connect(self._rename_subject)
        v.addWidget(rename_btn)

        return grp

    # ── Drag & Drop (probe photo) ─────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                self._set_probe(path)
                break

    # ── Album logic ───────────────────────────────────────────────────────────

    def _refresh_albums(self):
        albums = self.face_db.list_albums()
        self.album_combo.blockSignals(True)
        self.album_combo.clear()
        if albums:
            self.album_combo.addItems(albums)
        else:
            self.album_combo.addItem("— no indexed albums yet —")
        self.album_combo.blockSignals(False)
        self._on_album_changed()

    def _on_album_changed(self):
        album = self.album_combo.currentText()
        if not album or album.startswith("—"):
            self.album_stats_lbl.setText("")
            self.subject_list.clear()
            return
        try:
            st = self.face_db.stats(album)
            self.album_stats_lbl.setText(
                f"{st['total']} photos  │  {st['subjects']} subjects"
            )
            self._load_subjects(album)
        except Exception:
            pass

    def _load_subjects(self, album: str):
        subjects = self.face_db.list_subjects(album)
        self.subject_list.clear()
        for s in subjects:
            self.subject_list.addItem(s)

    # ── Probe photo ───────────────────────────────────────────────────────────

    def _browse_probe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Probe Photo", "",
            "Images (*.jpg *.jpeg *.png *.heic *.heif *.bmp *.webp);;All files (*)"
        )
        if path:
            self._set_probe(path)

    def _set_probe(self, path: str):
        self._probe_path = path
        self.probe_path_lbl.setText(os.path.basename(path))

        pix = QPixmap(path)
        if not pix.isNull():
            pix = pix.scaled(160, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.probe_lbl.setPixmap(pix)
            self.probe_lbl.setStyleSheet(
                f"border: 2px solid {ACCENT}; border-radius: 8px;"
            )
        else:
            self.probe_lbl.setText(f"📷 {os.path.basename(path)}")

        self.search_btn.setEnabled(True)

    # ── Search ────────────────────────────────────────────────────────────────

    def _run_search(self):
        album = self.album_combo.currentText()
        if not album or album.startswith("—"):
            self._set_status("Please select an album first.", TEXT_WARNING)
            return
        if not self._probe_path:
            self._set_status("Please select a probe photo first.", TEXT_WARNING)
            return

        cf_url = self.config.compreface_url
        cf_key = self.config.compreface_api_key
        sim    = self.config.similarity_threshold

        if not cf_url or not cf_key:
            # Offline mode — search the local DB directly using all subjects
            self._set_status("CompreFace not configured — showing all records for album.", TEXT_WARNING)
            records = self.face_db.query_by_album(album)
            self._show_results(records, label=f"All {len(records)} photos in '{album}'")
            return

        self.search_btn.setEnabled(False)
        self._set_status("Recognising face…", TEXT_MUTED)
        self._clear_grid()

        self._recognizer = _RecognizeThread(cf_url, cf_key, self._probe_path, sim, self)
        self._recognizer.result.connect(lambda s, sim: self._on_recognition(album, s, sim))
        self._recognizer.no_match.connect(lambda: self._on_no_match(album))
        self._recognizer.error.connect(self._on_search_error)
        self._recognizer.start()

    def _on_recognition(self, album: str, subject: str, similarity: float):
        self.search_btn.setEnabled(True)
        self._set_status(
            f"Identified as '{subject}'  ({similarity:.0%} confidence)", TEXT_SUCCESS
        )
        records = self.face_db.query_by_subject(album, subject)
        label   = f"{len(records)} photo(s) of '{subject}' in '{album}'"
        self._show_results(records, label=label)

    def _on_no_match(self, album: str):
        self.search_btn.setEnabled(True)
        self._set_status("No matching face found above threshold.", TEXT_WARNING)
        self._clear_grid()
        self.results_lbl.setText("No matching face found. Try a clearer photo or lower the similarity threshold in Settings.")

    def _on_search_error(self, msg: str):
        self.search_btn.setEnabled(True)
        self._set_status(f"Error: {msg}", TEXT_ERROR)

    # ── Results grid ──────────────────────────────────────────────────────────

    def _show_results(self, records: list[dict], label: str = ""):
        self._clear_grid()
        self.results_lbl.setText(label or f"{len(records)} result(s)")
        if not records:
            return

        cols = 5
        for idx, rec in enumerate(records):
            card = _ThumbCard(rec)
            self.results_grid.addWidget(card, idx // cols, idx % cols)

    def _clear_grid(self):
        while self.results_grid.count():
            item = self.results_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── Subject rename ────────────────────────────────────────────────────────

    def _rename_subject(self):
        album = self.album_combo.currentText()
        if not album or album.startswith("—"):
            return
        item = self.subject_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No subject selected", "Please select a subject to rename.")
            return
        old_name = item.text()
        new_name, ok = QInputDialog.getText(
            self, "Rename Subject",
            f"Rename '{old_name}' to:",
            text=old_name,
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            n = self.face_db.rename_subject(album, old_name, new_name.strip())
            QMessageBox.information(self, "Renamed", f"Renamed {n} record(s) from '{old_name}' → '{new_name}'.")
            self._load_subjects(album)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, color: str):
        self.search_status_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-family: '{FONT_MONO}';")
        self.search_status_lbl.setText(msg)

    def _load_from_config(self):
        """Called by main window after Settings save — refresh album list."""
        self._refresh_albums()
