"""
tabs/tab_metrics.py — MetricsTab: aba de métricas em tempo real.

Orquestra a UI (QListWidget + QWebEngineView) e delega:
  - Ingestão e cálculo de dados → MetricsDataMixin  (metrics_data.py)
  - Geração de HTML/JS          → MetricsRenderMixin (metrics_render.py)
"""
import json
from i18n import tr
import logging

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QPushButton,
    QSizePolicy, QMessageBox, QLabel
)
from PyQt5.QtWebEngineWidgets import QWebEngineView

from constants import (
    logger, DARK_BG, PANEL_BG, BORDER_COLOR, ACCENT_GREEN, ACCENT_BLUE,
    ACCENT_ORANGE, ACCENT_RED, TEXT_PRIMARY, TEXT_MUTED
)
from tabs.metrics_data   import MetricsDataMixin
from tabs.metrics_render import MetricsRenderMixin


class MetricsTab(MetricsDataMixin, MetricsRenderMixin, QWidget):
    """
    Aba de métricas em tempo real da rede Meshtastic.
    Recolhe dados de todos os pacotes recebidos e apresenta gráficos
    interactivos por secção usando Chart.js via QWebEngineView.

    Secções:
      1. Visão Geral       — resumo executivo da rede
      2. Canal & Airtime   — utilização do canal e airtime TX (firmware metrics)
      3. Qualidade RF      — distribuição de SNR e hops
      4. Tráfego           — pacotes por tipo e taxa de mensagens/min
      5. Nós & Bateria     — saúde dos nós, bateria
      6. Fiabilidade       — ACK/NAK, taxa de entrega
      7. Latência          — RTT médio/mín/máx/P90
      8. Vizinhança        — pares vizinhos directos com SNR
      9. Alcance & Links   — distância km entre vizinhos com GPS
     10. Intervalos        — intervalo entre pacotes por nó
    """

    @classmethod
    def get_sections(cls):
        """Returns sections with translated labels."""
        return [
            (tr("📊 Visão Geral"),      "overview"),
            (tr("📡 Canal & Airtime"),  "channel"),
            (tr("📶 Qualidade RF"),     "rf"),
            (tr("📦 Tráfego"),          "traffic"),
            (tr("🔋 Nós & Bateria"),    "nodes"),
            (tr("✅ Fiabilidade"),      "reliability"),
            (tr("⏱ Latência"),         "latency"),
            (tr("🔗 Vizinhança"),       "neighbors"),
            (tr("📏 Alcance & Links"),  "range_links"),
            (tr("⏰ Intervalos"),       "intervals"),
        ]

    # Limites do canal (documentação oficial Meshtastic)
    CH_UTIL_OK    = 25.0   # abaixo = verde
    CH_UTIL_WARN  = 50.0   # abaixo = laranja; acima = vermelho

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reset_data()
        self._page_ready = False
        # _refresh_timer: dispara runJavaScript a cada 5s — corre SEMPRE,
        # independente do carregamento. O JS protege com if(window._metricsUpdateData).
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5_000)
        self._refresh_timer.timeout.connect(self._on_auto_refresh)
        self._build_ui()
        self._refresh_timer.start()   # inicia imediatamente, nunca para

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Painel esquerdo — lista de secções
        left = QWidget()
        left.setFixedWidth(200)
        left.setStyleSheet(
            f"background:{PANEL_BG};border-right:1px solid {BORDER_COLOR};"
        )
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 8, 0, 0)
        ll.setSpacing(0)

        lbl = QLabel(f"  {tr('Métricas')}")
        lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;font-weight:bold;"
            f"padding:4px 12px 8px 12px;letter-spacing:1px;"
        )
        ll.addWidget(lbl)

        self._section_list = QListWidget()
        self._section_list.setStyleSheet(
            f"QListWidget{{background:{PANEL_BG};border:none;outline:none;}}"
            f"QListWidget::item{{color:{TEXT_PRIMARY};padding:10px 16px;"
            f"border-bottom:1px solid {BORDER_COLOR};font-size:12px;}}"
            f"QListWidget::item:selected{{background:{DARK_BG};"
            f"color:{ACCENT_GREEN};border-left:3px solid {ACCENT_GREEN};}}"
            f"QListWidget::item:hover{{background:{DARK_BG};}}"
        )
        for label, _ in self.get_sections():
            self._section_list.addItem(label)
        self._section_list.setCurrentRow(0)
        self._section_list.currentRowChanged.connect(self._on_section_changed)
        ll.addWidget(self._section_list, stretch=1)

        # Botão actualizar
        self._btn_refresh = QPushButton(tr("🔄  Actualizar"))
        self._btn_refresh.setStyleSheet(
            f"QPushButton{{background:{DARK_BG};color:{ACCENT_GREEN};"
            f"border:none;border-top:1px solid {BORDER_COLOR};"
            f"padding:10px;font-size:11px;}}"
            f"QPushButton:hover{{background:{PANEL_BG};}}"
        )
        self._btn_refresh.clicked.connect(self._on_manual_refresh)
        ll.addWidget(self._btn_refresh)

        # Label do último refresh
        self._lbl_last_refresh = QLabel("—")
        self._lbl_last_refresh.setAlignment(Qt.AlignCenter)
        self._lbl_last_refresh.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;padding:2px 0 6px 0;"
            f"background:{DARK_BG};"
        )
        ll.addWidget(self._lbl_last_refresh)

        # Botão limpar
        self._btn_clear = QPushButton(tr("🗑  Limpar dados"))
        btn_clear = self._btn_clear
        btn_clear.setStyleSheet(
            f"QPushButton{{background:{DARK_BG};color:{TEXT_MUTED};"
            f"border:none;border-top:1px solid {BORDER_COLOR};"
            f"padding:10px;font-size:11px;}}"
            f"QPushButton:hover{{color:{ACCENT_RED};}}"
        )
        btn_clear.clicked.connect(self._on_clear)
        ll.addWidget(btn_clear)

        root.addWidget(left)

        # Painel direito — gráficos
        self._chart_view = QWebEngineView()
        from PyQt5.QtWebEngineWidgets import QWebEnginePage
        class _Silent(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, msg, line, src):
                pass
        self._chart_view.setPage(_Silent(self._chart_view))
        self._chart_view.loadFinished.connect(self._on_chart_load_finished)
        root.addWidget(self._chart_view, stretch=1)

        self._render_section(0)

    # ── Orquestração de secções ───────────────────────────────────────────
    def _rebuild_section_list(self):
        """Refreshes section labels and re-renders current metric after a language change."""
        current_row = self._section_list.currentRow()
        self._section_list.clear()
        for label, _ in self.get_sections():
            self._section_list.addItem(label)
        self._section_list.setCurrentRow(current_row)
        # Update button labels
        if hasattr(self, "_btn_refresh"):
            self._btn_refresh.setText(tr("🔄  Actualizar"))
        if hasattr(self, "_btn_clear"):
            self._btn_clear.setText(tr("🗑  Limpar dados"))
        # Re-render the currently visible metric so it picks up the new language
        if current_row >= 0:
            self._render_section(current_row)

    def _on_section_changed(self, row: int):
        if 0 <= row < len(self.get_sections()):
            self._render_section(row)

    def _on_chart_load_finished(self, ok: bool):
        """Chamado quando a página HTML carregou completamente."""
        QTimer.singleShot(500, self._mark_page_ready)

    def _mark_page_ready(self):
        self._page_ready = True
        self._update_refresh_label()
        self._refresh_current()   # refresh imediato ao carregar

    def _on_clear(self):
        reply = QMessageBox.question(
            self, tr("Limpar Métricas"),
            tr("Limpar todos os dados de métricas recolhidos nesta sessão?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._reset_data()
            self._render_section(self._section_list.currentRow())

    def _section_has_data(self, key: str) -> bool:
        """Indica se a secção `key` já tem dados suficientes para sair do ecrã de espera."""
        if key == 'intervals':   return bool(self._data_intervals()['rows'])
        if key == 'neighbors':   return bool(self._nb_links)
        if key == 'range_links': return bool(self._data_range_links()['rows'])
        if key == 'rf':          return bool(self._snr_values or self._hops_values)
        if key == 'channel':     return bool(self._ch_util or self._air_tx)
        if key == 'nodes':       return bool(self._battery or self._packets)
        return True   # secções sem ecrã de espera consideram-se sempre com dados

    # Secções que mostram ecrã de espera enquanto não há dados
    _WAITING_SECTIONS = {'intervals', 'neighbors', 'range_links', 'rf', 'channel', 'nodes'}

    def _refresh_current(self):
        """Actualiza os dados da secção activa.
        - Waiting screen → data available: force full _render_section (setHtml).
        - Data screen: update via runJavaScript (no flash).
        """
        if not self._page_ready:
            return
        key = getattr(self, '_current_key', None)
        if not key:
            return

        # Se esta secção pode mostrar ecrã de espera, verifica se os dados chegaram
        # e se é necessário recarregar completamente para sair do ecrã de espera.
        if key in self._WAITING_SECTIONS:
            if not hasattr(self, '_was_waiting'):
                self._was_waiting = {}
            has_data_now = self._section_has_data(key)
            was_waiting  = self._was_waiting.get(key, True)
            if has_data_now and was_waiting:
                # Transição: espera → dados — recarrega HTML completo
                self._was_waiting[key] = False
                row = self._section_list.currentRow()
                if row >= 0:
                    self._render_section(row)
                return
            self._was_waiting[key] = not has_data_now

        data_fn = {
            'overview':    self._data_overview,
            'channel':     self._data_channel,
            'rf':          self._data_rf,
            'traffic':     self._data_traffic,
            'nodes':       self._data_nodes,
            'reliability': self._data_reliability,
            'latency':     self._data_latency,
            'neighbors':   self._data_neighbors,
            'range_links': self._data_range_links,
            'intervals':   self._data_intervals,
        }.get(key)
        if data_fn is None:
            return
        try:
            payload = json.dumps(data_fn(), ensure_ascii=False)
            self._chart_view.page().runJavaScript(
                f"if(window._metricsUpdateData) window._metricsUpdateData({payload});"
            )
        except Exception as e:
            logger.debug(f"MetricsTab refresh: {e}")

    def _on_auto_refresh(self):
        """Chamado pelo timer de 5s — actualiza só os dados via runJavaScript.
        Sem setHtml: sem flash, sem redesenho do DOM.
        """
        self._refresh_current()
        self._update_refresh_label()

    def _on_manual_refresh(self):
        """Chamado pelo botão Actualizar — força reload completo do HTML."""
        row = self._section_list.currentRow()
        if row >= 0:
            self._render_section(row)

    def _update_refresh_label(self):
        """Actualiza o label com a hora do último refresh."""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._lbl_last_refresh.setText(f"↻ {ts}")

    def _render_section(self, row: int):
        _, key = self.get_sections()[row]
        self._current_key = key
        self._page_ready   = False
        # Não parar _refresh_timer — corre sempre e é protegido pelo JS
        html_fn = {
            'overview':    self._html_overview,
            'channel':     self._html_channel,
            'rf':          self._html_rf,
            'traffic':     self._html_traffic,
            'nodes':       self._html_nodes,
            'reliability': self._html_reliability,
            'latency':     self._html_latency,
            'neighbors':   self._html_neighbors,
            'range_links': self._html_range_links,
            'intervals':   self._html_intervals,
        }.get(key, self._html_overview)
        self._chart_view.setHtml(html_fn())
        self._update_refresh_label()
