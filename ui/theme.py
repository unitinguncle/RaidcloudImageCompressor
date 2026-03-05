"""
ui/theme.py — RaidCloud Immich Suite brand theme constants and global QSS stylesheet.
Brand palette from unitinguncle/RaidcloudImageCompressor.
"""

# ─── Color Palette ────────────────────────────────────────────────────────────
BG_DARK        = "#141313"   # primary app background
BG_CARD        = "#1C1B1B"   # card / panel surfaces
BG_SIDEBAR     = "#0F0E0E"   # sidebar background
BG_INPUT       = "#1A1919"   # input field background
BG_HOVER       = "#222122"   # hover state for list items / sidebar buttons

ACCENT         = "#37B4FC"   # RaidCloud electric blue — primary accent
ACCENT_DARK    = "#1A8ED4"   # pressed / hover on accent buttons
ACCENT_GLOW    = "#37B4FC44" # glow used in box-shadow workarounds

BORDER         = "#2A2929"   # subtle border lines
BORDER_ACCENT  = "#37B4FC"   # focused / active borders

TEXT_PRIMARY   = "#FFFFFF"
TEXT_SECONDARY = "#A8BFCA"
TEXT_MUTED     = "#596875"
TEXT_SUCCESS   = "#4EDFA5"
TEXT_ERROR     = "#FF5C6F"
TEXT_WARNING   = "#FFB547"

PROGRESS_BG    = "#1E1D1D"
PROGRESS_CHUNK = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #37B4FC,stop:1 #1A8ED4)"

# ─── Typography ───────────────────────────────────────────────────────────────
FONT_UI        = "Segoe UI"   # Windows; Qt falls back to inter/SF on macOS
FONT_MONO      = "Courier New"
FONT_SIZE_SM   = "11px"
FONT_SIZE_BASE = "13px"
FONT_SIZE_LG   = "15px"
FONT_SIZE_XL   = "18px"
FONT_SIZE_TITLE = "22px"

# ─── Dimensions ───────────────────────────────────────────────────────────────
RADIUS         = "8px"
RADIUS_SM      = "5px"
RADIUS_LG      = "12px"
SIDEBAR_WIDTH  = 200

# ─── Global QSS stylesheet ────────────────────────────────────────────────────
APP_STYLESHEET = f"""
/* ── Global ── */
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: "{FONT_UI}", "Segoe UI", sans-serif;
    font-size: {FONT_SIZE_BASE};
}}

/* ── Scroll Area ── */
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: {BG_CARD};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {ACCENT_DARK};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {BG_CARD};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {ACCENT_DARK};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Labels ── */
QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}
QLabel[class="secondary"] {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_SM};
}}
QLabel[class="muted"] {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SM};
}}
QLabel[class="accent"] {{
    color: {ACCENT};
    font-family: "{FONT_MONO}";
}}
QLabel[class="success"] {{
    color: {TEXT_SUCCESS};
}}
QLabel[class="error"] {{
    color: {TEXT_ERROR};
}}
QLabel[class="section-title"] {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_LG};
    font-weight: 600;
    letter-spacing: 0.5px;
}}

/* ── Group Box ── */
QGroupBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    margin-top: 14px;
    padding-top: 12px;
    font-size: {FONT_SIZE_BASE};
    font-weight: 600;
    color: {TEXT_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 12px;
    color: {ACCENT};
    font-family: "{FONT_MONO}";
    font-size: {FONT_SIZE_SM};
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* ── Line Edits ── */
QLineEdit {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: 7px 10px;
    color: {TEXT_PRIMARY};
    font-family: "{FONT_MONO}";
    font-size: {FONT_SIZE_BASE};
    selection-background-color: {ACCENT_DARK};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled {{
    color: {TEXT_MUTED};
    border-color: {BORDER};
}}
QLineEdit[echoMode="2"] {{  /* password field */
    letter-spacing: 2px;
}}

/* ── Text Edit / Log area ── */
QTextEdit {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: 8px;
    color: {TEXT_SECONDARY};
    font-family: "{FONT_MONO}";
    font-size: 12px;
    selection-background-color: {ACCENT_DARK};
}}

/* ── Buttons — primary (accent) ── */
QPushButton {{
    background-color: {ACCENT};
    color: #000000;
    border: none;
    border-radius: {RADIUS_SM};
    padding: 8px 18px;
    font-size: {FONT_SIZE_BASE};
    font-weight: 700;
    letter-spacing: 0.4px;
    min-height: 32px;
}}
QPushButton:hover {{
    background-color: {ACCENT_DARK};
    color: {TEXT_PRIMARY};
}}
QPushButton:pressed {{
    background-color: #1270B0;
}}
QPushButton:disabled {{
    background-color: {BORDER};
    color: {TEXT_MUTED};
}}

/* ── Buttons — secondary (ghost) ── */
QPushButton[class="secondary"] {{
    background-color: transparent;
    color: {ACCENT};
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton[class="secondary"]:hover {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
    border-color: {ACCENT_DARK};
}}
QPushButton[class="secondary"]:pressed {{
    background-color: {BG_CARD};
}}

/* ── Buttons — danger ── */
QPushButton[class="danger"] {{
    background-color: transparent;
    color: {TEXT_ERROR};
    border: 1px solid {TEXT_ERROR};
}}
QPushButton[class="danger"]:hover {{
    background-color: #FF5C6F22;
}}

/* ── Combo Box ── */
QComboBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: 7px 10px;
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_BASE};
    min-height: 32px;
}}
QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {ACCENT};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_ACCENT};
    selection-background-color: {ACCENT_DARK};
    color: {TEXT_PRIMARY};
    outline: none;
}}

/* ── Spin Box ── */
QSpinBox, QDoubleSpinBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_BASE};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}

/* ── Sliders ── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -6px 0;
    border: 2px solid {BG_DARK};
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::groove:vertical {{
    width: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::handle:vertical {{
    background: {ACCENT};
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: 0 -6px;
}}

/* ── Progress Bar ── */
QProgressBar {{
    background-color: {PROGRESS_BG};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    text-align: center;
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_SM};
    font-weight: 600;
    min-height: 18px;
}}
QProgressBar::chunk {{
    background: {PROGRESS_CHUNK};
    border-radius: {RADIUS_SM};
}}

/* ── Check Box ── */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
    font-size: {FONT_SIZE_BASE};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_ACCENT};
    border-radius: 3px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}

/* ── Radio Button ── */
QRadioButton {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
    font-size: {FONT_SIZE_BASE};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_ACCENT};
    border-radius: 8px;
    background: {BG_INPUT};
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Tab Widget ── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    background: {BG_CARD};
    top: -1px;
}}
QTabBar::tab {{
    background: {BG_CARD};
    color: {TEXT_MUTED};
    padding: 9px 22px;
    border-top-left-radius: {RADIUS_SM};
    border-top-right-radius: {RADIUS_SM};
    margin-right: 3px;
    font-size: {FONT_SIZE_BASE};
    font-weight: 500;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
    background: {BG_DARK};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT_PRIMARY};
    background: {BG_HOVER};
}}

/* ── Date Edit ── */
QDateEdit {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
}}
QDateEdit:focus {{
    border-color: {ACCENT};
}}

/* ── Dialog ── */
QDialog {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
}}

/* ── Message Box ── */
QMessageBox {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
}}

/* ── Tooltip ── */
QToolTip {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {ACCENT};
    padding: 5px 10px;
    border-radius: {RADIUS_SM};
    font-size: {FONT_SIZE_SM};
}}
"""
