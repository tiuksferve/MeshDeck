"""
tabs/tab_messages.py — Aba de mensagens: canais, DMs (PKI/PSK),
indicadores de leitura e gestão de conversas.
"""
import hashlib
import html
import logging
from typing import Optional, Dict, List, Callable
from collections import defaultdict
from i18n import tr
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot, QObject
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QSplitter, QFrame, QLabel, QLineEdit, QPushButton,
    QTextEdit, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QSizePolicy, QHeaderView
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtGui import QColor, QFont

from constants import (
    logger, DARK_BG, PANEL_BG, BORDER_COLOR, ACCENT_GREEN, ACCENT_BLUE,
    ACCENT_ORANGE, ACCENT_RED, ACCENT_PURPLE, TEXT_PRIMARY, TEXT_MUTED,
    INPUT_BG, DM_BG, _is_broadcast
)

class ConversationContext:
    CHANNEL = "channel"
    DM      = "dm"


class _ReplyBridge(QObject):
    """Exposto ao JavaScript via QWebChannel para receber cliques de reply."""
    reply_requested = pyqtSignal(str, str)   # (from_name, text_preview)

    @pyqtSlot(str, str)
    def requestReply(self, from_name: str, text_preview: str):
        self.reply_requested.emit(from_name, text_preview)


class MessagesTab(QWidget):
    send_channel_message = pyqtSignal(int, str)
    send_direct_message  = pyqtSignal(str, str)
    unread_message       = pyqtSignal()   # emitido quando chega mensagem não lida

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
        self._batch_mode:  bool          = False  # suppresses _refresh_dm_list during batch loads
        self._reply_from:  Optional[str] = None   # nome do remetente a quem se responde
        self._reply_text:  Optional[str] = None   # preview do texto original

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        # Painel esquerdo: splitter vertical entre lista de canais e lista de DMs.
        # Ambas as secções são redimensionáveis pelo utilizador — resolve o problema
        # de DMs invisíveis em ecrãs de baixa resolução.
        left = QWidget()
        left.setMaximumWidth(280)
        left.setMinimumWidth(180)
        left_outer = QVBoxLayout(left)
        left_outer.setContentsMargins(0, 0, 4, 0)
        left_outer.setSpacing(0)

        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.setHandleWidth(4)
        left_splitter.setChildrenCollapsible(False)   # evita que DMs desapareçam em ecrãs pequenos
        left_splitter.setStyleSheet(
            f"QSplitter::handle{{background:{ACCENT_BLUE}44;"
            f"border-radius:2px;margin:1px 4px;}}"
            f"QSplitter::handle:hover{{background:{ACCENT_BLUE};}}"
        )

        # ── Secção Canais ──────────────────────────────────────────────────
        chan_widget = QWidget()
        chan_widget.setMinimumHeight(60)
        lv = QVBoxLayout(chan_widget)
        lv.setContentsMargins(0, 0, 0, 2)
        lv.setSpacing(4)

        self._chan_hdr = QLabel(tr("📻  Canais"))
        chan_hdr = self._chan_hdr
        chan_hdr.setStyleSheet(
            f"color:{ACCENT_BLUE};font-weight:bold;font-size:11px;"
            f"padding:3px 6px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;"
        )
        lv.addWidget(chan_hdr)

        self.channel_list = QListWidget()
        self.channel_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.channel_list.itemClicked.connect(self._on_channel_clicked)
        self.channel_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lv.addWidget(self.channel_list, stretch=1)
        left_splitter.addWidget(chan_widget)

        # ── Secção DMs ────────────────────────────────────────────────────
        dm_widget = QWidget()
        dm_widget.setMinimumHeight(80)
        dv = QVBoxLayout(dm_widget)
        dv.setContentsMargins(0, 2, 0, 0)
        dv.setSpacing(4)

        self._dm_hdr = QLabel(tr("📧  Mensagens Directas"))
        dm_hdr = self._dm_hdr
        dm_hdr.setStyleSheet(
            f"color:{ACCENT_PURPLE};font-weight:bold;font-size:11px;"
            f"padding:3px 6px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;"
        )
        dv.addWidget(dm_hdr)

        self.dm_list = QTableWidget()
        self.dm_list.setColumnCount(2)
        self.dm_list.setHorizontalHeaderLabels(["Short", tr("Nome Longo")])
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
        dv.addWidget(self.dm_list, stretch=1)
        left_splitter.addWidget(dm_widget)

        # Proporção inicial: canais ~30% / DMs ~70%.
        # setCollapsible(False) garante que nenhuma secção fica a 0px
        # mesmo em ecrãs de baixa resolução (ex: uConsole 1280×480).
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 2)
        left_splitter.setCollapsible(0, False)
        left_splitter.setCollapsible(1, False)
        left_splitter.setSizes([140, 340])
        self._left_splitter = left_splitter   # guardamos ref para retranslate/restore

        left_outer.addWidget(left_splitter)
        splitter.addWidget(left)

        right = QWidget()
        rv    = QVBoxLayout(right)
        rv.setContentsMargins(4, 0, 0, 0)
        rv.setSpacing(6)

        self.conv_header = QLabel(tr("Seleccione um canal ou nó"))
        self.conv_header.setStyleSheet(
            f"color:{ACCENT_GREEN};font-weight:bold;font-size:13px;"
            f"padding:6px 10px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;"
        )
        rv.addWidget(self.conv_header)

        self.messages_view = QWebEngineView()
        self.messages_view.setContextMenuPolicy(Qt.NoContextMenu)
        rv.addWidget(self.messages_view, stretch=1)
        # O webchannel será ligado após a criação do _web_channel (abaixo)

        # Banner de reply — aparece quando o utilizador clica ↩ numa mensagem
        self._reply_banner = QFrame()
        self._reply_banner.setVisible(False)
        self._reply_banner.setStyleSheet(
            f"background:#1a1a2e;border:1px solid {ACCENT_BLUE}88;"
            f"border-radius:6px;"
        )
        rb_layout = QHBoxLayout(self._reply_banner)
        rb_layout.setContentsMargins(10, 5, 8, 5)
        rb_layout.setSpacing(8)
        self._reply_banner_lbl = QLabel()
        self._reply_banner_lbl.setStyleSheet(
            f"color:{ACCENT_BLUE};font-size:11px;border:none;background:transparent;"
        )
        self._reply_banner_lbl.setWordWrap(True)
        rb_layout.addWidget(self._reply_banner_lbl, stretch=1)
        btn_cancel_reply = QPushButton("✕")
        btn_cancel_reply.setFixedSize(22, 22)
        btn_cancel_reply.setToolTip(tr("cancel_reply"))
        btn_cancel_reply.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_MUTED};"
            f"border:none;font-size:13px;padding:0;}}"
            f"QPushButton:hover{{color:{ACCENT_RED};}}"
        )
        btn_cancel_reply.clicked.connect(self._cancel_reply)
        rb_layout.addWidget(btn_cancel_reply)
        rv.addWidget(self._reply_banner)

        send_frame = QFrame()
        send_frame.setStyleSheet(
            f"background:{PANEL_BG};border:1px solid {BORDER_COLOR};border-radius:6px;"
        )
        sl = QHBoxLayout(send_frame)
        sl.setContentsMargins(8, 6, 8, 6)
        sl.setSpacing(8)

        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText(tr("Seleccione um canal ou nó para enviar mensagem…"))
        self.send_input.setEnabled(False)
        self.send_input.returnPressed.connect(self._on_send)
        sl.addWidget(self.send_input, stretch=1)

        self.btn_send = QPushButton(tr("📤  Enviar"))
        self.btn_send.setObjectName("btn_send_channel")
        self.btn_send.setFixedWidth(130)
        self.btn_send.setEnabled(False)
        self.btn_send.clicked.connect(self._on_send)
        sl.addWidget(self.btn_send)

        rv.addWidget(send_frame)

        # Ligar o _ReplyBridge ao QWebChannel para receber cliques de Reply do JS
        self._reply_bridge = _ReplyBridge(self)
        self._reply_bridge.reply_requested.connect(self._on_reply_requested)
        self._web_channel = QWebChannel(self)
        self._web_channel.registerObject("replyBridge", self._reply_bridge)
        self.messages_view.page().setWebChannel(self._web_channel)
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

    def retranslate(self):
        """Update all translatable labels after a language change."""
        if hasattr(self, '_chan_hdr'):
            self._chan_hdr.setText(tr("📻  Canais"))
        if hasattr(self, '_dm_hdr'):
            self._dm_hdr.setText(tr("📧  Mensagens Directas"))
        # Actualiza tooltip do botão cancelar reply
        if hasattr(self, '_reply_banner'):
            for btn in self._reply_banner.findChildren(QPushButton):
                btn.setToolTip(tr("cancel_reply"))
        # Actualiza texto do banner se reply estiver activo
        if hasattr(self, '_reply_from') and self._reply_from:
            safe_from    = html.escape(self._reply_from)
            safe_preview = html.escape(self._reply_text or "")
            self._reply_banner_lbl.setText(
                f"↩ {tr('reply_to')} <b>{safe_from}</b>: "
                f"<i style='color:{TEXT_MUTED};'>{safe_preview}</i>"
            )
        # Refresh the empty-state page if currently shown
        if hasattr(self, '_web') and hasattr(self, '_ctx_channel'):
            self._web.setHtml(self._empty_state_html())

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

    def set_batch_mode(self, enabled: bool):
        """Suppress _refresh_dm_list calls during bulk node loads.
        Call set_batch_mode(False) followed by _refresh_dm_list() to commit."""
        self._batch_mode = enabled

    def update_node_name(self, node_id: str, long_name: str, short_name: str, public_key: str = ''):
        if long_name:
            self.node_names[node_id] = long_name
        elif short_name:
            self.node_names[node_id] = short_name
        if short_name:
            self.node_short[node_id] = short_name
        if public_key:
            self.node_public_keys[node_id] = public_key
        if not self._batch_mode:
            self._refresh_dm_list()

    def _refresh_dm_list(self):
        if self._batch_mode:
            return
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
                col0.setToolTip(tr("Chave pública conhecida — DM PKI disponível (E2E)"))
            else:
                col0.setForeground(QColor(TEXT_MUTED))
                col0.setToolTip(tr("Chave pública desconhecida — DM via PSK de canal"))

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
        for entry in channels:
            # Suporta tuplos (idx, name, psk) e (idx, name, psk, role)
            idx  = entry[0]
            name = entry[1]
            role = entry[3] if len(entry) > 3 else None
            # role: 0=DISABLED, 1=PRIMARY, 2=SECONDARY
            # Canais DISABLED não são mostrados — não têm PSK activa nem uso
            if role is not None and role == 0:
                continue
            self.channel_map[idx] = name or tr("Canal {n}", n=idx)
            item = QListWidgetItem(self._fmt_channel(idx))
            item.setData(Qt.UserRole, idx)
            self.channel_list.addItem(item)

        n = self.channel_list.count()
        if n > 0 and self._ctx_channel is None:
            first = self.channel_list.item(0)
            self.channel_list.setCurrentItem(first)
            self._activate_channel(first.data(Qt.UserRole))

    def _fmt_channel(self, idx: int) -> str:
        name   = self.channel_map.get(idx, tr("Canal {n}", n=idx))
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

        name = self.channel_map.get(idx, tr("Canal {n}", n=idx))
        self.conv_header.setText(tr("channel_header", idx=idx, name=name))
        self.conv_header.setStyleSheet(
            f"color:{ACCENT_GREEN};font-weight:bold;font-size:13px;"
            f"padding:6px 10px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;"
        )
        self.send_input.setPlaceholderText(tr("Mensagem para #{n} · {name}…", n=idx, name=name))
        self.send_input.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_send.setObjectName("btn_send_channel")
        self.btn_send.setStyleSheet(
            f"background-color:#1a4a2e;color:{ACCENT_GREEN};border-color:{ACCENT_GREEN};"
        )
        self.btn_send.setText(tr("📤  Enviar"))
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

        self.conv_header.setText(tr("dm_header", label=html.escape(label), enc=enc_tag))
        self.conv_header.setStyleSheet(
            f"color:{ACCENT_PURPLE};font-weight:bold;font-size:13px;"
            f"padding:6px 10px;background:{DM_BG};"
            f"border:1px solid {ACCENT_PURPLE};border-radius:6px;"
        )
        self.send_input.setPlaceholderText(tr("Mensagem directa para {name}…", name=label))
        self.send_input.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_send.setObjectName("btn_send_dm")
        self.btn_send.setStyleSheet(
            f"background-color:#2a1a4a;color:{ACCENT_PURPLE};border-color:{ACCENT_PURPLE};"
        )
        self.btn_send.setText(tr("📧  Enviar DM"))
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

    def _on_reply_requested(self, from_name: str, text_preview: str):
        """Activado pelo botão ↩ no HTML via QWebChannel."""
        self._reply_from = from_name
        # Trunca o preview a 80 chars para não encher o banner
        self._reply_text = text_preview[:80] + ("…" if len(text_preview) > 80 else "")
        safe_from    = html.escape(self._reply_from)
        safe_preview = html.escape(self._reply_text)
        self._reply_banner_lbl.setText(
            f"↩ {tr('reply_to')} <b>{safe_from}</b>: "
            f"<i style='color:{TEXT_MUTED};'>{safe_preview}</i>"
        )
        self._reply_banner_lbl.setTextFormat(2)   # RichText
        self._reply_banner.setVisible(True)
        self.send_input.setFocus()

    def _cancel_reply(self):
        """Remove o contexto de reply."""
        self._reply_from = None
        self._reply_text = None
        self._reply_banner.setVisible(False)

    def _on_send(self):
        text = self.send_input.text().strip()
        if not text:
            return

        # Se há reply activo, prefixa com citação estilo blockquote
        if self._reply_from and self._reply_text:
            preview = self._reply_text.replace("\n", " ")
            text = f"↩ {self._reply_from}: {preview}\n{text}"
            self._cancel_reply()

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

        # Emite sinal de não-lida para qualquer mensagem recebida (não enviada).
        # O MainWindow decide se mostra badge (se a aba não está visível).
        # Inclui mensagens do canal activo — podem estar a chegar enquanto
        # o utilizador está noutra aba.
        if not entry.get('outgoing'):
            self.unread_message.emit()

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
        icon   = "📧" if is_dm else "💬"
        lbl    = f"DM: {self._ctx_dm_id}" if is_dm else f"Canal #{self._ctx_channel}"
        return (
            f"<html><meta charset='utf-8'><body style='background:{bg};color:{TEXT_MUTED};"
            "font-family:monospace;display:flex;align-items:center;"
            "justify-content:center;height:100vh;margin:0;text-align:center;font-size:14px;'>"
            f"<div>{icon}<br><br>{tr('Nenhuma mensagem em')}<br>"
            f"<b style='color:{color};'>{html.escape(lbl)}</b> {tr('ainda.')}</div>"
            "</body></html>"
        )

    def _html_header(self, key: str) -> str:
        is_dm = self._is_dm_key(key)
        bg    = DM_BG if is_dm else DARK_BG
        return f"""<html><head><meta charset="utf-8">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
var replyBridge = null;
new QWebChannel(qt.webChannelTransport, function(channel) {{
    replyBridge = channel.objects.replyBridge;
}});
function sendReply(fromName, textPreview) {{
    if (replyBridge) replyBridge.requestReply(fromName, textPreview);
}}
</script>
<style>
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
.body  {{font-size:15px;word-break:break-word;line-height:1.5;white-space:pre-wrap;}}
.meta  {{font-size:10px;color:{TEXT_MUTED};margin-top:4px;display:flex;
  align-items:center;gap:6px;}}
.reply-btn{{
  background:transparent;border:none;cursor:pointer;
  color:{TEXT_MUTED};font-size:11px;padding:0 2px;
  opacity:0.6;transition:opacity 0.15s;}}
.reply-btn:hover{{opacity:1;color:{ACCENT_BLUE};}}
.reply-quote{{
  border-left:3px solid {ACCENT_BLUE}88;padding:3px 8px;
  margin-bottom:5px;color:{TEXT_MUTED};font-size:12px;
  font-style:italic;background:{DARK_BG}88;border-radius:0 4px 4px 0;}}
</style></head><body>"""

    def _fmt_msg(self, msg: dict, prev_date) -> tuple:
        msg_date = msg["time"].date()
        parts    = []

        if prev_date is None or msg_date != prev_date:
            today = datetime.now().date()
            if msg_date == today:
                ds = f"&#8212; {tr('Hoje')} &#8212;"
            elif msg_date == today - timedelta(days=1):
                ds = f"&#8212; {tr('Ontem')} &#8212;"
            else:
                ds = f"&#8212; {msg_date.strftime('%d/%m/%Y')} &#8212;"
            parts.append(f'<div class="date-sep">{ds}</div>')

        raw_text    = msg["text"]
        sender_esc  = html.escape(msg["from_"])
        time_str    = msg["time"].strftime("%H:%M")
        color       = msg["color"]
        label       = html.escape(msg["label"])

        # Detecta prefixo de reply (↩ remetente: preview\nmensagem) e
        # formata como blockquote destacado + texto da mensagem separado.
        reply_quote_html = ""
        display_text = raw_text
        if raw_text.startswith("↩ ") and "\n" in raw_text:
            quote_line, _, display_text = raw_text.partition("\n")
            # quote_line: "↩ Nome: preview"
            quote_content = html.escape(quote_line[2:])   # remove "↩ "
            reply_quote_html = (
                f'<div class="reply-quote">↩ {quote_content}</div>'
            )
        safe_text = html.escape(display_text).replace("\n", "<br>")

        status        = msg.get('status', '')
        status_detail = msg.get('status_detail', '')
        if msg.get('outgoing'):
            if status == 'sending':
                status_html = f'<span title="{tr("A enviar...")}" style="color:{TEXT_MUTED};font-size:11px;">&#9679;&#9679;&#9679;</span>'
            elif status == 'ack_implicit':
                status_html = f'<span title="{tr("Recebido por relay")}" style="color:{ACCENT_ORANGE};font-size:12px;">&#10003;</span>'
            elif status == 'ack':
                status_html = f'<span title="{tr("Confirmado pelo destinatário")}" style="color:{ACCENT_GREEN};font-size:12px;">&#10003;&#10003;</span>'
            elif status == 'nak':
                err_esc     = html.escape(status_detail or tr('Falha'))
                status_html = f'<span title="{tr("Falha: {err}", err=err_esc)}" style="color:{ACCENT_RED};font-size:11px;">&#10007; {err_esc}</span>'
            else:
                status_html = ''
        else:
            status_html = ''

        # Botão ↩ para mensagens recebidas — passa nome e texto (escapados) ao JS
        reply_btn_html = ""
        if not msg["outgoing"]:
            safe_from_js = sender_esc.replace('"', "&quot;")
            safe_text_js = html.escape(display_text[:80]).replace('"', "&quot;")
            reply_btn_html = (
                f'<button class="reply-btn" '
                f'data-from="{safe_from_js}" data-text="{safe_text_js}" '
                f'onclick="sendReply(this.dataset.from,this.dataset.text)" '
                f'title="{tr("msg_reply_btn")}">↩</button>'
            )

        if msg["outgoing"]:
            parts.append(
                '<div class="row-out"><div class="bubble-out">'
                f'{reply_quote_html}'
                f'<div class="sender" style="color:{color}">{sender_esc}</div>'
                f'<div class="body">{safe_text}</div>'
                f'<div class="meta">{label} &middot; {time_str}'
                + (f' &nbsp;{status_html}' if status_html else '') +
                '</div></div></div>'
            )
        elif msg["dm"]:
            parts.append(
                '<div class="row-in"><div class="bubble-dm">'
                f'{reply_quote_html}'
                f'<div class="sender" style="color:{color}">{sender_esc}'
                f' <span style="color:{ACCENT_PURPLE};font-size:9px;">[DM]</span></div>'
                f'<div class="body">{safe_text}</div>'
                f'<div class="meta">{reply_btn_html}{label} &middot; {time_str}</div>'
                '</div></div>'
            )
        else:
            parts.append(
                '<div class="row-in"><div class="bubble-in">'
                f'{reply_quote_html}'
                f'<div class="sender" style="color:{color}">{sender_esc}</div>'
                f'<div class="body">{safe_text}</div>'
                f'<div class="meta">{reply_btn_html}{label} &middot; {time_str}</div>'
                '</div></div>'
            )
        return "\n".join(parts), msg_date