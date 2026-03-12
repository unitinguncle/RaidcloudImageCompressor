"""
ui/tabs/settings_tab.py — App-wide settings (server, binary, advanced).
"""

from PySide6.QtCore    import Qt
from PySide6.QtGui     import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QGroupBox, QComboBox, QSpinBox, QFileDialog,
    QScrollArea, QFrame, QMessageBox,
)

from core.config  import AppConfig
from core.uploader import UploaderThread
from ui.theme import (
    ACCENT, TEXT_MUTED, TEXT_SUCCESS, TEXT_ERROR, TEXT_WARNING, FONT_MONO,
)


class SettingsTab(QWidget):

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
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
        test_btn = QPushButton("Test Connection")
        test_btn.setProperty("class", "secondary")
        test_btn.clicked.connect(self._test_connection)
        self.conn_lbl = QLabel("")
        self.conn_lbl.setStyleSheet(f"font-size: 11px; font-family: '{FONT_MONO}';")
        test_row.addWidget(test_btn)
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
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" sec")
        form.addRow("Request Timeout:", self.timeout_spin)

        self.recursive_cb = QCheckBox("Recursively scan sub-folders")
        self.recursive_cb.setChecked(True)
        form.addRow("", self.recursive_cb)

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
        self.conn_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.conn_lbl.setText("Testing…")

        ok, msg = UploaderThread.test_connection(url, key)
        color = TEXT_SUCCESS if ok else TEXT_ERROR
        self.conn_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-family: '{FONT_MONO}';")
        self.conn_lbl.setText(msg)

    def _browse_binary(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select immich-go binary")
        if path:
            self.binary_edit.setText(path)

    def _save(self):
        self.config.server_url           = self.url_edit.text().strip()
        self.config.api_key              = self.key_edit.text().strip()
        self.config.binary_path_override = self.binary_edit.text().strip()
        self.config.log_level            = self.log_level_combo.currentText()
        self.config.timeout              = self.timeout_spin.value()
        self.config.recursive_upload     = self.recursive_cb.isChecked()
        self.config.sync()
        QMessageBox.information(self, "Saved", "Settings saved successfully.")

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
