"""
dialogs.py — Diálogos auxiliares: ConnectionDialog, PacketDetailDialog,
ConsoleWindow (log em tempo real) e RebootWaitDialog.
"""
import logging
import sys
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QPushButton, QFrame, QFormLayout, QTextEdit,
    QProgressBar, QSizePolicy
)
from PyQt5.QtGui import QFont

from constants import (
    logger, ACCENT_GREEN, ACCENT_BLUE, ACCENT_ORANGE, ACCENT_RED,
    TEXT_PRIMARY, TEXT_MUTED, PANEL_BG, DARK_BG, BORDER_COLOR, INPUT_BG
)

class ConnectionDialog(QDialog):
    def __init__(self, current_host="localhost", current_port=4403, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Conexão")
        self.setFixedSize(420, 240)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

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
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.host_edit = QLineEdit(current_host)
        self.host_edit.setPlaceholderText("ex: localhost  ou  192.168.1.1")
        form.addRow("Endereço:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(current_port)
        form.addRow("Porta:", self.port_spin)

        layout.addLayout(form)

        note = QLabel("💡 Endereço padrão: <b>localhost</b> · porta <b>4403</b>")
        note.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
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