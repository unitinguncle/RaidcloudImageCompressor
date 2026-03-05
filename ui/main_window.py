"""
ui/main_window.py — RaidCloud Immich Suite main application window.
Sidebar navigation + stacked panels.
"""

import sys

from PySide6.QtCore    import Qt, QSize, QTimer
from PySide6.QtGui     import QFont, QColor, QPalette, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame,
    QSizePolicy, QDialog, QProgressBar,
)

from core.config         import AppConfig
from core.binary_manager import (
    DownloadBinaryThread, get_default_binary_path,
)
from ui.theme import (
    BG_DARK, BG_SIDEBAR, BG_CARD, ACCENT, ACCENT_DARK,
    TEXT_PRIMARY, TEXT_MUTED, TEXT_SUCCESS, TEXT_ERROR,
    FONT_MONO, FONT_UI, SIDEBAR_WIDTH, BORDER,
)
from ui.tabs.compress_upload_tab import CompressUploadTab
from ui.tabs.google_takeout_tab  import GoogleTakeoutTab
from ui.tabs.local_upload_tab    import LocalUploadTab
from ui.tabs.settings_tab        import SettingsTab

import os


APP_TITLE   = "RaidCloud Immich Suite"
APP_VERSION = "v2.0.0"

NAV_ITEMS = [
    ("⚡", "Compress & Upload", "compress"),
    ("🌐", "Google Takeout",    "takeout"),
    ("📁", "Local Upload",      "local"),
    ("⚙",  "Settings",         "settings"),
]


class SidebarButton(QPushButton):
    """Styled sidebar navigation button."""

    NORMAL_STYLE = f"""
        QPushButton {{
            background: transparent;
            color: {TEXT_MUTED};
            border: none;
            border-left: 3px solid transparent;
            border-radius: 0;
            text-align: left;
            padding: 14px 16px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: rgba(55,180,252,0.08);
            color: {TEXT_PRIMARY};
            border-left: 3px solid rgba(55,180,252,0.4);
        }}
    """
    ACTIVE_STYLE = f"""
        QPushButton {{
            background: rgba(55,180,252,0.12);
            color: {ACCENT};
            border: none;
            border-left: 3px solid {ACCENT};
            border-radius: 0;
            text-align: left;
            padding: 14px 16px;
            font-size: 13px;
            font-weight: 600;
        }}
    """

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(f"  {icon}  {label}")
        self.setFont(QFont(FONT_UI, 12))
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(52)
        self.setMinimumWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(self.NORMAL_STYLE)

    def setActive(self, active: bool):
        self.setStyleSheet(self.ACTIVE_STYLE if active else self.NORMAL_STYLE)
        self.setChecked(active)


class TitleBar(QWidget):
    """Custom title-bar strip with logo + version + connection dot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setStyleSheet(f"background: {BG_SIDEBAR}; border-bottom: 1px solid {BORDER};")

        h = QHBoxLayout(self)
        h.setContentsMargins(20, 0, 16, 0)

        # Logo text
        logo = QLabel(f'<span style="color:{ACCENT}; font-family:Courier New; font-size:18px; font-weight:800; letter-spacing:2px;">RAIDCLOUD</span>'
                      f'<span style="color:{TEXT_MUTED}; font-family:Courier New; font-size:12px;"> IMMICH SUITE</span>')
        logo.setTextFormat(Qt.RichText)
        h.addWidget(logo)
        h.addStretch()

        # Version badge
        ver = QLabel(APP_VERSION)
        ver.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-family: '{FONT_MONO}';"
            f"background: {BG_CARD}; border: 1px solid {BORDER};"
            f"border-radius: 4px; padding: 2px 7px;"
        )
        h.addWidget(ver)

        # Connection dot
        self.conn_dot = QLabel("●")
        self.conn_dot.setStyleSheet(f"color: {BORDER}; font-size: 16px; margin-left: 12px;")
        self.conn_dot.setToolTip("Server connection status")
        h.addWidget(self.conn_dot)

    def set_connected(self, ok: bool):
        color = TEXT_SUCCESS if ok else TEXT_ERROR
        self.conn_dot.setStyleSheet(f"color: {color}; font-size: 16px; margin-left: 12px;")
        self.conn_dot.setToolTip("Connected to Immich" if ok else "Not connected")


class StatusBar(QWidget):
    """Bottom status strip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(
            f"background: {BG_SIDEBAR}; border-top: 1px solid {BORDER};"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 0, 16, 0)

        self.msg_lbl = QLabel("Ready")
        self.msg_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-family: '{FONT_MONO}';")
        h.addWidget(self.msg_lbl)
        h.addStretch()

        platform_lbl = QLabel(sys.platform)
        platform_lbl.setStyleSheet(f"color: {BORDER}; font-size: 10px; font-family: '{FONT_MONO}';")
        h.addWidget(platform_lbl)

    def set_message(self, msg: str, color: str = TEXT_MUTED):
        self.msg_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-family: '{FONT_MONO}';"
        )
        self.msg_lbl.setText(msg)

        # Auto-clear after 6 seconds
        QTimer.singleShot(6000, lambda: self.msg_lbl.setText("Ready"))


class MainWindow(QMainWindow):

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(1100, 720)

        self._build_ui()
        self._switch_tab(0)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_v = QVBoxLayout(root)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        # Title bar
        self.title_bar = TitleBar()
        root_v.addWidget(self.title_bar)

        # Main area (sidebar + content)
        main = QHBoxLayout()
        main.setSpacing(0)
        main.setContentsMargins(0, 0, 0, 0)
        root_v.addLayout(main, 1)

        # Sidebar
        sidebar = self._build_sidebar()
        main.addWidget(sidebar)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setStyleSheet(f"color: {BORDER};")
        main.addWidget(div)

        # Stacked pages
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {BG_DARK};")

        self._compress_tab = CompressUploadTab(self.config)
        self._takeout_tab  = GoogleTakeoutTab(self.config)
        self._local_tab    = LocalUploadTab(self.config)
        self._settings_tab = SettingsTab(self.config)

        self.stack.addWidget(self._compress_tab)
        self.stack.addWidget(self._takeout_tab)
        self.stack.addWidget(self._local_tab)
        self.stack.addWidget(self._settings_tab)
        main.addWidget(self.stack, 1)

        # Status bar
        self.status_bar = StatusBar()
        root_v.addWidget(self.status_bar)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"background: {BG_SIDEBAR};")

        v = QVBoxLayout(sidebar)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self._nav_buttons: list[SidebarButton] = []
        for i, (icon, label, _) in enumerate(NAV_ITEMS):
            btn = SidebarButton(icon, label)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._nav_buttons.append(btn)
            v.addWidget(btn)

        v.addStretch()

        # Footer: RaidCloud branding
        brand_sep = QFrame()
        brand_sep.setFrameShape(QFrame.HLine)
        brand_sep.setStyleSheet(f"color: {BORDER};")
        v.addWidget(brand_sep)

        brand_lbl = QLabel(
            f'<div style="text-align:center; color:{TEXT_MUTED}; font-size:10px;">'
            f'<br>by <span style="color:{ACCENT};">RaidCloud</span><br>© 2025<br>&nbsp;</div>'
        )
        brand_lbl.setTextFormat(Qt.RichText)
        brand_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(brand_lbl)

        return sidebar

    def _switch_tab(self, idx: int):
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setActive(i == idx)
        name = NAV_ITEMS[idx][1]
        self.status_bar.set_message(f"Viewing: {name}")
