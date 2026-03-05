"""
main.py — RaidCloud Immich Suite entry point.
Compress locally. Upload to Immich. One app.
"""

import sys
import multiprocessing
import os

from PySide6.QtWidgets import QApplication

from PySide6.QtGui     import QFont


def main():
    # Qt6 handles HiDPI automatically — no attribute flags needed
    app = QApplication(sys.argv)
    app.setApplicationName("RaidCloud Immich Suite")
    app.setOrganizationName("RaidCloud")
    app.setApplicationVersion("2.0.0")

    # Apply global stylesheet (import after QApplication is created)
    from ui.theme import APP_STYLESHEET, FONT_UI
    app.setStyleSheet(APP_STYLESHEET)
    app.setFont(QFont(FONT_UI, 11))

    from core.config      import AppConfig
    from ui.main_window   import MainWindow

    config = AppConfig()
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)
    main()
