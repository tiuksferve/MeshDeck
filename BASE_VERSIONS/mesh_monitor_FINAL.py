#!/usr/bin/env python3
"""
Monitor de nós Meshtastic com interface gráfica PyQt5.
Conecta via TCP ao daemon local, lista e pesquisa nós em tempo real.

CHANGELOG de correcções aplicadas:
  FIX-1  Reconexão automática: subscreve meshtastic.connection.lost,
         emite connection_changed(False) e tenta reconectar com backoff
         exponencial (5 s → 10 s → 30 s → 60 s, máx 4 tentativas).
  FIX-2  NeighborInfo em tempo real: processa NEIGHBORINFO_APP em
         _on_packet_received e emite neighbor_info_received para o mapa.
  FIX-3  DM PKI: indicador visual na lista (🔒/🔑/🔓) e feedback de
         erro simplificado ao utilizador.
  FIX-4  Nó local inserido antes de local_node_ready: obtém nodeNum via
         iface.localNode.nodeNum imediatamente e bloqueia inserção antes
         de qualquer batch.
  FIX-5  Polling simplificado: um único sync na ligação + eventos pubsub
         em tempo real; timer de 30 s mantido como safety-net mas sem
         re-desenho forçado se nada mudou.
  FIX-6  neighbor_info_received declarado formalmente como pyqtSignal
         na classe MeshtasticWorker.
  FIX-7  writeConfig com conversão explícita de enum via
         meshtastic.util.fromStr, validação antes de setattr e
         captura de erros por campo.
  FIX-8  Contador de nós usa source_model.get_visible_count() e nunca
         sofre interferência do filtro de pesquisa.
"""

import sys
import json
import logging
import os
import html
import hashlib
import functools
from typing import Optional, Dict, Any, Set, List, Callable, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from PyQt5.QtCore import (
    Qt, QAbstractTableModel, QSortFilterProxyModel,
    QModelIndex, pyqtSignal, QObject, QTimer, QUrl, QByteArray
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLineEdit, QTableView, QHeaderView,
    QMessageBox, QLabel, QDialog, QDialogButtonBox,
    QTextEdit, QPushButton, QTabWidget, QListWidget,
    QListWidgetItem, QSplitter, QFrame, QMenuBar, QAction,
    QAbstractItemView, QTableWidget, QTableWidgetItem,
    QSizePolicy, QSpinBox, QFormLayout, QScrollArea,
    QGroupBox, QComboBox, QCheckBox, QProgressBar,
    QDoubleSpinBox, QSlider, QStackedWidget
)
from PyQt5.QtGui import QFont, QColor, QPixmap, QPainter
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtSvg import QSvgRenderer

from pubsub import pub
from meshtastic.tcp_interface import TCPInterface
from meshtastic import BROADCAST_ADDR, BROADCAST_NUM

# ---------------------------------------------------------------------------
# Logging — sem output para o terminal; toda a saída vai para a ConsoleWindow
# ---------------------------------------------------------------------------
logging.getLogger().setLevel(logging.INFO)
# Remove qualquer handler de console existente (criado por dependências)
for _h in logging.root.handlers[:]:
    logging.root.removeHandler(_h)
# Silencia bibliotecas ruidosas
logging.getLogger("meshtastic").setLevel(logging.WARNING)
logging.getLogger("pubsub").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger("MeshtasticGUI")

# ---------------------------------------------------------------------------
# Paleta de cores
# ---------------------------------------------------------------------------
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


MAP_THEMES = [
    ("🌑 Escuro",        "CartoDB dark_matter",  ""),
    ("☀ Claro",         "CartoDB positron",      ""),
    ("🗺 OpenStreetMap", "OpenStreetMap",         ""),
    ("🛰 Satélite",
     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
     "Tiles &copy; Esri"),
]


# ---------------------------------------------------------------------------
# Diálogo de Conexão
# ---------------------------------------------------------------------------
class ConnectionDialog(QDialog):
    def __init__(self, current_host="localhost", current_port=4403, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Conexão")
        self.setFixedWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📡  Conexão ao Servidor Meshtastic")
        title.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:14px;font-weight:bold;padding-bottom:4px;"
        )
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        layout.addWidget(sep)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        self.host_edit = QLineEdit(current_host)
        self.host_edit.setPlaceholderText("ex: localhost  ou  192.168.1.1")
        form.addRow("Endereço:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(current_port)
        form.addRow("Porta:", self.port_spin)

        layout.addLayout(form)

        note = QLabel("💡 O endereço padrão para o daemon local é <b>localhost</b> porta <b>4403</b>.")
        note.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.setSpacing(8)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)

        btns.addStretch()

        self.btn_connect = QPushButton("🔌  Conectar")
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.setDefault(True)
        self.btn_connect.clicked.connect(self.accept)
        btns.addWidget(self.btn_connect)

        layout.addLayout(btns)

    @property
    def hostname(self) -> str:
        return self.host_edit.text().strip() or "localhost"

    @property
    def port(self) -> int:
        return self.port_spin.value()


# ---------------------------------------------------------------------------
# Diálogo de detalhes do pacote
# ---------------------------------------------------------------------------
class PacketDetailDialog(QDialog):
    def __init__(self, node_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalhes do Último Pacote")
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"📦  Pacote — {node_info.get('id_string', '')}")
        title.setStyleSheet(f"color:{ACCENT_GREEN};font-size:14px;font-weight:bold;")
        layout.addWidget(title)

        te = QTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont("Menlo", 11) if sys.platform == "darwin" else QFont("Consolas", 11))
        te.setStyleSheet(
            f"background-color:{DARK_BG};color:{ACCENT_GREEN};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;padding:12px;"
        )
        te.setText(str(node_info.get("last_packet", "Nenhum pacote armazenado")))
        layout.addWidget(te)

        btn = QPushButton("Fechar")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignRight)


# ---------------------------------------------------------------------------
# Favoritos — persistência completa em ficheiro JSON local
# ---------------------------------------------------------------------------
class FavoritesStore:
    """
    Guarda os dados completos de nós favoritos num ficheiro JSON local.
    Ao conectar, os favoritos são injectados na lista mesmo que o NodeDB
    do firmware não os inclua (ex: nós de outras redes já vistos).
    """
    _PATH = os.path.join(
        os.path.expanduser("~"), ".meshtastic_monitor_favorites.json"
    )
    _FIELDS = [
        "id_string", "id_num", "long_name", "short_name", "hw_model",
        "public_key", "latitude", "longitude", "altitude",
        "battery_level", "snr", "hops_away", "via_mqtt", "last_heard",
    ]

    def __init__(self):
        self._nodes: Dict[str, Dict] = {}   # id_string → dados completos
        self._load()

    # ── persistência ────────────────────────────────────────────────────
    def _load(self):
        try:
            if not os.path.exists(self._PATH):
                return
            with open(self._PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("nodes", data.get("favorites", []))
            if isinstance(raw, list):          # formato antigo (lista de IDs)
                for item in raw:
                    if isinstance(item, str):
                        self._nodes[item] = {"id_string": item}
                    elif isinstance(item, dict) and item.get("id_string"):
                        self._nodes[item["id_string"]] = item
            elif isinstance(raw, dict):
                self._nodes = raw
            # Reconverte last_heard guardado como string ISO
            for nd in self._nodes.values():
                lh = nd.get("last_heard")
                if isinstance(lh, str):
                    try:
                        nd["last_heard"] = datetime.fromisoformat(lh)
                    except Exception:
                        nd["last_heard"] = None
        except Exception as e:
            logger.warning(f"FavoritesStore.load: {e}")
            self._nodes = {}

    def _save(self):
        try:
            def _serial(v):
                return v.isoformat() if isinstance(v, datetime) else v
            out = {nid: {k: _serial(v) for k, v in nd.items()}
                   for nid, nd in self._nodes.items()}
            with open(self._PATH, "w", encoding="utf-8") as f:
                json.dump({"nodes": out}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"FavoritesStore.save: {e}")

    # ── API pública ──────────────────────────────────────────────────────
    def is_favorite(self, node_id: str) -> bool:
        return node_id in self._nodes

    def toggle(self, node_id: str, node_data: Optional[Dict] = None) -> bool:
        """Alterna favorito. Retorna True se agora é favorito."""
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._save()
            return False
        entry: Dict = {"id_string": node_id}
        if node_data:
            for f in self._FIELDS:
                v = node_data.get(f)
                if v is not None:
                    entry[f] = v
        self._nodes[node_id] = entry
        self._save()
        return True

    def update_node_data(self, node_id: str, node_data: Dict):
        """Actualiza os campos persistidos de um favorito já existente."""
        if node_id not in self._nodes:
            return
        nd = self._nodes[node_id]
        for f in self._FIELDS:
            v = node_data.get(f)
            if v is not None:
                nd[f] = v
        self._save()

    def get_all(self) -> Set[str]:
        return set(self._nodes.keys())

    def get_node_data(self, node_id: str) -> Optional[Dict]:
        return dict(self._nodes[node_id]) if node_id in self._nodes else None

    def get_all_nodes_data(self) -> List[Dict]:
        return [dict(nd) for nd in self._nodes.values()]


_FAVORITES = FavoritesStore()


# ---------------------------------------------------------------------------
# Modelo de dados — tabela de nós
# ---------------------------------------------------------------------------
class NodeTableModel(QAbstractTableModel):
    HEADERS = [
        "⭐", "📩", "🗺", "📡",
        "ID String", "ID Num", "Nome Longo", "Nome Curto", "Último Contato",
        "SNR (dB)", "Hops", "Via", "Latitude", "Longitude", "Altitude (m)",
        "Bateria (%)", "Modelo", "Último Tipo",
    ]

    COL_FAV        = 0
    COL_DM         = 1
    COL_MAP        = 2
    COL_TRACEROUTE = 3
    COL_DATA_START = 4

    node_inserted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: List[Dict[str, Any]] = []
        self._node_index: Dict[str, int] = {}
        self._local_node_id:  Optional[str] = None   # ID canónico !hex
        self._local_node_num: Optional[int] = None   # FIX-4: nodeNum int bloqueado cedo

    def rowCount(self, parent=QModelIndex()):
        return len(self._nodes)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = self._nodes[index.row()]
        col  = index.column()

        if role == Qt.DisplayRole:
            return self._display_value(node, col)

        if role == Qt.ForegroundRole:
            if col == self.COL_FAV:
                node_id = node.get("id_string", "")
                return QColor("#f5c518") if _FAVORITES.is_favorite(node_id) else QColor(BORDER_COLOR)
            if col == self.COL_DM:
                # Só mostramos DM se o nó tem last_heard (é alcançável)
                if isinstance(node.get("last_heard"), datetime):
                    return QColor(ACCENT_PURPLE)
                return QColor(BORDER_COLOR)
            if col == self.COL_TRACEROUTE:
                return QColor(ACCENT_BLUE)
            if col == self.COL_MAP:
                has_gps = (node.get('latitude') is not None and node.get('longitude') is not None)
                return QColor(ACCENT_GREEN) if has_gps else QColor(BORDER_COLOR)
            if col == 7:  # Nome Curto — verde se online (<2h), cinza se inactivo
                lh = node.get("last_heard")
                if isinstance(lh, datetime) and (datetime.now() - lh) <= timedelta(hours=2):
                    return QColor(ACCENT_GREEN)
                return QColor(TEXT_MUTED)
            if col == 9:  # SNR
                snr = node.get("snr")
                if snr is not None:
                    if snr >= 5:  return QColor(ACCENT_GREEN)
                    if snr >= 0:  return QColor(ACCENT_ORANGE)
                    return QColor(ACCENT_RED)
            if col == 11:  # Via
                return QColor(ACCENT_ORANGE) if node.get("via_mqtt") is True else QColor(ACCENT_GREEN)
            if col == 15:  # Bateria
                batt = node.get("battery_level")
                if batt is not None:
                    if batt > 60: return QColor(ACCENT_GREEN)
                    if batt > 20: return QColor(ACCENT_ORANGE)
                    return QColor(ACCENT_RED)

        if role == Qt.BackgroundRole:
            node_id = node.get("id_string", "")
            if _FAVORITES.is_favorite(node_id):
                return QColor("#1a1a0a")  # fundo dourado muito subtil para favoritos
            if node.get("_selected_highlight"):
                return QColor("#1a3a1a")

        if role == Qt.TextAlignmentRole and col in (
            self.COL_FAV, self.COL_DM, self.COL_MAP, self.COL_TRACEROUTE
        ):
            return Qt.AlignCenter

        if role == Qt.ToolTipRole:
            node_id = node.get("id_string", "")
            if col == self.COL_FAV:
                return "Clique para remover dos favoritos" if _FAVORITES.is_favorite(node_id) \
                       else "Clique para adicionar aos favoritos"
            if col == self.COL_MAP:
                has_gps = (node.get('latitude') is not None and node.get('longitude') is not None)
                return "Ver no mapa" if has_gps else "Sem dados de posição"
            if col == self.COL_DM:
                if not isinstance(node.get("last_heard"), datetime):
                    return "DM indisponível — nó nunca contactado"
                has_key = bool(node.get('public_key', ''))
                return "Enviar DM 🔒 PKI (chave pública conhecida)" if has_key \
                       else "Enviar DM 🔓 PSK (chave de canal)"

        return None

    def _display_value(self, node, col):
        if col == self.COL_FAV:
            node_id = node.get("id_string", "")
            return "⭐" if _FAVORITES.is_favorite(node_id) else "☆"
        if col == self.COL_DM:
            # Só exibe ícone activo se o nó já foi contactado
            if not isinstance(node.get("last_heard"), datetime):
                return "·"
            has_key = bool(node.get('public_key', ''))
            return "🔒" if has_key else "📩"
        if col == self.COL_MAP:
            has_gps = (node.get('latitude') is not None and node.get('longitude') is not None)
            return "🗺" if has_gps else "·"
        if col == self.COL_TRACEROUTE:
            return "📡"
        m = {
            4:  lambda n: n.get("id_string", ""),
            5:  lambda n: str(n.get("id_num", "")),
            6:  lambda n: n.get("long_name", "") or "⏳ Aguardando Info",
            7:  lambda n: n.get("short_name", "") or "--",
            8:  lambda n: (n["last_heard"].strftime("%Y-%m-%d %H:%M:%S")
                           if isinstance(n.get("last_heard"), datetime)
                           else str(n.get("last_heard", "Nunca"))),
            9:  lambda n: f"{n['snr']:.1f}" if n.get("snr") is not None else "",
            10: lambda n: str(n["hops_away"]) if n.get("hops_away") is not None else "",
            11: lambda n: "☁ MQTT" if n.get("via_mqtt") is True else "RF",
            12: lambda n: f"{n['latitude']:.6f}" if n.get("latitude") is not None else "",
            13: lambda n: f"{n['longitude']:.6f}" if n.get("longitude") is not None else "",
            14: lambda n: str(n["altitude"]) if n.get("altitude") is not None else "",
            15: lambda n: str(n["battery_level"]) if n.get("battery_level") is not None else "",
            16: lambda n: n.get("hw_model", ""),
            17: lambda n: n.get("last_packet_type", ""),
        }
        fn = m.get(col)
        return fn(node) if fn else None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    # FIX-4: aceita também nodeNum int para bloqueio precoce
    def set_local_node_id(self, node_id: str, node_num: Optional[int] = None):
        self._local_node_id  = node_id.lower() if node_id else None
        self._local_node_num = node_num

    def _is_local_node(self, node_id_string: str, node_id_num=None) -> bool:
        if self._local_node_num is not None and node_id_num is not None:
            try:
                if int(node_id_num) == self._local_node_num:
                    return True
            except (TypeError, ValueError):
                pass
        return bool(self._local_node_id and node_id_string
                    and node_id_string.lower() == self._local_node_id)

    def update_node_silent(self, node_id_string: str, node_data: Dict[str, Any]) -> bool:
        if node_id_string in self._node_index:
            row = self._node_index[node_id_string]
            self._nodes[row].update(node_data)
            return False
        else:
            # FIX-4: usa também id_num para identificar nó local antes de local_node_ready
            if self._is_local_node(node_id_string, node_data.get('id_num')):
                logger.debug(f'update_node_silent: inserção do nó local recusada ({node_id_string})')
                return False
            node_data["id_string"] = node_id_string
            row = len(self._nodes)
            self._nodes.append(node_data)
            self._node_index[node_id_string] = row
            return True

    def refresh_all(self):
        self.beginResetModel()
        self.endResetModel()
        self.node_inserted.emit()

    def update_node(self, node_id_string: str, node_data: Dict[str, Any], packet=None):
        if node_id_string in self._node_index:
            row = self._node_index[node_id_string]
            self._nodes[row].update(node_data)
            if packet is not None:
                self._nodes[row]["last_packet"] = packet
            tl = self.createIndex(row, 0)
            br = self.createIndex(row, len(self.HEADERS) - 1)
            self.dataChanged.emit(tl, br, [Qt.DisplayRole, Qt.ForegroundRole, Qt.BackgroundRole])
        else:
            if self._is_local_node(node_id_string, node_data.get('id_num')):
                logger.debug(f'update_node: inserção do nó local recusada ({node_id_string})')
                return
            row = len(self._nodes)
            self.beginInsertRows(QModelIndex(), row, row)
            node_data["id_string"] = node_id_string
            if packet is not None:
                node_data["last_packet"] = packet
            self._nodes.append(node_data)
            self._node_index[node_id_string] = row
            self.endInsertRows()
            logger.info(f"Modelo: NOVO nó {node_id_string} inserido")
            self.node_inserted.emit()

    def set_selected_highlight(self, node_id_string: Optional[str]):
        for node in self._nodes:
            node["_selected_highlight"] = (node.get("id_string") == node_id_string
                                            and node_id_string is not None)
        if self._nodes:
            tl = self.createIndex(0, 0)
            br = self.createIndex(len(self._nodes) - 1, len(self.HEADERS) - 1)
            self.dataChanged.emit(tl, br, [Qt.BackgroundRole])

    def get_node_count(self):
        return len(self._nodes)

    def get_visible_count(self) -> int:
        """
        FIX-8: Conta nós visíveis (com last_heard) excluindo o nó local.
        Este valor é sempre independente do filtro de pesquisa.
        """
        local_id = self._local_node_id
        return sum(
            1 for n in self._nodes
            if isinstance(n.get("last_heard"), datetime)
            and (not local_id or n.get("id_string", "").lower() != local_id)
        )

    def get_online_count(self) -> int:
        """Conta nós activos (last_heard < 2 horas) excluindo o nó local."""
        local_id = self._local_node_id
        cutoff   = datetime.now() - timedelta(hours=2)
        return sum(
            1 for n in self._nodes
            if isinstance(n.get("last_heard"), datetime)
            and n.get("last_heard") >= cutoff
            and (not local_id or n.get("id_string", "").lower() != local_id)
        )

    def get_node_data(self, r):
        return self._nodes[r] if 0 <= r < len(self._nodes) else None

    def get_all_nodes(self):
        return self._nodes

    def clear_all_nodes(self):
        if not self._nodes:
            return
        self.beginResetModel()
        self._nodes.clear()
        self._node_index.clear()
        self.endResetModel()

    def get_node_choices(self) -> List[tuple]:
        return [
            (n.get("id_string", ""), n.get("long_name", ""), n.get("short_name", ""))
            for n in self._nodes
        ]


# ---------------------------------------------------------------------------
# Proxy de pesquisa
# ---------------------------------------------------------------------------
class NodeFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text   = ""
        self._local_node_id: Optional[str] = None

    def set_filter_text(self, text: str):
        self._filter_text = text.lower()
        self.invalidateFilter()

    def get_filter_text(self):
        return self._filter_text

    def set_local_node_id(self, node_id: str):
        self._local_node_id = node_id
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        node  = model.get_node_data(source_row)
        if node is None:
            return False
        if self._local_node_id and node.get("id_string") == self._local_node_id:
            return False
        if not isinstance(node.get("last_heard"), datetime):
            return False
        if not self._filter_text:
            return True
        search_vals = [
            str(node.get("id_string", "")).lower(),
            str(node.get("long_name", "")).lower(),
            str(node.get("short_name", "")).lower(),
            str(node.get("id_num", "")).lower(),
        ]
        return any(self._filter_text in v for v in search_vals)

    def lessThan(self, left, right):
        """
        Favoritos SEMPRE acima de não-favoritos, independentemente da coluna ordenada.
        Dentro de cada grupo (fav/não-fav) aplica a ordenação normal da coluna.
        """
        model  = self.sourceModel()
        node_l = model.get_node_data(left.row())
        node_r = model.get_node_data(right.row())
        if node_l is None or node_r is None:
            return super().lessThan(left, right)
        fav_l = _FAVORITES.is_favorite(node_l.get("id_string", ""))
        fav_r = _FAVORITES.is_favorite(node_r.get("id_string", ""))
        if fav_l != fav_r:
            # favorito vai para cima seja qual for a ordem (asc ou desc)
            # sortOrder() diz-nos a direcção actual
            asc = (self.sortOrder() == Qt.AscendingOrder)
            # Se asc, lessThan(a,b)=True → a aparece antes → fav_l=True deve retornar True
            # Se desc, lessThan(a,b)=True → a aparece DEPOIS → fav_l=True deve retornar False
            return fav_l if asc else fav_r
        return super().lessThan(left, right)

    def get_visible_node_ids(self) -> Set[str]:
        ids = set()
        for proxy_row in range(self.rowCount()):
            src_row = self.mapToSource(self.index(proxy_row, 0)).row()
            node    = self.sourceModel().get_node_data(src_row)
            if node:
                ids.add(node.get("id_string", ""))
        return ids


# ---------------------------------------------------------------------------
# Widget do Mapa
# ---------------------------------------------------------------------------
class MapWidget(QWidget):
    node_deselected = pyqtSignal()

    TILE_URLS = {
        "🌑 Escuro":        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "☀ Claro":         "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "🗺 OpenStreetMap": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "🛰 Satélite":     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_nodes:    list          = []
        self._current_filter:   str           = ""
        self._theme_idx:        int           = 0
        self._map_initialized:  bool          = False
        self._last_marker_data: list          = []
        self._selected_node_id: Optional[str] = None
        self._pan_to_selected:  bool          = False
        self._selection_stable_time: float    = 0.0

        # Último nó que recebeu um pacote real — fica vermelho até outro tomar o lugar
        self._last_active_id:   str   = ""

        self._tr_records:         list = []
        self._tr_show_all:        bool = True
        self._tr_blocking_signals: bool = False
        self._tr_nodes:           list = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Painel esquerdo — lista de traceroutes ───────────────────────
        left = QWidget()
        left.setFixedWidth(220)
        left.setStyleSheet(
            f"background:{PANEL_BG};border-right:1px solid {BORDER_COLOR};"
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        hdr = QLabel("📡  Traceroutes")
        hdr.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:11px;font-weight:bold;"
            f"padding:6px 10px;border-bottom:1px solid {BORDER_COLOR};"
        )
        left_layout.addWidget(hdr)

        # Botão "Mostrar todas" — toggle verdadeiro ON/OFF
        self.btn_tr_all = QPushButton("◉  Mostrar todas")
        self.btn_tr_all.setCheckable(True)
        self.btn_tr_all.setChecked(True)
        self.btn_tr_all.setStyleSheet(
            f"QPushButton{{background:{DARK_BG};color:{ACCENT_GREEN};"
            f"border:none;border-bottom:1px solid {BORDER_COLOR};"
            f"font-size:11px;padding:5px 10px;text-align:left;}}"
            f"QPushButton:checked{{background:#1a3a2a;color:{ACCENT_GREEN};}}"
            f"QPushButton:hover{{background:#1e2d1e;}}"
        )
        self.btn_tr_all.clicked.connect(self._on_tr_all_toggled)
        left_layout.addWidget(self.btn_tr_all)

        # Botão "Limpar"
        btn_clear = QPushButton("🗑  Limpar lista")
        btn_clear.setStyleSheet(
            f"QPushButton{{background:{PANEL_BG};color:#cc3333;"
            f"border:none;border-bottom:1px solid {BORDER_COLOR};"
            f"font-size:10px;padding:4px 10px;text-align:left;font-weight:bold;}}"
            f"QPushButton:hover{{background:#2a1010;color:#ff5555;}}"
        )
        btn_clear.clicked.connect(self._on_tr_clear)
        left_layout.addWidget(btn_clear)

        # Lista scrollável de registos — cada item tem checkbox para multi-selecção
        self._tr_list_widget = QListWidget()
        self._tr_list_widget.setStyleSheet(
            f"QListWidget{{background:{DARK_BG};border:none;outline:none;"
            f"color:{TEXT_PRIMARY};font-size:11px;}}"
            f"QListWidget::item{{padding:5px 8px;"
            f"border-bottom:1px solid {BORDER_COLOR};}}"
            f"QListWidget::item:hover{{background:#1e2828;}}"
        )
        self._tr_list_widget.setWordWrap(True)
        self._tr_list_widget.setSelectionMode(QListWidget.NoSelection)
        self._tr_list_widget.itemChanged.connect(self._on_tr_item_changed)
        left_layout.addWidget(self._tr_list_widget, stretch=1)

        outer.addWidget(left)

        # ── Painel direito — mapa com barra de controlo ──────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        ctrl_bar = QWidget()
        ctrl_bar.setFixedHeight(40)
        ctrl_bar.setStyleSheet(
            f"background:{PANEL_BG};border-bottom:1px solid {BORDER_COLOR};"
        )
        ctrl_layout = QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(12, 4, 12, 4)
        ctrl_layout.setSpacing(6)

        lbl = QLabel("🎨  Tema:")
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        ctrl_layout.addWidget(lbl)

        theme_names = list(self.TILE_URLS.keys())
        self._theme_buttons: List[QPushButton] = []
        for i, name in enumerate(theme_names):
            btn = QPushButton(name)
            btn.setObjectName("btn_map_theme")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(functools.partial(self._on_theme_clicked, i))
            ctrl_layout.addWidget(btn)
            self._theme_buttons.append(btn)

        ctrl_layout.addStretch()

        # Legenda dos marcadores (sempre visível)
        self._legend_markers = QLabel(
            "<span style='color:#00ff88;font-size:13px;'>●</span> Seleccionado &nbsp;"
            "<span style='color:#ff4444;font-size:13px;'>●</span> Último pacote &nbsp;"
            "<span style='color:#2b7cd3;font-size:13px;'>●</span> RF &nbsp;"
            "<span style='color:#ff8800;font-size:13px;'>●</span> MQTT &nbsp;"
            "<span style='color:#555566;font-size:13px;'>●</span> Inativos"
        )
        self._legend_markers.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        ctrl_layout.addWidget(self._legend_markers)

        right_layout.addWidget(ctrl_bar)

        self.web = QWebEngineView()
        from PyQt5.QtWebEngineWidgets import QWebEnginePage
        class _SilentPage(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):
                if 'webkit' in message.lower() or 'deprecated' in message.lower():
                    return
                logger.debug(f"[MapJS] {message}")
        self.web.setPage(_SilentPage(self.web))
        right_layout.addWidget(self.web, stretch=1)

        outer.addWidget(right, stretch=1)

        self._show_placeholder()

        self._popup_check_timer = QTimer(self)
        self._popup_check_timer.setInterval(600)
        self._popup_check_timer.timeout.connect(self._check_popup_closed)

        # Poll para cliques no botão Traceroute dentro dos popups do mapa
        self._traceroute_cb = None
        self._tr_poll_timer = QTimer(self)
        self._tr_poll_timer.setInterval(1000)  # 1s — suficiente para detectar clique
        self._tr_poll_timer.timeout.connect(self._check_traceroute_request)
        self._tr_poll_timer.start()

    def _show_placeholder(self):
        self.web.setHtml(
            f"<html><body style='background:{DARK_BG};color:{TEXT_PRIMARY};"
            "font-family:monospace;display:flex;align-items:center;"
            "justify-content:center;height:100vh;margin:0;font-size:18px;'>"
            "📡 Aguardando dados de posição...</body></html>"
        )
        self._map_initialized = False

    def _map_html(self, center_lat: float, center_lon: float,
                  zoom: int, tile_url: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body,#map{{height:100%;margin:0;padding:0;background:{DARK_BG};}}
  .custom-tooltip{{
    background:{PANEL_BG} !important;
    border:1px solid {BORDER_COLOR} !important;
    color:{TEXT_PRIMARY} !important;
    font-family:monospace;font-size:12px;
    padding:6px 10px;border-radius:6px;
    box-shadow:0 2px 8px rgba(0,0,0,.6);
    white-space:nowrap;
  }}
  .custom-tooltip-tr{{
    background:{PANEL_BG} !important;
    border:1px solid {BORDER_COLOR} !important;
    color:{TEXT_PRIMARY} !important;
    font-family:monospace;font-size:12px;
    padding:6px 10px;border-radius:6px;
    box-shadow:0 2px 8px rgba(0,0,0,.6);
    white-space:pre;
  }}
  .custom-popup .leaflet-popup-content-wrapper{{
    background:{PANEL_BG};border:1px solid {BORDER_COLOR};
    color:{TEXT_PRIMARY};border-radius:8px;font-family:monospace;font-size:12px;
  }}
  .custom-popup .leaflet-popup-tip{{background:{PANEL_BG};}}
</style>
</head>
<body>
<div id="map"></div>
<script>
(function(){{
  var map = L.map('map', {{
    center: [{center_lat}, {center_lon}],
    zoom: {zoom},
    zoomControl: true
  }});
  var tileUrl = {json.dumps(tile_url)};
  L.tileLayer(tileUrl, {{maxZoom:19, attribution:''}}).addTo(map);
  window._map         = map;
  window._markerLayer = L.layerGroup().addTo(map);
  window._trLayer     = null;
  window._selPopupClosed = false;
  window._mapReady    = true;
  // Redesenha rotas ao mudar zoom (offset em px precisa de recalculo)
  map.on('zoomend', function() {{
    if(window._trLayer && window._trRedraw) {{ window._trRedraw(); }}
  }});
  console.log('MapWidget: Leaflet ready');
}})();
</script>
</body>
</html>"""

    def _init_map(self, center_lat: float, center_lon: float, zoom: int):
        tile_url = list(self.TILE_URLS.values())[self._theme_idx]
        html_str = self._map_html(center_lat, center_lon, zoom, tile_url)
        self._map_initialized = False
        self.web.loadFinished.connect(self._on_load_finished)
        self.web.setHtml(html_str, QUrl("about:blank"))

    def _on_load_finished(self, ok: bool):
        try:
            self.web.loadFinished.disconnect(self._on_load_finished)
        except Exception:
            pass
        if not ok:
            logger.warning("MapWidget: loadFinished ok=False")
            return
        QTimer.singleShot(50, self._after_load)

    def _after_load(self):
        self._map_initialized = True
        nodes_loc = [n for n in self._current_nodes
                     if n.get('latitude') is not None and n.get('longitude') is not None]
        if nodes_loc:
            most_recent = max(
                (n for n in nodes_loc if isinstance(n.get('last_heard'), datetime)),
                key=lambda n: n['last_heard'], default=None
            )
            self._inject_markers_js(nodes_loc, most_recent)
        if self._tr_records:
            self._draw_traceroute_js()

    def set_selected_node(self, node_id: Optional[str]):
        import time
        self._selected_node_id      = node_id
        self._pan_to_selected       = node_id is not None
        self._selection_stable_time = time.time()
        if node_id:
            self._popup_check_timer.start()

    def clear_auto_pan(self):
        self._pan_to_selected = False

    def mark_node_active(self, node_id: str):
        """Marca nó como o mais recentemente activo (vermelho no mapa).
        Apenas um nó fica vermelho de cada vez. Persiste até outro pacote chegar."""
        if not node_id:
            return
        self._last_active_id = node_id.lower()

    def clear_active_node(self):
        """Limpa o marcador vermelho (ex: ao desligar)."""
        self._last_active_id = ""

    def update_map(self, nodes: list, filter_text: str = ""):
        self._current_nodes  = nodes
        self._current_filter = filter_text

        nodes_loc = [n for n in nodes
                     if n.get('latitude') is not None and n.get('longitude') is not None]

        if filter_text:
            fl = filter_text.lower()
            nodes_loc = [n for n in nodes_loc if any(
                fl in str(n.get(k, "")).lower()
                for k in ('id_string', 'long_name', 'short_name')
            )]

        if not nodes_loc:
            self._show_placeholder()
            return

        most_recent = max(
            (n for n in nodes_loc if isinstance(n.get('last_heard'), datetime)),
            key=lambda n: n['last_heard'], default=None
        )
        new_marker_data = self._build_marker_data(nodes_loc, most_recent)

        if not self._map_initialized:
            if self._pan_to_selected and self._selected_node_id:
                sel = next((n for n in nodes_loc
                            if n.get('id_string') == self._selected_node_id), None)
            else:
                sel = None

            if sel:
                clat, clon, zoom = sel['latitude'], sel['longitude'], 13
            else:
                clat = sum(n['latitude']  for n in nodes_loc) / len(nodes_loc)
                clon = sum(n['longitude'] for n in nodes_loc) / len(nodes_loc)
                zoom = 8

            self._last_marker_data = new_marker_data
            self._init_map(clat, clon, zoom)
            return

        self._last_marker_data = new_marker_data

        if self._pan_to_selected and self._selected_node_id:
            sel = next((n for n in nodes_loc
                        if n.get('id_string') == self._selected_node_id), None)
            if sel:
                js_pan = (f"window._map.setView([{sel['latitude']},"
                          f"{sel['longitude']}],13);")
                self.web.page().runJavaScript(js_pan)

        self._inject_markers_js(nodes_loc, most_recent)

    def _build_marker_data(self, nodes_loc: list, most_recent) -> list:
        markers = []
        for node in nodes_loc:
            is_selected = (node.get('id_string') == self._selected_node_id
                           and self._selected_node_id is not None)
            via_mqtt    = node.get('via_mqtt')
            via         = "☁ MQTT" if via_mqtt is True else "RF"
            snr         = node.get('snr')
            batt        = node.get('battery_level')
            snr_str     = f"{snr:.1f} dB" if snr is not None else "—"
            batt_str    = f"{batt}%"       if batt is not None else "—"
            name        = node.get('long_name') or node.get('id_string', '')
            short       = node.get('short_name') or node.get('id_string', '')
            has_key     = bool(node.get('public_key', ''))
            enc_icon    = "🔒" if has_key else "🔓"
            node_id     = node.get('id_string', '')
            is_fav      = _FAVORITES.is_favorite(node_id)
            fav_star    = "⭐ " if is_fav else ""

            # Nó inactivo se last_heard > 2 horas (ou sem last_heard)
            last_heard     = node.get('last_heard')
            is_inactive    = True
            if isinstance(last_heard, datetime):
                is_inactive = (datetime.now() - last_heard) > timedelta(hours=2)

            # Nó activo recentemente: o último a enviar um pacote
            is_active_now = node_id.lower() == self._last_active_id

            # Formato legível para o popup
            if isinstance(last_heard, datetime):
                lh_str = last_heard.strftime("%H:%M:%S  %d/%m/%Y")
            else:
                lh_str = "—"

            # Prioridade de cor:
            # 1. Seleccionado (verde)
            # 2. Pacote recebido agora (vermelho) — prevalece sobre cinzento
            # 3. Inactivo >2h (cinzento)
            # 4. MQTT (laranja)  5. RF (azul)
            if is_selected:
                color, border_color, radius = "#00ff88", "#00cc66", 9
            elif is_active_now:
                color, border_color, radius = "#ff4444", "#cc0000", 7
            elif is_inactive:
                color, border_color, radius = "#555566", "#444455", 5
            elif via_mqtt is True:
                color, border_color, radius = "#ff8800", "#cc6600", 6
            else:
                color, border_color, radius = "#2b7cd3", "#1050aa", 6

            # Popup com botão de traceroute embutido
            popup_html = (
                f"<div style='font-family:monospace;font-size:12px;min-width:200px'>"
                f"<b>{'★ ' if is_selected else ''}{fav_star}{html.escape(name)}</b>"
                f"<hr style='margin:4px 0;border-color:#30363d'>"
                f"<table style='border-spacing:2px 2px;width:100%'>"
                f"<tr><td>🆔</td><td>{html.escape(str(node_id))}</td></tr>"
                f"<tr><td>📡</td><td>Via: <b>{via}</b></td></tr>"
                f"<tr><td>📶</td><td>SNR: {snr_str}</td></tr>"
                f"<tr><td>🔋</td><td>{batt_str}</td></tr>"
                f"<tr><td>{enc_icon}</td><td>DM: {'PKI' if has_key else 'PSK'}</td></tr>"
                f"<tr><td>🕐</td><td>{html.escape(lh_str)}</td></tr>"
                f"</table>"
                + (f"<div style='color:#00ff88;font-size:11px;margin-top:4px'>● Seleccionado</div>"
                   if is_selected else "")
                + f"<div style='margin-top:8px;text-align:center'>"
                  f"<a href='traceroute:{node_id}' style='color:#58a6ff;text-decoration:none;"
                  f"border:1px solid #58a6ff;border-radius:4px;padding:2px 8px;font-size:11px'>"
                  f"📡 Traceroute</a></div>"
                f"</div>"
            )

            tooltip = (f"{'⭐ ' if is_fav else ''}{short}  ·  {via}  ·  SNR:{snr_str}  ·  🔋{batt_str}")

            markers.append({
                "lat": node['latitude'], "lon": node['longitude'],
                "color": color, "border_color": border_color,
                "radius": radius, "selected": is_selected,
                "tooltip": ("★ " if is_selected else "") + tooltip,
                "popup": popup_html,
                "node_id": node_id,
            })
        return markers

    def set_traceroute_callback(self, fn):
        """Regista callback para quando o utilizador clica em 'Traceroute' no popup do mapa."""
        self._traceroute_cb = fn

    def _inject_markers_js(self, nodes_loc: list, most_recent):
        markers_data = self._build_marker_data(nodes_loc, most_recent)
        markers_json = json.dumps(markers_data, ensure_ascii=False)
        js = (
            "(function(){"
            "if(!window._mapReady){console.warn('map not ready');return;}"
            "window._selPopupClosed=false;"
            "window._markerLayer.clearLayers();"
            "var pins=" + markers_json + ";"
            "pins.forEach(function(p){"
            "var c=L.circleMarker([p.lat,p.lon],{"
            "radius:p.radius,fillColor:p.color,color:p.border_color,"
            "weight:p.selected?4:2,opacity:1,fillOpacity:p.selected?1.0:0.85});"
            # Tooltip numa linha — sem white-space:pre-line no CSS para tooltips de markers
            "c.bindTooltip(p.tooltip,{permanent:p.selected,direction:'top',"
            "className:'custom-tooltip',sticky:false});"
            "c.bindPopup(p.popup,{maxWidth:300,className:'custom-popup'});"
            "if(p.selected){"
            "c.on('popupclose',function(){window._selPopupClosed=true;});"
            "}"
            "c.on('popupopen',function(){"
            "setTimeout(function(){"
            "var links=document.querySelectorAll('a[href^=\"traceroute:\"]');"
            "links.forEach(function(a){"
            "if(!a._trBound){"
            "a._trBound=true;"
            "a.addEventListener('click',function(e){"
            "e.preventDefault();"
            "if(!window._trPendingLock){"
            "window._trPendingLock=true;"
            "window.qt_traceroute_request=a.getAttribute('href').replace('traceroute:','');"
            "setTimeout(function(){window._trPendingLock=false;},2000);"
            "}"
            "});"
            "}"
            "});"
            "},100);"
            "});"
            "window._markerLayer.addLayer(c);"
            "if(p.selected){c.openPopup();}"
            "});"
            "})();"
        )
        self.web.page().runJavaScript(js)

    def _check_popup_closed(self):
        import time
        if not self._selected_node_id or not self._map_initialized:
            self._popup_check_timer.stop()
            return
        if self._selection_stable_time == 0.0 or \
                (time.time() - self._selection_stable_time) < 1.0:
            return
        self.web.page().runJavaScript(
            "window._selPopupClosed===true?'yes':'no';",
            self._on_popup_check_result
        )

    def _on_popup_check_result(self, result):
        if result == 'yes':
            self.web.page().runJavaScript("window._selPopupClosed=false;")
            self.deselect_node()

    def deselect_node(self):
        self._selected_node_id = None
        self._pan_to_selected  = False
        self._last_marker_data = []
        self._popup_check_timer.stop()
        self.node_deselected.emit()
        if self._map_initialized and self._current_nodes:
            nodes_loc = [n for n in self._current_nodes
                         if n.get('latitude') is not None and n.get('longitude') is not None]
            if nodes_loc:
                most_recent = max(
                    (n for n in nodes_loc if isinstance(n.get('last_heard'), datetime)),
                    key=lambda n: n['last_heard'], default=None
                )
                self._inject_markers_js(nodes_loc, most_recent)

    def _on_tr_all_toggled(self, checked: bool):
        """Botão 'Mostrar todas': ON → marca todos os itens; OFF → desmarca todos."""
        self._tr_show_all = checked
        self.btn_tr_all.setText("◉  Mostrar todas" if checked else "○  Mostrar todas")

        # Actualiza checkboxes de todos os itens sem disparar _on_tr_item_changed
        self._tr_blocking_signals = True
        for i in range(self._tr_list_widget.count()):
            item = self._tr_list_widget.item(i)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._tr_blocking_signals = False

        if checked:
            self._draw_traceroute_js()
        else:
            self._clear_traceroute_js()

    def _on_tr_item_changed(self, item: QListWidgetItem):
        """Checkbox de um item mudou — redesenha o mapa com os itens marcados."""
        if self._tr_blocking_signals:
            return

        # Actualiza _tr_show_all conforme o estado actual de todos os itens
        all_checked  = all(
            self._tr_list_widget.item(i).checkState() == Qt.Checked
            for i in range(self._tr_list_widget.count())
        )
        none_checked = all(
            self._tr_list_widget.item(i).checkState() == Qt.Unchecked
            for i in range(self._tr_list_widget.count())
        )
        self._tr_show_all = all_checked
        # Actualiza botão sem disparar o seu slot
        self.btn_tr_all.blockSignals(True)
        self.btn_tr_all.setChecked(all_checked)
        self.btn_tr_all.setText("◉  Mostrar todas" if all_checked else "○  Mostrar todas")
        self.btn_tr_all.blockSignals(False)

        if none_checked:
            self._clear_traceroute_js()
        else:
            self._draw_traceroute_js()

    def _on_tr_clear(self):
        """Limpa todos os registos de traceroute — pede confirmação primeiro."""
        if not self._tr_records:
            return
        reply = QMessageBox.question(
            self, "Limpar lista de traceroutes",
            f"Tem a certeza que deseja remover todos os {len(self._tr_records)} "
            f"traceroute(s) da lista?\n\nAs linhas de rota no mapa também serão removidas.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return
        self._tr_records          = []
        self._tr_show_all         = True
        self._tr_blocking_signals = True
        self._tr_list_widget.clear()
        self._tr_blocking_signals = False
        self.btn_tr_all.setChecked(True)
        self.btn_tr_all.setText("◉  Mostrar todas")
        self._clear_traceroute_js()

    def show_traceroute_on_map(self, forward_edges: list, back_edges: list,
                               all_nodes: list, origin_id: str = "",
                               dest_id: str = "", origin_name: str = "",
                               dest_name: str = ""):
        """Adiciona um novo registo de traceroute à lista e redesenha."""
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%H:%M:%S")

        # Verifica se o destino tem coords (se não tiver, não vale a pena no mapa)
        node_idx = {n.get('id_string', ''): n for n in all_nodes}
        def _has_coords(nid):
            n = node_idx.get(nid) or node_idx.get(nid.lower() if nid else '')
            return bool(n and n.get('latitude') is not None)

        dest_has_loc = _has_coords(dest_id)

        rec = {
            'id':            len(self._tr_records),
            'ts':            ts,
            'origin_id':     origin_id,
            'origin_name':   origin_name or origin_id,
            'dest_id':       dest_id,
            'dest_name':     dest_name or dest_id,
            'forward_edges': list(forward_edges),
            'back_edges':    list(back_edges),
            'all_nodes':     list(all_nodes),
            'dest_has_loc':  dest_has_loc,
        }
        self._tr_records.append(rec)
        self._tr_nodes = list(all_nodes)

        # Adiciona item à lista com checkbox marcado por omissão
        # Usa short_name do nó se disponível, senão primeiras 8 chars do id
        def _short(nid, name):
            n = node_idx.get(nid) or node_idx.get(nid.lower() if nid else '')
            sn = (n.get('short_name') or '').strip() if n else ''
            if sn:
                return sn
            return name.split(' ')[0][:8] if name else nid[:8]

        origin_short = _short(origin_id, origin_name)
        dest_short   = _short(dest_id, dest_name)
        loc_tag      = "📍" if dest_has_loc else "❓"
        label        = f"{ts}\n→ {origin_short}\n  {loc_tag} {dest_short}"
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, rec['id'])
        item.setToolTip(f"{origin_name} → {dest_name}\n{ts}")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)   # marcado por omissão
        self._tr_blocking_signals = True
        self._tr_list_widget.addItem(item)
        self._tr_blocking_signals = False
        self._tr_list_widget.scrollToBottom()

        if self._map_initialized:
            self._draw_traceroute_js()

    def _build_node_cache(self) -> dict:
        """Constrói índice id_string→node em O(N) — usado por todas as operações de traceroute.
        Cobre nós actuais do mapa + nós de todos os registos de traceroute.
        """
        cache: dict = {}
        def _add(n):
            ids = (n.get('id_string') or '').strip().lower()
            if ids:
                cache.setdefault(ids, n)

        for n in self._current_nodes:
            _add(n)
        for rec in self._tr_records:
            for n in rec.get('all_nodes', []):
                _add(n)
        return cache

    def _node_idx(self) -> dict:
        """Alias para compatibilidade — usa _build_node_cache."""
        return self._build_node_cache()

    def _get_active_records(self) -> list:
        """Retorna os registos cujo item na lista está marcado (checked)."""
        if not self._tr_records:
            return []
        checked_ids = set()
        for i in range(self._tr_list_widget.count()):
            item = self._tr_list_widget.item(i)
            if item and item.checkState() == Qt.Checked:
                rid = item.data(Qt.UserRole)
                if rid is not None:
                    checked_ids.add(rid)
        return [rec for rec in self._tr_records if rec['id'] in checked_ids]

    def _get_active_edges(self) -> list:
        """Retorna segmentos entre nós com GPS dos registos activos.
        Constrói o cache de nós uma única vez para toda a operação.
        """
        active = self._get_active_records()
        if not active:
            return []

        # Cache único — O(1) por lookup; sem scan linear por nó
        cache = self._build_node_cache()

        def has_gps(nid):
            n = cache.get(nid.lower()) if nid else None
            return bool(n and n.get('latitude') is not None)

        result = []
        seen   = set()

        for rec in active:
            for direction, edge_list in (('ida',   rec['forward_edges']),
                                         ('volta', rec['back_edges'])):
                if not edge_list:
                    continue

                # Cadeia ordenada de nós
                chain = []
                for a, b, snr in edge_list:
                    if not chain:
                        chain.append((a, None))
                    chain.append((b, snr))

                gps_idx = [i for i, (nid, _) in enumerate(chain) if has_gps(nid)]
                if len(gps_idx) < 2:
                    continue

                for k in range(len(gps_idx) - 1):
                    i_from, i_to = gps_idx[k], gps_idx[k + 1]
                    nid_a   = chain[i_from][0]
                    nid_b   = chain[i_to][0]
                    snr     = chain[i_to][1] or 0.0
                    skipped = [chain[j][0] for j in range(i_from + 1, i_to)]
                    key = (nid_a, nid_b, direction)
                    if key not in seen:
                        result.append((nid_a, nid_b, snr, direction, skipped))
                        seen.add(key)

        return result

    def _find_node(self, nid: str):
        """Lookup pontual — para uso esporádico. Usar _build_node_cache em loops."""
        if not nid:
            return None
        nid_l = nid.lower()
        for n in self._current_nodes:
            if (n.get('id_string') or '').strip().lower() == nid_l:
                return n
        for rec in self._tr_records:
            for n in rec.get('all_nodes', []):
                if (n.get('id_string') or '').strip().lower() == nid_l:
                    return n
        return None

    def _draw_traceroute_js(self):
        """Desenha os segmentos entre nós com GPS. Cache construído uma única vez."""
        if not self._map_initialized:
            return

        edges = self._get_active_edges()
        if not edges:
            self._clear_traceroute_js()
            return

        # Reutiliza o mesmo cache — não reconstrói
        cache = self._build_node_cache()

        def find(nid):
            return cache.get(nid.lower()) if nid else None

        def pos(nid):
            n = find(nid)
            if not n:
                return None, None
            lat, lon = n.get('latitude'), n.get('longitude')
            return (float(lat), float(lon)) if lat is not None and lon is not None else (None, None)

        def node_info(nid):
            n = find(nid)
            if not n:
                return f"❓ {nid}"
            sn  = (n.get('short_name') or n.get('long_name') or nid).strip()
            via = "MQTT" if n.get('via_mqtt') else "RF"
            gps = "📍" if n.get('latitude') is not None else "❓"
            return f"{gps} {sn}  {via}"

        from collections import defaultdict

        # Separa cada segmento por direcção — ida e volta ficam em linhas distintas.
        # Constrói lista de segmentos normalizados.
        # Chave canónica: par de coords ordenado — independente da direcção.
        raw_segments = []
        canonical_count = {}   # (lat1,lon1,lat2,lon2) → quantas direcções usam este segmento

        for a, b, snr, direction, skipped in edges:
            la, loa = pos(a)
            lb, lob = pos(b)
            if la is None or lb is None:
                continue
            snr_str   = f"{snr:+.1f} dB" if snr != 0.0 else "SNR desconhecido"
            dir_arrow = "→" if direction == 'ida' else "←"
            skip_str  = ""
            if skipped:
                skip_str = f"\n⚠ Via (sem GPS): {', '.join(node_info(s) for s in skipped)}"
            dir_label = "Ida" if direction == 'ida' else "Volta"
            tip = (f"{dir_arrow} {dir_label}: {node_info(a)}  {dir_arrow}  {node_info(b)}"
                   f"  |  SNR: {snr_str}{skip_str}")
            col = '#00cc44' if direction == 'ida' else '#007a29'
            # off base: ida=+1, volta=-1
            off_base = 1 if direction == 'ida' else -1

            # Chave canónica: sempre o ponto de menor coordenada primeiro
            if (la, loa) <= (lb, lob):
                ck = (round(la,6), round(loa,6), round(lb,6), round(lob,6))
                flipped = False
            else:
                ck = (round(lb,6), round(lob,6), round(la,6), round(loa,6))
                flipped = True

            canonical_count[ck] = canonical_count.get(ck, 0) + 1
            raw_segments.append({
                'la': la, 'loa': loa, 'lb': lb, 'lob': lob,
                'tip': tip, 'col': col, 'off_base': off_base,
                'ck': ck, 'flipped': flipped,
            })

        if not raw_segments:
            self._clear_traceroute_js()
            return

        # Constrói segment_list final:
        # - segmentos únicos (só ida ou só volta): off=0 (linha centrada)
        # - segmentos partilhados (ida E volta): offset lateral de ±4px
        segment_list = []
        for seg in raw_segments:
            ck      = seg['ck']
            shared  = canonical_count[ck] >= 2   # mesmo caminho em ambas as direcções

            if not shared:
                off = 0   # linha centrada — sem offset
                la, loa, lb, lob = seg['la'], seg['loa'], seg['lb'], seg['lob']
            else:
                # Normaliza para direcção canónica SEM inverter off_base —
                # o off_base (±1) mantém-se: ida sempre +1, volta sempre -1,
                # independentemente de qual endpoint é maior/menor
                if seg['flipped']:
                    la, loa = seg['lb'], seg['lob']
                    lb, lob = seg['la'], seg['loa']
                else:
                    la, loa = seg['la'], seg['loa']
                    lb, lob = seg['lb'], seg['lob']
                off = seg['off_base']   # +1 ou -1, não invertido

            segment_list.append({
                'lat1': la, 'lon1': loa, 'lat2': lb, 'lon2': lob,
                'tip': seg['tip'], 'col': seg['col'], 'off': off,
            })

        if not segment_list:
            self._clear_traceroute_js()
            return

        js = (
            "(function(){"
            "if(!window._mapReady){return;}"
            "var segs=" + json.dumps(segment_list, ensure_ascii=False) + ";"
            "window._trSegs=segs;"
            "function drawSegs(){"
            "if(window._trLayer){window._map.removeLayer(window._trLayer);}"
            "window._trLayer=L.layerGroup().addTo(window._map);"
            "segs.forEach(function(e){"
            # Normaliza sempre de lat1→lat2 para o cálculo do perpendicular
            # O off (+1 ida, -1 volta) é aplicado ao perpendicular normalizado
            # Assim ida e volta ficam sempre em lados opostos independentemente
            # de qual endpoint é origem/destino
            "var p1=window._map.latLngToLayerPoint([e.lat1,e.lon1]);"
            "var p2=window._map.latLngToLayerPoint([e.lat2,e.lon2]);"
            "var dx=p2.x-p1.x,dy=p2.y-p1.y;"
            "var len=Math.sqrt(dx*dx+dy*dy)||1e-9;"
            # Perpendicular: roda 90° para a esquerda — sempre o mesmo sentido
            "var nx=-dy/len,ny=dx/len;"
            "var off=3*e.off;"
            "var q1=window._map.layerPointToLatLng([p1.x+nx*off,p1.y+ny*off]);"
            "var q2=window._map.layerPointToLatLng([p2.x+nx*off,p2.y+ny*off]);"
            "L.polyline([[q1.lat,q1.lng],[q2.lat,q2.lng]],"
            "{color:e.col,weight:2,opacity:0.90,interactive:true})"
            ".bindTooltip(e.tip,{sticky:true,className:'custom-tooltip-tr'})"
            ".addTo(window._trLayer);"
            "});"
            "}"
            "window._trRedraw=drawSegs;"
            "drawSegs();"
            "})();"
        )
        self.web.page().runJavaScript(js)

    def _clear_traceroute_js(self):
        if not self._map_initialized:
            return
        self.web.page().runJavaScript(
            "if(window._trLayer){window._map.removeLayer(window._trLayer);"
            "window._trLayer=null;}"
        )

    def clear_traceroute_layer(self):
        self._tr_records          = []
        self._tr_show_all         = True
        self._tr_blocking_signals = True
        self._tr_list_widget.clear()
        self._tr_blocking_signals = False
        self.btn_tr_all.setChecked(True)
        self.btn_tr_all.setText("◉  Mostrar todas")
        self._clear_traceroute_js()

    def _on_theme_clicked(self, idx: int):
        self._theme_idx = idx
        for i, btn in enumerate(self._theme_buttons):
            btn.setChecked(i == idx)
        self._map_initialized  = False
        self._last_marker_data = []
        if self._current_nodes:
            self.update_map(self._current_nodes)  # sem filtro — mapa mostra sempre tudo

    def _check_traceroute_request(self):
        """Verifica se o utilizador clicou em 'Traceroute' num popup do mapa."""
        if not self._map_initialized or not self._traceroute_cb:
            return
        if not self.isVisible():
            return
        self.web.page().runJavaScript(
            "(function(){var id=window.qt_traceroute_request||null;"
            "window.qt_traceroute_request=null;return id;})();",
            self._on_traceroute_request_result
        )

    def _on_traceroute_request_result(self, node_id):
        if node_id and self._traceroute_cb:
            self._traceroute_cb(node_id)

    def closeEvent(self, event):
        self._tr_poll_timer.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# ChannelsTab
# ---------------------------------------------------------------------------
class ChannelsTab(QWidget):
    ROLES        = ["PRIMARY", "SECONDARY", "DISABLED"]
    MODEM_PRESETS = [
        "LONG_FAST","LONG_SLOW","VERY_LONG_SLOW","MEDIUM_SLOW",
        "MEDIUM_FAST","SHORT_SLOW","SHORT_FAST","LONG_MODERATE",
    ]
    reboot_required = pyqtSignal()   # emitido após guardar com sucesso

    def __init__(self, parent=None):
        super().__init__(parent)
        self._iface    = None
        self._channels: list = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.status_lbl = QLabel("⚠  Sem conexão")
        self.status_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        top.addWidget(self.status_lbl)
        top.addStretch()

        btn_reload = QPushButton("🔄  Recarregar")
        btn_reload.clicked.connect(self._load_channels)
        top.addWidget(btn_reload)

        btn_add = QPushButton("➕  Adicionar Canal")
        btn_add.clicked.connect(self._add_channel)
        top.addWidget(btn_add)

        btn_save = QPushButton("💾  Guardar Alterações")
        btn_save.setObjectName("btn_connect")
        btn_save.clicked.connect(self._save_all)
        top.addWidget(btn_save)

        root.addLayout(top)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:{DARK_BG};}}")
        self._channels_container = QWidget()
        self._channels_container.setStyleSheet(f"background:{DARK_BG};")
        self._channels_layout = QVBoxLayout(self._channels_container)
        self._channels_layout.setSpacing(8)
        self._channels_layout.setContentsMargins(0, 0, 0, 0)
        self._channels_layout.addStretch()
        scroll.setWidget(self._channels_container)
        root.addWidget(scroll)

        self._channel_widgets: list = []

    def set_interface(self, iface):
        self._iface = iface
        self._load_channels()

    def clear_interface(self):
        self._iface = None
        self._channels = []
        self._clear_rows()
        self.status_lbl.setText("⚠  Sem conexão")

    def _load_channels(self):
        if not self._iface:
            self.status_lbl.setText("⚠  Sem conexão")
            return
        try:
            node = self._iface.localNode
            self._channels = list(node.channels) if node and node.channels else []
            self._rebuild_ui()
            self.status_lbl.setText(f"✅  {len(self._channels)} canal(ais) carregados")
        except Exception as e:
            logger.error(f"Erro ao carregar canais: {e}", exc_info=True)
            self.status_lbl.setText(f"❌  Erro: {e}")

    def _clear_rows(self):
        for row in self._channel_widgets:
            row.setParent(None)
            row.deleteLater()
        self._channel_widgets.clear()
        while self._channels_layout.count():
            item = self._channels_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_ui(self):
        self._clear_rows()
        for i, ch in enumerate(self._channels):
            row = _ChannelRow(i, ch, parent=self)
            row.remove_requested.connect(self._remove_channel)
            self._channels_layout.addWidget(row)
            self._channel_widgets.append(row)
        self._channels_layout.addStretch()

    def _add_channel(self):
        if not self._iface:
            QMessageBox.warning(self, "Sem Conexão", "Conecte-se primeiro.")
            return
        used = {ch.index for ch in self._channels if hasattr(ch, 'index')}
        for idx in range(8):
            if idx not in used:
                break
        else:
            QMessageBox.warning(self, "Limite atingido",
                                "O máximo de 8 canais (0-7) já foi atingido.")
            return

        try:
            from meshtastic.protobuf.channel_pb2 import Channel
            new_ch = Channel()
            new_ch.index = idx
            new_ch.role  = 2
            new_ch.settings.name = f"Canal {idx}"
            self._channels.append(new_ch)
            self._rebuild_ui()
            self.status_lbl.setText(f"➕  Canal {idx} adicionado — edite e guarde")
        except Exception as e:
            logger.error(f"Erro ao criar canal: {e}", exc_info=True)
            QMessageBox.critical(self, "Erro", f"Não foi possível criar canal:\n{e}")

    def _remove_channel(self, index: int):
        reply = QMessageBox.question(
            self, "Remover Canal",
            f"Remover o canal com índice {index}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self._channels = [ch for ch in self._channels
                          if getattr(ch, 'index', None) != index]
        self._rebuild_ui()
        self.status_lbl.setText(f"🗑  Canal {index} marcado para remoção — guarde para aplicar")

    def _save_all(self):
        if not self._iface:
            QMessageBox.warning(self, "Sem Conexão", "Não está conectado.")
            return
        reply = QMessageBox.question(
            self, "Guardar Canais",
            "Guardar todas as alterações de canais no nó?\n\n"
            "⚠  O nó irá reiniciar para aplicar as alterações.\n"
            "    A ligação TCP será temporariamente perdida e restabelecida.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.status_lbl.setText("A guardar…")
        errors = []
        saved  = 0
        try:
            node             = self._iface.localNode
            present_indices  = set()

            for row in self._channel_widgets:
                row.apply_to_channel()

            for ch in self._channels:
                try:
                    node.writeChannel(ch.index)
                    present_indices.add(ch.index)
                    saved += 1
                except Exception as e:
                    errors.append(f"Canal {getattr(ch,'index','?')}: {e}")

            for idx in range(8):
                if idx not in present_indices and idx != 0:
                    try:
                        from meshtastic.protobuf.channel_pb2 import Channel
                        empty      = Channel()
                        empty.index = idx
                        empty.role  = 0
                        node.writeChannel(idx)
                    except Exception:
                        pass

            msg = f"✅  {saved} canal(ais) guardados"
            if errors:
                msg += f" | ⚠ {len(errors)} erro(s)"
            self.status_lbl.setText(msg)
            QMessageBox.information(
                self, "Canais Guardados",
                f"{saved} canal(ais) guardados no nó." +
                (f"\n\nErros:\n" + "\n".join(errors[:5]) if errors else "")
            )
            if saved > 0:
                self.reboot_required.emit()
            else:
                self._load_channels()

        except Exception as e:
            logger.error(f"Erro ao guardar canais: {e}", exc_info=True)
            self.status_lbl.setText(f"❌ Erro: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao guardar canais:\n{e}")


class _ChannelRow(QWidget):
    remove_requested = pyqtSignal(int)

    def __init__(self, list_index: int, channel, parent=None):
        super().__init__(parent)
        self._channel  = channel
        self._ch_index = getattr(channel, 'index', list_index)
        self._build(channel)

    def _build(self, ch):
        self.setStyleSheet(
            f"background:{PANEL_BG};border:1px solid {BORDER_COLOR};border-radius:8px;"
        )
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 10, 12, 10)
        main.setSpacing(8)

        hdr        = QHBoxLayout()
        idx        = getattr(ch, 'index', 0)
        role_num   = getattr(ch, 'role', 0)
        role_names = {0: "DISABLED", 1: "PRIMARY", 2: "SECONDARY"}
        role_str   = role_names.get(role_num, str(role_num))
        color      = ACCENT_GREEN if role_num == 1 else (ACCENT_BLUE if role_num == 2 else TEXT_MUTED)

        lbl_idx = QLabel(f"📻  Canal {idx}")
        lbl_idx.setStyleSheet(f"color:{color};font-weight:bold;font-size:13px;")
        hdr.addWidget(lbl_idx)
        hdr.addStretch()

        btn_remove = QPushButton("🗑")
        btn_remove.setFixedSize(28, 28)
        btn_remove.setStyleSheet(
            f"background:{DARK_BG};color:{ACCENT_RED};"
            f"border:1px solid {ACCENT_RED};border-radius:4px;"
        )
        btn_remove.clicked.connect(lambda: self.remove_requested.emit(self._ch_index))
        hdr.addWidget(btn_remove)
        main.addLayout(hdr)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        def mk_lbl(t):
            l = QLabel(t + ":")
            l.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
            return l

        settings = getattr(ch, 'settings', None)
        name_val  = getattr(settings, 'name', '') if settings else ''
        self.w_name = QLineEdit(name_val or "")
        self.w_name.setPlaceholderText("Nome do canal")
        form.addRow(mk_lbl("Nome"), self.w_name)

        self.w_role = QComboBox()
        self.w_role.addItems(["DISABLED", "PRIMARY", "SECONDARY"])
        self.w_role.setCurrentIndex(min(role_num, 2))
        form.addRow(mk_lbl("Papel"), self.w_role)

        psk_bytes = getattr(settings, 'psk', b'') if settings else b''
        # Mostra como Base64 — formato standard das apps iOS/Android
        if isinstance(psk_bytes, (bytes, bytearray)) and len(psk_bytes) > 0:
            import base64 as _b64
            psk_display = _b64.b64encode(psk_bytes).decode('ascii')
        else:
            psk_display = ''
        self.w_psk = QLineEdit(psk_display)
        self.w_psk.setPlaceholderText("Base64 (ex: AQ==)  ou  default / none / random")

        # Selector de tipo + botão de geração
        self.w_psk_type = QComboBox()
        self.w_psk_type.addItems(["256-bit (32 bytes)", "128-bit (16 bytes)", "Default (AQ==)"])
        self.w_psk_type.setFixedWidth(155)
        self.w_psk_type.setStyleSheet(
            f"background:{DARK_BG};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;padding:2px 4px;font-size:11px;"
        )
        btn_gen_psk = QPushButton("🔑 Gerar")
        btn_gen_psk.setFixedWidth(70)
        btn_gen_psk.setStyleSheet(
            f"QPushButton{{background:{PANEL_BG};color:{ACCENT_BLUE};"
            f"border:1px solid {ACCENT_BLUE};border-radius:4px;padding:2px 6px;font-size:11px;}}"
            f"QPushButton:hover{{background:{ACCENT_BLUE};color:#000;}}"
        )
        btn_gen_psk.setToolTip("Gera uma chave PSK aleatória do tipo seleccionado")

        def _gen_psk():
            import os as _os, base64 as _b64
            t = self.w_psk_type.currentIndex()
            if t == 0:
                key = _os.urandom(32)
            elif t == 1:
                key = _os.urandom(16)
            else:
                key = bytes([1])   # Default = AQ==
            self.w_psk.setText(_b64.b64encode(key).decode('ascii'))

        btn_gen_psk.clicked.connect(_gen_psk)

        psk_row = QHBoxLayout()
        psk_row.setSpacing(4)
        psk_row.addWidget(self.w_psk)
        psk_row.addWidget(self.w_psk_type)
        psk_row.addWidget(btn_gen_psk)
        form.addRow(mk_lbl("PSK"), psk_row)

        self.w_uplink = QCheckBox("Uplink MQTT habilitado")
        self.w_uplink.setChecked(bool(getattr(settings, 'uplink_enabled', False) if settings else False))
        form.addRow(mk_lbl("Uplink MQTT"), self.w_uplink)

        self.w_downlink = QCheckBox("Downlink MQTT habilitado")
        self.w_downlink.setChecked(bool(getattr(settings, 'downlink_enabled', False) if settings else False))
        form.addRow(mk_lbl("Downlink MQTT"), self.w_downlink)

        mod_settings = getattr(settings, 'module_settings', None) if settings else None
        self.w_muted = QCheckBox("Silenciar notificações (is_muted)")
        self.w_muted.setChecked(bool(getattr(mod_settings, 'is_muted', False) if mod_settings else False))
        form.addRow(mk_lbl("Silenciar"), self.w_muted)

        pos_prec     = getattr(settings, 'module_settings', None)
        pos_prec_val = getattr(pos_prec, 'position_precision', 0) if pos_prec else 0
        self.w_pos_prec = QSpinBox()
        self.w_pos_prec.setRange(0, 32)
        self.w_pos_prec.setValue(int(pos_prec_val))
        form.addRow(mk_lbl("Precisão posição"), self.w_pos_prec)

        main.addLayout(form)

    def apply_to_channel(self):
        ch       = self._channel
        settings = getattr(ch, 'settings', None)
        if settings is None:
            return
        try:
            settings.name              = self.w_name.text().strip()
            role_map = {"DISABLED": 0, "PRIMARY": 1, "SECONDARY": 2}
            ch.role                    = role_map.get(self.w_role.currentText(), 2)
            settings.uplink_enabled    = self.w_uplink.isChecked()
            settings.downlink_enabled  = self.w_downlink.isChecked()
            if hasattr(settings, 'module_settings'):
                settings.module_settings.is_muted = self.w_muted.isChecked()
            psk_str = self.w_psk.text().strip()
            if psk_str:
                import base64 as _b64
                try:
                    ps = psk_str.lower()
                    if ps == 'default':
                        settings.psk = bytes([1])
                    elif ps == 'none':
                        settings.psk = bytes([0])
                    elif ps == 'random':
                        import os as _os
                        settings.psk = _os.urandom(32)
                    elif psk_str.startswith('0x') or psk_str.startswith('0X'):
                        settings.psk = bytes.fromhex(psk_str[2:])
                    else:
                        # Assume Base64 (formato das apps iOS/Android)
                        settings.psk = _b64.b64decode(psk_str)
                except Exception as _e:
                    logger.warning(f"PSK inválido '{psk_str}': {_e}")
            if hasattr(settings, 'module_settings'):
                settings.module_settings.position_precision = self.w_pos_prec.value()
        except Exception as e:
            logger.warning(f"Erro ao aplicar canal {self._ch_index}: {e}")


# ---------------------------------------------------------------------------
# Config definitions (unchanged)
# ---------------------------------------------------------------------------
MESHTASTIC_CONFIG_DEFS = {
    "localConfig.device": [
        ("Papel do nó",             "role",                    "combo",
         ["CLIENT","CLIENT_MUTE","CLIENT_HIDDEN","TRACKER","LOST_AND_FOUND",
          "SENSOR","TAK","TAK_TRACKER","REPEATER","ROUTER","ROUTER_CLIENT"]),
        ("Retransmitir mensagens",  "rebroadcast_mode",        "combo",
         ["ALL","ALL_SKIP_DECODING","LOCAL_ONLY","KNOWN_ONLY","NONE"]),
        ("Serial habilitado",       "serial_enabled",          "bool",   None),
        ("Debug via serial",        "debug_log_enabled",       "bool",   None),
        ("Butão GPIO",              "button_gpio",             "spin_int",(0,39)),
        ("Buzzer GPIO",             "buzzer_gpio",             "spin_int",(0,39)),
        ("Duplo clique alimentação","double_tap_as_button_press","bool",  None),
        ("LED em heartbeat",        "led_heartbeat_disabled",  "bool",   None),
        ("Intervalo broadcast NodeInfo (s)", "node_info_broadcast_secs","spin_int",(0,604800)),
        ("Modo avião",              "is_managed",              "bool",   None),
    ],
    "localConfig.position": [
        ("Modo GPS",                "gps_mode",                "combo",
         ["DISABLED","ENABLED","NOT_PRESENT"]),
        ("Intervalo update GPS (s)","gps_update_interval",     "spin_int",(0,86400)),
        ("Tentativa GPS (s)",       "gps_attempt_time",        "spin_int",(0,3600)),
        ("Intervalo broadcast pos (s)","position_broadcast_secs","spin_int",(0,86400)),
        ("Smart broadcast pos.",    "position_broadcast_smart_enabled","bool",None),
        ("Distância mínima smart (m)","broadcast_smart_minimum_distance","spin_int",(0,10000)),
        ("Intervalo mínimo smart (s)","broadcast_smart_minimum_interval_secs","spin_int",(0,3600)),
        ("Latitude fixa (graus)",   "fixed_lat",               "spin_float",(-90.0, 90.0)),
        ("Longitude fixa (graus)",  "fixed_lon",               "spin_float",(-180.0,180.0)),
        ("Altitude fixa (m)",       "fixed_alt",               "spin_int",  (-1000, 10000)),
        ("Precision de posição",    "position_flags",          "spin_int",(0,8191)),
        ("Receiver GPIO",           "rx_gpio",                 "spin_int",(0,39)),
        ("Transmitter GPIO",        "tx_gpio",                 "spin_int",(0,39)),
        ("Broadcast SBAS",          "gps_accept_2d",           "bool",   None),
        ("Max HDOP para aceitar",   "gps_max_dop",             "spin_int",(0,2000)),
    ],
    "localConfig.power": [
        ("Modo de economia",        "is_power_saving",         "bool",   None),
        ("Desligar na bateria (s)", "on_battery_shutdown_after_secs","spin_int",(0,86400)),
        ("Override ADC multiplicador","adc_multiplier_override","spin_float",(0.0,10.0)),
        ("Wait Bluetooth (s)",      "wait_bluetooth_secs",     "spin_int",(0,3600)),
        ("Modo SDS desligar (s)",   "sds_secs",                "spin_int",(0,86400)),
        ("Modo LS desligar (s)",    "ls_secs",                 "spin_int",(0,86400)),
        ("Tempo mínimo acordado (s)","min_wake_secs",          "spin_int",(0,3600)),
        ("INA endereço I2C bateria","device_battery_ina_address","spin_int",(0,127)),
        ("Powersave GPIO",          "powermon_enables",        "spin_int",(0,65535)),
    ],
    "localConfig.network": [
        ("WiFi habilitado",         "wifi_enabled",            "bool",   None),
        ("SSID WiFi",               "wifi_ssid",               "text",   None),
        ("Senha WiFi",              "wifi_psk",                "text",   None),
        ("Servidor NTP",            "ntp_server",              "text",   None),
        ("Ethernet habilitada",     "eth_enabled",             "bool",   None),
        ("Modo endereçamento",      "address_mode",            "combo",  ["DHCP","STATIC"]),
        ("IP estático",             "ipv4_config.ip",          "text",   None),
        ("Gateway",                 "ipv4_config.gateway",     "text",   None),
        ("Subnet",                  "ipv4_config.subnet",      "text",   None),
        ("DNS",                     "ipv4_config.dns",         "text",   None),
        ("RSync Server",            "rsync_server",            "text",   None),
    ],
    "localConfig.display": [
        ("Ecrã ligado (s)",         "screen_on_secs",          "spin_int",(0,3600)),
        ("Formato GPS",             "gps_format",              "combo",
         ["DEC","DMS","UTM","MGRS","OLC","OSGR"]),
        ("Múltiplo do auto dim.",   "auto_screen_carousel_secs","spin_int",(0,3600)),
        ("Unidades",                "units",                   "combo",  ["METRIC","IMPERIAL"]),
        ("OLED tipo",               "oled",                    "combo",
         ["OLED_AUTO","OLED_SSD1306","OLED_SH1106","OLED_SH1107"]),
        ("Modo do display",         "displaymode",             "combo",
         ["DEFAULT","TWOCOLOR","INVERTED","COLOR"]),
        ("Flip ecrã",               "flip_screen",             "bool",   None),
        ("Acord. por toque/mov.",   "wake_on_tap_or_motion",   "bool",   None),
        ("Cabeçalho negrito",       "heading_bold",            "bool",   None),
        ("Override largura fone",   "compass_north_top",       "bool",   None),
        ("Brilho do backlight",     "backlight_secs",          "spin_int",(0,3600)),
    ],
    "localConfig.lora": [
        ("Usar preset",             "use_preset",              "bool",   None),
        ("Modem preset",            "modem_preset",            "combo",
         ["LONG_FAST","LONG_SLOW","VERY_LONG_SLOW","MEDIUM_SLOW",
          "MEDIUM_FAST","SHORT_SLOW","SHORT_FAST","LONG_MODERATE"]),
        ("Região",                  "region",                  "combo",
         ["UNSET","US","EU_433","EU_868","CN","JP","ANZ","KR","TW",
          "RU","IN","NZ_865","TH","LORA_24","UA_433","UA_868",
          "MY_433","MY_919","SG_923","PH_433","PH_868","PH_915"]),
        ("Largura de banda",        "bandwidth",               "spin_int",(0,500)),
        ("Spreading factor",        "spread_factor",           "spin_int",(7,12)),
        ("Coding rate",             "coding_rate",             "spin_int",(5,8)),
        ("Offset frequência (MHz)", "frequency_offset",        "spin_float",(-100.0,100.0)),
        ("TX habilitado",           "tx_enabled",              "bool",   None),
        ("TX Power (dBm)",          "tx_power",                "spin_int",(0,30)),
        ("Hop limit",               "hop_limit",               "spin_int",(1,7)),
        ("Ignorar MQTT",            "ignore_mqtt",             "bool",   None),
        ("Override duty cycle",     "override_duty_cycle",     "bool",   None),
        ("Override frequency (MHz)","override_frequency",      "spin_float",(0.0,1000.0)),
        ("RX boosted gain (SX126x)","sx126x_rx_boosted_gain",  "bool",   None),
        ("PA fan GPIO",             "pa_fan_disabled",         "bool",   None),
        ("OK para MQTT",            "config_ok_to_mqtt",       "bool",   None),
    ],
    "localConfig.bluetooth": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Modo de emparelhamento",  "mode",                    "combo",
         ["RANDOM_PIN","FIXED_PIN","NO_PIN"]),
        ("PIN fixo",                "fixed_pin",               "spin_int",(0,999999)),
    ],
    "moduleConfig.mqtt": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Servidor",                "address",                 "text",   None),
        ("Utilizador",              "username",                "text",   None),
        ("Senha",                   "password",                "text",   None),
        ("Encriptação habilitada",  "encryption_enabled",      "bool",   None),
        ("JSON habilitado",         "json_enabled",            "bool",   None),
        ("TLS habilitado",          "tls_enabled",             "bool",   None),
        ("Root topic",              "root",                    "text",   None),
        ("Proxy para cliente",      "proxy_to_client_enabled", "bool",   None),
        ("Map reporting",           "map_reporting_enabled",   "bool",   None),
        ("Precisão do mapa",        "map_report_settings.position_precision","spin_int",(0,32)),
        ("Intervalo map report (s)","map_report_settings.publish_interval_secs","spin_int",(0,86400)),
    ],
    "moduleConfig.serial": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Echo",                    "echo",                    "bool",   None),
        ("Baud rate",               "baud",                    "combo",
         ["BAUD_DEFAULT","BAUD_110","BAUD_300","BAUD_600","BAUD_1200",
          "BAUD_2400","BAUD_4800","BAUD_9600","BAUD_19200","BAUD_38400",
          "BAUD_57600","BAUD_115200","BAUD_230400","BAUD_460800",
          "BAUD_576000","BAUD_921600"]),
        ("Timeout (ms)",            "timeout",                 "spin_int",(0,60000)),
        ("Modo",                    "mode",                    "combo",
         ["DEFAULT","SIMPLE","PROTO","TEXTMSG","NMEA","CALTOPO","WS85"]),
        ("RX GPIO",                 "rxd",                     "spin_int",(0,39)),
        ("TX GPIO",                 "txd",                     "spin_int",(0,39)),
        ("Somente RX",              "override_console_serial_port","bool",None),
    ],
    "moduleConfig.externalNotification": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Saída activa (ms)",       "output_ms",               "spin_int",(0,60000)),
        ("Saída GPIO",              "output",                  "spin_int",(0,39)),
        ("Saída vibra GPIO",        "output_vibra",            "spin_int",(0,39)),
        ("Saída buzzer GPIO",       "output_buzzer",           "spin_int",(0,39)),
        ("Alerta para mensagem",    "alert_message",           "bool",   None),
        ("Alerta msg pulso",        "alert_message_buzzer",    "bool",   None),
        ("Alerta msg vibra",        "alert_message_vibra",     "bool",   None),
        ("Alerta para bell",        "alert_bell",              "bool",   None),
        ("Alerta bell buzzer",      "alert_bell_buzzer",       "bool",   None),
        ("Alerta bell vibra",       "alert_bell_vibra",        "bool",   None),
        ("Usar PWM buzzer",         "use_pwm",                 "bool",   None),
        ("Nível activo GPIO",       "active",                  "bool",   None),
    ],
    "moduleConfig.storeForward": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Heartbeat",               "heartbeat",               "bool",   None),
        ("Num records",             "records",                 "spin_int",(0,300)),
        ("Histórico (s)",           "history_return_window",   "spin_int",(0,86400)),
        ("Max msgs histórico",      "history_return_max",      "spin_int",(0,300)),
        ("É servidor S&F",          "is_server",               "bool",   None),
    ],
    "moduleConfig.rangeTest": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Intervalo sender (s)",    "sender",                  "spin_int",(0,86400)),
        ("Guardar em CSV",          "save",                    "bool",   None),
    ],
    "moduleConfig.telemetry": [
        ("Intervalo dispositivo (s)","device_update_interval", "spin_int",(0,86400)),
        ("Intervalo ambiente (s)",  "environment_update_interval","spin_int",(0,86400)),
        ("Medição ambiente activa", "environment_measurement_enabled","bool",None),
        ("Ambiente no ecrã",        "environment_screen_enabled","bool",  None),
        ("Temperatura em Fahrenheit","environment_display_fahrenheit","bool",None),
        ("Intervalo air quality (s)","air_quality_interval",   "spin_int",(0,86400)),
        ("Air quality activo",      "air_quality_enabled",     "bool",   None),
        ("Intervalo potência (s)",  "power_update_interval",   "spin_int",(0,86400)),
        ("Medição potência activa", "power_measurement_enabled","bool",  None),
        ("Intervalo saúde (s)",     "health_update_interval",  "spin_int",(0,86400)),
        ("Saúde activo",            "health_telemetry_enabled","bool",   None),
    ],
    "moduleConfig.cannedMessage": [
        ("Rotação habilitada",      "rotary1_enabled",         "bool",   None),
        ("GPIO eventUp",            "inputbroker_event_cw",    "spin_int",(0,39)),
        ("GPIO eventDown",          "inputbroker_event_ccw",   "spin_int",(0,39)),
        ("GPIO eventPress",         "inputbroker_event_press", "spin_int",(0,39)),
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Permitir msg vazia",      "send_bell",               "bool",   None),
    ],
    "moduleConfig.audio": [
        ("Codec2 habilitado",       "codec2_enabled",          "bool",   None),
        ("GPIO PTT",                "ptt_pin",                 "spin_int",(0,39)),
        ("Modo codec2",             "bitrate",                 "combo",
         ["DEFAULT","CODEC2_3200","CODEC2_2400","CODEC2_1600","CODEC2_1400",
          "CODEC2_1300","CODEC2_1200","CODEC2_700","CODEC2_700B"]),
        ("I2S WS GPIO",             "i2s_ws",                  "spin_int",(0,39)),
        ("I2S SD GPIO",             "i2s_sd",                  "spin_int",(0,39)),
        ("I2S DIN GPIO",            "i2s_din",                 "spin_int",(0,39)),
        ("I2S SCK GPIO",            "i2s_sck",                 "spin_int",(0,39)),
    ],
    "moduleConfig.remotehardware": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Permitir input não seg.", "allow_undefined_pin_access","bool", None),
    ],
    "moduleConfig.neighborInfo": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Intervalo update (s)",    "update_interval",         "spin_int",(0,86400)),
        ("Transmitir sobre MQTT",   "transmit_over_lora",      "bool",   None),
    ],
    "moduleConfig.ambientLighting": [
        ("Habilitado LED",          "led_state",               "bool",   None),
        ("Corrente (mA)",           "current",                 "spin_int",(0,31)),
        ("Red",                     "red",                     "spin_int",(0,255)),
        ("Green",                   "green",                   "spin_int",(0,255)),
        ("Blue",                    "blue",                    "spin_int",(0,255)),
    ],
    "moduleConfig.detectionSensor": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Intervalo mínimo send (s)","minimum_broadcast_secs", "spin_int",(0,86400)),
        ("Intervalo estado (s)",    "state_broadcast_secs",    "spin_int",(0,86400)),
        ("Usar pull-up",            "use_pullup",              "bool",   None),
        ("Nome",                    "name",                    "text",   None),
        ("Monitor GPIO",            "monitor_pin",             "spin_int",(0,39)),
        ("Tipo de detecção",        "detection_triggered_high","bool",   None),
    ],
    "moduleConfig.paxcounter": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Intervalo Paxcount (s)",  "paxcounter_update_interval","spin_int",(0,86400)),
    ],
    "localConfig.security": [
        ("Chave pública (readonly)","public_key",              "readonly",None),
        ("Admin via canal legacy",  "admin_channel_enabled",   "bool",   None),
        ("Managed mode",            "is_managed",              "bool",   None),
        ("Modo serial (debug)",     "serial_enabled",          "bool",   None),
        ("Log debug via serial",    "debug_log_api_enabled",   "bool",   None),
    ],
}

SECTION_LABELS = {
    "localConfig.device":              "💻 Dispositivo",
    "localConfig.position":            "📍 Posição / GPS",
    "localConfig.power":               "🔋 Energia",
    "localConfig.network":             "🌐 Rede / WiFi",
    "localConfig.display":             "🖥 Display",
    "localConfig.lora":                "📡 LoRa",
    "localConfig.bluetooth":           "🔵 Bluetooth",
    "moduleConfig.mqtt":               "☁ MQTT",
    "moduleConfig.serial":             "🔌 Serial",
    "moduleConfig.externalNotification":"🔔 Notif. Externa",
    "moduleConfig.storeForward":       "📦 Store & Forward",
    "moduleConfig.rangeTest":          "📏 Range Test",
    "moduleConfig.telemetry":          "📊 Telemetria",
    "moduleConfig.cannedMessage":      "💬 Msgs Pre-definidas",
    "moduleConfig.audio":              "🎙 Audio / Codec2",
    "moduleConfig.remotehardware":     "🔧 Hardware Remoto",
    "moduleConfig.neighborInfo":       "🔗 Neighbor Info",
    "moduleConfig.ambientLighting":    "💡 Ilum. Ambiente",
    "moduleConfig.detectionSensor":    "🔍 Sensor Deteccao",
    "moduleConfig.paxcounter":         "🧮 Paxcounter",
    "localConfig.security":            "🔐 Segurança",
}

SECTION_WRITE_NAME = {
    "localConfig.device":              "device",
    "localConfig.position":            "position",
    "localConfig.power":               "power",
    "localConfig.network":             "network",
    "localConfig.display":             "display",
    "localConfig.lora":                "lora",
    "localConfig.bluetooth":           "bluetooth",
    "moduleConfig.mqtt":               "mqtt",
    "moduleConfig.serial":             "serial",
    "moduleConfig.externalNotification":"external_notification",
    "moduleConfig.storeForward":       "store_forward",
    "moduleConfig.rangeTest":          "range_test",
    "moduleConfig.telemetry":          "telemetry",
    "moduleConfig.cannedMessage":      "canned_message",
    "moduleConfig.audio":              "audio",
    "moduleConfig.remotehardware":     "remote_hardware",
    "moduleConfig.neighborInfo":       "neighbor_info",
    "moduleConfig.ambientLighting":    "ambient_lighting",
    "moduleConfig.detectionSensor":    "detection_sensor",
    "moduleConfig.paxcounter":         "paxcounter",
    "localConfig.security":            "security",
}


# ---------------------------------------------------------------------------
# ConfigTab
# ---------------------------------------------------------------------------
class ConfigTab(QWidget):
    config_save_requested = pyqtSignal(dict)
    reboot_required       = pyqtSignal()   # emitido após guardar com sucesso

    def __init__(self, parent=None):
        super().__init__(parent)
        self._iface        = None
        self._local_node   = None
        self._config_widgets: Dict[str, Dict[str, QWidget]] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        hdr = QHBoxLayout()
        title = QLabel("⚙ Config. do No Local")
        title.setStyleSheet(f"color:{ACCENT_ORANGE};font-size:15px;font-weight:bold;")
        hdr.addWidget(title)
        hdr.addStretch()

        self.status_label = QLabel("Não conectado")
        self.status_label.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        hdr.addWidget(self.status_label)

        btn_reload = QPushButton("🔄  Recarregar")
        btn_reload.setObjectName("btn_reload_config")
        btn_reload.clicked.connect(self.reload_config)
        hdr.addWidget(btn_reload)

        self.btn_save = QPushButton("💾  Guardar Alterações")
        self.btn_save.setObjectName("btn_save_config")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_config)
        hdr.addWidget(self.btn_save)

        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(sep)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        left = QWidget()
        left.setMaximumWidth(200)
        left.setMinimumWidth(150)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)
        lv.setSpacing(4)

        sec_lbl = QLabel("Secções")
        sec_lbl.setStyleSheet(
            f"color:{ACCENT_BLUE};font-weight:bold;font-size:11px;"
            f"padding:4px 8px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;"
        )
        lv.addWidget(sec_lbl)

        self.section_list = QListWidget()
        self.section_list.currentRowChanged.connect(self._on_section_changed)
        lv.addWidget(self.section_list)
        splitter.addWidget(left)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{PANEL_BG};")
        splitter.addWidget(self.stack)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self._show_placeholder("Conecte-se a um nó para ver as configurações.")

    def set_interface(self, iface):
        self._iface = iface
        self.reload_config()
        if hasattr(self, '_channels_tab_widget') and self._channels_tab_widget:
            self._channels_tab_widget.set_interface(iface)

    def clear_interface(self):
        self._iface      = None
        self._local_node = None
        self.btn_save.setEnabled(False)
        self.status_label.setText("Não conectado")
        if hasattr(self, '_channels_tab_widget') and self._channels_tab_widget:
            self._channels_tab_widget.clear_interface()
        self.section_list.clear()
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
        self._show_placeholder("Conecte-se a um nó para ver as configurações.")

    def reload_config(self):
        if not self._iface:
            self._show_placeholder("Conecte-se a um nó para ver as configurações.")
            return
        self.status_label.setText("A carregar configuração…")
        QTimer.singleShot(100, self._do_reload)

    def _do_reload(self):
        try:
            self._local_node = self._iface.getNode("^local")
            if not self._local_node:
                self._show_placeholder("Não foi possível obter o nó local.")
                self.status_label.setText("Erro: nó local indisponível")
                return
            self._build_config_ui()
            self.btn_save.setEnabled(True)
            self.status_label.setText("✅ Configuração carregada")
        except Exception as e:
            logger.error(f"Erro ao carregar configuração: {e}", exc_info=True)
            self._show_placeholder(f"Erro ao carregar: {e}")
            self.status_label.setText("❌ Erro ao carregar")

    def _build_config_ui(self):
        self.section_list.clear()
        self._config_widgets.clear()
        while self.stack.count():
            self.stack.removeWidget(self.stack.widget(0))

        self.section_list.addItem("📻 Canais")
        self._channels_tab_widget = ChannelsTab()
        if self._iface:
            self._channels_tab_widget.set_interface(self._iface)
        self._channels_tab_widget.reboot_required.connect(self.reboot_required)
        self.stack.addWidget(self._channels_tab_widget)

        self.section_list.addItem("👤 Usuário")
        self.stack.addWidget(self._build_device_info_page())

        for sec_key, field_defs in MESHTASTIC_CONFIG_DEFS.items():
            label = SECTION_LABELS.get(sec_key, sec_key)
            self.section_list.addItem(label)
            fields_with_values = self._read_section_values(sec_key, field_defs)
            page = self._build_section_page(sec_key, fields_with_values)
            self.stack.addWidget(page)

        if self.section_list.count() > 0:
            self.section_list.setCurrentRow(0)

    def _read_section_values(self, sec_key: str, field_defs: list) -> list:
        import re
        parts = sec_key.split('.', 1)
        if len(parts) != 2:
            return [(lbl, ft, fn, None, ex) for lbl, fn, ft, ex in field_defs]
        config_attr, sub_attr = parts
        sub_obj = None
        try:
            cfg_root = getattr(self._local_node, config_attr, None)
            if cfg_root is not None:
                sub_obj = getattr(cfg_root, sub_attr, None)
                if sub_obj is None:
                    snake   = re.sub(r'(?<!^)(?=[A-Z])', '_', sub_attr).lower()
                    sub_obj = getattr(cfg_root, snake, None)
        except Exception as e:
            logger.warning(f"Erro ao aceder {sec_key}: {e}")
        result = []
        for label, field_name, field_type, extra in field_defs:
            current_val = None
            if sub_obj is not None:
                try:
                    obj = sub_obj
                    for part in field_name.split('.'):
                        if obj is None:
                            break
                        obj = getattr(obj, part, None)
                    current_val = obj
                except Exception as e:
                    logger.debug(f"Não leu {sec_key}.{field_name}: {e}")
            result.append((label, field_type, field_name, current_val, extra))
        return result

    def _build_device_info_page(self) -> QWidget:
        sec_key = "__device_info__"
        self._config_widgets[sec_key] = {}
        page    = QWidget()
        page.setStyleSheet(f"background:{PANEL_BG};")
        scroll  = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{border:none;background:{PANEL_BG};}}")
        content = QWidget()
        content.setStyleSheet(f"background:{PANEL_BG};")
        form    = QFormLayout(content)
        form.setSpacing(12)
        form.setContentsMargins(16, 16, 16, 16)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        fields_ro, fields_rw = [], []
        try:
            my_info = self._iface.getMyNodeInfo() if self._iface else None
            if my_info:
                user      = my_info.get('user', {})
                fields_ro = [
                    ("ID do Nó",  "id",       user.get('id', '—')),
                    ("Modelo HW", "hw_model", user.get('hwModel', '—')),
                    ("Firmware",  "firmware", str(my_info.get('firmwareVersion', '—'))),
                ]
                fields_rw = [
                    ("Nome Longo",       "long_name",   user.get('longName', '')),
                    ("Nome Curto",       "short_name",  user.get('shortName', '')),
                    ("Licenciado (Ham)", "is_licensed", user.get('isLicensed', False)),
                ]
        except Exception as e:
            logger.warning(f"Erro ao ler info dispositivo: {e}")
        for label, key, val in fields_ro:
            lbl = QLabel(str(val) if val is not None else "—")
            lbl.setStyleSheet(
                f"color:{ACCENT_BLUE};background:{DARK_BG};"
                f"border:1px solid {BORDER_COLOR};border-radius:4px;padding:4px 8px;"
            )
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(self._make_label(label), lbl)
        if fields_rw:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"color:{BORDER_COLOR};")
            form.addRow(sep)
            note = QLabel("✏  Campos editáveis — guardar usa setOwner()")
            note.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;font-style:italic;")
            form.addRow(note)
        for label, key, val in fields_rw:
            if isinstance(val, bool):
                w = QCheckBox()
                w.setChecked(bool(val))
            else:
                w = QLineEdit(str(val) if val is not None else "")
            form.addRow(self._make_label(label), w)
            self._config_widgets[sec_key][key] = w
        scroll.setWidget(content)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        return page

    def _build_section_page(self, sec_key: str, fields: list) -> QWidget:
        self._config_widgets[sec_key] = {}
        page    = QWidget()
        page.setStyleSheet(f"background:{PANEL_BG};")
        scroll  = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{border:none;background:{PANEL_BG};}}")
        content = QWidget()
        content.setStyleSheet(f"background:{PANEL_BG};")
        form    = QFormLayout(content)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        if not fields:
            form.addRow(QLabel("Nenhum campo disponível para esta secção."))
        else:
            for label, field_type, field_name, current_val, extra in fields:
                w = self._create_field_widget(field_type, current_val, extra)
                if w:
                    form.addRow(self._make_label(label), w)
                    self._config_widgets[sec_key][field_name] = w
        scroll.setWidget(content)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        return page

    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text + ":")
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        return lbl

    # FIX-7: conversão explícita de enums e validação antes de setattr
    @staticmethod
    def _coerce_value(obj, field_name: str, value):
        """
        Converte `value` para o tipo correcto do campo protobuf `field_name`
        em `obj`, usando a API de reflexão do protobuf quando disponível.
        Retorna (coerced_value, error_str_or_None).
        """
        import google.protobuf.descriptor as descriptor_module

        if value is None:
            return None, None

        # Tenta obter o descriptor do campo para verificar o tipo
        try:
            desc = obj.DESCRIPTOR.fields_by_name.get(field_name)
        except Exception:
            desc = None

        if desc is not None:
            ftype = desc.type
            # ENUM: converte string para int usando o descriptor
            if ftype == descriptor_module.FieldDescriptor.TYPE_ENUM:
                enum_type = desc.enum_type
                if isinstance(value, str):
                    # 1. Tentativa directa
                    ev = enum_type.values_by_name.get(value)
                    if ev is not None:
                        return ev.number, None
                    # 2. Tenta com prefixos comuns do protobuf Meshtastic
                    #    ex: 'DEC' → 'GPS_FORMAT_DEC', 'DEFAULT' → 'CODEC2_DEFAULT'
                    uval = value.upper()
                    for v in enum_type.values:
                        vname = v.name.upper()
                        # Correspondência por sufixo: o nome do enum termina com _VALUE
                        if vname == uval or vname.endswith('_' + uval):
                            return v.number, None
                    # 3. Tenta por número
                    try:
                        int_val = int(value)
                        if any(v.number == int_val for v in enum_type.values):
                            return int_val, None
                    except (ValueError, TypeError):
                        pass
                    # 4. Usa o valor 0 (default do protobuf) e regista aviso leve
                    #    em vez de bloquear o save completo
                    default_v = next((v for v in enum_type.values if v.number == 0), None)
                    if default_v is not None:
                        logger.debug(f"Enum '{value}' não reconhecido para {field_name}, usando default {default_v.name}")
                        return default_v.number, None
                    return None, f"Valor de enum inválido '{value}' para {field_name}"
                try:
                    return int(value), None
                except (ValueError, TypeError):
                    return None, f"Não foi possível converter '{value}' para enum {field_name}"

            # BOOL
            if ftype == descriptor_module.FieldDescriptor.TYPE_BOOL:
                if isinstance(value, bool):
                    return value, None
                if isinstance(value, str):
                    return value.lower() in ('true','1','yes'), None
                return bool(value), None

            # INT / UINT / SINT
            int_types = {
                descriptor_module.FieldDescriptor.TYPE_INT32,
                descriptor_module.FieldDescriptor.TYPE_INT64,
                descriptor_module.FieldDescriptor.TYPE_UINT32,
                descriptor_module.FieldDescriptor.TYPE_UINT64,
                descriptor_module.FieldDescriptor.TYPE_SINT32,
                descriptor_module.FieldDescriptor.TYPE_SINT64,
                descriptor_module.FieldDescriptor.TYPE_FIXED32,
                descriptor_module.FieldDescriptor.TYPE_FIXED64,
                descriptor_module.FieldDescriptor.TYPE_SFIXED32,
                descriptor_module.FieldDescriptor.TYPE_SFIXED64,
            }
            if ftype in int_types:
                try:
                    return int(value), None
                except (ValueError, TypeError):
                    return None, f"Valor inteiro inválido '{value}' para {field_name}"

            # FLOAT / DOUBLE
            if ftype in (descriptor_module.FieldDescriptor.TYPE_FLOAT,
                         descriptor_module.FieldDescriptor.TYPE_DOUBLE):
                try:
                    return float(value), None
                except (ValueError, TypeError):
                    return None, f"Valor float inválido '{value}' para {field_name}"

            # STRING / BYTES
            if ftype == descriptor_module.FieldDescriptor.TYPE_STRING:
                return str(value), None
            if ftype == descriptor_module.FieldDescriptor.TYPE_BYTES:
                if isinstance(value, (bytes, bytearray)):
                    return bytes(value), None
                try:
                    return bytes.fromhex(str(value)), None
                except ValueError:
                    return str(value).encode(), None

        # Sem descriptor — usa tipo Python directo
        return value, None

    def _save_config(self):
        import re
        if not self._iface or not self._local_node:
            QMessageBox.warning(self, "Sem Conexão", "Não está conectado a nenhum nó.")
            return
        reply = QMessageBox.question(
            self, "Guardar Configuração",
            "Deseja guardar todas as alterações de configuração no nó?\n\n"
            "⚠  O nó irá reiniciar após guardar para aplicar as configurações.\n"
            "    A ligação TCP será temporariamente perdida e restabelecida.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.status_label.setText("A guardar…")
        errors         = []
        saved_sections = set()

        try:
            # Abre transacção — o firmware só reinicia uma vez no commitSettingsTransaction,
            # depois de todos os valores terem sido recebidos e gravados
            try:
                self._local_node.beginSettingsTransaction()
            except Exception as e:
                logger.debug(f"beginSettingsTransaction não suportado ou falhou: {e}")

            # ── Recolhe dados do owner (aplica no fim, após writeConfigs) ──
            owner_long  = None
            owner_short = None
            owner_licensed = False
            dev_w = self._config_widgets.get("__device_info__", {})
            if dev_w:
                for key, w in dev_w.items():
                    val = self._get_widget_value(w)
                    if key == "long_name":     owner_long     = val
                    elif key == "short_name":  owner_short    = val
                    elif key == "is_licensed": owner_licensed = bool(val)

            # ── Secções de config ─────────────────────────────────────
            for sec_key, fields_widgets in self._config_widgets.items():
                if sec_key == "__device_info__" or not fields_widgets:
                    continue
                parts = sec_key.split('.', 1)
                if len(parts) != 2:
                    continue
                config_attr, sub_attr = parts
                cfg_root = getattr(self._local_node, config_attr, None)
                if cfg_root is None:
                    continue
                # Tenta pelo nome original, depois pelo nome snake do SECTION_WRITE_NAME,
                # depois pela conversão camelCase→snake genérica
                sub_obj = getattr(cfg_root, sub_attr, None)
                if sub_obj is None:
                    write_name = SECTION_WRITE_NAME.get(sec_key)
                    if write_name:
                        sub_obj = getattr(cfg_root, write_name, None)
                if sub_obj is None:
                    snake   = re.sub(r'(?<!^)(?=[A-Z])', '_', sub_attr).lower()
                    sub_obj = getattr(cfg_root, snake, None)
                if sub_obj is None:
                    errors.append(f"Secção {sec_key} não encontrada")
                    continue

                section_saved = False
                for field_name, widget in fields_widgets.items():
                    try:
                        raw_value = self._get_widget_value(widget)
                        if raw_value is None:
                            continue

                        obj          = sub_obj
                        field_parts  = field_name.split('.')
                        for part in field_parts[:-1]:
                            obj = getattr(obj, part, None)
                            if obj is None:
                                break
                        if obj is None:
                            continue

                        last = field_parts[-1]
                        if not hasattr(obj, last):
                            continue

                        # FIX-7: conversão explícita via descriptor
                        coerced, err = self._coerce_value(obj, last, raw_value)
                        if err:
                            errors.append(f"{sec_key}.{field_name}: {err}")
                            continue
                        if coerced is None:
                            continue

                        setattr(obj, last, coerced)
                        section_saved = True

                    except Exception as e:
                        errors.append(f"{sec_key}.{field_name}: {e}")

                if section_saved:
                    write_name = SECTION_WRITE_NAME.get(sec_key, sub_attr)
                    try:
                        self._local_node.writeConfig(write_name)
                        saved_sections.add(sec_key)
                    except Exception as e:
                        errors.append(f"writeConfig({write_name}): {e}")

            # ── Commit da transacção — o nó reinicia uma única vez ────
            try:
                self._local_node.commitSettingsTransaction()
            except Exception as e:
                logger.debug(f"commitSettingsTransaction não suportado ou falhou: {e}")

            # ── setOwner após commit — garante que o nome é gravado ───
            # O setOwner envia AdminMessage directamente ao firmware;
            # deve ser enviado depois do commit para não ser afectado pelo reinício
            if owner_long is not None or owner_short is not None:
                try:
                    self._local_node.setOwner(
                        long_name=owner_long or "",
                        short_name=owner_short or "",
                        is_licensed=owner_licensed
                    )
                    saved_sections.add("owner")
                except Exception as e:
                    errors.append(f"setOwner: {e}")

            if saved_sections:
                self.status_label.setText(f"✅ {len(saved_sections)} secção(ões) guardadas")
                msg = f"Configuração guardada!\n{len(saved_sections)} secção(ões) enviadas ao nó."
                if errors:
                    msg += f"\n\n⚠ {len(errors)} aviso(s):\n" + "\n".join(errors[:8])
                QMessageBox.information(self, "Configuração Guardada", msg)
                self.reboot_required.emit()
            else:
                self.status_label.setText("⚠ Nada guardado")
                msg = "Não foram detectadas alterações para guardar."
                if errors:
                    msg += f"\n\nErros:\n" + "\n".join(errors[:8])
                QMessageBox.information(self, "Sem Alterações", msg)

        except Exception as e:
            logger.error(f"Erro ao guardar configuração: {e}", exc_info=True)
            self.status_label.setText("❌ Erro ao guardar")
            QMessageBox.critical(self, "Erro", f"Erro ao guardar configuração:\n{e}")

    def _on_section_changed(self, row: int):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _create_field_widget(self, field_type: str, current_val, extra) -> Optional[QWidget]:
        if field_type == "readonly":
            lbl = QLabel(str(current_val) if current_val is not None else "—")
            lbl.setStyleSheet(
                f"color:{ACCENT_BLUE};background:{DARK_BG};"
                f"border:1px solid {BORDER_COLOR};border-radius:4px;padding:4px 8px;font-size:12px;"
            )
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            return lbl
        elif field_type == "text":
            w = QLineEdit()
            w.setText(str(current_val) if current_val is not None else "")
            return w
        elif field_type == "bool":
            w = QCheckBox()
            if current_val is not None:
                w.setChecked(bool(current_val))
            return w
        elif field_type == "spin_int":
            w  = QSpinBox()
            lo, hi = (extra[0], extra[1]) if extra and isinstance(extra, tuple) else (0, 2147483647)
            lo = max(lo, -2147483648)
            hi = min(hi,  2147483647)
            w.setRange(lo, hi)
            if current_val is not None:
                try:
                    v = int(current_val)
                    w.setValue(max(lo, min(hi, v)))
                except (TypeError, ValueError, OverflowError):
                    pass
            return w
        elif field_type == "spin_float":
            w = QDoubleSpinBox()
            if extra and isinstance(extra, tuple):
                w.setRange(extra[0], extra[1])
            else:
                w.setRange(-1e9, 1e9)
            w.setDecimals(4)
            if current_val is not None:
                try:
                    w.setValue(float(current_val))
                except (TypeError, ValueError):
                    pass
            return w
        elif field_type == "combo":
            w = QComboBox()
            if extra and isinstance(extra, list):
                w.addItems(extra)
            if current_val is not None:
                val_str = str(current_val)
                idx     = w.findText(val_str)
                if idx >= 0:
                    w.setCurrentIndex(idx)
                else:
                    try:
                        int_val = int(current_val)
                        if 0 <= int_val < w.count():
                            w.setCurrentIndex(int_val)
                    except (TypeError, ValueError):
                        pass
            return w
        return None

    def _get_widget_value(self, widget: QWidget):
        if isinstance(widget, QLabel):        return None
        elif isinstance(widget, QLineEdit):   return widget.text()
        elif isinstance(widget, QCheckBox):   return widget.isChecked()
        elif isinstance(widget, QSpinBox):    return widget.value()
        elif isinstance(widget, QDoubleSpinBox): return widget.value()
        elif isinstance(widget, QComboBox):   return widget.currentText()
        return None

    def _show_placeholder(self, text: str):
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
        self.section_list.clear()
        placeholder = QWidget()
        layout      = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:14px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        self.stack.addWidget(placeholder)


# ---------------------------------------------------------------------------
# MessagesTab
# ---------------------------------------------------------------------------
class ConversationContext:
    CHANNEL = "channel"
    DM      = "dm"


class MessagesTab(QWidget):
    send_channel_message = pyqtSignal(int, str)
    send_direct_message  = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.channel_map:   Dict[int, str]   = {}
        self.unread_count:  Dict[str, int]   = defaultdict(int)
        self.messages:      Dict[str, list]  = defaultdict(list)
        self._pending_ack:  Dict[int, dict]  = {}
        self.node_names:    Dict[str, str]   = {}
        self.node_short:    Dict[str, str]   = {}
        self.node_colors:   Dict[str, str]   = {}
        self.node_public_keys: Dict[str, str] = {}
        self._dm_last_received: Dict[str, datetime] = {}

        self._ctx_type:    str           = ConversationContext.CHANNEL
        self._ctx_channel: Optional[int] = None
        self._ctx_dm_id:   Optional[str] = None
        self._my_node_id:  Optional[str] = None
        self._node_choices_fn: Callable  = lambda: []
        self._filter_text: str           = ""

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        left = QWidget()
        left.setMaximumWidth(280)
        left.setMinimumWidth(180)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)
        lv.setSpacing(4)

        chan_hdr = QLabel("📻  Canais")
        chan_hdr.setStyleSheet(
            f"color:{ACCENT_BLUE};font-weight:bold;font-size:11px;"
            f"padding:3px 6px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;"
        )
        lv.addWidget(chan_hdr)

        self.channel_list = QListWidget()
        self.channel_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.channel_list.itemClicked.connect(self._on_channel_clicked)
        self.channel_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.channel_list.setFixedHeight(34)
        lv.addWidget(self.channel_list)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};margin:2px 0;")
        lv.addWidget(sep)

        dm_hdr = QLabel("📩  Mensagens Directas")
        dm_hdr.setStyleSheet(
            f"color:{ACCENT_PURPLE};font-weight:bold;font-size:11px;"
            f"padding:3px 6px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;"
        )
        lv.addWidget(dm_hdr)

        self.dm_list = QTableWidget()
        self.dm_list.setColumnCount(2)
        self.dm_list.setHorizontalHeaderLabels(["Short", "Nome Longo"])
        self.dm_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dm_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dm_list.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
        self.dm_list.verticalHeader().setVisible(False)
        self.dm_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dm_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.dm_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dm_list.setShowGrid(False)
        self.dm_list.setAlternatingRowColors(True)
        self.dm_list.cellClicked.connect(self._on_dm_cell_clicked)
        lv.addWidget(self.dm_list, stretch=1)

        splitter.addWidget(left)

        right = QWidget()
        rv    = QVBoxLayout(right)
        rv.setContentsMargins(4, 0, 0, 0)
        rv.setSpacing(6)

        self.conv_header = QLabel("Seleccione um canal ou nó")
        self.conv_header.setStyleSheet(
            f"color:{ACCENT_GREEN};font-weight:bold;font-size:13px;"
            f"padding:6px 10px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;"
        )
        rv.addWidget(self.conv_header)

        self.messages_view = QWebEngineView()
        self.messages_view.setContextMenuPolicy(Qt.NoContextMenu)
        rv.addWidget(self.messages_view, stretch=1)

        send_frame = QFrame()
        send_frame.setStyleSheet(
            f"background:{PANEL_BG};border:1px solid {BORDER_COLOR};border-radius:6px;"
        )
        sl = QHBoxLayout(send_frame)
        sl.setContentsMargins(8, 6, 8, 6)
        sl.setSpacing(8)

        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("Seleccione um canal ou nó para enviar mensagem…")
        self.send_input.setEnabled(False)
        self.send_input.returnPressed.connect(self._on_send)
        sl.addWidget(self.send_input, stretch=1)

        self.btn_send = QPushButton("📤  Enviar")
        self.btn_send.setObjectName("btn_send_channel")
        self.btn_send.setFixedWidth(130)
        self.btn_send.setEnabled(False)
        self.btn_send.clicked.connect(self._on_send)
        sl.addWidget(self.btn_send)

        rv.addWidget(send_frame)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def _color(self, node_id: str) -> str:
        if node_id not in self.node_colors:
            hue = int(hashlib.md5(node_id.encode()).hexdigest()[:8], 16) % 360
            self.node_colors[node_id] = f"hsl({hue}, 70%, 65%)"
        return self.node_colors[node_id]

    def set_node_choices_provider(self, fn: Callable):
        self._node_choices_fn = fn

    def set_my_node_id(self, node_id: str):
        self._my_node_id    = node_id
        self._my_node_num: Optional[int] = None
        if node_id and node_id.startswith('!'):
            try:
                self._my_node_num = int(node_id[1:], 16) & 0xFFFFFFFF
            except ValueError:
                pass
        logger.info(f"My node: id={node_id} num={self._my_node_num}")

    def set_filter_text(self, text: str):
        self._filter_text = text.lower()
        self._refresh_dm_list()

    def update_node_name(self, node_id: str, long_name: str, short_name: str, public_key: str = ''):
        if long_name:
            self.node_names[node_id] = long_name
        elif short_name:
            self.node_names[node_id] = short_name
        if short_name:
            self.node_short[node_id] = short_name
        if public_key:
            self.node_public_keys[node_id] = public_key
        self._refresh_dm_list()

    def _refresh_dm_list(self):
        choices    = self._node_choices_fn()
        current_id = self._ctx_dm_id
        ft         = self._filter_text

        if ft:
            choices = [
                (nid, long_, short) for nid, long_, short in choices
                if ft in nid.lower() or ft in long_.lower() or ft in short.lower()
            ]

        def sort_key(item):
            nid = item[0]
            ts  = self._dm_last_received.get(nid)
            if ts is not None:
                return (0, -ts.timestamp())
            return (1, item[1].lower())

        choices = sorted(choices, key=sort_key)

        self.dm_list.setRowCount(0)
        for row_idx, (nid, long_, short) in enumerate(choices):
            unread_key = f"dm:{nid}"
            unread     = self.unread_count.get(unread_key, 0)
            has_key    = bool(self.node_public_keys.get(nid, ''))

            short_disp = short or nid
            if unread > 0:
                short_disp = f"🔴 {short_disp}"
            # FIX-3: ícone de encriptação no DM list
            enc_prefix = "🔒 " if has_key else ""
            col0 = QTableWidgetItem(enc_prefix + short_disp)
            col0.setData(Qt.UserRole, nid)
            if unread > 0:
                col0.setForeground(QColor(ACCENT_PURPLE))
            elif has_key:
                col0.setForeground(QColor(ACCENT_GREEN))
                col0.setToolTip("Chave pública conhecida — DM PKI disponível (E2E)")
            else:
                col0.setForeground(QColor(TEXT_MUTED))
                col0.setToolTip("Chave pública desconhecida — DM via PSK de canal")

            long_disp = long_ or short or nid
            col1      = QTableWidgetItem(long_disp)
            col1.setData(Qt.UserRole, nid)
            col1.setForeground(QColor(TEXT_MUTED))

            self.dm_list.insertRow(row_idx)
            self.dm_list.setItem(row_idx, 0, col0)
            self.dm_list.setItem(row_idx, 1, col1)
            self.dm_list.setRowHeight(row_idx, 26)

            if nid == current_id:
                self.dm_list.selectRow(row_idx)

    def update_channels(self, channels: List[tuple]):
        self.channel_list.clear()
        self.channel_map.clear()
        for idx, name, _ in channels:
            self.channel_map[idx] = name or f"Canal {idx}"
            item = QListWidgetItem(self._fmt_channel(idx))
            item.setData(Qt.UserRole, idx)
            self.channel_list.addItem(item)

        n    = self.channel_list.count()
        row_h = 34
        self.channel_list.setFixedHeight(max(34, n * row_h + 2))

        if n > 0 and self._ctx_channel is None:
            first = self.channel_list.item(0)
            self.channel_list.setCurrentItem(first)
            self._activate_channel(first.data(Qt.UserRole))

    def _fmt_channel(self, idx: int) -> str:
        name   = self.channel_map.get(idx, f"Canal {idx}")
        unread = self.unread_count.get(f"ch:{idx}", 0)
        prefix = f"🔴({unread}) " if unread > 0 else "  "
        return f"{prefix}#{idx}  {name}"

    def _refresh_channel_list(self):
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            item.setText(self._fmt_channel(item.data(Qt.UserRole)))

    def _on_channel_clicked(self, item: QListWidgetItem):
        self.dm_list.clearSelection()
        self._activate_channel(item.data(Qt.UserRole))

    def _activate_channel(self, idx: int):
        self._ctx_type    = ConversationContext.CHANNEL
        self._ctx_channel = idx
        self._ctx_dm_id   = None

        key = f"ch:{idx}"
        self.unread_count[key] = 0
        self._refresh_channel_list()

        name = self.channel_map.get(idx, f"Canal {idx}")
        self.conv_header.setText(f"📻  # {idx}  ·  {name}")
        self.conv_header.setStyleSheet(
            f"color:{ACCENT_GREEN};font-weight:bold;font-size:13px;"
            f"padding:6px 10px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;"
        )
        self.send_input.setPlaceholderText(f"Mensagem para #{idx} · {name}…")
        self.send_input.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_send.setObjectName("btn_send_channel")
        self.btn_send.setStyleSheet(
            f"background-color:#1a4a2e;color:{ACCENT_GREEN};border-color:{ACCENT_GREEN};"
        )
        self.btn_send.setText("📤  Enviar")
        self._display_conversation(key)

    def _on_dm_cell_clicked(self, row: int, _col: int):
        item = self.dm_list.item(row, 0)
        if item:
            self.channel_list.clearSelection()
            self._activate_dm(item.data(Qt.UserRole))

    def activate_dm_for_node(self, node_id: str):
        self.channel_list.clearSelection()
        self._activate_dm(node_id)
        self._refresh_dm_list()

    def _activate_dm(self, node_id: str):
        self._ctx_type    = ConversationContext.DM
        self._ctx_channel = None
        self._ctx_dm_id   = node_id

        key = f"dm:{node_id}"
        self.unread_count[key] = 0
        self._refresh_dm_list()

        long_  = self.node_names.get(node_id, node_id)
        short  = self.node_short.get(node_id, "")
        has_key = bool(self.node_public_keys.get(node_id, ''))
        # FIX-3: indicador de modo na header da conversa DM
        enc_tag = " 🔒 PKI" if has_key else " 🔓 PSK"
        label  = f"{long_}  ({short})" if long_ and short and long_ != short else (long_ or short or node_id)

        self.conv_header.setText(f"📩  DM  →  {html.escape(label)}{enc_tag}")
        self.conv_header.setStyleSheet(
            f"color:{ACCENT_PURPLE};font-weight:bold;font-size:13px;"
            f"padding:6px 10px;background:{DM_BG};"
            f"border:1px solid {ACCENT_PURPLE};border-radius:6px;"
        )
        self.send_input.setPlaceholderText(f"Mensagem directa para {label}…")
        self.send_input.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_send.setObjectName("btn_send_dm")
        self.btn_send.setStyleSheet(
            f"background-color:#2a1a4a;color:{ACCENT_PURPLE};border-color:{ACCENT_PURPLE};"
        )
        self.btn_send.setText("📩  Enviar DM")
        self._display_conversation(key)
        self.send_input.setFocus()

    def add_message(self, channel_index: int, from_id: str, text: str, packet: dict):
        rx_time = packet.get("rxTime")
        ts      = datetime.fromtimestamp(rx_time) if rx_time else datetime.now()
        via_mqtt      = packet.get("viaMqtt", False)
        pki_encrypted = packet.get("pkiEncrypted", False)

        to_raw = packet.get("to")
        try:
            to_num = int(to_raw) & 0xFFFFFFFF if to_raw is not None else 0xFFFFFFFF
        except (TypeError, ValueError):
            to_num = 0xFFFFFFFF

        my_num = getattr(self, '_my_node_num', None)
        if my_num is None and self._my_node_id and self._my_node_id.startswith('!'):
            try:
                my_num = int(self._my_node_id[1:], 16) & 0xFFFFFFFF
            except ValueError:
                pass

        to_id_str = packet.get("toId", "")

        is_dm = (
            pki_encrypted
            or (to_id_str and to_id_str == self._my_node_id)
            or (my_num is not None and to_num == my_num)
            or (not _is_broadcast(to_num) and to_num != 0)
        )

        if is_dm:
            key = f"dm:{from_id}"
            self._dm_last_received[from_id] = ts
        else:
            key = f"ch:{channel_index}"

        if from_id == self._my_node_id:
            return

        if pki_encrypted:
            label = "🔒 PKI"
        elif via_mqtt:
            label = "☁ MQTT"
        else:
            label = "📡 RF"

        # Adiciona contagem de hops ao label se disponível
        hops = packet.get('hopsAway')
        if hops is not None:
            try:
                h = int(hops)
                label += f"  ·  {h} hop{'s' if h != 1 else ''}"
            except (TypeError, ValueError):
                pass

        entry = self._build_entry(ts, from_id, text,
                                  label=label, is_dm=is_dm, outgoing=False)
        self._store_and_display(key, entry)

    def add_outgoing_channel_message(self, channel_index: int, text: str, packet_id: int = 0):
        key   = f"ch:{channel_index}"
        entry = self._build_entry(datetime.now(), self._my_node_id or "Eu", text,
                                  label="📤 Enviado", is_dm=False, outgoing=True,
                                  packet_id=packet_id)
        self._store_and_display(key, entry)

    def add_outgoing_dm(self, dest_id: str, text: str, pki: bool = False, packet_id: int = 0):
        key   = f"dm:{dest_id}"
        label = "📤 DM PKI" if pki else "📤 DM"
        entry = self._build_entry(datetime.now(), self._my_node_id or "Eu", text,
                                  label=label, is_dm=True, outgoing=True, packet_id=packet_id)
        self._store_and_display(key, entry)

    def update_message_status(self, packet_id: int, status: str, error_reason: str):
        entry = self._pending_ack.get(packet_id)
        if not entry:
            return
        entry['status'] = status
        if status == 'nak':
            entry['status_detail'] = error_reason
        if status in ('ack', 'nak'):
            self._pending_ack.pop(packet_id, None)
        for key, msgs in self.messages.items():
            if entry in msgs:
                if key == self._active_key():
                    self._display_conversation(key)
                break

    def _on_send(self):
        text = self.send_input.text().strip()
        if not text:
            return
        if self._ctx_type == ConversationContext.CHANNEL and self._ctx_channel is not None:
            self.send_channel_message.emit(self._ctx_channel, text)
        elif self._ctx_type == ConversationContext.DM and self._ctx_dm_id:
            self.send_direct_message.emit(self._ctx_dm_id, text)
        self.send_input.clear()

    def _build_entry(self, timestamp: datetime, from_id: str, text: str,
                     label: str, is_dm: bool, outgoing: bool, packet_id: int = 0) -> dict:
        friendly = "Eu" if outgoing else self.node_names.get(from_id, from_id)
        color    = ACCENT_GREEN if outgoing else self._color(from_id)
        status   = 'sending' if outgoing else ''
        return dict(time=timestamp, from_=friendly, from_id=from_id,
                    text=text, label=label, dm=is_dm, outgoing=outgoing,
                    color=color, packet_id=packet_id, status=status, status_detail='')

    def _store_and_display(self, key: str, entry: dict):
        self.messages[key].append(entry)
        self.messages[key].sort(key=lambda x: x["time"])
        if entry.get('outgoing') and entry.get('packet_id'):
            self._pending_ack[entry['packet_id']] = entry

        if key == self._active_key():
            self._append_to_view(entry)
        else:
            self.unread_count[key] = self.unread_count.get(key, 0) + 1
            if key.startswith("ch:"):
                self._refresh_channel_list()
            else:
                self._refresh_dm_list()

    def _active_key(self) -> Optional[str]:
        if self._ctx_type == ConversationContext.CHANNEL and self._ctx_channel is not None:
            return f"ch:{self._ctx_channel}"
        if self._ctx_type == ConversationContext.DM and self._ctx_dm_id:
            return f"dm:{self._ctx_dm_id}"
        return None

    def _display_conversation(self, key: str):
        msgs = self.messages.get(key, [])
        if not msgs:
            self.messages_view.setHtml(self._empty_html(key))
            return
        parts, prev = [self._html_header(key)], None
        for msg in msgs:
            block, prev = self._fmt_msg(msg, prev)
            parts.append(block)
        parts.append("</body></html>")
        self.messages_view.setHtml("\n".join(parts))
        self.messages_view.loadFinished.connect(
            lambda ok, v=self.messages_view: v.page().runJavaScript(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
        )

    def _append_to_view(self, msg: dict):
        key = self._active_key()
        if key:
            self._display_conversation(key)

    def _is_dm_key(self, key: str) -> bool:
        return key.startswith("dm:")

    def _empty_html(self, key: str) -> str:
        is_dm  = self._is_dm_key(key)
        bg     = DM_BG if is_dm else DARK_BG
        color  = ACCENT_PURPLE if is_dm else ACCENT_BLUE
        icon   = "📩" if is_dm else "💬"
        lbl    = f"DM: {self._ctx_dm_id}" if is_dm else f"Canal #{self._ctx_channel}"
        return (
            f"<html><meta charset='utf-8'><body style='background:{bg};color:{TEXT_MUTED};"
            "font-family:monospace;display:flex;align-items:center;"
            "justify-content:center;height:100vh;margin:0;text-align:center;font-size:14px;'>"
            f"<div>{icon}<br><br>Nenhuma mensagem em<br>"
            f"<b style='color:{color};'>{html.escape(lbl)}</b> ainda.</div>"
            "</body></html>"
        )

    def _html_header(self, key: str) -> str:
        is_dm = self._is_dm_key(key)
        bg    = DM_BG if is_dm else DARK_BG
        return f"""<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:{bg};color:{TEXT_PRIMARY};
  font-family:'Menlo','Cascadia Code','Consolas',monospace;
  font-size:15px;padding:8px 6px 20px 6px;}}
.date-sep{{text-align:center;color:{TEXT_MUTED};font-size:11px;
  letter-spacing:2px;margin:10px 0 6px 0;}}
.row-in {{display:flex;justify-content:flex-start;margin:3px 0;}}
.row-out{{display:flex;justify-content:flex-end;  margin:3px 0;}}
.bubble-in{{
  background:{PANEL_BG};border:1px solid {BORDER_COLOR};
  border-radius:2px 12px 12px 12px;
  max-width:72%;padding:7px 11px 5px 11px;}}
.bubble-dm{{
  background:#1e1535;border:1px solid {ACCENT_PURPLE}66;
  border-radius:2px 12px 12px 12px;
  max-width:72%;padding:7px 11px 5px 11px;}}
.bubble-out{{
  background:#0f2d1a;border:1px solid {ACCENT_GREEN}55;
  border-radius:12px 2px 12px 12px;
  max-width:72%;padding:7px 11px 5px 11px;text-align:right;}}
.sender{{font-weight:bold;font-size:12px;margin-bottom:3px;}}
.body  {{font-size:15px;word-break:break-word;line-height:1.5;}}
.meta  {{font-size:10px;color:{TEXT_MUTED};margin-top:4px;}}
</style></head><body>"""

    def _fmt_msg(self, msg: dict, prev_date) -> tuple:
        msg_date = msg["time"].date()
        parts    = []

        if prev_date is None or msg_date != prev_date:
            today = datetime.now().date()
            if msg_date == today:
                ds = "&#8212; Hoje &#8212;"
            elif msg_date == today - timedelta(days=1):
                ds = "&#8212; Ontem &#8212;"
            else:
                ds = f"&#8212; {msg_date.strftime('%d/%m/%Y')} &#8212;"
            parts.append(f'<div class="date-sep">{ds}</div>')

        safe_text   = html.escape(msg["text"]).replace("\n", "<br>")
        sender_esc  = html.escape(msg["from_"])
        time_str    = msg["time"].strftime("%H:%M")
        color       = msg["color"]
        label       = html.escape(msg["label"])

        status        = msg.get('status', '')
        status_detail = msg.get('status_detail', '')
        if msg.get('outgoing'):
            if status == 'sending':
                status_html = f'<span title="A enviar..." style="color:{TEXT_MUTED};font-size:11px;">&#9679;&#9679;&#9679;</span>'
            elif status == 'ack_implicit':
                status_html = f'<span title="Recebido por relay" style="color:{ACCENT_ORANGE};font-size:12px;">&#10003;</span>'
            elif status == 'ack':
                status_html = f'<span title="Confirmado pelo destinatario" style="color:{ACCENT_GREEN};font-size:12px;">&#10003;&#10003;</span>'
            elif status == 'nak':
                err_esc     = html.escape(status_detail or 'Falha')
                status_html = f'<span title="Falha: {err_esc}" style="color:{ACCENT_RED};font-size:11px;">&#10007; {err_esc}</span>'
            else:
                status_html = ''
        else:
            status_html = ''

        if msg["outgoing"]:
            parts.append(
                '<div class="row-out"><div class="bubble-out">'
                f'<div class="sender" style="color:{color}">{sender_esc}</div>'
                f'<div class="body">{safe_text}</div>'
                f'<div class="meta">{label} &middot; {time_str}'
                + (f' &nbsp;{status_html}' if status_html else '') +
                '</div></div></div>'
            )
        elif msg["dm"]:
            parts.append(
                '<div class="row-in"><div class="bubble-dm">'
                f'<div class="sender" style="color:{color}">{sender_esc}'
                f' <span style="color:{ACCENT_PURPLE};font-size:9px;">[DM]</span></div>'
                f'<div class="body">{safe_text}</div>'
                f'<div class="meta">{label} &middot; {time_str}</div>'
                '</div></div>'
            )
        else:
            parts.append(
                '<div class="row-in"><div class="bubble-in">'
                f'<div class="sender" style="color:{color}">{sender_esc}</div>'
                f'<div class="body">{safe_text}</div>'
                f'<div class="meta">{label} &middot; {time_str}</div>'
                '</div></div>'
            )
        return "\n".join(parts), msg_date


# ---------------------------------------------------------------------------
# MeshtasticWorker
# ---------------------------------------------------------------------------
class MeshtasticWorker(QObject):
    connection_changed      = pyqtSignal(bool)
    node_updated            = pyqtSignal(str, dict, object)
    error_occurred          = pyqtSignal(str)
    message_received        = pyqtSignal(int, str, str, object)
    channels_updated        = pyqtSignal(list)
    my_node_id_ready        = pyqtSignal(str)
    interface_ready         = pyqtSignal(object)
    dm_sent                 = pyqtSignal(str, str, bool, int)
    channel_message_sent    = pyqtSignal(int, str, int)
    message_status_updated  = pyqtSignal(int, str, str)
    traceroute_result       = pyqtSignal(list, list, str, str)
    local_node_ready        = pyqtSignal(str, str, str, bool, bool)
    nodes_batch             = pyqtSignal(list)
    nodedb_reset            = pyqtSignal()
    # FIX-6: sinal formalmente declarado
    neighbor_info_received  = pyqtSignal(str, list)   # (from_id, [(neighbor_id, snr), ...])
    # resultado do envio de posição: (sucesso, mensagem_para_ui)
    position_sent           = pyqtSignal(bool, str)

    NODE_POLL_INTERVAL_MS = 15_000   # 15s — TCP menos fiável que BLE, precisa de safety-net mais frequente

    def __init__(self, hostname="localhost", port=4403, parent=None):
        super().__init__(parent)
        self.hostname   = hostname
        self.port       = port
        self.iface: Optional[TCPInterface] = None
        self._connected = False
        self._known_nodes: Set[str] = set()
        self._channels:    Dict[int, tuple] = {}
        self._poll_last_seen: Dict[str, int] = {}   # nid → lastHeard timestamp
        self._reconnect_attempts = 0
        self._reconnect_timer    = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_reconnect)

    def start(self):
        if self.iface is not None:
            return
        try:
            logger.info(f"Conectando a {self.hostname}:{self.port} …")
            self._known_nodes.clear()
            self._poll_last_seen.clear()
            self._reconnect_attempts = 0
            pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
            pub.subscribe(self._on_connection_lost,        "meshtastic.connection.lost")
            pub.subscribe(self._on_node_updated,           "meshtastic.node.updated")
            pub.subscribe(self._on_text_message,           "meshtastic.receive.text")
            pub.subscribe(self._on_packet_received,        "meshtastic.receive")
            self.iface = TCPInterface(self.hostname, self.port)
        except Exception as e:
            self.error_occurred.emit(
                f"Falha ao criar interface TCP ({self.hostname}:{self.port}): {e}"
            )
            logger.exception("Erro ao iniciar worker")

    def stop(self):
        self._reconnect_timer.stop()
        for topic, handler in [
            ("meshtastic.connection.established", self._on_connection_established),
            ("meshtastic.connection.lost",        self._on_connection_lost),
            ("meshtastic.node.updated",           self._on_node_updated),
            ("meshtastic.receive.text",           self._on_text_message),
            ("meshtastic.receive",                self._on_packet_received),
        ]:
            try:
                pub.unsubscribe(handler, topic)
            except Exception:
                pass
        self._known_nodes.clear()
        if self.iface:
            try:
                self.iface.close()
            except Exception as e:
                logger.error(f"Erro ao fechar: {e}")
            finally:
                self.iface      = None
                self._connected = False
                self.connection_changed.emit(False)

    def _on_connection_lost(self, interface=None):
        """Chamado pela biblioteca quando a ligação TCP é perdida."""
        logger.warning("Ligação perdida — a tentar reconectar…")
        self._connected = False
        self.connection_changed.emit(False)
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        """Backoff exponencial: 5s → 10s → 30s → 60s (máx)."""
        delays = [5_000, 10_000, 30_000, 60_000]
        idx    = min(self._reconnect_attempts, len(delays) - 1)
        delay  = delays[idx]
        self._reconnect_attempts += 1
        logger.info(f"Reconexão #{self._reconnect_attempts} em {delay//1000}s…")
        self._reconnect_timer.start(delay)

    def _do_reconnect(self):
        """Tenta fechar a interface antiga e criar uma nova."""
        if self._connected:
            return
        try:
            if self.iface:
                try:
                    self.iface.close()
                except Exception:
                    pass
                self.iface = None
            self._known_nodes.clear()
            self._poll_last_seen.clear()
            logger.info(f"A reconectar a {self.hostname}:{self.port}…")
            self.iface = TCPInterface(self.hostname, self.port)
        except Exception as e:
            logger.warning(f"Reconexão falhada: {e}")
            self._schedule_reconnect()

    def send_message(self, channel_index: int, text: str):
        if not self.iface or not self._connected:
            self.error_occurred.emit("Não conectado — impossível enviar mensagem.")
            return
        try:
            result = self.iface.sendText(text, channelIndex=channel_index, wantAck=True)
            pkt_id = result.id if result and hasattr(result, 'id') else 0
            logger.info(f"Canal {channel_index} msg enviada (pkt_id={pkt_id:#010x})")
            self.channel_message_sent.emit(channel_index, text, pkt_id)
        except Exception as e:
            self.error_occurred.emit(f"Erro ao enviar mensagem: {e}")

    def reset_nodedb(self):
        if not self.iface or not self._connected:
            self.error_occurred.emit("Não conectado — impossível resetar NodeDB.")
            return
        try:
            local_node = self.iface.localNode
            if hasattr(local_node, 'resetNodeDb'):
                local_node.resetNodeDb()
                logger.info("NodeDB resetado via localNode.resetNodeDb()")
            else:
                from meshtastic.protobuf import admin_pb2
                p = admin_pb2.AdminMessage()
                p.nodedb_reset = 1
                self.iface.localNode._sendAdmin(p)
                logger.info("NodeDB resetado via admin packet")
            self.nodedb_reset.emit()
        except Exception as e:
            logger.error(f"Erro ao resetar NodeDB: {e}", exc_info=True)
            self.error_occurred.emit(f"Erro ao resetar NodeDB: {e}")

    def send_traceroute(self, dest_id: str, hop_limit: int = 3):
        if not self.iface or not self._connected:
            self.error_occurred.emit("Não conectado — impossível enviar traceroute.")
            return
        try:
            from meshtastic.protobuf import mesh_pb2, portnums_pb2
            r = mesh_pb2.RouteDiscovery()
            self.iface.sendData(
                r,
                destinationId=dest_id,
                portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                wantResponse=True,
                hopLimit=hop_limit,
                channelIndex=0,
            )
            logger.info(f"Traceroute enviado para {dest_id} (hopLimit={hop_limit})")
        except Exception as e:
            logger.error(f"Erro ao enviar traceroute: {e}", exc_info=True)
            self.error_occurred.emit(f"Erro ao enviar traceroute: {e}")

    def send_position(self):
        """
        Envia a posição do nó local para a rede.

        Estratégia (por ordem de preferência):
          1. localNode.setPosition() — a biblioteca lê lat/lon da config interna
             e faz o broadcast directamente via firmware.
          2. Fallback manual: lê latitudeI/longitudeI do nodesByNum e constrói
             o pacote POSITION_APP à mão.

        Em ambos os casos emite position_sent(True/False, mensagem) para que
        _on_send_position possa actualizar a statusBar *apenas* após saber
        o resultado real.
        """
        if not self.iface or not self._connected:
            self.position_sent.emit(False, "Não conectado.")
            return
        try:
            import time
            from meshtastic.protobuf import mesh_pb2, portnums_pb2
            from meshtastic import BROADCAST_NUM

            local_node = self.iface.localNode
            local_num  = local_node.nodeNum

            # ── Tentativa 1: API de alto nível da biblioteca ──────────────
            # localNode.setPosition() envia directamente sem precisar de
            # ler coordenadas da cache TCP — funciona mesmo que nodesByNum
            # ainda não tenha recebido a posição do firmware.
            sent_via_api = False
            try:
                local_node.setPosition(
                    lat=None, lon=None, alt=None,
                    # Sem argumentos → firmware usa a posição interna (GPS ou fixa)
                )
                sent_via_api = True
                logger.info("send_position: enviado via localNode.setPosition()")
                self.position_sent.emit(True, "📍 Posição enviada para a rede (via firmware).")
                return
            except TypeError:
                # Versões mais antigas da lib exigem lat/lon explícitos
                pass
            except Exception as api_err:
                logger.debug(f"send_position: setPosition() falhou ({api_err}), tentando fallback")

            # ── Tentativa 2: lê coordenadas da cache e envia manualmente ──
            # Procura em nodesByNum (cache do daemon) e também na config fixa
            pos_data: dict = {}
            if hasattr(self.iface, 'nodesByNum'):
                pos_data = self.iface.nodesByNum.get(local_num, {}).get('position', {})

            lat_i = pos_data.get('latitudeI')
            lon_i = pos_data.get('longitudeI')

            # Tenta também a posição fixa na configuração do localNode
            if not lat_i or not lon_i:
                try:
                    pos_cfg = getattr(local_node, 'localConfig', None)
                    if pos_cfg:
                        pos_cfg = getattr(pos_cfg, 'position', None)
                    if pos_cfg:
                        fixed_lat = getattr(pos_cfg, 'fixed_lat',  None)
                        fixed_lon = getattr(pos_cfg, 'fixed_lon',  None)
                        fixed_alt = getattr(pos_cfg, 'fixed_alt',  None)
                        if fixed_lat and fixed_lon:
                            # Converte graus → inteiros × 1e7 se necessário
                            lat_i = int(fixed_lat * 1e7) if isinstance(fixed_lat, float) else int(fixed_lat)
                            lon_i = int(fixed_lon * 1e7) if isinstance(fixed_lon, float) else int(fixed_lon)
                            if fixed_alt:
                                pos_data['altitude'] = int(fixed_alt)
                            logger.info(f"send_position: usando posição fixa da config ({lat_i/1e7:.6f}, {lon_i/1e7:.6f})")
                except Exception as cfg_err:
                    logger.debug(f"send_position: não leu posição fixa da config: {cfg_err}")

            if not lat_i or not lon_i:
                msg = (
                    "O nó local não tem posição disponível.\n\n"
                    "Verifique se:\n"
                    "  • O GPS está activo e já adquiriu sinal, ou\n"
                    "  • Está definida uma posição fixa em Configurações → Posição/GPS\n"
                    "    (campos Latitude fixa / Longitude fixa)."
                )
                logger.warning("send_position: sem coordenadas — abortar")
                self.position_sent.emit(False, msg)
                return

            pos             = mesh_pb2.Position()
            pos.latitude_i  = int(lat_i)
            pos.longitude_i = int(lon_i)
            alt = pos_data.get('altitude')
            if alt:
                pos.altitude = int(alt)
            pos.time      = int(time.time())
            pos.timestamp = pos.time

            self.iface.sendData(
                pos,
                destinationId=BROADCAST_NUM,
                portNum=portnums_pb2.PortNum.POSITION_APP,
                wantAck=False,
                wantResponse=False,
                channelIndex=0,
            )
            msg = f"📍 Posição enviada ({lat_i/1e7:.6f}, {lon_i/1e7:.6f})."
            logger.info(msg)
            self.position_sent.emit(True, msg)

        except Exception as e:
            logger.error(f"Erro ao enviar posição: {e}", exc_info=True)
            self.position_sent.emit(False, f"Erro ao enviar posição: {e}")

    def send_node_info(self):
        if not self.iface or not self._connected:
            return
        try:
            local_node = self.iface.localNode
            if not local_node:
                self.error_occurred.emit("Nó local não disponível.")
                return
            local_num  = local_node.nodeNum
            me         = (self.iface.nodesByNum.get(local_num, {})
                          if hasattr(self.iface, 'nodesByNum') else {})
            user_data  = me.get('user', {})
            long_name  = user_data.get('longName', '')
            short_name = user_data.get('shortName', '')
            # setOwner reenvia o NODEINFO_APP broadcast com os dados actuais
            local_node.setOwner(long_name=long_name, short_name=short_name)
            logger.info(f"send_node_info: via setOwner ('{long_name}' / '{short_name}')")
        except Exception as e:
            logger.error(f"Erro ao enviar NODEINFO: {e}", exc_info=True)
            self.error_occurred.emit(f"Erro ao enviar Info do Nó: {e}")

    def send_direct_message(self, dest_id: str, text: str):
        if not self.iface or not self._connected:
            self.error_occurred.emit("Não conectado — impossível enviar DM.")
            return
        try:
            from meshtastic.protobuf import portnums_pb2

            dest_num: Optional[int] = None
            if dest_id.startswith('!'):
                try:
                    dest_num = int(dest_id[1:], 16) & 0xFFFFFFFF
                except ValueError:
                    pass

            dest_node = None
            if dest_num is not None and hasattr(self.iface, 'nodesByNum'):
                dest_node = self.iface.nodesByNum.get(dest_num)
            if dest_node is None and hasattr(self.iface, 'nodes'):
                dest_node = self.iface.nodes.get(dest_id)

            has_pubkey = bool(dest_node and dest_node.get('user', {}).get('publicKey', ''))

            if has_pubkey:
                try:
                    result = self.iface.sendData(
                        text.encode("utf-8"),
                        destinationId=dest_id,
                        portNum=portnums_pb2.PortNum.TEXT_MESSAGE_APP,
                        wantAck=True,
                        channelIndex=0,
                        pkiEncrypted=True,
                    )
                    pkt_id = result.id if result and hasattr(result, 'id') else 0
                    logger.info(f"DM PKI enviado para {dest_id} (pkt_id={pkt_id:#010x})")
                    self.dm_sent.emit(dest_id, text, True, pkt_id)
                    return
                except Exception as pki_err:
                    err_str = str(pki_err)
                    if 'PKI_UNKNOWN_PUBKEY' in err_str or 'unknown' in err_str.lower():
                        # FIX-3: mensagem de erro simplificada
                        logger.warning(f"DM PKI falhou para {dest_id}: {pki_err}")
                        self.error_occurred.emit(
                            f"Não foi possível enviar DM encriptado (PKI) para {dest_id}.\n\n"
                            "O rádio ainda não tem a chave pública deste nó.\n"
                            "Aguarde que ele se anuncie na rede (pode demorar alguns minutos)\n"
                            "ou clique em  📡 Nó → Enviar Info do Nó  para anunciar a sua chave."
                        )
                        return
                    raise

            # Fallback PSK
            logger.info(f"DM para {dest_id}: sem publicKey → PSK canal 0")
            result = self.iface.sendText(
                text, destinationId=dest_id, wantAck=True, channelIndex=0,
            )
            pkt_id = result.id if result and hasattr(result, 'id') else 0
            self.dm_sent.emit(dest_id, text, False, pkt_id)

        except Exception as e:
            logger.error(f"Erro ao enviar DM para {dest_id}: {e}", exc_info=True)
            self.error_occurred.emit(f"Erro ao enviar DM: {e}")

    def _on_text_message(self, packet, interface=None):
        try:
            from_id = packet.get('fromId', '')
            if not from_id:
                from_num = packet.get('from')
                if from_num:
                    if self.iface and hasattr(self.iface, 'nodesByNum'):
                        node    = self.iface.nodesByNum.get(int(from_num), {})
                        from_id = node.get('user', {}).get('id', '')
                    if not from_id and self.iface and hasattr(self.iface, 'nodes'):
                        node    = self.iface.nodes.get(from_num, {})
                        from_id = node.get('user', {}).get('id', '')
                    if not from_id:
                        from_id = f"!{int(from_num):08x}"
            if not from_id:
                return

            text = packet.get('decoded', {}).get('text', '')
            if not text:
                return

            pki_encrypted = bool(packet.get('pkiEncrypted', False))
            channel       = int(packet.get('channel', 0))
            to_raw        = packet.get('to', 0xFFFFFFFF)
            try:
                to_num = int(to_raw) & 0xFFFFFFFF
            except (TypeError, ValueError):
                to_num = 0xFFFFFFFF

            logger.info(
                f"MSG: from={from_id} to_raw={to_raw!r} to_num=0x{to_num:08x} "
                f"ch={channel} pki={pki_encrypted} txt={text[:40]!r}"
            )

            to_id = packet.get('toId', '')
            if not to_id and not _is_broadcast(to_num):
                if self.iface and hasattr(self.iface, 'nodesByNum'):
                    to_node = self.iface.nodesByNum.get(to_num, {})
                    to_id   = to_node.get('user', {}).get('id', '')
                if not to_id:
                    to_id = f"!{to_num:08x}"

            if pki_encrypted:
                pk_raw = packet.get('publicKey')
                if pk_raw and self.iface:
                    try:
                        import base64
                        from_num_int = packet.get('from')
                        if from_num_int:
                            from_num_int = int(from_num_int)
                            node_entry   = None
                            if hasattr(self.iface, 'nodesByNum'):
                                node_entry = self.iface.nodesByNum.get(from_num_int)
                            if node_entry is None and hasattr(self.iface, 'nodes'):
                                node_entry = self.iface.nodes.get(from_id)
                            if node_entry and 'user' in node_entry:
                                if isinstance(pk_raw, bytes):
                                    node_entry['user']['publicKey'] = base64.b64encode(pk_raw).decode()
                                else:
                                    node_entry['user']['publicKey'] = str(pk_raw)
                    except Exception as e:
                        logger.debug(f"Não actualizou publicKey de {from_id}: {e}")

            pkt_safe = {
                'fromId':       from_id,
                'toId':         to_id,
                'to':           to_num,
                'channel':      channel,
                'rxTime':       packet.get('rxTime'),
                'viaMqtt':      packet.get('viaMqtt', False),
                'pkiEncrypted': pki_encrypted,
                'decoded':      {'text': text},
                'hopsAway':     None,
            }
            # Tenta obter hopsAway do NodeDB (mais fiável que hopLimit do pacote)
            try:
                from_num_int = packet.get('from')
                if from_num_int and self.iface:
                    nd = (getattr(self.iface, 'nodesByNum', {}) or {}).get(from_num_int, {})
                    ha = nd.get('hopsAway')
                    if ha is not None:
                        pkt_safe['hopsAway'] = ha
                    elif packet.get('hopStart') is not None and packet.get('hopLimit') is not None:
                        pkt_safe['hopsAway'] = int(packet['hopStart']) - int(packet['hopLimit'])
            except Exception:
                pass

            if pki_encrypted:
                pk_raw = packet.get('publicKey')
                if pk_raw and from_id:
                    try:
                        import base64
                        pk_b64 = base64.b64encode(pk_raw).decode() if isinstance(pk_raw, bytes) else str(pk_raw)
                        self.node_updated.emit(from_id, {'public_key': pk_b64}, None)
                    except Exception:
                        pass

            self.message_received.emit(channel, from_id, text, pkt_safe)
        except Exception as e:
            logger.error(f"Erro no handler de texto: {e}", exc_info=True)

    def _sync_nodedb(self) -> int:
        if not self.iface or not self._connected:
            return 0

        nodes_src = getattr(self.iface, 'nodesByNum', None) or {}
        if not nodes_src:
            nodes_str = getattr(self.iface, 'nodes', None) or {}
            nodes_src = {}
            for k, v in nodes_str.items():
                try:
                    nodes_src[int(str(k).lstrip('!'), 16)] = v
                except Exception:
                    pass

        deduped: Dict[int, dict] = {}
        for raw_key, node in nodes_src.items():
            if not isinstance(node, dict):
                continue
            try:
                num = int(node.get('num') or raw_key)
            except (TypeError, ValueError):
                continue
            if num not in deduped:
                deduped[num] = node
            else:
                if (node.get('user', {}).get('publicKey') and
                        not deduped[num].get('user', {}).get('publicKey')):
                    deduped[num] = node

        if deduped:
            self.nodes_batch.emit(list(deduped.items()))
        return len(deduped)

    def _poll_nodedb(self):
        """
        Safety-net polling — sincroniza o NodeDB completo a cada 30s.
        Equivalente ao comportamento das apps iOS/Android: lê iface.nodesByNum
        e emite updates para todos os nós. Apanha nós novos e actualizações
        que a biblioteca não emitiu via pubsub (frequente com meshtasticd via TCP).
        """
        if not self.iface or not self._connected:
            return
        try:
            nodes_src = getattr(self.iface, 'nodesByNum', None) or {}
            count = 0
            for raw_key, node in nodes_src.items():
                if not isinstance(node, dict):
                    continue
                self._emit_node(node.get('num') or raw_key, node)
                count += 1
            logger.debug(f"Poll NodeDB: {count} nós sincronizados")
        except Exception as e:
            logger.debug(f"Erro no poll NodeDB: {e}")

    def _on_connection_established(self, interface=None):
        logger.info("Conexão estabelecida.")
        self._connected          = True
        self._reconnect_attempts = 0
        self._reconnect_timer.stop()
        self._known_nodes.clear()
        self._poll_last_seen.clear()
        self.connection_changed.emit(True)

        # FIX-4: bloqueia inserção do nó local ANTES do batch inicial
        try:
            if self.iface and self.iface.localNode:
                local_num  = self.iface.localNode.nodeNum
                local_id   = f"!{int(local_num):08x}" if local_num else None
                logger.info(f"Nó local: num={local_num} id={local_id}")
                # Emite sinal auxiliar para que MainWindow configure os modelos imediatamente
                if local_id:
                    self._local_num_known = local_num
                    self._local_id_known  = local_id
                    self.my_node_id_ready.emit(local_id)   # bloqueia proxy antes do batch
        except Exception as e:
            logger.warning(f"Não foi possível determinar nodeNum local: {e}")

        # Carga inicial completa
        try:
            loaded = self._sync_nodedb()
            logger.info(f"NodeDB inicial: {loaded} nós carregados")
        except Exception as e:
            logger.error(f"Erro ao carregar NodeDB inicial: {e}", exc_info=True)

        # FIX-6: NeighborInfo inicial do NodeDB
        try:
            nodes_src = getattr(self.iface, 'nodesByNum', None) or {}
            for raw_key, node in nodes_src.items():
                if not isinstance(node, dict):
                    continue
                neighbors_raw = node.get('neighborInfo', {}).get('neighbors', [])
                if not neighbors_raw:
                    continue
                try:
                    num     = int(node.get('num') or raw_key)
                    from_id = node.get('user', {}).get('id') or f"!{num:08x}"
                except (TypeError, ValueError):
                    continue
                neighbors = []
                for nb in neighbors_raw:
                    nb_num = nb.get('nodeId') or nb.get('node_id')
                    if nb_num:
                        neighbors.append((f"!{int(nb_num):08x}", float(nb.get('snr', 0.0))))
                if neighbors:
                    self.neighbor_info_received.emit(from_id, neighbors)
        except Exception as e:
            logger.debug(f"Erro ao carregar NeighborInfo inicial: {e}")

        # Metadados do nó local
        try:
            my_id = self._get_my_node_id()
            if my_id:
                self.my_node_id_ready.emit(my_id)

            local_num  = self.iface.localNode.nodeNum if self.iface and self.iface.localNode else None
            local_user = {}
            if local_num and hasattr(self.iface, "nodesByNum"):
                local_user = self.iface.nodesByNum.get(local_num, {}).get("user", {})
            if not local_user and my_id and hasattr(self.iface, "nodes"):
                local_user = self.iface.nodes.get(my_id, {}).get("user", {})
            ln  = local_user.get("longName", "")
            sn  = local_user.get("shortName", "")
            nid = local_user.get("id", my_id or "")

            gps_enabled  = False
            has_position = False
            try:
                local_node_obj = self.iface.localNode if self.iface else None
                if local_node_obj:
                    pos_cfg = getattr(local_node_obj, 'localConfig', None)
                    if pos_cfg:
                        pos_cfg = getattr(pos_cfg, 'position', None)
                    if pos_cfg:
                        gps_mode    = getattr(pos_cfg, 'gps_mode', None)
                        gps_enabled = (gps_mode == 1) if gps_mode is not None else False
            except Exception:
                pass
            try:
                if local_num and hasattr(self.iface, 'nodesByNum'):
                    pos          = self.iface.nodesByNum.get(local_num, {}).get('position', {})
                    has_position = bool(pos and pos.get('latitudeI') and pos.get('longitudeI'))
            except Exception:
                pass

            self.local_node_ready.emit(ln, sn, nid, gps_enabled, has_position)
        except Exception as e:
            logger.error(f"Erro ao obter metadados locais: {e}")

        self.interface_ready.emit(self.iface)
        self._attempt_load_channels(retry_count=0)

    def _get_my_node_id(self):
        try:
            if not self.iface:
                return None
            my_info = self.iface.getMyNodeInfo()
            if my_info and 'user' in my_info:
                return my_info['user'].get('id')
            for node_id, node in self.iface.nodes.items():
                if node.get('user', {}).get('id') and node.get('isMe'):
                    return node['user']['id']
        except Exception as e:
            logger.error(f"Erro ao obter ID local: {e}")
        return None

    def _attempt_load_channels(self, retry_count=0):
        if not self._load_channels_from_node() and retry_count < 5:
            QTimer.singleShot(2000,
                              functools.partial(self._attempt_load_channels, retry_count + 1))

    def _on_node_updated(self, node, interface=None):
        if not isinstance(node, dict):
            return
        num = node.get('num')
        nid = node.get('user', {}).get('id')
        if not nid and num:
            try:
                nid = f"!{int(num):08x}"
            except (TypeError, ValueError):
                return
        if not nid:
            return
        self._emit_node(num, node)

    def _on_packet_received(self, packet, interface=None):
        try:
            from_id_num    = packet.get('from')
            from_id_string = packet.get('fromId')
            if not from_id_string and from_id_num and self.iface:
                from_id_string = (self.iface.nodes.get(from_id_num, {})
                                  .get('user', {}).get('id'))
            if not from_id_string:
                return

            decoded = packet.get('decoded') or {}
            portnum = decoded.get('portnum')

            if portnum != 'ROUTING_APP':
                if self.iface and self.iface.localNode:
                    local_num = self.iface.localNode.nodeNum
                    is_local  = False
                    if from_id_num is not None and local_num is not None:
                        try:
                            is_local = int(from_id_num) == int(local_num)
                        except (TypeError, ValueError):
                            pass
                    if not is_local and local_num is not None and from_id_string:
                        try:
                            is_local = from_id_string.lower() == f'!{int(local_num):08x}'
                        except (TypeError, ValueError):
                            pass
                    if is_local:
                        logger.debug(f'Loopback ignorado: portnum={portnum} from={from_id_string}')
                        return

            if portnum == 'TEXT_MESSAGE_APP':
                # Actualiza lastHeard/snr do remetente (igual às apps iOS/Android)
                # mas não processa o conteúdo aqui — isso é feito por _on_text_message
                _txt_updates: Dict[str, Any] = {}
                for key, pkt_key in (('snr', 'rxSnr'), ('via_mqtt', 'viaMqtt')):
                    val = packet.get(pkt_key)
                    if val is not None:
                        _txt_updates[key] = val
                # hopsAway vem do NodeDB actualizado pela biblioteca, não do pacote
                if self.iface:
                    _num = packet.get('from')
                    if _num:
                        _nd = (getattr(self.iface, 'nodesByNum', {}) or {}).get(_num, {})
                        _ha = _nd.get('hopsAway')
                        if _ha is not None:
                            _txt_updates['hops_away'] = _ha
                rx_time = packet.get('rxTime')
                if rx_time:
                    try:
                        _txt_updates['last_heard'] = datetime.fromtimestamp(rx_time)
                    except Exception:
                        pass
                if _txt_updates:
                    self.node_updated.emit(from_id_string, _txt_updates, packet)
                return

            if portnum == 'ROUTING_APP':
                try:
                    routing    = decoded.get('routing', {})
                    request_id = decoded.get('requestId', 0)
                    if request_id:
                        error_reason = routing.get('errorReason', 'NONE')
                        if error_reason and error_reason != 'NONE':
                            status = 'nak'
                        else:
                            from_num  = packet.get('from')
                            local_num = self.iface.localNode.nodeNum if self.iface else None
                            if from_num and local_num and int(from_num) == int(local_num):
                                status = 'ack_implicit'
                            else:
                                status = 'ack'
                        self.message_status_updated.emit(request_id, status, error_reason or 'NONE')
                except Exception as e:
                    logger.debug(f"Erro ao processar ROUTING_APP: {e}")
                return

            if portnum == 'TRACEROUTE_APP':
                try:
                    want_response = packet.get('wantResponse', False)
                    if want_response:
                        return

                    tr = decoded.get('traceroute', {})
                    if not tr:
                        return

                    origin_num = packet.get('to')
                    dest_num   = packet.get('from')

                    def num_to_id(n):
                        try:
                            ni = int(n)
                            if ni == 0 or ni == 0xFFFFFFFF:
                                return None
                            if self.iface and hasattr(self.iface, 'nodesByNum'):
                                uid = self.iface.nodesByNum.get(ni, {}).get('user', {}).get('id', '')
                                if uid:
                                    return uid
                            return f"!{ni:08x}"
                        except (TypeError, ValueError):
                            return None

                    forward_edges = []
                    back_edges    = []

                    route_toward = [r for r in (tr.get('route') or []) if r]
                    snr_toward   = list(tr.get('snrTowards') or tr.get('snrToward') or [])
                    full_toward  = [origin_num] + route_toward + [dest_num]
                    for i in range(len(full_toward) - 1):
                        a_id = num_to_id(full_toward[i])
                        b_id = num_to_id(full_toward[i + 1])
                        if not a_id or not b_id:
                            continue
                        snr = float(snr_toward[i]) / 4.0 if i < len(snr_toward) else 0.0
                        forward_edges.append((a_id, b_id, snr))

                    route_back = [r for r in (tr.get('routeBack') or []) if r]
                    snr_back   = list(tr.get('snrBack') or [])
                    full_back  = [dest_num] + route_back + [origin_num]
                    for i in range(len(full_back) - 1):
                        a_id = num_to_id(full_back[i])
                        b_id = num_to_id(full_back[i + 1])
                        if not a_id or not b_id:
                            continue
                        snr = float(snr_back[i]) / 4.0 if i < len(snr_back) else 0.0
                        back_edges.append((a_id, b_id, snr))

                    if forward_edges or back_edges:
                        origin_str = num_to_id(origin_num) or '?'
                        dest_str   = num_to_id(dest_num) or '?'
                        self.traceroute_result.emit(forward_edges, back_edges, origin_str, dest_str)
                except Exception as e:
                    logger.debug(f"Erro ao processar TRACEROUTE_APP: {e}", exc_info=True)
                return

            # FIX-2: processa NEIGHBORINFO_APP em tempo real
            if portnum == 'NEIGHBORINFO_APP':
                try:
                    ni_data   = decoded.get('neighborinfo', {})
                    if not ni_data:
                        ni_data = decoded.get('neighborInfo', {})
                    neighbors_raw = ni_data.get('neighbors', [])
                    if neighbors_raw:
                        neighbors = []
                        for nb in neighbors_raw:
                            nb_num = nb.get('nodeId') or nb.get('node_id')
                            if nb_num:
                                neighbors.append((f"!{int(nb_num):08x}",
                                                  float(nb.get('snr', 0.0))))
                        if neighbors:
                            self.neighbor_info_received.emit(from_id_string, neighbors)
                            logger.info(
                                f"NeighborInfo de {from_id_string}: "
                                f"{len(neighbors)} vizinhos"
                            )
                except Exception as e:
                    logger.debug(f"Erro ao processar NEIGHBORINFO_APP: {e}")
                # Continua para o processamento genérico de updates

            updates: Dict[str, Any] = {}

            if portnum == 'NODEINFO_APP':
                user = decoded.get('user', {})
                updates.update({
                    'long_name':  user.get('longName', ''),
                    'short_name': user.get('shortName', ''),
                    'hw_model':   user.get('hwModel', ''),
                    'id_num':     from_id_num,
                })
                self._extract_position(decoded.get('position', {}), updates)
                self._known_nodes.add(from_id_string)

            elif portnum == 'POSITION_APP':
                self._extract_position(decoded.get('position', {}), updates)
                if from_id_string not in self._known_nodes:
                    self._known_nodes.add(from_id_string)

            elif portnum == 'TELEMETRY_APP':
                dm = decoded.get('telemetry', {}).get('deviceMetrics', {})
                if dm:
                    updates['battery_level'] = dm.get('batteryLevel')

            for key, pkt_key in (('snr', 'rxSnr'), ('via_mqtt', 'viaMqtt')):
                val = packet.get(pkt_key)
                if val is not None:
                    updates[key] = val

            # hopsAway vem do NodeDB actualizado pela biblioteca (não do hopLimit do pacote)
            if self.iface and from_id_num:
                _nd = (getattr(self.iface, 'nodesByNum', {}) or {}).get(from_id_num, {})
                _ha = _nd.get('hopsAway')
                if _ha is not None:
                    updates['hops_away'] = _ha

            rx_time = packet.get('rxTime')
            if rx_time:
                updates['last_heard'] = datetime.fromtimestamp(rx_time)

            updates['last_packet_type'] = portnum or 'desconhecido'
            if 'id_num' not in updates and from_id_num:
                updates['id_num'] = from_id_num

            # Para nós MQTT que não enviam NODEINFO/POSITION/TELEMETRY frequentemente,
            # garantimos que pelo menos o last_heard e via_mqtt são actualizados
            # mesmo que não haja mais nenhum campo relevante.
            if updates:
                self.node_updated.emit(from_id_string, updates, packet)

        except Exception as e:
            logger.error(f"Erro no processamento de pacote: {e}", exc_info=True)

    @staticmethod
    def _extract_position(pos: dict, updates: dict):
        lat_i = pos.get('latitudeI')
        lon_i = pos.get('longitudeI')
        if lat_i is not None: updates['latitude']  = lat_i / 1e7
        if lon_i is not None: updates['longitude'] = lon_i / 1e7
        alt = pos.get('altitude')
        if alt is not None:   updates['altitude']  = alt

    def _emit_node(self, node_id_num, node_obj: dict, packet=None):
        user = node_obj.get('user', {})
        nid  = user.get('id')
        if not nid:
            if node_id_num:
                try:
                    nid = f"!{int(node_id_num):08x}"
                except (TypeError, ValueError):
                    return
            else:
                return

        self._known_nodes.add(nid)
        last_heard = node_obj.get('lastHeard')
        if last_heard:
            try:
                last_heard = datetime.fromtimestamp(last_heard)
            except Exception:
                pass

        pos   = node_obj.get('position', {})
        lat_i = pos.get('latitudeI')
        lon_i = pos.get('longitudeI')

        data = {
            "id_num":        node_id_num,
            "long_name":     user.get('longName', ''),
            "short_name":    user.get('shortName', ''),
            "last_heard":    last_heard,
            "snr":           node_obj.get('snr'),
            "hops_away":     node_obj.get('hopsAway'),
            "via_mqtt":      node_obj.get('viaMqtt'),
            "latitude":      lat_i / 1e7 if lat_i is not None else None,
            "longitude":     lon_i / 1e7 if lon_i is not None else None,
            "altitude":      pos.get('altitude'),
            "battery_level": node_obj.get('deviceMetrics', {}).get('batteryLevel'),
            "hw_model":      user.get('hwModel', ''),
            "public_key":    user.get('publicKey', ''),
        }
        self.node_updated.emit(nid, data, packet)

    def _load_channels_from_node(self) -> bool:
        try:
            if not self.iface:
                return False
            local_node = self.iface.getNode("^local")
            if not local_node or not getattr(local_node, 'channels', None):
                return False

            self._channels.clear()
            for ch in local_node.channels:
                index    = ch.index
                raw_name = (ch.settings.name if ch.settings else "") or ""
                name     = raw_name if raw_name else ("Primary" if index == 0 else f"Canal {index}")
                psk      = ch.settings.psk if ch.settings else b""
                self._channels[index] = (name, psk)

            if not self._channels:
                return False

            self.channels_updated.emit([
                (idx, name, psk) for idx, (name, psk) in self._channels.items()
            ])
            return True
        except Exception as e:
            logger.error(f"Erro ao carregar canais: {e}", exc_info=True)
            return False


# ---------------------------------------------------------------------------
# ConsoleWindow — janela de logs não-bloqueante
# ---------------------------------------------------------------------------
class _LogHandler(logging.Handler):
    """Handler que emite log records para um slot Qt."""
    def __init__(self, callback):
        super().__init__()
        self._cb = callback

    def emit(self, record):
        try:
            self._cb(self.format(record))
        except Exception:
            pass


class ConsoleWindow(QWidget):
    """Janela flutuante com os logs da aplicação. Não bloqueia a janela principal."""

    log_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("🖥  Consola de Logs")
        self.resize(860, 420)
        self.setAttribute(Qt.WA_DeleteOnClose, False)  # reutilizar

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Barra de controlos
        ctrl = QHBoxLayout()
        self._lbl_count = QLabel("0 linhas")
        self._lbl_count.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        ctrl.addWidget(self._lbl_count)
        ctrl.addStretch()

        lbl_filter = QLabel("Filtro:")
        lbl_filter.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        ctrl.addWidget(lbl_filter)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("palavra-chave…")
        self._filter.setFixedWidth(180)
        self._filter.setStyleSheet(
            f"background:{DARK_BG};color:{TEXT_PRIMARY};border:1px solid {BORDER_COLOR};"
            f"border-radius:4px;padding:2px 6px;font-size:11px;"
        )
        self._filter.textChanged.connect(self._apply_filter)
        ctrl.addWidget(self._filter)

        btn_clear = QPushButton("🗑 Limpar")
        btn_clear.setStyleSheet(
            f"QPushButton{{background:{PANEL_BG};color:{TEXT_MUTED};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;padding:3px 10px;"
            f"font-size:11px;}}"
            f"QPushButton:hover{{color:{TEXT_PRIMARY};}}"
        )
        btn_clear.clicked.connect(self._clear)
        ctrl.addWidget(btn_clear)
        root.addLayout(ctrl)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Monospace", 9) if sys.platform != "darwin" else QFont("Menlo", 10))
        self._text.setStyleSheet(
            f"background:{DARK_BG};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;padding:4px;"
        )
        self._text.setLineWrapMode(QTextEdit.NoWrap)
        root.addWidget(self._text)

        self._all_lines: list = []
        self._line_count = 0

        # Ligação do handler de logging
        self.log_signal.connect(self._append_line)
        self._handler = _LogHandler(self.log_signal.emit)
        self._handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        ))
        logging.getLogger().addHandler(self._handler)

    def _append_line(self, text: str):
        self._all_lines.append(text)
        if len(self._all_lines) > 2000:
            self._all_lines = self._all_lines[-1500:]
        flt = self._filter.text().strip().lower()
        if not flt or flt in text.lower():
            self._text.append(text)
            self._text.moveCursor(self._text.textCursor().End)
        self._line_count += 1
        self._lbl_count.setText(f"{len(self._all_lines)} linhas")

    def _apply_filter(self, text: str):
        flt = text.strip().lower()
        self._text.setUpdatesEnabled(False)
        self._text.clear()
        for line in self._all_lines:
            if not flt or flt in line.lower():
                self._text.append(line)
        self._text.moveCursor(self._text.textCursor().End)
        self._text.setUpdatesEnabled(True)

    def _clear(self):
        self._all_lines.clear()
        self._text.clear()
        self._lbl_count.setText("0 linhas")

    def closeEvent(self, event):
        # Oculta em vez de destruir
        self.hide()
        event.ignore()


# ---------------------------------------------------------------------------
# RebootWaitDialog — aguarda reinício do nó e libera reconexão
# ---------------------------------------------------------------------------
class RebootWaitDialog(QDialog):
    """Diálogo modal que desliga do nó, faz a contagem de 15s obrigatória
    (tempo mínimo recomendado pela documentação Meshtastic para aguardar
    após guardar configurações antes de reconectar via TCP) e libera o
    botão de reconexão quando o tempo termina."""

    reconnect_requested = pyqtSignal()
    WAIT_SECONDS = 15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("A reiniciar nó…")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(24, 20, 24, 20)

        # Ícone + título
        lbl_title = QLabel("🔄  Nó a reiniciar")
        lbl_title.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:15px;font-weight:bold;"
        )
        lbl_title.setAlignment(Qt.AlignCenter)
        root.addWidget(lbl_title)

        lbl_info = QLabel(
            "As configurações foram enviadas ao nó.\n"
            "O nó está a reiniciar para as aplicar.\n\n"
            "Aguarde antes de reconectar para garantir\n"
            "que o serviço TCP está novamente disponível."
        )
        lbl_info.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:12px;")
        lbl_info.setAlignment(Qt.AlignCenter)
        root.addWidget(lbl_info)

        # Barra de progresso
        self._progress = QProgressBar()
        self._progress.setRange(0, self.WAIT_SECONDS)
        self._progress.setValue(self.WAIT_SECONDS)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        self._progress.setStyleSheet(
            f"QProgressBar{{background:{PANEL_BG};border:1px solid {BORDER_COLOR};"
            f"border-radius:4px;}}"
            f"QProgressBar::chunk{{background:{ACCENT_GREEN};border-radius:4px;}}"
        )
        root.addWidget(self._progress)

        # Botão de reconexão (bloqueado durante a contagem)
        self._btn = QPushButton(f"🔌  Aguarde {self.WAIT_SECONDS}s…")
        self._btn.setEnabled(False)
        self._btn.setObjectName("btn_connect")
        self._btn.setMinimumHeight(38)
        self._btn.clicked.connect(self._on_reconnect)
        root.addWidget(self._btn)

        # Timer de contagem
        self._remaining = self.WAIT_SECONDS
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Impede fechar com Esc/X durante a contagem
        self.setWindowFlags(self.windowFlags() | Qt.CustomizeWindowHint)
        self._done = False

    def _tick(self):
        self._remaining -= 1
        self._progress.setValue(self._remaining)
        if self._remaining > 0:
            self._btn.setText(f"🔌  Aguarde {self._remaining}s…")
        else:
            self._timer.stop()
            self._btn.setEnabled(True)
            self._btn.setText("🔌  Reconectar agora")
            self._done = True

    def _on_reconnect(self):
        self._timer.stop()
        self.reconnect_requested.emit()
        self.accept()

    def closeEvent(self, event):
        if not self._done:
            event.ignore()   # bloqueia fechar antes do tempo
        else:
            self._timer.stop()
            super().closeEvent(event)


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: Optional[MeshtasticWorker] = None
        self._hostname  = "localhost"
        self._port      = 4403
        self._selected_node_id: Optional[str]   = None
        self._pending_traceroute_dest: Optional[tuple] = None

        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background:{PANEL_BG}; color:{ACCENT_GREEN}; font-size:11px; }}"
        )

        self._countdown_seconds  = 0
        self._countdown_base_msg = ""
        self._countdown_timer    = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

        self.source_model = NodeTableModel(self)
        self.proxy_model  = NodeFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setDynamicSortFilter(False)

        # FIX-5: timer de polling — safety-net, não substitui eventos pubsub
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(MeshtasticWorker.NODE_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_nodedb)

        # Debounce do mapa: agrupa vários updates consecutivos num único redesenho
        self._map_debounce = QTimer(self)
        self._map_debounce.setSingleShot(True)
        self._map_debounce.setInterval(800)
        self._map_debounce.timeout.connect(self._refresh_map)

        self._console_window = ConsoleWindow()

        self._init_ui()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        QTimer.singleShot(100, self._open_connection_dialog)

    def _init_ui(self):
        self.setWindowTitle("Meshtastic Monitor")
        self.resize(1440, 760)

        menu_bar = self.menuBar()

        conn_menu = menu_bar.addMenu("🔌  Conexão")

        act_connect = QAction("🔌  Conectar…", self)
        act_connect.setShortcut("Ctrl+K")
        act_connect.triggered.connect(self._open_connection_dialog)
        conn_menu.addAction(act_connect)

        conn_menu.addSeparator()

        act_disconnect = QAction("⏹  Desconectar", self)
        act_disconnect.triggered.connect(self._disconnect)
        conn_menu.addAction(act_disconnect)

        node_menu = menu_bar.addMenu("📡  Nó")

        self.act_send_nodeinfo = QAction("📡  Enviar Info do Nó", self)
        self.act_send_nodeinfo.setShortcut("Ctrl+I")
        self.act_send_nodeinfo.setEnabled(False)
        self.act_send_nodeinfo.triggered.connect(self._on_send_nodeinfo)
        node_menu.addAction(self.act_send_nodeinfo)

        node_menu.addSeparator()

        self.act_send_position = QAction("📍  Enviar Posição Manual", self)
        self.act_send_position.setShortcut("Ctrl+P")
        self.act_send_position.setEnabled(False)
        self.act_send_position.triggered.connect(self._on_send_position)
        node_menu.addAction(self.act_send_position)

        config_menu = menu_bar.addMenu("🔧  Ferramentas")

        self.act_reset_nodedb = QAction("🗑  Reset NodeDB", self)
        self.act_reset_nodedb.setEnabled(False)
        self.act_reset_nodedb.triggered.connect(self._on_reset_nodedb)
        config_menu.addAction(self.act_reset_nodedb)

        config_menu.addSeparator()

        act_console = QAction("🖥  Consola de logs…", self)
        act_console.setShortcut("Ctrl+L")
        act_console.triggered.connect(self._show_console_window)
        config_menu.addAction(act_console)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(8)

        # ── Barra superior ──────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(12)

        logo_lbl = QLabel()
        logo_svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="28" height="28">
  <rect width="100" height="100" rx="16" fill="#2b2b2b"/>
  <line x1="18" y1="78" x2="38" y2="22" stroke="#67EA94" stroke-width="13" stroke-linecap="round"/>
  <line x1="42" y1="78" x2="67" y2="22" stroke="#67EA94" stroke-width="13" stroke-linecap="round"/>
  <line x1="67" y1="22" x2="88" y2="78" stroke="#67EA94" stroke-width="13" stroke-linecap="round"/>
</svg>"""
        renderer = QSvgRenderer(QByteArray(logo_svg))
        pixmap   = QPixmap(28, 28)
        pixmap.fill(Qt.transparent)
        painter  = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        logo_lbl.setPixmap(pixmap)
        logo_lbl.setFixedSize(28, 28)
        top.addWidget(logo_lbl)

        title_lbl = QLabel("  Meshtastic Monitor")
        title_lbl.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:16px;font-weight:bold;letter-spacing:1px;"
        )
        top.addWidget(title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        top.addWidget(sep)

        lbl_search = QLabel("🔍")
        lbl_search.setStyleSheet(f"color:{TEXT_MUTED};font-size:14px;")
        top.addWidget(lbl_search)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Pesquisar por ID, nome longo ou curto…")
        self.search_edit.setMinimumWidth(280)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        top.addWidget(self.search_edit)

        top.addStretch()

        # FIX-8: label do contador — actualizado por source_model.get_visible_count()
        self.node_count_label = QLabel("Nós: 0")
        self.node_count_label.setStyleSheet(
            f"color:{ACCENT_BLUE};font-weight:bold;font-size:13px;"
            f"background:{PANEL_BG};padding:4px 12px;"
            f"border:1px solid {BORDER_COLOR};border-radius:12px;"
        )
        self.node_count_label.setToolTip("Total de nós na rede (excluindo o nó local)")
        top.addWidget(self.node_count_label)

        self.conn_indicator = QLabel("⚫  Desconectado")
        self.conn_indicator.setStyleSheet(
            f"color:{ACCENT_RED};font-weight:bold;font-size:12px;"
            f"background:{PANEL_BG};padding:4px 12px;"
            f"border:1px solid {BORDER_COLOR};border-radius:12px;"
        )
        top.addWidget(self.conn_indicator)

        root.addLayout(top)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(line)

        self.tab_widget = QTabWidget()
        root.addWidget(self.tab_widget, stretch=1)

        self.list_tab = QWidget()
        self.tab_widget.addTab(self.list_tab, "📋  Lista de Nós")
        self._setup_list_tab()

        self.map_tab = QWidget()
        self.tab_widget.addTab(self.map_tab, "🗺  Mapa")
        self._setup_map_tab()

        self.messages_tab = MessagesTab()
        self.messages_tab.send_channel_message.connect(self._on_send_channel_message)
        self.messages_tab.send_direct_message.connect(self._on_send_direct_message)
        self.messages_tab.set_node_choices_provider(
            lambda: self.source_model.get_node_choices()
        )
        self.tab_widget.addTab(self.messages_tab, "💬  Mensagens")

        self.config_tab = ConfigTab()
        self.config_tab.reboot_required.connect(self._on_reboot_required)
        self.tab_widget.addTab(self.config_tab, "⚙ Configurações")

    def _setup_list_tab(self):
        layout = QVBoxLayout(self.list_tab)
        layout.setContentsMargins(0, 8, 0, 0)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 0, 6, 4)
        hint = QLabel(
            "💡 ⭐ → Favorito  ·  📩/🔒 → DM  ·  🗺 → Mapa  ·  📡 → Traceroute  ·  "
            "Duplo clique → Detalhes  &nbsp;&nbsp;|&nbsp;&nbsp;"
            "<span style='color:#f5c518;'>⭐</span> Favorito (fixo no topo)  &nbsp;"
            "<span style='color:#8b949e;'>☆</span> Não favorito"
        )
        hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;padding:2px 0;")
        bar.addWidget(hint)
        bar.addStretch()
        self.local_node_label = QLabel("Nó local: —")
        self.local_node_label.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:11px;padding:2px 8px;"
            f"background:{PANEL_BG};border:1px solid {BORDER_COLOR};border-radius:8px;"
        )
        bar.addWidget(self.local_node_label)
        layout.addLayout(bar)

        self.table_view = QTableView()
        self.table_view.setModel(self.proxy_model)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setWordWrap(False)
        # Performance crítica: ResizeToContents é O(n) por célula visível a cada repaint.
        # Usar Interactive (largura fixa) para todas as colunas de dados.
        hh = self.table_view.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        # Colunas de ícone — fixas e estreitas
        hh.setSectionResizeMode(NodeTableModel.COL_FAV,        QHeaderView.Fixed)
        hh.setSectionResizeMode(NodeTableModel.COL_DM,         QHeaderView.Fixed)
        hh.setSectionResizeMode(NodeTableModel.COL_MAP,        QHeaderView.Fixed)
        hh.setSectionResizeMode(NodeTableModel.COL_TRACEROUTE, QHeaderView.Fixed)
        self.table_view.setColumnWidth(NodeTableModel.COL_FAV,        28)
        self.table_view.setColumnWidth(NodeTableModel.COL_DM,         30)
        self.table_view.setColumnWidth(NodeTableModel.COL_MAP,        30)
        self.table_view.setColumnWidth(NodeTableModel.COL_TRACEROUTE, 30)
        # Larguras razoáveis para as colunas de dados
        col_widths = {
            4:  90,   # ID String
            5:  80,   # ID Num
            6: 180,   # Nome Longo
            7:  60,   # Nome Curto
            8: 145,   # Último Contato
            9:  70,   # SNR
            10: 45,   # Hops
            11: 65,   # Via
            12: 95,   # Latitude
            13: 95,   # Longitude
            14: 75,   # Altitude
            15: 70,   # Bateria
            16: 110,  # Modelo
            17: 120,  # Último Tipo (Stretch)
        }
        for col, w in col_widths.items():
            self.table_view.setColumnWidth(col, w)
        # Última coluna estica para preencher espaço restante
        hh.setSectionResizeMode(17, QHeaderView.Stretch)
        self.table_view.verticalHeader().setDefaultSectionSize(26)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.doubleClicked.connect(self._on_double_click)
        self.table_view.clicked.connect(self._on_table_clicked)
        self.table_view.sortByColumn(8, Qt.DescendingOrder)
        layout.addWidget(self.table_view)

    def _setup_map_tab(self):
        layout = QVBoxLayout(self.map_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        self.map_widget = MapWidget()
        self.map_widget.node_deselected.connect(self._on_node_deselected)
        self.map_widget.set_traceroute_callback(self._on_map_traceroute_request)
        layout.addWidget(self.map_widget)

    def _on_map_traceroute_request(self, node_id: str):
        """Chamado quando o utilizador clica em 'Traceroute' no popup do mapa."""
        if not self.worker or not self.worker._connected:
            QMessageBox.warning(self, "Desconectado",
                                "Conecte-se primeiro para enviar traceroute.")
            return
        # Bloqueia novo envio enquanto countdown activo
        if self._countdown_seconds > 0:
            QMessageBox.information(
                self, "Traceroute em curso",
                f"Aguarde {self._countdown_seconds}s até o traceroute anterior terminar."
            )
            return
        all_nodes = self.source_model.get_all_nodes()
        node = next((n for n in all_nodes if n.get("id_string") == node_id), None)
        name = (node.get('long_name') or node_id) if node else node_id

        # Verifica duplicado na lista
        local_id = getattr(self, '_local_node_id_str', None) or ''
        existing = next(
            (rec for rec in self.map_widget._tr_records
             if (rec.get('origin_id') == local_id and rec.get('dest_id') == node_id)
             or (rec.get('origin_id') == node_id and rec.get('dest_id') == local_id)),
            None
        )
        if existing:
            reply = QMessageBox.question(
                self, "Traceroute já existente",
                f"Já existe um traceroute para {name} na lista.\n\n"
                f"Deseja enviar um novo traceroute mesmo assim?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return

        self._pending_traceroute_dest = (node_id, name)
        self.worker.send_traceroute(node_id)
        self._show_countdown_message(
            f"📡 Traceroute enviado para {name} — aguardando resposta…", 30
        )

    # ------------------------------------------------------------------
    # Conexão / desconexão
    # ------------------------------------------------------------------
    def _open_connection_dialog(self):
        dlg = ConnectionDialog(self._hostname, self._port, self)
        if dlg.exec_() == QDialog.Accepted:
            self._hostname = dlg.hostname
            self._port     = dlg.port
            self._connect()

    def _connect(self):
        self._poll_timer.stop()
        if self.worker:
            self.worker.stop()
            self.worker.deleteLater()
            self.worker = None
        self.source_model.set_local_node_id("")
        self.source_model.clear_all_nodes()
        # FIX-8: reseta contador sem interferência do filtro
        self.node_count_label.setText("Nós: 0"); self.node_count_label.setTextFormat(2)
        self.map_widget.clear_active_node(); self.map_widget.update_map([], "")
        self._init_worker()

    def _on_reboot_required(self):
        """Chamado após guardar configurações — desliga e abre o diálogo de espera."""
        # Pára o poll imediatamente
        self._poll_timer.stop()

        # Desliga worker de forma segura (o nó pode já estar a reiniciar)
        if self.worker:
            try:
                self.worker.stop()
            except Exception as e:
                logger.debug(f"_on_reboot_required worker.stop: {e}")
            try:
                self.worker.deleteLater()
            except Exception:
                pass
            self.worker = None

        # Limpa UI
        self.config_tab.clear_interface()
        self.source_model.clear_all_nodes()
        self.node_count_label.setText("Nós: 0"); self.node_count_label.setTextFormat(2)
        self.map_widget.clear_active_node(); self.map_widget.update_map([], "")
        self.local_node_label.setText("Nó local: —")
        self.source_model.set_local_node_id("")
        self.proxy_model.set_local_node_id("")
        self._on_connection_changed(False)

        # Abre diálogo de espera — modal, bloqueia até reconectar
        dlg = RebootWaitDialog(self)
        dlg.reconnect_requested.connect(self._connect)
        dlg.exec_()

    def _disconnect(self):
        self._poll_timer.stop()
        if self.worker:
            self.worker.stop()
        self.config_tab.clear_interface()
        self.source_model.clear_all_nodes()
        self.node_count_label.setText("Nós: 0"); self.node_count_label.setTextFormat(2)
        self.map_widget.clear_active_node(); self.map_widget.update_map([], "")
        self.local_node_label.setText("Nó local: —")
        self.source_model.set_local_node_id("")
        self.proxy_model.set_local_node_id("")
        self._on_connection_changed(False)

    def _init_worker(self):
        self.worker = MeshtasticWorker(hostname=self._hostname, port=self._port)
        self.worker.connection_changed.connect(self._on_connection_changed)
        self.worker.node_updated.connect(self._on_node_updated)
        self.worker.nodes_batch.connect(self._on_nodes_batch)
        self.worker.error_occurred.connect(self._on_worker_error)
        self.worker.dm_sent.connect(self._on_dm_sent)
        self.worker.channel_message_sent.connect(self._on_channel_sent)
        self.worker.message_status_updated.connect(self.messages_tab.update_message_status)
        self.worker.message_received.connect(self.messages_tab.add_message)
        self.worker.nodedb_reset.connect(self._on_nodedb_reset)
        self.worker.channels_updated.connect(self.messages_tab.update_channels)
        # FIX-4: my_node_id_ready é o primeiro sinal — bloqueia inserção do nó local
        self.worker.my_node_id_ready.connect(self._on_my_node_id_ready)
        self.worker.local_node_ready.connect(self._on_local_node_ready)
        self.worker.interface_ready.connect(self.config_tab.set_interface)
        self.worker.traceroute_result.connect(self._on_traceroute_result)
        self.source_model.node_inserted.connect(self.messages_tab._refresh_dm_list)
        self.worker.start()

        QTimer.singleShot(2000, self._check_connection_state)

    def _check_connection_state(self):
        if self.worker and self.worker.iface is not None:
            try:
                is_conn = getattr(self.worker.iface, 'isConnected', None)
                if callable(is_conn):
                    connected = is_conn()
                elif is_conn is not None:
                    connected = bool(is_conn)
                else:
                    connected = (hasattr(self.worker.iface, 'nodes')
                                 and self.worker.iface.nodes is not None)
                if connected:
                    self._on_connection_changed(True)
                    if self.messages_tab.channel_list.count() == 0:
                        self.worker._attempt_load_channels(retry_count=0)
            except Exception as e:
                logger.debug(f"_check_connection_state: {e}")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_connection_changed(self, connected: bool):
        if connected:
            host = f"{self._hostname}:{self._port}"
            self.conn_indicator.setText(f"🟢  {host}")
            self.conn_indicator.setStyleSheet(
                f"color:{ACCENT_GREEN};font-weight:bold;font-size:12px;"
                f"background:{PANEL_BG};padding:4px 12px;"
                f"border:1px solid {ACCENT_GREEN};border-radius:12px;"
            )
            self.act_send_nodeinfo.setEnabled(True)
            self.act_reset_nodedb.setEnabled(True)
            self.act_send_position.setEnabled(True)
            self._poll_timer.start()
        else:
            self._poll_timer.stop()
            self.conn_indicator.setText("🔴  Desconectado")
            self.conn_indicator.setStyleSheet(
                f"color:{ACCENT_RED};font-weight:bold;font-size:12px;"
                f"background:{PANEL_BG};padding:4px 12px;"
                f"border:1px solid {ACCENT_RED};border-radius:12px;"
            )
            self.act_send_nodeinfo.setEnabled(False)
            self.act_reset_nodedb.setEnabled(False)
            self.act_send_position.setEnabled(False)

    # FIX-4: slot dedicado para bloqueio precoce do nó local
    def _on_my_node_id_ready(self, node_id: str):
        """
        Primeiro sinal após ligação — configura filtros ANTES de qualquer batch.
        Usa também o nodeNum inteiro para bloqueio mais robusto (FIX-4).
        """
        node_num = None
        if self.worker and self.worker.iface and self.worker.iface.localNode:
            node_num = self.worker.iface.localNode.nodeNum
        self.source_model.set_local_node_id(node_id, node_num)
        self.proxy_model.set_local_node_id(node_id)
        self.messages_tab.set_my_node_id(node_id)
        logger.info(f"Nó local registado: id={node_id} num={node_num}")

    def _poll_nodedb(self):
        """FIX-5: polling como safety-net — não redesenha se nada mudou."""
        if self.worker and self.worker._connected:
            try:
                self.worker._sync_nodedb()
            except Exception as e:
                logger.debug(f"Erro no poll NodeDB: {e}")

    def _on_nodes_batch(self, batch: list):
        if not batch:
            return
        new_nodes = []
        for num, node in batch:
            user       = node.get('user', {})
            nid        = user.get('id') or f"!{num:08x}"
            pos        = node.get('position', {})
            lat_i      = pos.get('latitudeI')
            lon_i      = pos.get('longitudeI')
            last_heard = node.get('lastHeard')
            if last_heard:
                try:
                    last_heard = datetime.fromtimestamp(last_heard)
                except Exception:
                    last_heard = None
            data = {
                "id_num":        num,
                "long_name":     user.get('longName', ''),
                "short_name":    user.get('shortName', ''),
                "last_heard":    last_heard,
                "snr":           node.get('snr'),
                "hops_away":     node.get('hopsAway'),
                "via_mqtt":      node.get('viaMqtt'),
                "latitude":      lat_i / 1e7 if lat_i is not None else None,
                "longitude":     lon_i / 1e7 if lon_i is not None else None,
                "altitude":      pos.get('altitude'),
                "battery_level": node.get('deviceMetrics', {}).get('batteryLevel'),
                "hw_model":      user.get('hwModel', ''),
                "public_key":    user.get('publicKey', ''),
            }
            was_new = self.source_model.update_node_silent(nid, data)
            if was_new:
                new_nodes.append((nid, data))

        # Injecta favoritos ausentes do NodeDB em passagem única
        node_idx = self.source_model._node_index
        for fav_data in _FAVORITES.get_all_nodes_data():
            fav_id = fav_data.get("id_string")
            if fav_id and node_idx.get(fav_id) is None:
                self.source_model.update_node_silent(fav_id, fav_data)

        self.source_model.refresh_all()
        self.proxy_model.invalidateFilter()
        self._update_node_count()

        for nid, data in new_nodes:
            self.messages_tab.update_node_name(
                nid, data["long_name"], data["short_name"], data["public_key"]
            )

        if self.tab_widget.currentIndex() == 1:
            self._map_debounce.start()

    def _on_node_updated(self, node_id_string: str, node_data: dict, packet):
        self.source_model.update_node(node_id_string, node_data, packet)
        self._update_node_count()
        # Marca o nó como activo (vermelho no mapa) se veio de um pacote real
        if packet is not None:
            self.map_widget.mark_node_active(node_id_string)
            # Garante redesenho do mapa para mostrar cor vermelha
            if self.tab_widget.currentIndex() == 1:
                self._map_debounce.start()
        self.messages_tab.update_node_name(
            node_id_string,
            node_data.get("long_name", ""),
            node_data.get("short_name", ""),
            node_data.get("public_key", "")
        )
        if _FAVORITES.is_favorite(node_id_string):
            _FAVORITES.update_node_data(node_id_string, node_data)
        local_id = getattr(self, '_local_node_id_str', None)
        if local_id and node_id_string == local_id:
            has_pos = (node_data.get('latitude') is not None or
                       node_data.get('longitude') is not None)
            if has_pos:
                self._update_local_node_label(True)
        if self.tab_widget.currentIndex() == 1:
            self._map_debounce.start()  # debounce: reagrupa updates rápidos

    def _on_worker_error(self, message: str):
        QMessageBox.critical(self, "Erro no Meshtastic", message)

    def _on_local_node_ready(self, long_name: str, short_name: str, node_id: str,
                             gps_enabled: bool, has_position: bool):
        self._local_long_name  = long_name
        self._local_short_name = short_name
        self._local_node_id_str = node_id
        self._local_gps_enabled = gps_enabled
        self._update_local_node_label(has_position)

    def _update_local_node_label(self, has_position: bool):
        long_name   = getattr(self, '_local_long_name',   '')
        short_name  = getattr(self, '_local_short_name',  '')
        node_id     = getattr(self, '_local_node_id_str', '')
        gps_enabled = getattr(self, '_local_gps_enabled', False)

        if gps_enabled and has_position:
            gps_icon = "📍"
            gps_tip  = "GPS activo com posição conhecida"
        elif gps_enabled and not has_position:
            gps_icon = "🔍"
            gps_tip  = "GPS activo mas posição ainda não disponível"
        else:
            gps_icon = "📵"
            gps_tip  = "GPS desactivado"

        parts = []
        if long_name:  parts.append(long_name)
        if short_name: parts.append(f"[{short_name}]")
        if node_id:    parts.append(node_id)
        parts.append(gps_icon)
        label_text = "  🏠  " + "  ·  ".join(parts) if parts else "Nó local: —"
        self.local_node_label.setText(label_text)
        self.local_node_label.setToolTip(
            f"Nó local  ·  {long_name} [{short_name}]  ·  {node_id}\nGPS: {gps_tip}"
        )

    def _on_search_text_changed(self, text: str):
        self.proxy_model.set_filter_text(text)
        self.messages_tab.set_filter_text(text)
        # FIX-8: contador NÃO muda com pesquisa — reflecte sempre o total real
        if self.tab_widget.currentIndex() == 1:
            self._refresh_map()

    def _on_double_click(self, index):
        col = index.column()
        if col in (NodeTableModel.COL_FAV, NodeTableModel.COL_DM, NodeTableModel.COL_MAP):
            return
        row  = self.proxy_model.mapToSource(index).row()
        node = self.source_model.get_node_data(row)
        if node:
            PacketDetailDialog(node, self).exec_()

    def _on_table_clicked(self, index):
        row  = self.proxy_model.mapToSource(index).row()
        node = self.source_model.get_node_data(row)
        if not node:
            return
        node_id = node.get("id_string", "")
        col     = index.column()

        if col == NodeTableModel.COL_FAV:
            # Toggle favorito — guarda dados completos do nó
            _FAVORITES.toggle(node_id, node)
            self.source_model.refresh_all()
            self.proxy_model.invalidate()

        elif col == NodeTableModel.COL_DM:
            # Só activo se nó já contactado
            if node_id and isinstance(node.get("last_heard"), datetime):
                self.tab_widget.setCurrentIndex(2)
                self.messages_tab.activate_dm_for_node(node_id)

        elif col == NodeTableModel.COL_MAP:
            has_gps = (node.get('latitude') is not None and node.get('longitude') is not None)
            if has_gps:
                self._highlight_node_on_map(node_id, node)
            else:
                QMessageBox.information(
                    self, "Sem Posição",
                    f"O nó {node.get('long_name') or node_id} não tem dados de geolocalização."
                )

        elif col == NodeTableModel.COL_TRACEROUTE:
            if node_id and self.worker and self.worker._connected:
                # Bloqueia novo envio enquanto countdown de traceroute anterior está activo
                if self._countdown_seconds > 0:
                    QMessageBox.information(
                        self, "Traceroute em curso",
                        f"Aguarde {self._countdown_seconds}s até o traceroute anterior terminar."
                    )
                    return
                name = node.get('long_name') or node_id

                # Verifica se já existe um traceroute para este destino na lista
                local_id = getattr(self, '_local_node_id_str', None) or ''
                existing = next(
                    (rec for rec in self.map_widget._tr_records
                     if (rec.get('origin_id') == local_id and rec.get('dest_id') == node_id)
                     or (rec.get('origin_id') == node_id and rec.get('dest_id') == local_id)),
                    None
                )
                if existing:
                    reply = QMessageBox.question(
                        self, "Traceroute já existente",
                        f"Já existe um traceroute para {name} na lista.\n\n"
                        f"Deseja enviar um novo traceroute mesmo assim?",
                        QMessageBox.Yes | QMessageBox.Cancel,
                        QMessageBox.Cancel,
                    )
                    if reply != QMessageBox.Yes:
                        return

                self._pending_traceroute_dest = (node_id, name)
                self.worker.send_traceroute(node_id)
                self._show_countdown_message(
                    f"📡 Traceroute enviado para {name} — aguardando resposta…", 30
                )
            elif not self.worker or not self.worker._connected:
                QMessageBox.warning(self, "Desconectado",
                                    "Conecte-se primeiro para enviar traceroute.")

    def _on_traceroute_result(self, forward_edges: list, back_edges: list,
                              origin_id: str, dest_id: str):
        all_nodes = self.source_model.get_all_nodes()
        node_idx  = {n.get("id_string", ""): n for n in all_nodes}

        def resolve_name(nid):
            n  = node_idx.get(nid)
            if not n:
                return nid
            ln = (n.get("long_name") or "").strip()
            sn = (n.get("short_name") or "").strip()
            return f"{ln} [{sn}]" if ln else nid

        def has_coords(nid):
            n = node_idx.get(nid)
            return bool(n and n.get("latitude") is not None and n.get("longitude") is not None)

        # ── Detecta traceroutes iniciados pelo nó local ──────────────────
        # origin_id = quem fez o pedido (packet['to'])
        # dest_id   = quem respondeu   (packet['from'])
        # Para ser "nosso", a origem DEVE ser o nó local e o destino DEVE
        # ser o nó para o qual enviámos o pedido.
        my_id   = getattr(self, '_local_node_id_str', None)
        pending = self._pending_traceroute_dest
        is_mine = False
        if pending and my_id:
            pending_id, _ = pending
            # Normaliza para comparação case-insensitive
            if (origin_id.lower() == my_id.lower() and
                    dest_id.lower() == pending_id.lower()):
                is_mine = True
                self._pending_traceroute_dest = None

        if not is_mine:
            # Traceroute enviado por outro nó — pergunta se o utilizador quer ver
            origin_name = resolve_name(origin_id)
            dest_name   = resolve_name(dest_id)
            reply = QMessageBox.question(
                self,
                "Traceroute de terceiro recebido",
                f"Foi recebido um traceroute entre:\n\n"
                f"  Origem:  {origin_name}\n"
                f"  Destino: {dest_name}\n\n"
                "Deseja visualizar o resultado?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        origin_name  = resolve_name(origin_id)
        dest_name    = resolve_name(dest_id)
        total_links  = len(forward_edges) + len(back_edges)
        self._show_countdown_message(
            f"📡 Traceroute: {origin_name} → {dest_name}  ({total_links} links)", 30
        )

        if not forward_edges and not back_edges:
            QMessageBox.information(self, "Traceroute", "Resposta recebida mas sem rota.")
            return

        def build_section(edges, label):
            if not edges:
                return []
            lines = [f"  {label}:"]
            for i, (a_id, b_id, snr) in enumerate(edges):
                snr_str = f"{snr:+.1f} dB" if snr != 0.0 else "SNR desconhecido"
                ca = "📍" if has_coords(a_id) else "❓"
                cb = "📍" if has_coords(b_id) else "❓"
                lines.append(
                    f"    Hop {i+1}/{len(edges)}: {ca}{resolve_name(a_id)}"
                    f"  →  {cb}{resolve_name(b_id)}  [{snr_str}]"
                )
            return lines

        body = (
            f"Origem:     {origin_name}\n"
            f"Destino:    {dest_name}\n"
            f"Hops ida:   {len(forward_edges)}\n"
            f"Hops volta: {len(back_edges)}\n\n"
            + "\n".join(
                build_section(forward_edges, "Rota de ida  (origem → destino)") +
                build_section(back_edges,    "Rota de volta (destino → origem)")
            )
        )

        def any_drawable(edges):
            return any(has_coords(a) or has_coords(b) for a, b, _ in edges)
        # Mostra "Mostrar no Mapa" apenas se o nó destino tiver coordenadas
        # (sem GPS no destino a rota no mapa fica incompleta e sem utilidade)
        can_show_map = has_coords(dest_id) and (any_drawable(forward_edges) or any_drawable(back_edges))

        dlg = QDialog(self)
        dlg.setWindowTitle("Resultado do Traceroute")
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setSpacing(10)
        dlg_layout.setContentsMargins(16, 14, 16, 14)

        lbl_title = QLabel(f"🔍  {origin_name}  →  {dest_name}")
        lbl_title.setStyleSheet(f"color:{ACCENT_GREEN};font-size:13px;font-weight:bold;")
        dlg_layout.addWidget(lbl_title)

        legend = QLabel(
            "📍 com localização  ❓ sem localização"
        )
        legend.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        dlg_layout.addWidget(legend)

        font_mono = QFont("Menlo", 11) if sys.platform == "darwin" else QFont("Consolas", 10)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setFont(font_mono)
        te.setPlainText(body)
        te.setStyleSheet(
            f"background:{PANEL_BG};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;padding:6px;"
        )
        te.setLineWrapMode(QTextEdit.NoWrap)

        # Calcula dimensões exactas para mostrar todo o conteúdo sem scroll
        fm        = te.fontMetrics()
        n_lines   = body.count('\n') + 1
        max_chars = max((len(l) for l in body.splitlines()), default=60)
        char_w    = fm.averageCharWidth()
        line_h    = fm.height() + 2          # +2 px de espaçamento entre linhas
        need_w    = char_w * (max_chars + 4) + 40   # margem interna + scrollbar
        need_h    = line_h * n_lines + 24            # padding interno
        dlg_w     = max(560, min(need_w, 1200))
        dlg_h     = max(240, min(need_h, 800))       # limita a 800 px de ecrã
        te.setMinimumWidth(dlg_w - 40)
        te.setMinimumHeight(dlg_h)
        te.setMaximumHeight(dlg_h)
        dlg.resize(dlg_w, dlg_h + 100)   # +100 para título + legenda + botões

        dlg_layout.addWidget(te)

        btn_row = QHBoxLayout()
        if can_show_map:
            btn_map = QPushButton("🗺  Mostrar no Mapa")
            _fwd   = list(forward_edges)
            _bck   = list(back_edges)
            _nodes = list(all_nodes)
            _oid   = origin_id
            _did   = dest_id
            _on    = origin_name
            _dn    = dest_name
            def _show_on_map():
                self.map_widget.show_traceroute_on_map(
                    _fwd, _bck, _nodes, _oid, _did, _on, _dn)
                self.tab_widget.setCurrentIndex(1)
                dlg.accept()
            btn_map.clicked.connect(_show_on_map)
            btn_row.addWidget(btn_map)
        else:
            lbl_no_map = QLabel("⚠ Nenhum nó da rota tem localização — mapa indisponível.")
            lbl_no_map.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
            btn_row.addWidget(lbl_no_map)

        btn_row.addStretch()
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        dlg_layout.addLayout(btn_row)

        dlg.exec_()

    def _on_node_deselected(self):
        self._selected_node_id = None
        self.source_model.set_selected_highlight(None)

    def _highlight_node_on_map(self, node_id: str, node: dict):
        self._selected_node_id = node_id
        self.source_model.set_selected_highlight(node_id)
        self.map_widget.set_selected_node(node_id)
        self._refresh_map()
        QTimer.singleShot(800, lambda: self.map_widget.clear_auto_pan())
        self.tab_widget.setCurrentIndex(1)

    def _on_tab_changed(self, index):
        if index == 1:
            self._refresh_map()

    def _update_node_count(self):
        """Actualiza o label com total de nós e quantos estão online (<2h)."""
        total  = self.source_model.get_visible_count()
        online = self.source_model.get_online_count()
        self.node_count_label.setTextFormat(2)   # Qt.RichText
        self.node_count_label.setText(
            f"Nós: {total}&nbsp;&nbsp;"
            f"<span style='color:#39d353;font-weight:bold'>⬤ {online} online</span>"
        )

    def _show_console_window(self):
        """Abre/mostra a janela de consola de logs (não-bloqueante)."""
        self._console_window.show()
        self._console_window.raise_()
        self._console_window.activateWindow()

    def _refresh_map(self):
        # O mapa mostra nós com last_heard válido (mesma regra da lista),
        # incluindo o nó local — útil para desenhar linhas de traceroute
        all_nodes = [
            n for n in self.source_model.get_all_nodes()
            if isinstance(n.get("last_heard"), datetime)
        ]
        self.map_widget.update_map(all_nodes)

    def _on_send_channel_message(self, channel_index: int, text: str):
        if self.worker:
            self.worker.send_message(channel_index, text)

    def _on_send_direct_message(self, dest_id: str, text: str):
        if self.worker:
            self.worker.send_direct_message(dest_id, text)

    def _on_reset_nodedb(self):
        reply = QMessageBox.question(
            self, "Reset NodeDB",
            "Apagar o NodeDB do nó local?\n\nTodos os nós conhecidos serão removidos do firmware.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes and self.worker:
            self.act_reset_nodedb.setEnabled(False)
            self.worker.reset_nodedb()

    def _on_nodedb_reset(self):
        self.source_model.clear_all_nodes()
        self.node_count_label.setText("Nós: 0"); self.node_count_label.setTextFormat(2)
        self.map_widget.clear_active_node(); self.map_widget.update_map([], "")
        self.act_reset_nodedb.setEnabled(True)

    def _show_countdown_message(self, msg: str, seconds: int):
        self._countdown_seconds  = seconds
        self._countdown_base_msg = msg
        self._countdown_timer.stop()
        self._update_countdown_bar()
        self._countdown_timer.start()

    def _on_countdown_tick(self):
        self._countdown_seconds -= 1
        if self._countdown_seconds <= 0:
            self._countdown_timer.stop()
            self.statusBar().clearMessage()
        else:
            self._update_countdown_bar()

    def _update_countdown_bar(self):
        self.statusBar().showMessage(
            f"{self._countdown_base_msg}  [{self._countdown_seconds}s]"
        )

    def _on_send_nodeinfo(self):
        if self.worker:
            self.act_send_nodeinfo.setEnabled(False)
            self.worker.send_node_info()
            self.statusBar().showMessage("📡 Info do Nó enviada para a rede.", 5000)
            QTimer.singleShot(3000, lambda: self.act_send_nodeinfo.setEnabled(True))

    def _on_send_position(self):
        if not self.worker:
            return
        # Liga o sinal de resultado (uma só vez por chamada) antes de disparar
        def _on_result(ok: bool, msg: str):
            try:
                self.worker.position_sent.disconnect(_on_result)
            except Exception:
                pass
            self.act_send_position.setEnabled(True)
            if ok:
                self.statusBar().showMessage(msg, 6000)
            else:
                # Falha real — mostra diálogo de erro (não só na barra)
                self.statusBar().clearMessage()
                QMessageBox.warning(self, "Envio de Posição", msg)

        self.act_send_position.setEnabled(False)
        self.worker.position_sent.connect(_on_result)
        self.worker.send_position()

    def _on_dm_sent(self, dest_id: str, text: str, pki: bool, packet_id: int):
        self.messages_tab.add_outgoing_dm(dest_id, text, pki=pki, packet_id=packet_id)

    def _on_channel_sent(self, channel_index: int, text: str, packet_id: int):
        self.messages_tab.add_outgoing_channel_message(channel_index, text, packet_id=packet_id)

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        event.accept()


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    app.setApplicationName("Meshtastic Monitor")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()