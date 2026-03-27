#!/usr/bin/env python3
"""
main.py — Ponto de entrada da aplicação Meshtastic Monitor.
Instancia a MainWindow e inicia o loop Qt.

Uso:
    python3 main.py
    # ou dentro da pasta meshtastic_monitor/:
    python3 -m meshtastic_monitor.main
"""
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, QByteArray, QSettings
from i18n import tr
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTableView, QHeaderView, QSplitter, QFrame,
    QTabWidget, QSizePolicy, QMessageBox, QDialog, QAction, QMenuBar,
    QAbstractItemView, QPushButton, QTextEdit
)
from PyQt5.QtGui import QFont, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

from constants import (
    logger, APP_STYLESHEET, APP_VERSION, APP_NAME, DARK_BG, PANEL_BG, BORDER_COLOR,
    ACCENT_GREEN, ACCENT_BLUE, ACCENT_ORANGE, ACCENT_RED, ACCENT_PURPLE,
    TEXT_PRIMARY, TEXT_MUTED, INPUT_BG, HOVER_BG
)
from models import (
    NodeTableModel, NodeFilterProxyModel, _FAVORITES
)
from worker import MeshtasticWorker
from dialogs import ConnectionDialog, ConsoleWindow, RebootWaitDialog, PacketDetailDialog
from tabs.tab_nodes import MapWidget
from tabs.tab_messages import MessagesTab
from tabs.tab_config import ConfigTab
from tabs.tab_metrics import MetricsTab

def _play_notification_sound():
    """Toca som de notificação cross-platform.
    Tenta em cascata: aplay (ALSA/Linux) → paplay (PulseAudio) →
    afplay (macOS) → winsound (Windows) → QApplication.beep() (fallback).
    """
    import sys, subprocess
    if sys.platform.startswith("linux"):
        # Gera tom de 880 Hz por 200ms via aplay (ALSA — funciona no uConsole)
        try:
            import struct, math
            rate = 22050
            freq = 880
            dur  = 0.2
            n    = int(rate * dur)
            # WAV header + PCM mono 16-bit
            pcm  = bytes(struct.pack('<h', int(32767 * math.sin(2 * math.pi * freq * i / rate)))
                         for i in range(n))
            # RIFF header
            data_size = len(pcm)
            header = struct.pack('<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + data_size, b'WAVE',
                b'fmt ', 16, 1, 1, rate, rate * 2, 2, 16,
                b'data', data_size)
            wav = header + pcm
            subprocess.Popen(
                ['aplay', '-q', '-'],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            ).communicate(wav)
            return
        except Exception:
            pass
        # Fallback: paplay com ficheiro de som do sistema
        for cmd in [
            ['paplay', '/usr/share/sounds/freedesktop/stereo/message.oga'],
            ['paplay', '/usr/share/sounds/ubuntu/stereo/message-new-instant.ogg'],
        ]:
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                continue
    elif sys.platform == "darwin":
        try:
            subprocess.Popen(['afplay', '/System/Library/Sounds/Tink.aiff'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    elif sys.platform == "win32":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
            return
        except Exception:
            pass
    # Último recurso: beep Qt (pode não funcionar em todos os sistemas)
    try:
        from PyQt5.QtWidgets import QApplication
        QApplication.beep()
    except Exception:
        pass


class MainWindow(QMainWindow):
    # Índices das abas — alterar aqui se a ordem mudar
    TAB_NODES    = 0
    TAB_MESSAGES = 1
    TAB_MAP      = 2
    TAB_METRICS  = 3
    TAB_CONFIG   = 4

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

        # Indicador permanente de SNR/pacotes na status bar (canto direito)
        self._stats_label = QLabel("📶 —")
        self._stats_label.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;padding:0 8px;"
        )
        self._stats_label.setToolTip(tr("SNR tooltip"))
        self.statusBar().addPermanentWidget(self._stats_label)

        # Contador de pacotes para calcular pkt/min
        self._pkt_timestamps: list = []

        # Idioma — carrega preferência guardada (default: English)
        _qs = QSettings("CT7BRA", "MeshtasticMonitor")
        _saved_lang = _qs.value("language", "en")
        from i18n import set_language as _set_lang
        _set_lang(_saved_lang)

        # Som — persiste entre sessões via QSettings
        self._sound_enabled = _qs.value("sound_enabled", True, type=bool)
        self._countdown_seconds  = 0
        self._countdown_base_msg = ""
        self._countdown_timer    = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

        # Reconexão automática — contagem regressiva na status bar
        self._reconnect_seconds  = 0
        self._reconnect_attempt  = 0
        self._reconnect_bar_timer = QTimer(self)
        self._reconnect_bar_timer.setInterval(1000)
        self._reconnect_bar_timer.timeout.connect(self._on_reconnect_tick)

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
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1440, 760)

        menu_bar = self.menuBar()

        self._conn_menu   = menu_bar.addMenu(tr("🔌  Conexão"))
        conn_menu = self._conn_menu

        self._act_connect = QAction(tr("🔌  Conectar…"), self)
        self._act_connect.setShortcut("Ctrl+K")
        self._act_connect.triggered.connect(self._open_connection_dialog)
        conn_menu.addAction(self._act_connect)

        conn_menu.addSeparator()

        self._act_disconnect = QAction(tr("⏹  Desconectar"), self)
        self._act_disconnect.triggered.connect(self._disconnect)
        conn_menu.addAction(self._act_disconnect)

        self._node_menu   = menu_bar.addMenu(tr("📡  Nó"))
        node_menu = self._node_menu

        self.act_send_nodeinfo = QAction(tr("📡  Enviar Info do Nó"), self)
        self.act_send_nodeinfo.setShortcut("Ctrl+I")
        self.act_send_nodeinfo.setEnabled(False)
        self.act_send_nodeinfo.triggered.connect(self._on_send_nodeinfo)
        node_menu.addAction(self.act_send_nodeinfo)

        node_menu.addSeparator()

        self.act_send_position = QAction(tr("📍  Enviar Posição Manual"), self)
        self.act_send_position.setShortcut("Ctrl+P")
        self.act_send_position.setEnabled(False)
        self.act_send_position.triggered.connect(self._on_send_position)
        node_menu.addAction(self.act_send_position)

        self._config_menu = menu_bar.addMenu(tr("🔧  Ferramentas"))
        config_menu = self._config_menu

        self.act_reset_nodedb = QAction(tr("🗑  Reset NodeDB"), self)
        self.act_reset_nodedb.setEnabled(False)
        self.act_reset_nodedb.triggered.connect(self._on_reset_nodedb)
        config_menu.addAction(self.act_reset_nodedb)

        config_menu.addSeparator()

        self._act_console = QAction(tr("🖥  Consola de logs…"), self)
        self._act_console.setShortcut("Ctrl+L")
        self._act_console.triggered.connect(self._show_console_window)
        config_menu.addAction(self._act_console)

        config_menu.addSeparator()

        self.act_sound = QAction(tr("🔔  Som em nova mensagem"), self)
        self.act_sound.setCheckable(True)
        self.act_sound.setChecked(True)    # default: ligado
        self.act_sound.setToolTip(tr("Activa beep do sistema ao receber mensagem não lida"))
        self.act_sound.toggled.connect(self._on_sound_toggled)
        config_menu.addAction(self.act_sound)

        # ── Menu Sobre ─────────────────────────────────────────────────────
        self._about_menu  = menu_bar.addMenu(tr("ℹ️  Sobre"))
        about_menu = self._about_menu
        self._act_info = QAction(tr("📋  Sobre Meshtastic Monitor"), self)
        self._act_info.triggered.connect(self._show_about_dialog)
        about_menu.addAction(self._act_info)

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
        self.search_edit.setPlaceholderText(tr("Pesquisar por ID, nome longo ou curto…"))
        self.search_edit.setMinimumWidth(280)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        top.addWidget(self.search_edit)

        top.addStretch()

        # FIX-8: label do contador — actualizado por source_model.get_visible_count()
        self.node_count_label = QLabel(tr("Nós: {total}", total=0))
        self.node_count_label.setStyleSheet(
            f"color:{ACCENT_BLUE};font-weight:bold;font-size:13px;"
            f"background:{PANEL_BG};padding:4px 12px;"
            f"border:1px solid {BORDER_COLOR};border-radius:12px;"
        )
        self.node_count_label.setToolTip(tr("Total de nós na rede (excluindo o nó local)"))
        top.addWidget(self.node_count_label)

        self.conn_indicator = QLabel(tr("⚫  Desconectado"))
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
        self.tab_widget.addTab(self.list_tab, tr("📋  Lista de Nós"))
        self._setup_list_tab()

        self.messages_tab = MessagesTab()
        self.messages_tab.send_channel_message.connect(self._on_send_channel_message)
        self.messages_tab.send_direct_message.connect(self._on_send_direct_message)
        self.messages_tab.unread_message.connect(self._on_messages_unread)
        self.messages_tab.set_node_choices_provider(
            lambda: self.source_model.get_node_choices()
        )
        self.tab_widget.addTab(self.messages_tab, tr("💬  Mensagens"))

        self.map_tab = QWidget()
        self.tab_widget.addTab(self.map_tab, tr("🗺  Mapa"))
        self._setup_map_tab()

        self.metrics_tab = MetricsTab()
        self.tab_widget.addTab(self.metrics_tab, tr("📈 Métricas"))

        self.config_tab = ConfigTab()
        self.config_tab.reboot_required.connect(self._on_reboot_required)
        self.tab_widget.addTab(self.config_tab, tr("⚙ Configurações"))

    def _refresh_hint_bar(self):
        """Rebuilds the hint bar label with the current language."""
        if not hasattr(self, '_hint_label'):
            return
        txt = (
            tr("hint_bar")
            + tr("Duplo clique → Detalhes") + "  &nbsp;&nbsp;|&nbsp;&nbsp;"
            + f"<span style='color:#f5c518;'>{tr('hint_fav')}</span>"
            + f"<span style='color:#8b949e;'>{tr('hint_nofav')}</span>"
        )
        self._hint_label.setText(txt)

    def _setup_list_tab(self):
        layout = QVBoxLayout(self.list_tab)
        layout.setContentsMargins(0, 8, 0, 0)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 0, 6, 4)
        self._hint_label = QLabel()
        self._refresh_hint_bar()
        hint = self._hint_label
        hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;padding:2px 0;")
        bar.addWidget(hint)
        bar.addStretch()
        self.local_node_label = QLabel(tr("Nó local: —"))
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
        all_nodes = self.source_model.get_all_nodes()
        node = next((n for n in all_nodes if n.get("id_string") == node_id), None)
        name = (node.get('long_name') or node_id) if node else node_id
        self._send_traceroute(node_id, name)

    # ------------------------------------------------------------------
    # Conexão / desconexão
    # ------------------------------------------------------------------
    def _open_connection_dialog(self):
        dlg = ConnectionDialog(self._hostname, self._port, self)
        dlg.language_changed.connect(self._on_language_changed)
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
        _FAVORITES.set_interface(None)
        self.source_model.set_local_node_id("")
        self.source_model.clear_all_nodes()
        # FIX-8: reseta contador sem interferência do filtro
        self.node_count_label.setText(tr("Nós: {total}", total=0)); self.node_count_label.setTextFormat(2)
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
        self.node_count_label.setText(tr("Nós: {total}", total=0)); self.node_count_label.setTextFormat(2)
        self.map_widget.clear_active_node(); self.map_widget.update_map([], "")
        self.local_node_label.setText(tr("Nó local: —"))
        self.source_model.set_local_node_id("")
        self.proxy_model.set_local_node_id("")
        self._on_connection_changed(False)

        # Abre diálogo de espera — modal, bloqueia até reconectar
        dlg = RebootWaitDialog(self)
        dlg.reconnect_requested.connect(self._connect)
        dlg.exec_()

    def _disconnect(self):
        self._poll_timer.stop()
        self._pkt_timestamps.clear()
        self._stats_label.setText("📶 —")
        _FAVORITES.set_interface(None)
        if self.worker:
            self.worker.stop()
        self.config_tab.clear_interface()
        self.source_model.clear_all_nodes()
        self.node_count_label.setText(tr("Nós: {total}", total=0)); self.node_count_label.setTextFormat(2)
        self.map_widget.clear_active_node(); self.map_widget.update_map([], "")
        self.local_node_label.setText(tr("Nó local: —"))
        self.source_model.set_local_node_id("")
        self.proxy_model.set_local_node_id("")
        self._on_connection_changed(False)

    def _init_worker(self):
        self.worker = MeshtasticWorker(hostname=self._hostname, port=self._port)
        self.worker.connection_changed.connect(self._on_connection_changed)
        self.worker.node_updated.connect(self._on_node_updated)
        self.worker.node_updated.connect(self._on_node_updated_metrics)
        self.worker.raw_packet_received.connect(
            lambda pkt: self.metrics_tab.ingest_raw_packet(pkt)
        )
        self.worker.raw_packet_received.connect(self._on_packet_stats)
        self.worker.nodes_batch.connect(self._on_nodes_batch)
        self.worker.error_occurred.connect(self._on_worker_error)
        self.worker.dm_sent.connect(self._on_dm_sent)
        self.worker.channel_message_sent.connect(self._on_channel_sent)
        self.worker.message_status_updated.connect(self.messages_tab.update_message_status)
        self.worker.message_status_updated.connect(
            lambda req_id, status, detail: self.metrics_tab.ingest_message_status(req_id, status)
        )
        self.worker.channel_message_sent.connect(
            lambda ch, text, pid: self.metrics_tab.ingest_message_sent(pid)
        )
        self.worker.dm_sent.connect(
            lambda dest, text, pki, pid: self.metrics_tab.ingest_message_sent(pid)
        )
        self.worker.message_received.connect(self.messages_tab.add_message)
        self.worker.nodedb_reset.connect(self._on_nodedb_reset)
        self.worker.channels_updated.connect(self.messages_tab.update_channels)
        # FIX-4: my_node_id_ready é o primeiro sinal — bloqueia inserção do nó local
        self.worker.my_node_id_ready.connect(self._on_my_node_id_ready)
        self.worker.local_node_ready.connect(self._on_local_node_ready)
        self.worker.interface_ready.connect(self.config_tab.set_interface)
        self.worker.traceroute_result.connect(self._on_traceroute_result)
        self.worker.neighbor_info_received.connect(
            lambda nid, nbs: self.map_widget.add_neighbor_info(nid, nbs)
        )
        self.worker.neighbor_info_received.connect(
            lambda nid, nbs: self.metrics_tab.ingest_neighbor_info(nid, nbs)
        )
        self.worker.reconnect_status.connect(self._on_reconnect_status)
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
            self.conn_indicator.setText(tr("🟢  {host}", host=host))
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
            self.conn_indicator.setText(tr("🔴  Desconectado"))
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
        logger.info(f"Local node registered: id={node_id} num={node_num}")

    def _poll_nodedb(self):
        """FIX-5: polling como safety-net — não redesenha se nada mudou."""
        if self.worker and self.worker._connected:
            try:
                self.worker._sync_nodedb()
            except Exception as e:
                logger.debug(f"NodeDB poll error: {e}")

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
            # lastHeard=0 significa "desconhecido" no NodeDB — não sobrescrever com datetime inválido
            last_heard_raw = node.get('lastHeard')
            last_heard = None
            if last_heard_raw:
                try:
                    last_heard = datetime.fromtimestamp(int(last_heard_raw))
                except Exception:
                    pass
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


        self.source_model.refresh_all()
        self.proxy_model.invalidateFilter()
        self._update_node_count()

        for nid, data in new_nodes:
            self.messages_tab.update_node_name(
                nid, data["long_name"], data["short_name"], data["public_key"]
            )

        if self.tab_widget.currentIndex() == self.TAB_MAP:
            self._map_debounce.start()

    def _on_node_updated(self, node_id_string: str, node_data: dict, packet):
        self.source_model.update_node(node_id_string, node_data, packet)
        self._update_node_count()
        # Marca o nó como activo (vermelho no mapa) se veio de um pacote real
        if packet is not None:
            self.map_widget.mark_node_active(node_id_string)
            # Garante redesenho do mapa para mostrar cor vermelha
            if self.tab_widget.currentIndex() == self.TAB_MAP:
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
                self._local_has_pos = True
                self._update_local_node_label(True)
        if self.tab_widget.currentIndex() == self.TAB_MAP:
            self._map_debounce.start()  # debounce: reagrupa updates rápidos

    def _on_node_updated_metrics(self, node_id_string: str, node_data: dict, packet):
        """Alimenta a MetricsTab com dados de cada pacote recebido."""
        if packet is not None:
            self.metrics_tab.ingest_packet(packet, node_data)
        # Regista posição GPS para cálculo de alcance de links
        lat = node_data.get('latitude')
        lon = node_data.get('longitude')
        if lat is not None and lon is not None:
            self.metrics_tab.ingest_node_position(node_id_string, lat, lon)

    def _on_worker_error(self, message: str):
        QMessageBox.critical(self, tr("Erro no Meshtastic"), message)

    def _sync_firmware_favorites(self):
        """Lê favoritos do firmware após ligação estabelecida."""
        if self.worker and self.worker.iface:
            _FAVORITES.set_interface(self.worker.iface)
            self.source_model.refresh_all()
            self.proxy_model.invalidateFilter()

    def _on_local_node_ready(self, long_name: str, short_name: str, node_id: str,
                             gps_enabled: bool, has_position: bool):
        self._local_long_name   = long_name
        self._local_short_name  = short_name
        self._local_node_id_str = node_id
        self._local_gps_enabled = gps_enabled
        self._local_has_pos     = has_position
        self._update_local_node_label(has_position)
        # Sincronizar favoritos do firmware (iface pronta neste ponto)
        QTimer.singleShot(500, self._sync_firmware_favorites)

        # Insere / actualiza o nó local na tabela para que fique sempre visível
        if node_id and self.worker and self.worker.iface:
            try:
                local_num  = self.worker.iface.localNode.nodeNum if self.worker.iface.localNode else None
                node_entry = {}
                if local_num and hasattr(self.worker.iface, 'nodesByNum'):
                    node_entry = self.worker.iface.nodesByNum.get(local_num, {})

                pos   = node_entry.get('position', {})
                lat_i = pos.get('latitudeI')
                lon_i = pos.get('longitudeI')
                user  = node_entry.get('user', {})
                last_heard_ts = node_entry.get('lastHeard')
                last_heard = None
                if last_heard_ts:
                    try:
                        last_heard = datetime.fromtimestamp(last_heard_ts)
                    except Exception:
                        pass

                local_data = {
                    "id_num":        local_num,
                    "long_name":     long_name or user.get('longName', ''),
                    "short_name":    short_name or user.get('shortName', ''),
                    "last_heard":    last_heard or datetime.now(),
                    "snr":           node_entry.get('snr'),
                    "hops_away":     0,   # nó local — 0 hops
                    "via_mqtt":      False,
                    "latitude":      lat_i / 1e7 if lat_i is not None else None,
                    "longitude":     lon_i / 1e7 if lon_i is not None else None,
                    "altitude":      pos.get('altitude'),
                    "battery_level": node_entry.get('deviceMetrics', {}).get('batteryLevel'),
                    "hw_model":      user.get('hwModel', ''),
                    "public_key":    user.get('publicKey', ''),
                    "last_packet_type": "LOCAL",
                }
                self.source_model.update_node(node_id, local_data)
                self.proxy_model.invalidateFilter()
                self._update_node_count()
                self.messages_tab.update_node_name(
                    node_id, local_data["long_name"], local_data["short_name"],
                    local_data["public_key"]
                )
                logger.info(f"Local node inserted in table: {node_id}")
            except Exception as e:
                logger.debug(f"Error inserting local node in table: {e}")

    def _update_local_node_label(self, has_position: bool):
        long_name   = getattr(self, '_local_long_name',   '')
        short_name  = getattr(self, '_local_short_name',  '')
        node_id     = getattr(self, '_local_node_id_str', '')
        gps_enabled = getattr(self, '_local_gps_enabled', False)

        if gps_enabled and has_position:
            gps_icon = "📍"
            gps_tip  = tr("GPS activo com posição conhecida")
        elif gps_enabled and not has_position:
            gps_icon = "🔍"
            gps_tip  = tr("GPS activo mas posição ainda não disponível")
        else:
            gps_icon = "📵"
            gps_tip  = tr("GPS desactivado")

        parts = []
        if long_name:  parts.append(long_name)
        if short_name: parts.append(f"[{short_name}]")
        if node_id:    parts.append(node_id)
        parts.append(gps_icon)
        label_text = "  🏠  " + "  ·  ".join(parts) if parts else tr("Nó local: —")
        self.local_node_label.setText(label_text)
        self.local_node_label.setToolTip(
            tr("nó local tooltip", long_name=long_name, short_name=short_name, node_id=node_id, gps_tip=gps_tip)
        )

    def _on_search_text_changed(self, text: str):
        self.proxy_model.set_filter_text(text)
        self.messages_tab.set_filter_text(text)
        # FIX-8: contador NÃO muda com pesquisa — reflecte sempre o total real
        if self.tab_widget.currentIndex() == self.TAB_MAP:
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
                self.tab_widget.setCurrentIndex(self.TAB_MESSAGES)
                self.messages_tab.activate_dm_for_node(node_id)

        elif col == NodeTableModel.COL_MAP:
            has_gps = (node.get('latitude') is not None and node.get('longitude') is not None)
            if has_gps:
                self._highlight_node_on_map(node_id, node)
            else:
                QMessageBox.information(
                    self, tr("Sem Posição"),
                    tr("O nó {name} não tem dados de geolocalização.", name=node.get('long_name') or node_id)
                )

        elif col == NodeTableModel.COL_TRACEROUTE:
            if node_id:
                name = node.get('long_name') or node_id
                self._send_traceroute(node_id, name)

    def _send_traceroute(self, node_id: str, name: str) -> None:
        """Valida pré-condições e envia traceroute para node_id.

        Centraliza toda a lógica partilhada entre o clique na tabela
        (_on_table_clicked) e o clique no popup do mapa
        (_on_map_traceroute_request), eliminando duplicação.

        Verifica, por ordem:
          1. Ligação activa ao daemon
          2. Countdown de traceroute anterior ainda em curso
          3. Traceroute duplicado já presente na lista (pede confirmação)
        """
        if not self.worker or not self.worker._connected:
            QMessageBox.warning(self, tr("Desconectado"),
                                tr("Conecte-se primeiro para enviar traceroute."))
            return

        if self._countdown_seconds > 0:
            QMessageBox.information(
                self, tr("Traceroute em curso"),
                tr("Aguarde {n}s até o traceroute anterior terminar.", n=self._countdown_seconds)
            )
            return

        local_id = getattr(self, '_local_node_id_str', None) or ''
        existing = next(
            (rec for rec in self.map_widget._tr_records
             if (rec.get('origin_id') == local_id and rec.get('dest_id') == node_id)
             or (rec.get('origin_id') == node_id and rec.get('dest_id') == local_id)),
            None
        )
        if existing:
            reply = QMessageBox.question(
                self, tr("Traceroute já existente"),
                tr("traceroute_existente_msg", name=name),
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return

        self._pending_traceroute_dest = (node_id, name)
        self.worker.send_traceroute(node_id)
        self._show_countdown_message(
            tr("📡 Traceroute enviado para {name} — aguardando resposta…", name=name), 30
        )

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
            # Traceroute directed at us from a remote node.
            # origin_id = packet['to'] = local node (we are the target)
            # dest_id   = packet['from'] = remote (who sent the traceroute to us)
            # Display: Origem = remote (who initiated), Destino = local (us)
            origin_name = resolve_name(origin_id)
            dest_name   = resolve_name(dest_id)
            notif_origem  = dest_name    # remote initiator
            notif_destino = origin_name  # local node (us)
            reply = QMessageBox.question(
                self,
                tr("Traceroute de terceiro recebido"),
                (tr("Foi recebido um traceroute direcionado ao nó local:\n\n")
                 + f"  {tr('Origem:')}  {notif_origem}\n"
                 + f"  {tr('Destino:')} {notif_destino}\n\n"
                 + tr("Deseja visualizar o resultado?")),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        origin_name  = resolve_name(origin_id)
        dest_name    = resolve_name(dest_id)
        total_links  = len(forward_edges) + len(back_edges)
        self._show_countdown_message(
            tr("traceroute_status", origin=origin_name, dest=dest_name, n=total_links), 30
        )

        if not forward_edges and not back_edges:
            QMessageBox.information(self, "Traceroute", tr("Resposta recebida mas sem rota."))
            return

        def build_section(edges, label):
            if not edges:
                return []
            lines = [f"  {label}:"]
            for i, (a_id, b_id, snr) in enumerate(edges):
                snr_str = f"{snr:+.1f} dB" if snr != 0.0 else tr("SNR desconhecido")
                ca = "📍" if has_coords(a_id) else "❓"
                cb = "📍" if has_coords(b_id) else "❓"
                hop_lbl = tr("Hop")
                lines.append(
                    f"    {hop_lbl} {i+1}/{len(edges)}: {ca}{resolve_name(a_id)}"
                    f"  →  {cb}{resolve_name(b_id)}  [{snr_str}]"
                )
            return lines

        # Display logic:
        # is_mine=True  (we sent):     Origem=local,  Destino=remote
        # is_mine=False (we received): Origem=remote, Destino=local
        # In the protocol packet: origin_id=packet['to']=local when is_mine=True,
        # and origin_id=packet['to']=remote when is_mine=False.
        if is_mine:
            # We initiated: local is origin, remote is destination
            lbl_a     = tr("Origem:")
            lbl_b     = tr("Destino:")
            name_a    = origin_name   # local node
            name_b    = dest_name     # remote
            fwd_label = tr("Rota de ida") + "  (" + tr("origem") + " → " + tr("destino") + ")"
            bck_label = tr("Rota de volta") + " (" + tr("destino") + " → " + tr("origem") + ")"
        else:
            # We received: remote is origin, local is destination
            lbl_a     = tr("Origem:")
            lbl_b     = tr("Destino:")
            name_a    = dest_name     # remote (packet['from'] = who sent the traceroute to us)
            name_b    = origin_name   # local node (packet['to'] = us)
            fwd_label = tr("Rota de ida") + "  (" + tr("origem") + " → " + tr("destino") + ")"
            bck_label = tr("Rota de volta") + " (" + tr("destino") + " → " + tr("origem") + ")"

        # For received traceroutes, swap which edges are "ida" vs "volta":
        # forward_edges in protocol = local→remote (origin_id→dest_id)
        # When received: display origem=remote, destino=local
        # So protocol's "forward" (local→remote) = display "volta" (destino→origem)
        # And protocol's "back" (remote→local)   = display "ida"   (origem→destino)
        if is_mine:
            display_fwd = forward_edges
            display_bck = back_edges
            n_fwd = len(forward_edges)
            n_bck = len(back_edges)
        else:
            display_fwd = back_edges     # remote→local = "ida" from remote's perspective
            display_bck = forward_edges  # local→remote = "volta" from remote's perspective
            n_fwd = len(back_edges)
            n_bck = len(forward_edges)

        body = (
            lbl_a + f"     {name_a}\n"
            + lbl_b + f"    {name_b}\n"
            + tr("Hops ida:   {n}", n=n_fwd) + "\n"
            + tr("Hops volta: {n}", n=n_bck) + "\n\n"
            + "\n".join(
                build_section(display_fwd, fwd_label) +
                build_section(display_bck, bck_label)
            )
        )

        def any_drawable(edges):
            return any(has_coords(a) or has_coords(b) for a, b, _ in edges)
        # Mostra "Mostrar no Mapa" apenas se o nó destino tiver coordenadas
        # (sem GPS no destino a rota no mapa fica incompleta e sem utilidade)
        can_show_map = has_coords(dest_id) and (any_drawable(forward_edges) or any_drawable(back_edges))

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Resultado do Traceroute"))
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setSpacing(10)
        dlg_layout.setContentsMargins(16, 14, 16, 14)

        lbl_title = QLabel(
            f"🔍  {name_a}  →  {name_b}"
        )
        lbl_title.setStyleSheet(f"color:{ACCENT_GREEN};font-size:13px;font-weight:bold;")
        dlg_layout.addWidget(lbl_title)

        legend = QLabel(
            tr("📍 com localização  ❓ sem localização")
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

        # Calcula dimensões exactas para mostrar ttodo o conteúdo sem scroll
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
            btn_map = QPushButton(tr("🗺  Mostrar no Mapa"))
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
                self.tab_widget.setCurrentIndex(self.TAB_MAP)  # Mapa
                dlg.accept()
            btn_map.clicked.connect(_show_on_map)
            btn_row.addWidget(btn_map)
        else:
            lbl_no_map = QLabel(tr("⚠ Nenhum nó da rota tem localização — mapa indisponível."))
            lbl_no_map.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
            btn_row.addWidget(lbl_no_map)

        btn_row.addStretch()
        btn_close = QPushButton(tr("Fechar"))
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
        self.tab_widget.setCurrentIndex(self.TAB_MAP)  # Mapa

    # ── Notificação de mensagem não lida na aba ────────────────────────────

    def _on_language_changed(self, lang: str):
        """Called when user picks a new language in the connection dialog.
        Rebuilds every static label created at construction time.
        """
        # ── Hint bar ──────────────────────────────────────────────────────
        self._refresh_hint_bar()

        # ── Tabs ──────────────────────────────────────────────────────────
        self.tab_widget.setTabText(self.TAB_NODES,    tr("📋  Lista de Nós"))
        self.tab_widget.setTabText(self.TAB_MESSAGES, tr("💬  Mensagens"))
        self.tab_widget.setTabText(self.TAB_MAP,      tr("🗺  Mapa"))
        self.tab_widget.setTabText(self.TAB_METRICS,  tr("📈 Métricas"))
        self.tab_widget.setTabText(self.TAB_CONFIG,   tr("⚙ Configurações"))

        # ── Menus (titles) ────────────────────────────────────────────────
        if hasattr(self, "_conn_menu"):   self._conn_menu.setTitle(tr("🔌  Conexão"))
        if hasattr(self, "_node_menu"):   self._node_menu.setTitle(tr("📡  Nó"))
        if hasattr(self, "_config_menu"): self._config_menu.setTitle(tr("🔧  Ferramentas"))
        if hasattr(self, "_about_menu"):  self._about_menu.setTitle(tr("ℹ️  Sobre"))

        # ── Menu actions ──────────────────────────────────────────────────
        if hasattr(self, "_act_connect"):    self._act_connect.setText(tr("🔌  Conectar…"))
        if hasattr(self, "_act_disconnect"): self._act_disconnect.setText(tr("⏹  Desconectar"))
        if hasattr(self, "act_send_nodeinfo"): self.act_send_nodeinfo.setText(tr("📡  Enviar Info do Nó"))
        if hasattr(self, "act_send_position"): self.act_send_position.setText(tr("📍  Enviar Posição Manual"))
        if hasattr(self, "act_reset_nodedb"):  self.act_reset_nodedb.setText(tr("🗑  Reset NodeDB"))
        if hasattr(self, "_act_console"):    self._act_console.setText(tr("🖥  Consola de logs…"))
        if hasattr(self, "act_sound"):       self.act_sound.setText(tr("🔔  Som em nova mensagem"))
        if hasattr(self, "_act_info"):       self._act_info.setText(tr("📋  Sobre Meshtastic Monitor"))

        # ── Connection indicator ──────────────────────────────────────────
        connected = (getattr(self, "worker", None) is not None and
                     getattr(self.worker, "iface", None) is not None)
        if not connected:
            self.conn_indicator.setText(tr("⚫  Desconectado"))

        # ── Node count + local node label ─────────────────────────────────
        self._update_node_count()
        if hasattr(self, "local_node_label") and not connected:
            self.local_node_label.setText(tr("Nó local: —"))
        elif connected:
            self._update_local_node_label(
                getattr(self, "_local_gps_enabled", False) and
                getattr(self, "_local_has_pos", False)
            )

        # ── Table headers ─────────────────────────────────────────────────
        self.source_model.headerDataChanged.emit(
            Qt.Horizontal, 0, len(self.source_model.HEADERS) - 1
        )

        # ── Search placeholder ────────────────────────────────────────────
        if hasattr(self, "search_edit"):
            self.search_edit.setPlaceholderText(tr("Pesquisar por ID, nome longo ou curto…"))

        # ── Node count tooltip ────────────────────────────────────────────
        if hasattr(self, "node_count_label"):
            self.node_count_label.setToolTip(tr("Total de nós na rede (excluindo o nó local)"))

        # ── SNR tooltip ───────────────────────────────────────────────────
        if hasattr(self, "_stats_label"):
            self._stats_label.setToolTip(tr("SNR tooltip"))

        # ── Metrics section list ──────────────────────────────────────────
        if hasattr(self, "metrics_tab"):
            self.metrics_tab._rebuild_section_list()

        # Force table view to repaint (picks up translated headers + tooltips)
        if hasattr(self, "table_view"):
            self.table_view.viewport().update()
        # Retranslate messages tab headers
        if hasattr(self, "messages_tab"):
            self.messages_tab.retranslate()
        # Retranslate config tab
        if hasattr(self, "config_tab"):
            self.config_tab.retranslate()
        # Retranslate map widget (theme buttons + legend)
        if hasattr(self, "map_widget"):
            self.map_widget.retranslate()

    def _on_sound_toggled(self, enabled: bool):
        self._sound_enabled = enabled
        QSettings("CT7BRA", "MeshtasticMonitor").setValue("sound_enabled", enabled)
        msg = tr("🔔 Som de notificação activado") if enabled else tr("🔔 Som de notificação silenciado")
        self.statusBar().showMessage(msg, 3000)

    def _on_messages_unread(self):
        """Mostra indicador vermelho na aba Mensagens e beep se som activo."""
        if self.tab_widget.currentIndex() != self.TAB_MESSAGES:
            self.tab_widget.setTabText(self.TAB_MESSAGES, tr("💬  Mensagens") + "  🔴")
            if self._sound_enabled:
                _play_notification_sound()

    def _clear_messages_badge(self):
        """Remove o indicador da aba Mensagens."""
        self.tab_widget.setTabText(self.TAB_MESSAGES, tr("💬  Mensagens"))

    def _on_tab_changed(self, index):
        if index == self.TAB_MAP:
            self._refresh_map()
        if index == self.TAB_MESSAGES:
            self._clear_messages_badge()

    def _update_node_count(self):
        """Actualiza o label com total de nós e quantos estão online (<2h)."""
        total  = self.source_model.get_visible_count()
        online = self.source_model.get_online_count()
        self.node_count_label.setTextFormat(2)   # Qt.RichText
        self.node_count_label.setText(
            tr("Nós: {total}", total=total) + "&nbsp;&nbsp;"
            f"<span style='color:#39d353;font-weight:bold'>⬤ {online} online</span>"
        )

    def _show_about_dialog(self):
        """Diálogo de apresentação da aplicação."""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Sobre o Meshtastic Monitor"))
        dlg.setMinimumWidth(460)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(dlg)
        root.setSpacing(12)
        root.setContentsMargins(28, 24, 28, 20)

        # Título
        lbl_title = QLabel("📡  Meshtastic Monitor")
        lbl_title.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:20px;font-weight:bold;"
        )
        lbl_title.setAlignment(Qt.AlignCenter)
        root.addWidget(lbl_title)

        lbl_version = QLabel(tr("Versão {v}  ·  2026", v=APP_VERSION))
        lbl_version.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        lbl_version.setAlignment(Qt.AlignCenter)
        root.addWidget(lbl_version)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(sep)

        # Descrição
        lbl_desc = QLabel(
            tr("about_desc")
            + tr("uconsole_line")
        )
        lbl_desc.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:12px;line-height:1.6;")
        lbl_desc.setAlignment(Qt.AlignCenter)
        lbl_desc.setWordWrap(True)
        root.addWidget(lbl_desc)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(sep2)

        # Funcionalidades resumidas
        features = QLabel(
            tr("about_feat1")
            + tr("about_feat2")
            + tr("about_feat3")
            + tr("about_feat4")
            + tr("about_feat5")
        )
        features.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;line-height:1.8;")
        features.setAlignment(Qt.AlignLeft)
        root.addWidget(features)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(sep3)

        # Autor
        lbl_author = QLabel(tr("Criado por") + "  <b>CT7BRA — Tiago Veiga</b>")
        lbl_author.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:13px;"
        )
        lbl_author.setAlignment(Qt.AlignCenter)
        lbl_author.setTextFormat(2)   # RichText
        root.addWidget(lbl_author)

        lbl_tech = QLabel("Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js")
        lbl_tech.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
        lbl_tech.setAlignment(Qt.AlignCenter)
        root.addWidget(lbl_tech)

        # Botão fechar
        btn = QPushButton(tr("Fechar"))
        btn.setObjectName("btn_connect")
        btn.setFixedWidth(100)
        btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        dlg.exec_()

    def _show_console_window(self):
        """Abre/mostra a janela de consola de logs (não-bloqueante)."""
        self._console_window.show()
        self._console_window.raise_()
        # activateWindow() não é suportado em Wayland e gera aviso no log — omitir nessa plataforma
        from PyQt5.QtGui import QGuiApplication
        if QGuiApplication.platformName() != "wayland":
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
            self, tr("Reset NodeDB"),
            tr("Apagar o NodeDB do nó local?\n\nTodos os nós conhecidos serão removidos do firmware."),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes and self.worker:
            self.act_reset_nodedb.setEnabled(False)
            self.worker.reset_nodedb()

    def _on_nodedb_reset(self):
        self.source_model.clear_all_nodes()
        self.node_count_label.setText(tr("Nós: {total}", total=0)); self.node_count_label.setTextFormat(2)
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
            self.statusBar().showMessage(tr("📡 Info do Nó enviada para a rede."), 5000)
            QTimer.singleShot(3000, lambda: self.act_send_nodeinfo.setEnabled(True))

    def _on_send_position(self):
        if not self.worker:
            return
        # Desliga ligações anteriores do sinal antes de ligar uma nova
        # (evita que um send rápido acumule múltiplos handlers)
        try:
            self.worker.position_sent.disconnect()
        except Exception:
            pass

        def _on_result(ok: bool, msg: str):
            try:
                self.worker.position_sent.disconnect(_on_result)
            except Exception:
                pass
            self.act_send_position.setEnabled(True)
            if ok:
                self.statusBar().showMessage(msg, 6000)
            else:
                self.statusBar().clearMessage()
                QMessageBox.warning(self, tr("Envio de Posição"), msg)

        self.act_send_position.setEnabled(False)
        self.worker.position_sent.connect(_on_result)
        self.worker.send_position()

    def _on_dm_sent(self, dest_id: str, text: str, pki: bool, packet_id: int):
        self.messages_tab.add_outgoing_dm(dest_id, text, pki=pki, packet_id=packet_id)

    def _on_channel_sent(self, channel_index: int, text: str, packet_id: int):
        self.messages_tab.add_outgoing_channel_message(channel_index, text, packet_id=packet_id)

    def _on_packet_stats(self, pkt: dict):
        """Actualiza o indicador de SNR/pkt·min na status bar a cada pacote recebido."""
        now = time.time()

        # SNR do pacote (pode não existir em pacotes MQTT ou sem rádio)
        snr = pkt.get("rxSnr")

        if snr is None:
            snr_str  = "—"
            snr_color = TEXT_MUTED
        elif snr >= 5:
            snr_str  = f"{snr:+.1f} dB"
            snr_color = ACCENT_GREEN    # sinal forte
        elif snr >= 0:
            snr_str  = f"{snr:+.1f} dB"
            snr_color = ACCENT_ORANGE   # sinal mediano
        else:
            snr_str  = f"{snr:+.1f} dB"
            snr_color = ACCENT_RED      # sinal fraco

        # Pacotes/min — janela deslizante de 60s
        self._pkt_timestamps.append(now)
        cutoff = now - 60
        self._pkt_timestamps = [t for t in self._pkt_timestamps if t >= cutoff]
        ppm = len(self._pkt_timestamps)

        self._stats_label.setText(
            f"📶 SNR <span style='color:{snr_color};font-weight:bold'>"
            f"{snr_str}</span>  ·  {ppm} pkt/min"
        )
        self._stats_label.setTextFormat(2)   # Qt.RichText

    def _on_reconnect_status(self, attempt: int, delay_s: int):
        """Slot do sinal reconnect_status do worker.
        attempt=0 → reconectado; attempt>0 → a aguardar próxima tentativa.
        """
        if attempt == 0:
            # Reconectado — para o ticker e limpa a status bar
            self._reconnect_bar_timer.stop()
            self._reconnect_seconds = 0
            self.statusBar().clearMessage()
        else:
            # Inicia contagem regressiva visível
            self._reconnect_attempt  = attempt
            self._reconnect_seconds  = delay_s
            self._reconnect_bar_timer.start()
            self._update_reconnect_bar()

    def _on_reconnect_tick(self):
        """Decrementa o contador de reconexão a cada segundo."""
        self._reconnect_seconds -= 1
        if self._reconnect_seconds <= 0:
            self._reconnect_bar_timer.stop()
            self.statusBar().showMessage(
                tr("🔄 A tentar reconectar… (tentativa {n})", n=self._reconnect_attempt)
            )
        else:
            self._update_reconnect_bar()

    def _update_reconnect_bar(self):
        self.statusBar().showMessage(
            tr("🔌 Ligação perdida — a reconectar em {n}s (tentativa {k})…", n=self._reconnect_seconds, k=self._reconnect_attempt)
        )

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