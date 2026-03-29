"""
constants.py — Paleta de cores, estilos Qt, constantes globais e temas de mapa.
Importado por todos os outros módulos.
"""
import logging

APP_VERSION = "1.0.1-beta.1"
APP_NAME    = "MeshDeck"
from meshtastic import BROADCAST_NUM

logging.getLogger().setLevel(logging.INFO)
for _h in logging.root.handlers[:]:
    logging.root.removeHandler(_h)
logging.getLogger("meshtastic").setLevel(logging.WARNING)
logging.getLogger("pubsub").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger("MeshtasticGUI")

DARK_BG        = "#0d1117"
PANEL_BG       = "#161b22"
BORDER_COLOR   = "#30363d"
ACCENT_GREEN   = "#39d353"
ACCENT_BLUE    = "#58a6ff"
ACCENT_ORANGE  = "#f0883e"
ACCENT_RED     = "#f85149"
ACCENT_PURPLE  = "#bc8cff"
TEXT_PRIMARY   = "#e6edf3"
TEXT_MUTED     = "#8b949e"
INPUT_BG       = "#21262d"
HOVER_BG       = "#1f2937"
DM_BG          = "#1a1a2e"

APP_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {DARK_BG};
    color: {TEXT_PRIMARY};
    font-family: 'Menlo', 'Cascadia Code', 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}}
QMenuBar {{
    background-color: {PANEL_BG};
    color: {TEXT_PRIMARY};
    border-bottom: 1px solid {BORDER_COLOR};
    padding: 2px;
}}
QMenuBar::item:selected {{ background-color: {HOVER_BG}; color: {ACCENT_BLUE}; }}
QMenu {{
    background-color: {PANEL_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
}}
QMenu::item:selected {{ background-color: {HOVER_BG}; color: {ACCENT_BLUE}; }}
QTabWidget::pane {{
    border: 1px solid {BORDER_COLOR};
    background: {PANEL_BG};
    border-radius: 6px;
}}
QTabBar::tab {{
    background: {DARK_BG};
    color: {TEXT_MUTED};
    padding: 8px 20px;
    border: 1px solid {BORDER_COLOR};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 12px;
    font-weight: bold;
    min-width: 100px;
}}
QTabBar::tab:selected {{
    background: {PANEL_BG};
    color: {ACCENT_GREEN};
    border-bottom: 2px solid {ACCENT_GREEN};
}}
QTabBar::tab:hover:!selected {{ background: {HOVER_BG}; color: {TEXT_PRIMARY}; }}
QTableView {{
    background-color: {PANEL_BG};
    alternate-background-color: {DARK_BG};
    color: {TEXT_PRIMARY};
    gridline-color: {BORDER_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    selection-background-color: #1f3a5f;
    selection-color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background-color: {DARK_BG};
    color: {ACCENT_BLUE};
    padding: 6px 10px;
    border: none;
    border-right: 1px solid {BORDER_COLOR};
    border-bottom: 1px solid {BORDER_COLOR};
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QLineEdit {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
}}
QLineEdit:focus {{ border-color: {ACCENT_BLUE}; }}
QLineEdit:hover {{ border-color: {TEXT_MUTED}; }}
QSpinBox, QDoubleSpinBox {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 4px 8px;
}}
QComboBox {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 4px 8px;
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    selection-background-color: #1f3a5f;
}}
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_COLOR};
    border-radius: 3px;
    background: {INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT_GREEN};
    border-color: {ACCENT_GREEN};
}}
QGroupBox {{
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: bold;
    color: {ACCENT_BLUE};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {ACCENT_BLUE};
}}
QPushButton {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: bold;
    font-size: 12px;
}}
QPushButton:hover {{ background-color: {HOVER_BG}; border-color: {ACCENT_BLUE}; color: {ACCENT_BLUE}; }}
QPushButton:pressed {{ background-color: #1f3a5f; }}
QPushButton#btn_connect {{
    background-color: #1a4a2e;
    color: {ACCENT_GREEN};
    border-color: {ACCENT_GREEN};
    font-size: 13px;
}}
QPushButton#btn_connect:hover {{ background-color: #1f5c38; }}
QPushButton#btn_send_channel {{
    background-color: #1a4a2e;
    color: {ACCENT_GREEN};
    border-color: {ACCENT_GREEN};
}}
QPushButton#btn_send_channel:hover {{ background-color: #1f5c38; }}
QPushButton#btn_send_dm {{
    background-color: #2a1a4a;
    color: {ACCENT_PURPLE};
    border-color: {ACCENT_PURPLE};
}}
QPushButton#btn_send_dm:hover {{ background-color: #35206a; }}
QPushButton#btn_map_theme {{
    background-color: {INPUT_BG};
    color: {TEXT_MUTED};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: normal;
}}
QPushButton#btn_map_theme:hover {{ border-color: {ACCENT_BLUE}; color: {ACCENT_BLUE}; }}
QPushButton#btn_map_theme:checked {{
    background-color: #1f3a5f;
    color: {ACCENT_BLUE};
    border-color: {ACCENT_BLUE};
    font-weight: bold;
}}
QPushButton#btn_save_config {{
    background-color: #1a4a2e;
    color: {ACCENT_GREEN};
    border-color: {ACCENT_GREEN};
    font-size: 13px;
    padding: 8px 24px;
}}
QPushButton#btn_save_config:hover {{ background-color: #1f5c38; }}
QPushButton#btn_reload_config {{
    background-color: #1a2a4a;
    color: {ACCENT_BLUE};
    border-color: {ACCENT_BLUE};
}}
QPushButton#btn_reload_config:hover {{ background-color: #1f3a5f; }}
QTextEdit {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 8px;
    font-size: 13px;
}}
QListWidget {{
    background-color: {PANEL_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
}}
QListWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {BORDER_COLOR}; }}
QListWidget::item:selected {{ background-color: #1f3a5f; color: {ACCENT_BLUE}; }}
QListWidget::item:hover:!selected {{ background-color: {HOVER_BG}; }}
QTableWidget {{
    background-color: {PANEL_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    alternate-background-color: {DARK_BG};
    selection-background-color: #1f3a5f;
    gridline-color: transparent;
}}
QTableWidget QHeaderView::section {{
    background-color: {DARK_BG};
    color: {ACCENT_PURPLE};
    padding: 4px 8px;
    border: none;
    border-right: 1px solid {BORDER_COLOR};
    border-bottom: 1px solid {BORDER_COLOR};
    font-weight: bold;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QScrollBar:vertical {{
    background: {DARK_BG}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_COLOR}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{
    background: {DARK_BG}; height: 8px; border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_COLOR}; border-radius: 4px; min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QSplitter::handle {{ background: {BORDER_COLOR}; width: 2px; }}
QLabel {{ color: {TEXT_PRIMARY}; }}
QDialog {{ background-color: {PANEL_BG}; }}
"""

_BROADCAST_NUMS = {BROADCAST_NUM, 0xFFFFFFFF, 4294967295, -1}


def _is_broadcast(to_num) -> bool:
    try:
        n = int(to_num)
        if n < 0:
            n = n & 0xFFFFFFFF
        return n in _BROADCAST_NUMS or n == 0
    except (TypeError, ValueError):
        return True