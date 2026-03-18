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
    QProgressBar, QSizePolicy, QRadioButton, QButtonGroup, QComboBox
)
from PyQt5.QtGui import QFont

from i18n import tr, register_retranslate, get_language, set_language
from constants import (
    logger, ACCENT_GREEN, ACCENT_BLUE, ACCENT_ORANGE, ACCENT_RED,
    TEXT_PRIMARY, TEXT_MUTED, PANEL_BG, DARK_BG, BORDER_COLOR, INPUT_BG
)

class ConnectionDialog(QDialog):
    def __init__(self, current_host="localhost", current_port=4403, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Configure Connection"))
        self.setFixedWidth(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel("📡  " + tr("Meshtastic Server Connection"))
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
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.host_edit = QLineEdit(current_host)
        self.host_edit.setPlaceholderText("ex: localhost  or  192.168.1.1")
        form.addRow(tr("Address:"), self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(current_port)
        form.addRow(tr("Port:"), self.port_spin)

        # Language selector
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("🇬🇧  English", "en")
        self.lang_combo.addItem("🇵🇹  Português", "pt")
        self.lang_combo.setMinimumWidth(200)
        self.lang_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        cur_idx = 0 if get_language() == "en" else 1
        self.lang_combo.setCurrentIndex(cur_idx)
        form.addRow(tr("Interface Language:"), self.lang_combo)

        layout.addLayout(form)

        note = QLabel(tr("💡 Default address for local daemon is <b>localhost</b> port <b>4403</b>."))
        note.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;padding:2px 0;")
        note.setWordWrap(False)
        layout.addWidget(note)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.setSpacing(8)

        btn_cancel = QPushButton(tr("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)

        btns.addStretch()

        self.btn_connect = QPushButton(tr("🔌  Connect"))
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

    @property
    def language(self) -> str:
        return self.lang_combo.currentData() if hasattr(self, "lang_combo") else get_language()


# ---------------------------------------------------------------------------
# Diálogo de detalhes do pacote
class PacketDetailDialog(QDialog):
    def __init__(self, node_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Details of Last Packet"))
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
        te.setText(str(node_info.get("last_packet", "No packet stored")))
        layout.addWidget(te)

        btn = QPushButton(tr("Close"))
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
        self.setWindowTitle(tr("🖥  Log Console"))
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
class RebootWaitDialog(QDialog):
    """Diálogo modal que desliga do nó, faz a contagem de 15s obrigatória
    (tempo mínimo recomendado pela documentação Meshtastic para aguardar
    após guardar configurações antes de reconectar via TCP) e libera o
    botão de reconexão quando o tempo termina."""

    reconnect_requested = pyqtSignal()
    WAIT_SECONDS = 15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Rebooting node…"))
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(24, 20, 24, 20)

        # Ícone + título
        lbl_title = QLabel("🔄  " + tr("Rebooting node…"))
        lbl_title.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:15px;font-weight:bold;"
        )
        lbl_title.setAlignment(Qt.AlignCenter)
        root.addWidget(lbl_title)

        lbl_info = QLabel(
            tr("The settings have been sent to the node.") + "\n"
            + tr("The node is restarting to apply them.") + "\n\n"
            + tr("Wait before reconnecting to ensure") + "\n"
            + tr("the TCP service will be available again.")
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
        self._btn = QPushButton(f"🔌  {tr('Wait')} {self.WAIT_SECONDS}s…")
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
            self._btn.setText(f"🔌  {tr('Wait')} {self._remaining}s…")
        else:
            self._timer.stop()
            self._btn.setEnabled(True)
            self._btn.setText(tr("🔌  Reconnect now"))
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

class LanguageDialog(QDialog):
    """Dialog for selecting the interface language."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Select Language"))
        self.setFixedWidth(320)
        self.setModal(True)
        self._selected = get_language()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel("🌐  " + tr("Select Language"))
        title.setStyleSheet(
            f"color:{ACCENT_BLUE};font-size:14px;font-weight:bold;"
        )
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        layout.addWidget(sep)

        lbl = QLabel(tr("Choose the interface language:"))
        lbl.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:12px;")
        layout.addWidget(lbl)

        from PyQt5.QtWidgets import QButtonGroup, QRadioButton
        self._btn_en = QRadioButton("🇬🇧  English")
        self._btn_pt = QRadioButton("🇵🇹  Português")
        self._btn_en.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:13px;padding:4px;")
        self._btn_pt.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:13px;padding:4px;")

        if get_language() == "en":
            self._btn_en.setChecked(True)
        else:
            self._btn_pt.setChecked(True)

        self._btn_en.toggled.connect(lambda c: setattr(self, '_selected', 'en') if c else None)
        self._btn_pt.toggled.connect(lambda c: setattr(self, '_selected', 'pt') if c else None)

        layout.addWidget(self._btn_en)
        layout.addWidget(self._btn_pt)
        layout.addStretch()

        btns = QHBoxLayout()
        btn_cancel = QPushButton(tr("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addStretch()
        btn_apply = QPushButton(tr("Apply"))
        btn_apply.setObjectName("btn_connect")
        btn_apply.setDefault(True)
        btn_apply.clicked.connect(self.accept)
        btns.addWidget(btn_apply)
        layout.addLayout(btns)

    @property
    def selected_language(self) -> str:
        return self._selected

