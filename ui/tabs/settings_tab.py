"""
ui/tabs/settings_tab.py — App-wide settings (server, binary, advanced).
"""

from PySide6.QtCore    import Qt, Signal
from PySide6.QtGui     import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QGroupBox, QComboBox, QSpinBox, QFileDialog,
    QScrollArea, QFrame, QMessageBox,
)

from core.config  import AppConfig
from core.uploader import UploaderThread, ConnectionTestThread
from core.rustfs_uploader import RustFSUploader
from core.compreface_client import ComprefaceClient
from ui.theme import (
    ACCENT, TEXT_MUTED, TEXT_SUCCESS, TEXT_ERROR, TEXT_WARNING, FONT_MONO,
)


class SettingsTab(QWidget):

    settings_saved = Signal()  # emitted after every successful save

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._conn_tester: ConnectionTestThread | None = None
        self._build_ui()
        self._load()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        title = QLabel("⚙  SETTINGS")
        title.setFont(QFont(FONT_MONO, 16, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px;")
        outer.addWidget(title)

        subtitle = QLabel("Configure your Immich server connection and advanced options.")
        subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        outer.addWidget(subtitle)

        # Scroll area for settings content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setSpacing(14)
        v.setContentsMargins(0, 0, 8, 0)

        v.addWidget(self._build_connection_group())
        v.addWidget(self._build_binary_group())
        v.addWidget(self._build_advanced_group())
        v.addWidget(self._build_rustfs_group())
        v.addWidget(self._build_compreface_group())
        v.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)
        outer.addWidget(self._build_button_row())

    def _build_connection_group(self) -> QGroupBox:
        grp = QGroupBox("IMMICH SERVER")
        form = QFormLayout(grp)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setSpacing(10)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://your-immich-server.com")
        form.addRow("Server URL:", self.url_edit)

        api_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Immich API key")
        show_btn = QPushButton("Show")
        show_btn.setProperty("class", "secondary")
        show_btn.setCheckable(True)
        show_btn.toggled.connect(
            lambda on: (
                self.key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password),
                show_btn.setText("Hide" if on else "Show"),
            )
        )
        api_row.addWidget(self.key_edit)
        api_row.addWidget(show_btn)
        form.addRow("API Key:", api_row)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setProperty("class", "secondary")
        self.test_btn.clicked.connect(self._test_connection)
        self.conn_lbl = QLabel("")
        self.conn_lbl.setStyleSheet(f"font-size: 11px; font-family: '{FONT_MONO}';")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.conn_lbl)
        test_row.addStretch()
        form.addRow("", test_row)

        return grp

    def _build_binary_group(self) -> QGroupBox:
        grp = QGroupBox("IMMICH-GO BINARY")
        form = QFormLayout(grp)
        form.setSpacing(10)

        self.binary_edit = QLineEdit()
        self.binary_edit.setPlaceholderText("Leave blank to use auto-downloaded binary")
        bin_row = QHBoxLayout()
        browse_bin = QPushButton("Browse")
        browse_bin.setProperty("class", "secondary")
        browse_bin.clicked.connect(self._browse_binary)
        bin_row.addWidget(self.binary_edit)
        bin_row.addWidget(browse_bin)
        form.addRow("Binary Path:", bin_row)

        clear_btn = QPushButton("Clear (use auto-download)")
        clear_btn.setProperty("class", "secondary")
        clear_btn.clicked.connect(lambda: self.binary_edit.clear())
        form.addRow("", clear_btn)

        return grp

    def _build_advanced_group(self) -> QGroupBox:
        grp = QGroupBox("ADVANCED")
        form = QFormLayout(grp)
        form.setSpacing(10)

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARN", "ERROR"])
        self.log_level_combo.setCurrentText("INFO")
        form.addRow("Log Level:", self.log_level_combo)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 3600)
        self.timeout_spin.setValue(1200)
        self.timeout_spin.setSuffix(" sec")
        form.addRow("Client Timeout:", self.timeout_spin)

        self.recursive_cb = QCheckBox("Recursively scan sub-folders")
        self.recursive_cb.setChecked(True)
        form.addRow("", self.recursive_cb)

        return grp

    def _build_rustfs_group(self) -> QGroupBox:
        grp = QGroupBox("RUSTFS  (S3 Object Storage on Unraid)")
        form = QFormLayout(grp)
        form.setSpacing(10)

        self.rustfs_endpoint_edit = QLineEdit()
        self.rustfs_endpoint_edit.setPlaceholderText("http://192.168.1.10:9000")
        form.addRow("Endpoint URL:", self.rustfs_endpoint_edit)

        self.rustfs_access_key_edit = QLineEdit()
        self.rustfs_access_key_edit.setPlaceholderText("Access key (minioadmin)")
        form.addRow("Access Key:", self.rustfs_access_key_edit)

        secret_row = QHBoxLayout()
        self.rustfs_secret_key_edit = QLineEdit()
        self.rustfs_secret_key_edit.setEchoMode(QLineEdit.Password)
        self.rustfs_secret_key_edit.setPlaceholderText("Secret key  (in-memory only)")
        show_secret_btn = QPushButton("Show")
        show_secret_btn.setProperty("class", "secondary")
        show_secret_btn.setCheckable(True)
        show_secret_btn.toggled.connect(
            lambda on: (
                self.rustfs_secret_key_edit.setEchoMode(
                    QLineEdit.Normal if on else QLineEdit.Password
                ),
                show_secret_btn.setText("Hide" if on else "Show"),
            )
        )
        secret_row.addWidget(self.rustfs_secret_key_edit)
        secret_row.addWidget(show_secret_btn)
        form.addRow("Secret Key:", secret_row)

        self.rustfs_bucket_edit = QLineEdit()
        self.rustfs_bucket_edit.setPlaceholderText("photos")
        form.addRow("Bucket:", self.rustfs_bucket_edit)

        test_row = QHBoxLayout()
        self.rustfs_test_btn = QPushButton("Test RustFS Connection")
        self.rustfs_test_btn.setProperty("class", "secondary")
        self.rustfs_test_btn.clicked.connect(self._test_rustfs)
        self.rustfs_status_lbl = QLabel("")
        self.rustfs_status_lbl.setStyleSheet(f"font-size: 11px; font-family: '{FONT_MONO}';")
        test_row.addWidget(self.rustfs_test_btn)
        test_row.addWidget(self.rustfs_status_lbl)
        test_row.addStretch()
        form.addRow("", test_row)

        return grp

    def _build_compreface_group(self) -> QGroupBox:
        grp = QGroupBox("COMPREFACE  (Face Recognition Service)")
        form = QFormLayout(grp)
        form.setSpacing(10)

        self.cf_url_edit = QLineEdit()
        self.cf_url_edit.setPlaceholderText("http://192.168.1.10:8000")
        form.addRow("Server URL:", self.cf_url_edit)

        cf_key_row = QHBoxLayout()
        self.cf_key_edit = QLineEdit()
        self.cf_key_edit.setEchoMode(QLineEdit.Password)
        self.cf_key_edit.setPlaceholderText("Recognition service API key  (in-memory only)")
        show_cf_btn = QPushButton("Show")
        show_cf_btn.setProperty("class", "secondary")
        show_cf_btn.setCheckable(True)
        show_cf_btn.toggled.connect(
            lambda on: (
                self.cf_key_edit.setEchoMode(
                    QLineEdit.Normal if on else QLineEdit.Password
                ),
                show_cf_btn.setText("Hide" if on else "Show"),
            )
        )
        cf_key_row.addWidget(self.cf_key_edit)
        cf_key_row.addWidget(show_cf_btn)
        form.addRow("API Key:", cf_key_row)

        self.cf_sim_edit = QLineEdit()
        self.cf_sim_edit.setPlaceholderText("0.85  (0.0 – 1.0, higher = stricter)")
        form.addRow("Similarity threshold:", self.cf_sim_edit)

        cf_test_row = QHBoxLayout()
        self.cf_test_btn = QPushButton("Test CompreFace Connection")
        self.cf_test_btn.setProperty("class", "secondary")
        self.cf_test_btn.clicked.connect(self._test_compreface)
        self.cf_status_lbl = QLabel("")
        self.cf_status_lbl.setStyleSheet(f"font-size: 11px; font-family: '{FONT_MONO}';")
        cf_test_row.addWidget(self.cf_test_btn)
        cf_test_row.addWidget(self.cf_status_lbl)
        cf_test_row.addStretch()
        form.addRow("", cf_test_row)

        return grp

    def _build_button_row(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)

        save_btn = QPushButton("💾  Save Settings")
        save_btn.setFixedHeight(38)
        save_btn.clicked.connect(self._save)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setProperty("class", "danger")
        reset_btn.setFixedHeight(38)
        reset_btn.clicked.connect(self._reset)

        row.addWidget(save_btn, 2)
        row.addWidget(reset_btn, 1)
        return w

    def _test_connection(self):
        url = self.url_edit.text().strip()
        key = self.key_edit.text().strip()
        if not url or not key:
            self.conn_lbl.setStyleSheet(f"color: {TEXT_WARNING}; font-size: 11px;")
            self.conn_lbl.setText("Enter URL and key first.")
            return
        self.test_btn.setEnabled(False)
        self.conn_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.conn_lbl.setText("Testing…")

        self._conn_tester = ConnectionTestThread(url, key, parent=self)
        self._conn_tester.result.connect(self._on_conn_result)
        self._conn_tester.start()

    def _on_conn_result(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        color = TEXT_SUCCESS if ok else TEXT_ERROR
        self.conn_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-family: '{FONT_MONO}';")
        self.conn_lbl.setText(msg)

    def _test_rustfs(self):
        endpoint   = self.rustfs_endpoint_edit.text().strip()
        access_key = self.rustfs_access_key_edit.text().strip()
        secret_key = self.rustfs_secret_key_edit.text().strip()
        bucket     = self.rustfs_bucket_edit.text().strip() or "photos"
        if not endpoint or not access_key or not secret_key:
            self.rustfs_status_lbl.setStyleSheet(f"color: {TEXT_WARNING}; font-size: 11px;")
            self.rustfs_status_lbl.setText("Fill endpoint, access key, and secret key first.")
            return
        self.rustfs_test_btn.setEnabled(False)
        self.rustfs_status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.rustfs_status_lbl.setText("Testing…")

        from PySide6.QtCore import QThread, Signal as Sig
        class _RustFSTestThread(QThread):
            result = Sig(bool, str)
            def __init__(self, ep, ak, sk, bk, parent=None):
                super().__init__(parent)
                self._ep, self._ak, self._sk, self._bk = ep, ak, sk, bk
            def run(self):
                try:
                    up = RustFSUploader(self._ep, self._ak, self._sk, self._bk)
                    ok, msg = up.test_connection()
                    self.result.emit(ok, msg)
                except Exception as exc:
                    self.result.emit(False, str(exc))

        self._rustfs_tester = _RustFSTestThread(endpoint, access_key, secret_key, bucket, self)
        def _on_result(ok, msg):
            self.rustfs_test_btn.setEnabled(True)
            color = TEXT_SUCCESS if ok else TEXT_ERROR
            self.rustfs_status_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-family: '{FONT_MONO}';")
            self.rustfs_status_lbl.setText(msg)
        self._rustfs_tester.result.connect(_on_result)
        self._rustfs_tester.start()

    def _test_compreface(self):
        url = self.cf_url_edit.text().strip()
        key = self.cf_key_edit.text().strip()
        if not url or not key:
            self.cf_status_lbl.setStyleSheet(f"color: {TEXT_WARNING}; font-size: 11px;")
            self.cf_status_lbl.setText("Fill URL and API key first.")
            return
        self.cf_test_btn.setEnabled(False)
        self.cf_status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.cf_status_lbl.setText("Testing…")

        from PySide6.QtCore import QThread, Signal as Sig
        class _CFTestThread(QThread):
            result = Sig(bool, str)
            def __init__(self, url, key, parent=None):
                super().__init__(parent)
                self._url, self._key = url, key
            def run(self):
                try:
                    client = ComprefaceClient(self._url, self._key)
                    ok, msg = client.test_connection()
                    self.result.emit(ok, msg)
                except Exception as exc:
                    self.result.emit(False, str(exc))

        self._cf_tester = _CFTestThread(url, key, self)
        def _on_result(ok, msg):
            self.cf_test_btn.setEnabled(True)
            color = TEXT_SUCCESS if ok else TEXT_ERROR
            self.cf_status_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-family: '{FONT_MONO}';")
            self.cf_status_lbl.setText(msg)
        self._cf_tester.result.connect(_on_result)
        self._cf_tester.start()

    def _browse_binary(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select immich-go binary")
        if path:
            self.binary_edit.setText(path)

    def _save(self):
        url = self.url_edit.text().strip()
        if url and not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Invalid URL", "Server URL must start with http:// or https://")
            return

        self.config.server_url           = url
        self.config.api_key              = self.key_edit.text().strip()
        self.config.binary_path_override = self.binary_edit.text().strip()
        self.config.log_level            = self.log_level_combo.currentText()
        self.config.timeout              = self.timeout_spin.value()
        self.config.recursive_upload     = self.recursive_cb.isChecked()

        # RustFS
        self.config.rustfs_endpoint  = self.rustfs_endpoint_edit.text().strip()
        self.config.rustfs_access_key = self.rustfs_access_key_edit.text().strip()
        self.config.rustfs_secret_key = self.rustfs_secret_key_edit.text().strip()
        self.config.rustfs_bucket    = self.rustfs_bucket_edit.text().strip() or "photos"

        # CompreFace
        self.config.compreface_url     = self.cf_url_edit.text().strip()
        self.config.compreface_api_key = self.cf_key_edit.text().strip()
        try:
            self.config.similarity_threshold = float(self.cf_sim_edit.text())
        except ValueError:
            pass

        self.config.sync()
        QMessageBox.information(self, "Saved", "Settings saved successfully.")
        self.settings_saved.emit()

    def _reset(self):
        reply = QMessageBox.question(
            self, "Reset Settings",
            "This will clear all saved settings. Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.config.reset()
            self._load()

    def _load(self):
        self.url_edit.setText(self.config.server_url)
        self.key_edit.setText(self.config.api_key)
        self.binary_edit.setText(self.config.binary_path_override)
        self.log_level_combo.setCurrentText(self.config.log_level)
        self.timeout_spin.setValue(self.config.timeout)
        self.recursive_cb.setChecked(self.config.recursive_upload)
        # RustFS
        self.rustfs_endpoint_edit.setText(self.config.rustfs_endpoint)
        self.rustfs_access_key_edit.setText(self.config.rustfs_access_key)
        self.rustfs_secret_key_edit.setText(self.config.rustfs_secret_key)
        self.rustfs_bucket_edit.setText(self.config.rustfs_bucket)
        # CompreFace
        self.cf_url_edit.setText(self.config.compreface_url)
        self.cf_key_edit.setText(self.config.compreface_api_key)
        self.cf_sim_edit.setText(str(self.config.similarity_threshold))
