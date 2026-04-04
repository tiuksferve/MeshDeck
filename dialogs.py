"""
dialogs.py — Diálogos auxiliares: ConnectionDialog, PacketDetailDialog,
ConsoleWindow (log em tempo real) e RebootWaitDialog.
"""
import logging
from i18n import tr, set_language, get_language
import sys
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSettings
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QSpinBox, QPushButton, QFrame, QFormLayout, QTextEdit,
    QProgressBar, QSizePolicy, QStackedWidget, QTabBar,
)
from PyQt5.QtGui import QFont

from constants import (
    logger, ACCENT_GREEN, ACCENT_BLUE, ACCENT_ORANGE, ACCENT_RED,
    TEXT_PRIMARY, TEXT_MUTED, PANEL_BG, DARK_BG, BORDER_COLOR, INPUT_BG
)

# ---------------------------------------------------------------------------
# Serial port helpers
# ---------------------------------------------------------------------------
try:
    import serial.tools.list_ports as _list_ports
    _SERIAL_AVAILABLE = True
except ImportError:
    _list_ports = None
    _SERIAL_AVAILABLE = False

_KNOWN_VIDS = {"303a", "10c4", "067b", "0403", "1a86", "2341", "239a", "1d50", "2fe3"}
_MESH_KEYWORDS = ("meshtastic", "rak", "heltec", "lilygo", "t-beam", "tbeam")


def list_serial_ports() -> list:
    """Return [(device, label), …] for likely Meshtastic ports."""
    if not _SERIAL_AVAILABLE:
        return []
    mesh, other = [], []
    for p in _list_ports.comports():
        vid = f"{p.vid:04x}" if p.vid else ""
        desc = (p.description or "").lower()
        mfr  = (p.manufacturer or "").lower()
        label = f"{p.device}  —  {p.description or 'Unknown'}"
        if vid in _KNOWN_VIDS or any(k in desc or k in mfr for k in _MESH_KEYWORDS):
            mesh.append((p.device, label))
        else:
            other.append((p.device, label))
    return mesh + other


class ConnectionDialog(QDialog):
    """Connection dialog with live language switching.

    Build-once pattern: layout is created once in __init__.
    _retranslate_ui() updates only text content — never destroys widgets.
    This preserves field values and avoids blank-dialog bugs.
    """
    from PyQt5.QtCore import pyqtSignal as _sig
    language_changed = _sig(str)

    MODE_TCP    = 0
    MODE_SERIAL = 1

    def __init__(self, current_host="localhost", current_port=4403,
                 current_mode=0, current_serial_port="", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(460)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Ensure dialog always opens in English the first time
        # (QSettings may have saved "pt" from a previous run — we still honour it,
        #  but the spec says the dialog must default to English on first use)
        if not QSettings("CT7BRA", "MeshDeck").contains("language"):
            set_language("en")

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(24, 18, 24, 18)

        # ── Language selector ──────────────────────────────────────────────
        lang_row = QHBoxLayout()
        lang_row.setSpacing(8)
        self._lang_lbl = QLabel()
        self._lang_lbl.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:12px;")
        lang_row.addWidget(self._lang_lbl)

        self._lang_combo = QComboBox()
        self._lang_combo.setMinimumWidth(150)
        self._lang_combo.setMinimumHeight(28)
        # Always use native names so the user recognises their own language
        self._lang_combo.addItem("English", "en")
        self._lang_combo.addItem("Português", "pt")
        cur_idx = self._lang_combo.findData(get_language())
        if cur_idx >= 0:
            self._lang_combo.setCurrentIndex(cur_idx)
        # Connect AFTER setting index to avoid premature retranslate
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        root.addLayout(lang_row)

        # ── Title ──────────────────────────────────────────────────────────
        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:14px;font-weight:bold;padding:4px 0;"
        )
        root.addWidget(self._title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(sep)

        # ── Mode tab bar ───────────────────────────────────────────────────
        self._tab_bar = QTabBar()
        self._tab_bar.addTab("")   # TCP
        self._tab_bar.addTab("")   # Serial
        self._tab_bar.setStyleSheet(
            f"QTabBar::tab{{color:{TEXT_MUTED};background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-bottom:none;"
            f"border-radius:4px 4px 0 0;padding:5px 16px;margin-right:2px;}}"
            f"QTabBar::tab:selected{{color:{ACCENT_GREEN};background:{DARK_BG};"
            f"border-color:{ACCENT_GREEN};}}"
        )
        self._tab_bar.setCurrentIndex(current_mode)
        self._tab_bar.currentChanged.connect(self._on_mode_changed)
        root.addWidget(self._tab_bar)

        # ── Stacked pages ──────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(
            f"QStackedWidget{{border:1px solid {BORDER_COLOR};"
            f"border-radius:0 4px 4px 4px;background:{DARK_BG};"
            f"padding:12px;}}"
        )
        root.addWidget(self._stack)

        # Page 0 — TCP/IP
        tcp_page = QWidget()
        tcp_layout = QVBoxLayout(tcp_page)
        tcp_layout.setSpacing(10)
        tcp_layout.setContentsMargins(8, 8, 8, 8)

        tcp_form = QFormLayout()
        tcp_form.setSpacing(10)
        tcp_form.setLabelAlignment(Qt.AlignRight)
        tcp_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._lbl_address = QLabel()
        self.host_edit = QLineEdit(current_host)
        self.host_edit.setMinimumWidth(240)
        self.host_edit.setMinimumHeight(28)
        tcp_form.addRow(self._lbl_address, self.host_edit)

        self._lbl_port = QLabel()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(current_port)
        self.port_spin.setMinimumHeight(28)
        tcp_form.addRow(self._lbl_port, self.port_spin)

        tcp_layout.addLayout(tcp_form)

        self._tcp_note_lbl = QLabel()
        self._tcp_note_lbl.setTextFormat(Qt.RichText)
        self._tcp_note_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;padding-top:2px;")
        tcp_layout.addWidget(self._tcp_note_lbl)
        tcp_layout.addStretch()
        self._stack.addWidget(tcp_page)

        # Page 1 — Serial / USB (connects via SerialInterface directly)
        serial_page = QWidget()
        serial_layout = QVBoxLayout(serial_page)
        serial_layout.setSpacing(10)
        serial_layout.setContentsMargins(8, 8, 8, 8)

        serial_form = QFormLayout()
        serial_form.setSpacing(10)
        serial_form.setLabelAlignment(Qt.AlignRight)
        serial_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._lbl_serial_port = QLabel()
        port_row = QHBoxLayout()
        port_row.setSpacing(6)
        self._serial_combo = QComboBox()
        self._serial_combo.setMinimumHeight(28)
        self._serial_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        port_row.addWidget(self._serial_combo)
        self._btn_refresh = QPushButton("🔄")
        self._btn_refresh.setFixedWidth(34)
        self._btn_refresh.setMinimumHeight(28)
        self._btn_refresh.clicked.connect(self._refresh_serial_ports)
        port_row.addWidget(self._btn_refresh)
        serial_form.addRow(self._lbl_serial_port, port_row)
        serial_layout.addLayout(serial_form)

        self._serial_note_lbl = QLabel()
        self._serial_note_lbl.setTextFormat(Qt.RichText)
        self._serial_note_lbl.setWordWrap(True)
        self._serial_note_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;padding-top:4px;")
        serial_layout.addWidget(self._serial_note_lbl)
        serial_layout.addStretch()
        self._stack.addWidget(serial_page)

        # Sync stack to tab
        self._stack.setCurrentIndex(current_mode)

        # ── Buttons ────────────────────────────────────────────────────────
        btns = QHBoxLayout()
        btns.setSpacing(8)

        self._btn_cancel = QPushButton()
        self._btn_cancel.setMinimumHeight(32)
        self._btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self._btn_cancel)

        btns.addStretch()

        self.btn_connect = QPushButton()
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.setMinimumHeight(32)
        self.btn_connect.setDefault(True)
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        btns.addWidget(self.btn_connect)

        root.addLayout(btns)

        # Populate serial ports then translate
        self._refresh_serial_ports(preselect=current_serial_port)
        self._retranslate_ui()

    def _retranslate_ui(self):
        """Update every translatable string without touching the layout."""
        self.setWindowTitle(tr("Configurar Conexão"))
        self._lang_lbl.setText(tr("Idioma:"))
        self._title_lbl.setText(tr("📡  Conexão ao Servidor Meshtastic"))
        self._tab_bar.setTabText(self.MODE_TCP,    tr("conn_tab_tcp"))
        self._tab_bar.setTabText(self.MODE_SERIAL, tr("conn_tab_serial"))
        self._lbl_address.setText(tr("Endereço:"))
        self._lbl_port.setText(tr("Porta:"))
        self.host_edit.setPlaceholderText(tr("ex: localhost  ou  192.168.1.1"))
        self._btn_cancel.setText(tr("Cancelar"))
        self.btn_connect.setText(tr("🔌  Conectar"))
        note = tr("💡 Endereço padrão: localhost · porta 4403")
        note = note.replace("localhost", "<b>localhost</b>").replace("4403", "<b>4403</b>")
        self._tcp_note_lbl.setText(note)
        self._lbl_serial_port.setText(tr("serial_port_label"))
        self._btn_refresh.setToolTip(tr("serial_refresh_tip"))
        self._serial_note_lbl.setText(tr("serial_note_direct"))

    def _on_lang_changed(self, index: int):
        lang = self._lang_combo.itemData(index)
        if not lang:
            return
        set_language(lang)
        QSettings("CT7BRA", "MeshDeck").setValue("language", lang)
        self._retranslate_ui()          # update this dialog immediately
        self.language_changed.emit(lang) # notify MainWindow

    # ── Serial helpers ────────────────────────────────────────────────────

    def _refresh_serial_ports(self, preselect: str = ""):
        self._serial_combo.blockSignals(True)
        self._serial_combo.clear()
        ports = list_serial_ports()
        if not ports:
            self._serial_combo.addItem(tr("serial_no_ports"), "")
        else:
            for device, label in ports:
                self._serial_combo.addItem(label, device)
        if preselect:
            idx = self._serial_combo.findData(preselect)
            if idx >= 0:
                self._serial_combo.setCurrentIndex(idx)
        self._serial_combo.blockSignals(False)

    # ── Mode switching ─────────────────────────────────────────────────────

    def _on_mode_changed(self, index: int):
        self._stack.setCurrentIndex(index)

    # ── Connect button ─────────────────────────────────────────────────────

    def _on_connect_clicked(self):
        self.accept()

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def hostname(self) -> str:
        return self.host_edit.text().strip() or "localhost"

    @property
    def port(self) -> int:
        return self.port_spin.value()

    @property
    def connection_mode(self) -> int:
        """MODE_TCP or MODE_SERIAL."""
        return self._tab_bar.currentIndex()

    @property
    def selected_serial_port(self) -> str:
        return self._serial_combo.currentData() or ""


class PacketDetailDialog(QDialog):
    def __init__(self, node_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Detalhes do Último Pacote"))
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"📦  {tr('Pacote')} — {node_info.get('id_string', '')}")
        title.setStyleSheet(f"color:{ACCENT_GREEN};font-size:14px;font-weight:bold;")
        layout.addWidget(title)

        te = QTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont("Menlo", 11) if sys.platform == "darwin" else QFont("Consolas", 11))
        te.setStyleSheet(
            f"background-color:{DARK_BG};color:{ACCENT_GREEN};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;padding:12px;"
        )
        te.setText(str(node_info.get("last_packet", tr("Nenhum pacote armazenado"))))
        layout.addWidget(te)

        btn = QPushButton(tr("Fechar"))
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignRight)


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
        self.setWindowTitle(tr("🖥  Consola de Logs"))
        self.resize(860, 420)
        self.setAttribute(Qt.WA_DeleteOnClose, False)  # reutilizar

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Barra de controlos
        ctrl = QHBoxLayout()
        self._lbl_count = QLabel(tr("0 linhas"))
        self._lbl_count.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        ctrl.addWidget(self._lbl_count)
        ctrl.addStretch()

        lbl_filter = QLabel(tr("Filtro:"))
        lbl_filter.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        ctrl.addWidget(lbl_filter)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(tr("palavra-chave…"))
        self._filter.setFixedWidth(180)
        self._filter.setStyleSheet(
            f"background:{DARK_BG};color:{TEXT_PRIMARY};border:1px solid {BORDER_COLOR};"
            f"border-radius:4px;padding:2px 6px;font-size:11px;"
        )
        self._filter.textChanged.connect(self._apply_filter)
        ctrl.addWidget(self._filter)

        btn_clear = QPushButton(tr("🗑 Limpar"))
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
        self._lbl_count.setText(tr("{n} linhas", n=len(self._all_lines)))

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
        self._lbl_count.setText(tr("0 linhas"))

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
    WAIT_SECONDS = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("A reiniciar nó…"))
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(24, 20, 24, 20)

        # Ícone + título
        lbl_title = QLabel(tr("🔄  Nó a reiniciar"))
        lbl_title.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:15px;font-weight:bold;"
        )
        lbl_title.setAlignment(Qt.AlignCenter)
        root.addWidget(lbl_title)

        lbl_info = QLabel(
            tr("reboot_msg")
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
        self._btn = QPushButton(tr("🔌  Aguarde {n}s…", n=self.WAIT_SECONDS))
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
            self._btn.setText(tr("🔌  Aguarde {n}s…", n=self._remaining))
        else:
            self._timer.stop()
            self._btn.setEnabled(True)
            self._btn.setText(tr("🔌  Reconectar agora"))
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
