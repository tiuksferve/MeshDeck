"""
tabs/tab_metrics.py — Aba de métricas em tempo real: Canal & Airtime,
Qualidade RF, Tráfego, Nós & Bateria, Reliability e Latência.
Usa Chart.js via QWebEngineView para visualização.
"""
import json
import logging
import math
import time
from datetime import datetime

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
from i18n import tr

class MetricsTab(QWidget):
    """
    Aba de métricas em tempo real da rede Meshtastic.
    Recolhe dados de todos os pacotes recebidos e apresenta gráficos
    interactivos por secção usando Chart.js via QWebEngineView.

    Secções:
      1. Visão Geral       — resumo executivo da rede
      2. Canal & Airtime   — utilization do canal e airtime TX (firmware metrics)
      3. Qualidade RF      — distribuição de SNR e hops
      4. Tráfego           — pacotes por tipo e taxa de mensagens/min
      5. Nós & Bateria     — saúde dos nodes, bateria
      6. Reliability       — ACK/NAK, taxa de entrega
    """

    SECTIONS = [
        (tr("📊 Overview"),      "overview"),
        (tr("📡 Channel & Airtime"),  "channel"),
        (tr("📶 RF Quality"),     "rf"),
        (tr("📦 Traffic"),          "traffic"),
        (tr("🔋 Nodes & Battery"),    "nodes"),
        (tr("✅ Reliability"),      "reliability"),
        (tr("⏱ Latency"),         "latency"),
        (tr("🔗 Neighbourhood"),       "neighbors"),
        (tr("📏 Range & Links"),  "range_links"),
        (tr("⏰ Intervals"),       "intervals"),
    ]

    # Limites do canal (documentação oficial Meshtastic)
    CH_UTIL_OK    = 25.0   # abaixo = verde
    CH_UTIL_WARN  = 50.0   # abaixo = laranja; acima = vermelho

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reset_data()
        self._page_ready = False   # True após a página carregar completamente
        # Timer criado ANTES de _build_ui porque _render_section já o usa
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._refresh_current)
        self._build_ui()
        self._refresh_timer.start()

    def _reset_data(self):
        """Inicializa / limpa todas as estruturas de dados de métricas."""
        from collections import deque
        self._start_time  = time.time()

        # Mapa de nomes curtos: nid → short_name (actualizado em cada pacote)
        self._node_short: dict = {}   # nid → short_name ou nid se desconhecido

        # Packets received — lista de (timestamp, from_id, portnum, snr, hops, via_mqtt)
        self._packets: list = []

        # Canal & Airtime — por nó: {nid: [{'ts':..,'ch_util':..,'air_tx':..}]}
        self._ch_util: dict  = {}   # nid → último channelUtilization (%)
        self._air_tx: dict   = {}   # nid → último airUtilTx (%)
        self._ch_util_ts: list = [] # [(ts, valor_average)]  — série temporal 30 pontos

        # Qualidade RF — histogramas
        self._snr_values:  list = []   # todos os SNR recebidos
        self._hops_values: list = []   # todos os hops recebidos

        # Tráfego por tipo de portnum
        self._portnum_counts: dict = {}

        # Bateria por nó  (101 = alimentação externa / powered)
        self._battery: dict  = {}   # nid → nível (0-100 ou 101=powered)
        self._voltage: dict  = {}   # nid → tensão em Volts
        self._uptime:  dict  = {}   # nid → uptimeSeconds

        # Latência — registo de timestamps de envio dos nossos pacotes
        # {packet_id → ts_sent}  — quando chega ACK calcula RTT
        self._sent_ts:    dict  = {}   # packet_id → time.time() quando enviado
        self._rtt_values: list  = []   # lista de RTT em segundos (para stats)

        # Hardware model por nó
        self._hw_model:   dict  = {}   # nid → hw_model string

        # Reliability — local node (mensagens enviadas)
        self._msgs_sent         = 0
        self._msgs_acked        = 0    # ACK real do destinatário
        self._msgs_ack_implicit = 0    # retransmissão local confirmada (não é entrega)
        self._msgs_naked        = 0
        self._sent_packet_ids: set = set()   # IDs dos nossos pacotes enviados (filtro)

        # Reliability — rede (observação passiva de todos os pacotes)
        # Packet IDs vistos: {packet_id → (from_id, timestamp, count_seen)}
        # Duplicados = mesmo ID visto mais de uma vez (sinal de flood saudável)
        self._pkt_ids: dict    = {}    # packet_id → {'from': nid, 'ts': t, 'count': n}
        self._duplicates: int  = 0     # pacotes recebidos com ID já visto
        self._routing_acks: int = 0    # ROUTING_APP com ACKs received na rede
        self._routing_naks: int = 0    # ROUTING_APP com NAKs received na rede
        # Série temporal de PDR observado (janela 30 min)
        self._pdr_ts: list     = []    # [(ts, pct_unique)]

        # Série temporal de nodes activos (janela 60 min, ponto a cada 5s)
        self._nodes_active_ts: list = []  # [(ts, count)]

        # Vizinhança (NeighborInfo) — {nid: [(nb_id, snr), ...]}
        self._nb_links:   dict = {}   # nid → lista de (neighbor_id, snr)

        # Intervalo entre pacotes por nó — {nid: [last_ts, [interval_secs, ...]]}
        self._pkt_intervals: dict = {}  # nid → {'last': ts, 'vals': [s,...]}

        # Alcance por link (calculado de POSITION_APP + GPS coords)
        # {canonical_pair: {'dist_km': float, 'snr': float, 'count': int}}
        self._link_range: dict = {}   # (nid_a, nid_b) → stats

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

        lbl = QLabel("  Metrics")
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
        for label, _ in self.SECTIONS:
            self._section_list.addItem(label)
        self._section_list.setCurrentRow(0)
        self._section_list.currentRowChanged.connect(self._on_section_changed)
        ll.addWidget(self._section_list, stretch=1)

        # Botão limpar
        btn_clear = QPushButton(tr("🗑  Clear data"))
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
        # Marca página como pronta quando o HTML termina de carregar
        self._chart_view.loadFinished.connect(self._on_chart_load_finished)
        root.addWidget(self._chart_view, stretch=1)

        self._render_section(0)

    def _on_section_changed(self, row: int):
        if 0 <= row < len(self.SECTIONS):
            self._render_section(row)

    def _on_chart_load_finished(self, ok: bool):
        """Chamado quando a página HTML carregou completamente."""
        # Aguarda mais 500ms para o Chart.js inicializar os charts
        QTimer.singleShot(500, self._mark_page_ready)

    def _mark_page_ready(self):
        self._page_ready = True
        self._refresh_timer.start()   # retoma o timer periódico
        self._refresh_current()       # refresh imediato para popular dados

    def _on_clear(self):
        reply = QMessageBox.question(
            self, tr("Clear Metrics"),
            tr("Clear all metrics data collected this session?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._reset_data()
            self._render_section(self._section_list.currentRow())

    def _refresh_current(self):
        """Actualiza os dados da secção activa sem recarregar o HTML (sem flash)."""
        key = getattr(self, '_current_key', None)
        if not key:
            return
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

    # ── Ingestão de dados ─────────────────────────────────────────────────
    def ingest_packet(self, packet: dict, node_data: dict):
        """Chamado em cada pacote recebido — extrai e acumula métricas."""
        ts  = time.time()
        nid = packet.get('fromId', '')
        portnum   = (packet.get('decoded') or {}).get('portnum', 'UNKNOWN_APP')
        snr       = packet.get('rxSnr')
        via_mqtt  = packet.get('viaMqtt', False)

        # Guarda nome curto do nó para usar nas tabelas
        sn = (node_data.get('short_name') or '').strip()
        if nid and sn:
            self._node_short[nid] = sn

        # hopsAway do node_data (mais reliable)
        hops = node_data.get('hops_away')

        self._packets.append((ts, nid, portnum, snr, hops, via_mqtt))
        # Manter max 5000 pacotes
        if len(self._packets) > 5000:
            self._packets = self._packets[-4000:]

        # SNR
        if snr is not None:
            self._snr_values.append(float(snr))
            if len(self._snr_values) > 2000:
                self._snr_values = self._snr_values[-1500:]

        # Hops
        if hops is not None:
            self._hops_values.append(int(hops))

        # Portnum counts
        self._portnum_counts[portnum] = self._portnum_counts.get(portnum, 0) + 1

        # Telemetria — channel utilization e airtime
        decoded = packet.get('decoded') or {}
        if portnum == 'TELEMETRY_APP':
            dm = decoded.get('telemetry', {}).get('deviceMetrics', {})
            if dm:
                ch   = dm.get('channelUtilization')
                air  = dm.get('airUtilTx')
                batt = dm.get('batteryLevel')
                volt = dm.get('voltage')
                uptm = dm.get('uptimeSeconds')
                if ch   is not None and nid: self._ch_util[nid]  = float(ch)
                if air  is not None and nid: self._air_tx[nid]   = float(air)
                # batteryLevel=101 significa alimentação externa (powered)
                if batt is not None and nid: self._battery[nid]  = int(batt)
                if volt is not None and nid: self._voltage[nid]  = round(float(volt), 3)
                if uptm is not None and nid: self._uptime[nid]   = int(uptm)
                # Série temporal: média de todos os nodes
                if self._ch_util:
                    avg = sum(self._ch_util.values()) / len(self._ch_util)
                    self._ch_util_ts.append((ts, round(avg, 1)))
                    if len(self._ch_util_ts) > 120:   # 120 pontos ~10min cada = 20h
                        self._ch_util_ts = self._ch_util_ts[-120:]

        # Bateria, channel util e air_tx de qualquer update (node_data enriquecido)
        batt2    = node_data.get('battery_level')
        ch_util2 = node_data.get('channel_utilization')
        air_tx2  = node_data.get('air_util_tx')
        volt2    = node_data.get('voltage')
        uptm2    = node_data.get('uptime_seconds')
        hw2      = node_data.get('hw_model', '')
        if batt2    is not None and nid: self._battery[nid]  = int(batt2)
        if ch_util2 is not None and nid: self._ch_util[nid]  = float(ch_util2)
        if air_tx2  is not None and nid: self._air_tx[nid]   = float(air_tx2)
        if volt2    is not None and nid: self._voltage[nid]  = round(float(volt2), 3)
        if uptm2    is not None and nid: self._uptime[nid]   = int(uptm2)
        if hw2 and nid:
            self._hw_model[nid] = hw2

        # Série temporal de nodes activos (a cada 60s)
        if not self._nodes_active_ts or ts - self._nodes_active_ts[-1][0] >= 60:
            cutoff = ts - 7200  # 2h
            active = len(set(
                p[1] for p in self._packets if p[0] >= cutoff
            ))
            self._nodes_active_ts.append((ts, active))
            if len(self._nodes_active_ts) > 120:
                self._nodes_active_ts = self._nodes_active_ts[-120:]

        # Intervalo entre pacotes por nó
        if nid:
            entry = self._pkt_intervals.setdefault(nid, {'last': None, 'vals': []})
            if entry['last'] is not None:
                interval = ts - entry['last']
                if 1 < interval < 3600:   # ignora gaps > 1h (nó estava offline)
                    entry['vals'].append(round(interval, 1))
                    if len(entry['vals']) > 100:
                        entry['vals'] = entry['vals'][-80:]
            entry['last'] = ts

        # ── Reliability da rede — processada em ingest_raw_packet ─────────

    def ingest_message_status(self, req_id: int, status: str):
        """Regista ACK/NAK APENAS para mensagens enviadas pelo local node."""
        if req_id not in self._sent_packet_ids:
            return
        if status == 'nak':
            self._msgs_naked += 1
            self._sent_packet_ids.discard(req_id)
            self._sent_ts.pop(req_id, None)
        elif status == 'ack':
            self._msgs_acked += 1
            # Calcula RTT se tivermos o timestamp de envio
            sent_at = self._sent_ts.pop(req_id, None)
            if sent_at is not None:
                rtt = round(time.time() - sent_at, 2)
                if 0 < rtt < 300:   # ignora valores impossíveis
                    self._rtt_values.append(rtt)
                    if len(self._rtt_values) > 200:
                        self._rtt_values = self._rtt_values[-150:]
            self._sent_packet_ids.discard(req_id)
        elif status == 'ack_implicit':
            self._msgs_ack_implicit += 1
        self._refresh_if_reliability()

    def ingest_message_sent(self, packet_id: int):
        """Regista mensagem enviada pelo local node com o seu packet_id."""
        self._msgs_sent += 1
        if packet_id:
            self._sent_packet_ids.add(packet_id)
            self._sent_ts[packet_id] = time.time()   # regista timestamp para RTT
        # Força refresh imediato na secção Reliability
        self._refresh_if_reliability()

    def _refresh_if_reliability(self):
        """Dispara refresh imediato se a secção activa for Reliability e a página está pronta."""
        if getattr(self, '_current_key', None) != 'reliability':
            return
        if not getattr(self, '_page_ready', False):
            return   # página ainda a carregar — o timer vai actualizar quando pronta
        # Chama directamente sem singleShot para minimizar latência
        self._refresh_current()


    def retranslate_sections(self):
        """Rebuild section list labels in current language."""
        self._section_list.clear()
        for label, _ in self.SECTIONS:
            self._section_list.addItem(label)
        row = getattr(self, '_current_row', 0)
        self._section_list.setCurrentRow(min(row, len(self.SECTIONS)-1))

    def ingest_neighbor_info(self, from_id: str, neighbors: list):
        """Regista dados de NeighborInfo para a tabela de vizinhança nas métricas."""
        if from_id and neighbors:
            self._nb_links[from_id] = neighbors

    def ingest_raw_packet(self, packet: dict):
        """Processa pacote raw para métricas de fiabilidade da rede (todos os nodes)."""
        ts      = time.time()
        pkt_id  = packet.get('id')
        nid     = packet.get('fromId', '')
        decoded = packet.get('decoded') or {}
        portnum = decoded.get('portnum', '')

        # ── Duplicados (flood) ─────────────────────────────────────────
        # Rastreia IDs unique; duplicados = mesmo ID recebido via múltiplos nodes
        # Indica flood activo (saudável) vs congestionamento (excessivo)
        if pkt_id and nid:
            if pkt_id in self._pkt_ids:
                self._duplicates += 1
                self._pkt_ids[pkt_id]['count'] += 1
                # Actualiza ts para o mais recente (mantém o ID vivo na janela)
                self._pkt_ids[pkt_id]['ts'] = ts
            else:
                self._pkt_ids[pkt_id] = {'from': nid, 'ts': ts, 'count': 1}
            # Manter apenas últimos 5 minutos de IDs
            cutoff_ids = ts - 300
            self._pkt_ids = {k: v for k, v in self._pkt_ids.items()
                             if v['ts'] >= cutoff_ids}

        # ── ACK/NAK da rede (ROUTING_APP) ─────────────────────────────
        # Conta todos os ROUTING_APP vistos na rede:
        #   - Com requestId: respostas directas a mensagens (ACK/NAK de entrega)
        #   - Sem requestId: erros internos do firmware (NO_ROUTE, MAX_RETRANSMIT)
        #                    — também indicam problemas de fiabilidade na rede
        if portnum == 'ROUTING_APP':
            routing = decoded.get('routing', {}) or {}
            err = (routing.get('errorReason', 'NONE') or 'NONE').upper()
            if err != 'NONE' and err != '':
                self._routing_naks += 1
            else:
                # Só conta ACK se tem requestId (resposta a pedido real)
                request_id = decoded.get('requestId', 0)
                if request_id:
                    self._routing_acks += 1

    # ── Renderização de secções ───────────────────────────────────────────
    def _render_section(self, row: int):
        _, key = self.SECTIONS[row]
        self._current_key = key
        self._page_ready   = False   # página ainda não carregou
        self._refresh_timer.stop()   # pausa timer até loadFinished
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
        # O timer é retomado em _mark_page_ready via loadFinished + 500ms

    def _base_html(self, title: str, body: str) -> str:
        """Template HTML base com Chart.js e estilos."""
        return f"""<!DOCTYPE html><html><head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; color: #e6edf3; font-family: 'Segoe UI', Arial, sans-serif;
         font-size: 13px; padding: 16px; overflow-y: auto; }}
  h2 {{ color: #39d353; font-size: 16px; margin-bottom: 4px; }}
  .subtitle {{ color: #8b949e; font-size: 11px; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
           padding: 14px; }}
  .card h3 {{ color: #8b949e; font-size: 11px; font-weight: normal;
              text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
  .kpi {{ font-size: 32px; font-weight: bold; color: #e6edf3; }}
  .kpi-sub {{ font-size: 11px; color: #8b949e; margin-top: 2px; }}
  .kpi.green {{ color: #39d353; }}
  .kpi.orange {{ color: #f0883e; }}
  .kpi.red {{ color: #f85149; }}
  .kpi.blue {{ color: #58a6ff; }}
  .bar-wrap {{ margin-top: 6px; }}
  .bar-bg {{ background: #21262d; border-radius: 4px; height: 8px; overflow: hidden; }}
  .bar-fill {{ height: 8px; border-radius: 4px; transition: width 0.5s; }}
  .chart-wrap {{ position: relative; height: 220px; }}
  .chart-wrap-lg {{ position: relative; height: 280px; }}
  .full {{ grid-column: 1 / -1; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ color: #8b949e; text-align: left; padding: 6px 8px;
        border-bottom: 1px solid #30363d; font-weight: normal; font-size: 11px; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #21262d; }}
  tr:hover td {{ background: #21262d; }}
  .tag {{ display: inline-block; padding: 1px 6px; border-radius: 4px;
           font-size: 10px; font-weight: bold; }}
  .tag-green {{ background: #1a3d1a; color: #39d353; }}
  .tag-orange {{ background: #3d2a0a; color: #f0883e; }}
  .tag-red {{ background: #3d0a0a; color: #f85149; }}
  .tag-blue {{ background: #0a1f3d; color: #58a6ff; }}
  .tag-gray {{ background: #21262d; color: #8b949e; }}
  .no-data {{ color: #8b949e; text-align: center; padding: 40px 0; font-size: 13px; }}
  .updated {{ color: #8b949e; font-size: 10px; text-align: right; margin-top: 12px; }}
</style>
</head><body>
<h2>{title}</h2>
{body}
</body></html>"""

    def _ts_label(self, ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime('%H:%M')

    def _now_str(self) -> str:
        return datetime.now().strftime('%H:%M:%S')


    # ── Funções de dados para actualização sem reload ──────────────────────
    def _data_overview(self) -> dict:
        now = time.time()
        total_pkts = len(self._packets)
        active_nids = set(p[1] for p in self._packets if p[0] >= now-7200 and p[1])
        ppm = len([p for p in self._packets if p[0] >= now-60])
        snr_avg = round(sum(self._snr_values)/len(self._snr_values),1) if self._snr_values else None
        hops_avg = round(sum(self._hops_values)/len(self._hops_values),2) if self._hops_values else None
        ch_avg = round(sum(self._ch_util.values())/len(self._ch_util),1) if self._ch_util else None
        air_avg = round(sum(self._air_tx.values())/len(self._air_tx),1) if self._air_tx else None
        total_r = self._msgs_acked + self._msgs_naked
        delivery = round(self._msgs_acked/total_r*100,1) if total_r>0 else None
        nid_counts = {}
        for p in self._packets:
            if p[1]: nid_counts[p[1]] = nid_counts.get(p[1],0)+1
        top = sorted(nid_counts.items(), key=lambda x:-x[1])[:8]
        table_rows = [[self._name(nid), cnt, round(self._ch_util.get(nid,0),1),
                       self._battery.get(nid)] for nid,cnt in top]
        return {"total_pkts":total_pkts,"n_active":len(active_nids),"ppm":ppm,
                "snr_avg":snr_avg,"hops_avg":hops_avg,"ch_avg":ch_avg,"air_avg":air_avg,
                "delivery":delivery,"table_rows":table_rows,"now":self._now_str()}

    def _data_channel(self) -> dict:
        duty = {nid: round(min(a*6,100.0),2) for nid,a in self._air_tx.items()}
        duty_avg = round(sum(duty.values())/len(duty),2) if duty else None
        air_avg  = round(sum(self._air_tx.values())/len(self._air_tx),2) if self._air_tx else None
        ch_net_avg = round(sum(self._ch_util.values())/len(self._ch_util),1) if self._ch_util else None
        ts_labels = [self._ts_label(t) for t,_ in self._ch_util_ts]
        ts_vals   = [v for _,v in self._ch_util_ts]
        rows=[]
        for nid in sorted(set(list(self._ch_util.keys())+list(self._air_tx.keys()))):
            ch=self._ch_util.get(nid,0); air=self._air_tx.get(nid,0)
            dc=duty.get(nid,round(min(air*6,100.0),2))
            rows.append([self._name(nid), round(ch,1), round(air,2), dc])
        return {"duty_avg":duty_avg,"air_avg":air_avg,"ch_net_avg":ch_net_avg,
                "ts_labels":ts_labels,"ts_vals":ts_vals,"rows":rows,"now":self._now_str()}

    def _name(self, nid: str) -> str:
        """Devolve o nome curto do nó se disponível, senão o ID."""
        return self._node_short.get(nid, nid) if nid else nid

    def _rf_assessment(self, snr_avg, snr_med, snr_p10, hops_values) -> str:
        """Avaliação da qualidade RF da rede baseada em distribuição de pacotes por faixa de SNR."""
        if snr_avg is None or not self._snr_values:
            return "⏳ Waiting for enough data for assessment..."

        n = len(self._snr_values)
        # Distribuição por faixa — igual às apps iOS/Android
        pct_exc  = round(sum(1 for v in self._snr_values if v >= 8)   / n * 100)  # ≥ 8dB excelente
        pct_good = round(sum(1 for v in self._snr_values if 5 <= v < 8) / n * 100)  # 5–8 bom
        pct_marg = round(sum(1 for v in self._snr_values if 0 <= v < 5) / n * 100)  # 0–5 marginal
        pct_weak = round(sum(1 for v in self._snr_values if v < 0)     / n * 100)  # <0 fraco
        pct_ok = pct_exc + pct_good

        lines = []

        # ── Análise da distribuição ──────────────────────────────────────
        lines.append(
            f"<b>Quality distribution</b> in " + str(n) + " packets: "
            f"<span style='color:#39d353'>{pct_exc}% excellent (≥8dB)</span> · "
            f"<span style='color:#56d364'>{pct_good}% good (5–8dB)</span> · "
            f"<span style='color:#f0883e'>{pct_marg}% marginal (0–5dB)</span> · "
            f"<span style='color:#f85149'>{pct_weak}% weak (&lt;0dB)</span>"
        )

        # ── Avaliação global ─────────────────────────────────────────────
        if pct_ok >= 80:
            lines.append("✅ <b>Network in excellent RF condition.</b> The vast majority of packets chega com sinal forte.")
        elif pct_ok >= 60:
            lines.append("✅ <b>Good RF quality.</b> Most links are stable with some margins.")
        elif pct_ok >= 40:
            lines.append("⚠️ <b>Moderate RF quality.</b> A significant portion of packets is in the marginal zone — risk of loss in adverse conditions.")
        else:
            lines.append("🚨 <b>Weak RF quality.</b> Over 60% of packets arrive with poor signal. Check antennas and positioning.")

        # ── SNR P10 (worst 10%) ───────────────────────────────────────────
        if snr_p10 is not None:
            if snr_p10 < -10:
                lines.append(f"⚠️ <b>Worst decile:</b> SNR ≤ {snr_p10} dB — some links severely degraded, frequent packet loss possible.")
            elif snr_p10 < 0:
                lines.append(f"ℹ️ <b>Worst decile:</b> SNR ≤ {snr_p10} dB — marginal links at coverage edge.")
            else:
                lines.append(f"✅ <b>Worst decile:</b> SNR ≥ {snr_p10} dB — even the worst paths have reasonable signal.")

        # ── Análise de hops ──────────────────────────────────────────────
        if hops_values:
            avg_hops = sum(hops_values) / len(hops_values)
            pct_direct = round(hops_values.count(0) / len(hops_values) * 100)
            pct_1hop   = round(hops_values.count(1) / len(hops_values) * 100)
            max_hops   = max(hops_values)
            lines.append(
                f"<b>Topology:</b> {pct_direct}% direct · {pct_1hop}% at 1 hop · avg {avg_hops:.1f} hops · max {max_hops} hops."
            )
            if avg_hops > 2.5:
                lines.append("⚠️ High average hops — network relies heavily on repeaters. May increase latency and congestion.")
            if max_hops >= 6:
                lines.append(f"⚠️ Maximum of {max_hops} hops detected — near firmware limit (7). Consider reviewing the configured hop limit.")

        # ── Conclusão ────────────────────────────────────────────────────
        if pct_ok >= 70 and (not hops_values or sum(hops_values)/len(hops_values) < 2):
            lines.append("<br><b>Conclusion:</b> Healthy and well-sized RF network. 🟢")
        elif pct_ok >= 50:
            lines.append("<br><b>Conclusion:</b> Functional network with room for improvement. Monitor during high traffic periods. 🟡")
        else:
            lines.append("<br><b>Conclusion:</b> RF quality below expectations. Review antenna infrastructure, positioning and radio mode. 🔴")

        return "<br>".join(lines)

    def _data_rf(self) -> dict:
        def histogram(vals,bucket=2,mn=-20,mx=14):
            buckets=list(range(mn,mx+bucket,bucket)); counts=[0]*len(buckets)
            for v in vals:
                idx=min(int((v-mn)//bucket),len(counts)-1); idx=max(0,idx); counts[idx]+=1
            return [str(b) for b in buckets], counts
        snr_labels,snr_counts = histogram(self._snr_values) if self._snr_values else ([],[])
        max_hops = max(self._hops_values) if self._hops_values else 7
        hop_labels=[str(i) for i in range(0,min(max_hops+2,9))]
        hop_counts=[self._hops_values.count(i) for i in range(len(hop_labels))]
        n=len(self._snr_values)
        snr_sorted=sorted(self._snr_values)
        snr_avg = round(sum(snr_sorted)/n,1) if n else None
        snr_med = round(snr_sorted[n//2],1) if n else None
        snr_p10 = round(snr_sorted[max(0,n//10)],1) if n else None
        assessment = self._rf_assessment(snr_avg, snr_med, snr_p10, self._hops_values)
        return {"n":n, "snr_avg":snr_avg, "snr_med":snr_med, "snr_p10":snr_p10,
                "snr_labels":snr_labels,"snr_counts":snr_counts,
                "hop_labels":hop_labels,"hop_counts":hop_counts,
                "assessment": assessment}

    def _data_traffic(self) -> dict:
        now = time.time()
        label_map={"TEXT_MESSAGE_APP":"💬 Mensagem","NODEINFO_APP":"🆔 NodeInfo",
                   "POSITION_APP":"📍 Position","TELEMETRY_APP":"📊 Telemetry",
                   "TRACEROUTE_APP":"🔍 Traceroute","ROUTING_APP":"🔀 Routing",
                   "NEIGHBORINFO_APP":"🔗 NeighborInfo","ADMIN_APP":"⚙ Admin",
                   "RANGE_TEST_APP":"📏 Range Test","STORE_AND_FORWARD_APP":"📦 S&F"}
        # Sessão inteira
        counts={}
        for pname,cnt in self._portnum_counts.items():
            lbl=label_map.get(pname,pname.replace("_APP","").replace("_"," ").title())
            counts[lbl]=counts.get(lbl,0)+cnt
        sc=sorted(counts.items(),key=lambda x:-x[1])
        labels=[k for k,_ in sc]; values=[v for _,v in sc]
        # Pattern of routing
        n_direct  = sum(1 for p in self._packets if p[4] == 0)
        n_1hop    = sum(1 for p in self._packets if p[4] == 1)
        n_multi   = sum(1 for p in self._packets if p[4] is not None and p[4] >= 2)
        n_unknown = sum(1 for p in self._packets if p[4] is None)
        n_rf=len([p for p in self._packets if not p[5]])
        n_mqtt=len([p for p in self._packets if p[5]])
        bins=[]
        for i in range(29,-1,-1):
            t0=now-(i+1)*60; t1=now-i*60
            cnt=len([p for p in self._packets if t0<=p[0]<t1])
            bins.append((datetime.fromtimestamp(t1).strftime("%H:%M"),cnt))
        return {"labels":labels,"values":values,
                "n_direct":n_direct,"n_1hop":n_1hop,"n_multi":n_multi,"n_unknown":n_unknown,
                "n_rf":n_rf,"n_mqtt":n_mqtt,
                "ppm_labels":[b[0] for b in bins],"ppm_vals":[b[1] for b in bins]}

    def _data_nodes(self) -> dict:
        now = time.time()
        cutoff2h = now - 7200
        n_active = len(set(p[1] for p in self._packets if p[0] >= cutoff2h and p[1]))

        # Bateria — exclui 0 (sem dados) e trata 101 como "Powered"
        batt_real  = {nid: v for nid, v in self._battery.items() if 1 <= v <= 100}
        batt_power = {nid for nid, v in self._battery.items() if v == 101}
        batt_buckets = [0, 0, 0, 0, 0]   # 0-20, 20-40, 40-60, 60-80, 80-100
        for v in batt_real.values():
            batt_buckets[min(int(v // 20), 4)] += 1
        batt_avg = round(sum(batt_real.values()) / len(batt_real), 0) if batt_real else None

        # Linhas de bateria ordenadas (pior primeiro), com tensão se disponível
        batt_rows = []
        for nid, v in sorted(self._battery.items(), key=lambda x: x[1]):
            volt = self._voltage.get(nid)
            uptm = self._uptime.get(nid)
            batt_rows.append([nid, v, volt, uptm])

        # Hardware model distribution
        hw_model = self._hw_model
        hw_counts: dict = {}
        for nid, hw in hw_model.items():
            hw_counts[hw] = hw_counts.get(hw, 0) + 1
        hw_sorted = sorted(hw_counts.items(), key=lambda x: -x[1])

        # Nodes with GPS
        # Contados da lista de pacotes unique que tiveram um POSITION_APP
        n_gps = sum(1 for p in self._packets
                    if p[2] == 'POSITION_APP' and p[1])
        n_gps_unique = len(set(p[1] for p in self._packets
                               if p[2] == 'POSITION_APP' and p[1]))

        ts_labels = [self._ts_label(t) for t, _ in self._nodes_active_ts]
        ts_vals   = [v for _, v in self._nodes_active_ts]

        return {
            "n_active": n_active,
            "n_battery": len(self._battery), "n_powered": len(batt_power),
            "batt_avg": batt_avg,
            "ts_labels": ts_labels, "ts_vals": ts_vals,
            "batt_buckets": batt_buckets, "batt_rows": batt_rows,
            "hw_labels": [h for h, _ in hw_sorted],
            "hw_values": [c for _, c in hw_sorted],
            "n_gps_unique": n_gps_unique,
        }

    def _data_reliability(self) -> dict:
        now = time.time()

        # ── Nó local ────────────────────────────────────────────────────
        total_resp = self._msgs_acked + self._msgs_naked
        delivery   = round(self._msgs_acked / total_resp * 100, 1) if total_resp > 0 else None
        nak_rate   = round(self._msgs_naked / total_resp * 100, 1) if total_resp > 0 else None
        # pending: mensagens enviadas que ainda não têm resposta (ACK real ou NAK)
        # ack_implicit não é resposta final — mantemos pendentes
        pending    = max(self._msgs_sent - self._msgs_acked - self._msgs_naked, 0)

        # ── RTT (round-trip time) ─────────────────────────────────────
        rtt_avg = round(sum(self._rtt_values) / len(self._rtt_values), 1) if self._rtt_values else None
        rtt_min = round(min(self._rtt_values), 1) if self._rtt_values else None
        rtt_max = round(max(self._rtt_values), 1) if self._rtt_values else None
        rtt_med = round(sorted(self._rtt_values)[len(self._rtt_values)//2], 1) if self._rtt_values else None

        # ── Rede ────────────────────────────────────────────────────────
        total_pkt      = len(self._pkt_ids)
        dup_rate       = round(self._duplicates / max(total_pkt, 1) * 100, 1) if total_pkt > 0 else None
        net_ack_total  = self._routing_acks + self._routing_naks
        net_nak_rate   = round(self._routing_naks / net_ack_total * 100, 1) if net_ack_total > 0 else None
        active_senders = len(set(v["from"] for v in self._pkt_ids.values()))

        # Probabilidade de colisão estimada (modelo Poisson para LoRa com CAD)
        # p_col = (1 - e^(-ch_util/100)) * 100 * 0.5
        # O factor 0.5 reflecte que o CAD (Channel Activity Detection) do LoRa
        # reduz colisões em ~50% vs ALOHA puro.
        ch_util_avg = (sum(self._ch_util.values()) / len(self._ch_util)
                       if self._ch_util else None)
        if ch_util_avg is not None:
            p_col = round((1 - math.exp(-ch_util_avg / 100.0)) * 100 * 0.5, 1)
        else:
            p_col = None

        return {
            "sent": self._msgs_sent, "acked": self._msgs_acked,
            "ack_implicit": self._msgs_ack_implicit,
            "naked": self._msgs_naked, "pending": pending,
            "delivery": delivery, "nak_rate": nak_rate,
            "rtt_avg": rtt_avg, "rtt_min": rtt_min,
            "rtt_max": rtt_max, "rtt_med": rtt_med,
            "n_rtt": len(self._rtt_values),
            "total_pkt": total_pkt, "duplicates": self._duplicates,
            "dup_rate": dup_rate,
            "net_acks": self._routing_acks, "net_naks": self._routing_naks,
            "net_nak_rate": net_nak_rate, "active_senders": active_senders,
            "p_col": p_col,
            "ch_util_avg": round(ch_util_avg, 1) if ch_util_avg is not None else None,
        }

    # ── 1. Visão Geral ────────────────────────────────────────────────────
    def _html_overview(self) -> str:
        now = time.time()
        total_pkts = len(self._packets)
        cutoff2h   = now - 7200
        active_nids = set(p[1] for p in self._packets if p[0] >= cutoff2h and p[1])
        n_active   = len(active_nids)

        # Pacotes último minuto
        ppm = len([p for p in self._packets if p[0] >= now - 60])

        snr_avg = round(sum(self._snr_values) / len(self._snr_values), 1) if self._snr_values else None
        hops_avg = round(sum(self._hops_values) / len(self._hops_values), 2) if self._hops_values else None

        ch_util_avg = round(sum(self._ch_util.values()) / len(self._ch_util), 1) if self._ch_util else None
        air_avg     = round(sum(self._air_tx.values()) / len(self._air_tx), 1) if self._air_tx else None

        # Delivery rate
        total_r = self._msgs_acked + self._msgs_naked
        delivery = round(self._msgs_acked / total_r * 100, 1) if total_r > 0 else None

        def kpi(val, unit, label, color=""):
            v = f"{val}{unit}" if val is not None else "—"
            return f'<div class="card"><h3>{label}</h3><div class="kpi {color}">{v}</div></div>'

        def ch_kpi(val):
            if val is None: return kpi(None, "", "Channel Util. (avg)")
            color = "green" if val < self.CH_UTIL_OK else ("orange" if val < self.CH_UTIL_WARN else "red")
            bar_color = "#39d353" if val < self.CH_UTIL_OK else ("#f0883e" if val < self.CH_UTIL_WARN else "#f85149")
            pct = min(int(val), 100)
            return f'''<div class="card"><h3>Channel Util. (avg)</h3>
              <div class="kpi {color}">{val}%</div>
              <div class="bar-wrap"><div class="bar-bg">
              <div class="bar-fill" style="width:{pct}%;background:{bar_color}"></div>
              </div></div>
              <div class="kpi-sub">&lt;25% optimal · &lt;50% acceptable · &gt;50% critical</div>
            </div>'''

        # Tabela top nodes por pacotes
        nid_counts = {}
        for p in self._packets:
            if p[1]: nid_counts[p[1]] = nid_counts.get(p[1], 0) + 1
        top = sorted(nid_counts.items(), key=lambda x: -x[1])[:8]
        rows = "".join(
            f"<tr><td>{self._name(nid)}</td><td>{cnt}</td>"
            f"<td>{round(self._ch_util.get(nid, 0), 1)}%</td>"
            f"<td>{self._battery.get(nid, '—')}{'%' if self._battery.get(nid) is not None else ''}</td></tr>"
            for nid, cnt in top
        ) or "<tr><td colspan='4' class='no-data'>No data yet</td></tr>"

        body = f"""
<div class="subtitle">Session summary · Updated: {self._now_str()}</div>
<div class="grid-3">
  {kpi(total_pkts, "", "Total Packets", "blue")}
  {kpi(n_active, " nodes", "Active Nodes (2h)", "green")}
  {kpi(ppm, "/min", "Packets/min", "")}
</div>
<div class="grid-3">
  {kpi(snr_avg, " dB", "Avg SNR", "green" if snr_avg and snr_avg >= 0 else "orange")}
  {kpi(hops_avg, " hops", "Avg Hops", "")}
  {kpi(delivery, "%", "Delivery rate", "green" if delivery and delivery >= 80 else "orange")}
</div>
<div class="grid">
  {ch_kpi(ch_util_avg)}
  {kpi(air_avg, "%", "Airtime TX (avg)", "green" if air_avg and air_avg < 10 else "orange")}
</div>
<div class="card" style="margin-top:16px">
  <h3>Top Nodes by Packets</h3>
  <table><tr><th>ID</th><th>Packets</th><th>Ch. Util.</th><th>Battery</th></tr>{rows}</table>
</div>
<div class="updated">Session started · {datetime.fromtimestamp(self._start_time).strftime('%H:%M:%S %d/%m/%Y')}</div>
<script>
window._metricsUpdateData = function(d) {{
  function set(id, val) {{ var e=document.getElementById(id); if(e) e.textContent=val; }}
  function setClass(id, cls) {{ var e=document.getElementById(id); if(e) {{ e.className='kpi '+cls; }} }}
  set('kpi-pkts', d.total_pkts);
  set('kpi-active', (d.n_active || '—') + (d.n_active !== null ? ' nodes' : ''));
  set('kpi-ppm', (d.ppm || 0) + '/min');
  set('kpi-snr', d.snr_avg !== null ? d.snr_avg + ' dB' : '—');
  set('kpi-hops', d.hops_avg !== null ? d.hops_avg + ' hops' : '—');
  set('kpi-delivery', d.delivery !== null ? d.delivery + '%' : '—');
  set('kpi-chutil', d.ch_avg !== null ? d.ch_avg + '%' : '—');
  set('kpi-air', d.air_avg !== null ? d.air_avg + '%' : '—');
  set('updated-ts', 'Actualizado: ' + d.now);
}};
</script>"""
        return self._base_html("📊 Overview", body)

    # ── 2. Canal & Airtime ────────────────────────────────────────────────
    # Limites de duty cycle horário (EU_433 / EU_868 — ETSI EN300.220)
    DUTY_CYCLE_LIMIT_EU = 10.0   # 10%/hora — limite legal EU
    DUTY_CYCLE_WARN_EU  =  7.0   # 7%/hora — aviso preventivo

    def _html_channel(self) -> str:
        if not self._ch_util and not self._ch_util_ts and not self._air_tx:
            body = '<div class="no-data">⏳ Waiting for telemetry data (TELEMETRY_APP)...<br><br>Nodes must have the telemetry module enabled.</div>'
            return self._base_html("📡 Channel & Airtime", body)

        # Hourly Duty Cycle estimado: airUtilTx (10 min) × 6 = estimativa 1h
        # airUtilTx é uma métrica POR NÓ (tx of that node).
        # channelUtilization é da REDE (rx+tx de todos os dispositivos no canal).
        # Mostramos o pior nó (mais alto duty cycle) como indicador de risco.
        # Fonte: ETSI EN300.220 — EU_433/EU_868 limite 10%/hora.
        duty_per_node = {nid: round(min(air * 6, 100.0), 2)
                         for nid, air in self._air_tx.items()}

        # Nó com maior duty cycle (pior caso)
        worst_nid = max(duty_per_node, key=duty_per_node.get) if duty_per_node else None
        worst_dc  = duty_per_node[worst_nid] if worst_nid else None

        ts_labels = [self._ts_label(t) for t, _ in self._ch_util_ts]
        ts_vals   = [v for _, v in self._ch_util_ts]

        def duty_status(dc):
            if dc >= self.DUTY_CYCLE_LIMIT_EU: return "red",    "🚨 LIMIT EXCEEDED"
            if dc >= self.DUTY_CYCLE_WARN_EU:  return "orange", "⚠ Near limit"
            return "green", "✅ Normal"

        # Tabela por nó
        rows = ""
        all_nids = sorted(set(list(self._ch_util.keys()) + list(self._air_tx.keys())))
        for nid in all_nids:
            ch  = self._ch_util.get(nid, 0)
            air = self._air_tx.get(nid, 0)
            dc  = duty_per_node.get(nid, round(min(air * 6, 100.0), 2))
            ch_tag  = "green" if ch  < self.CH_UTIL_OK  else ("orange" if ch  < self.CH_UTIL_WARN else "red")
            air_tag = "green" if air < 10               else ("orange" if air < 25               else "red")
            dc_color, dc_label = duty_status(dc)
            dc_pct = min(int(dc / self.DUTY_CYCLE_LIMIT_EU * 100), 100)
            bar_c  = {"green": "#39d353", "orange": "#f0883e", "red": "#f85149"}[dc_color]
            worst_mark = " 🔺" if nid == worst_nid and worst_dc and worst_dc >= self.DUTY_CYCLE_WARN_EU else ""
            display_name = self._name(nid)
            rows += (
                f"<tr><td>{display_name}{worst_mark}</td>"
                f"<td><span class='tag tag-{ch_tag}'>{ch:.1f}%</span></td>"
                f"<td><span class='tag tag-{air_tag}'>{air:.2f}%</span></td>"
                f"<td><span class='tag tag-{dc_color}'>{dc:.2f}%</span>"
                f"  <div class='bar-bg' style='margin-top:3px'>"
                f"  <div class='bar-fill' style='width:{dc_pct}%;background:{bar_c}'></div></div></td>"
                f"<td style='font-size:11px'>{dc_label}</td></tr>"
            )
        if not rows:
            rows = "<tr><td colspan='5' class='no-data'>No data</td></tr>"

        # KPI: pior nó (mais relevante para conformidade EU)
        # KPI principal: channelUtilization average da rede
        # (cada nó reporta o que VÊ no canal — é a métrica da rede, não do node)
        ch_net_avg = round(sum(self._ch_util.values()) / len(self._ch_util), 1) if self._ch_util else None
        if ch_net_avg is not None:
            ch_color = "green" if ch_net_avg < self.CH_UTIL_OK else ("orange" if ch_net_avg < self.CH_UTIL_WARN else "red")
            ch_bar_c = {"green": "#39d353", "orange": "#f0883e", "red": "#f85149"}[ch_color]
            ch_pct   = min(int(ch_net_avg), 100)
            ch_label = "✅ Optimal (<25%)" if ch_net_avg < self.CH_UTIL_OK else ("⚠ Acceptable (<50%)" if ch_net_avg < self.CH_UTIL_WARN else "🚨 Critical (>50%)")
            ch_kpi = (
                f'<div class="card"><h3>Network Channel Utilization</h3>'
                f'<div id="ch-net-val" class="kpi {ch_color}">{ch_net_avg}%</div>'
                f'<div class="bar-wrap"><div class="bar-bg">'
                f'<div class="bar-fill" style="width:{ch_pct}%;background:{ch_bar_c}"></div></div></div>'
                f'<div class="kpi-sub"><b>Network metric</b> — observed airtime per node (RX+TX of all) · {ch_label}<br>'
                f'Firmware delays above 25% · GPS limit: 40%</div></div>'
            )
        else:
            ch_kpi = '<div class="card"><h3>Network Channel Utilization</h3><div class="kpi" style="color:#8b949e">—</div><div class="kpi-sub">Waiting for telemetry data...</div></div>'

        # KPI secundário: duty cycle do pior nó (airUtilTx por nó — conformidade EU)
        if worst_dc is not None:
            worst_name = self._name(worst_nid)
            dc_color_w, dc_label_w = duty_status(worst_dc)
            dc_pct_w = min(int(worst_dc / self.DUTY_CYCLE_LIMIT_EU * 100), 100)
            bar_c_w  = {"green": "#39d353", "orange": "#f0883e", "red": "#f85149"}[dc_color_w]
            duty_kpi = (
                f'<div class="card"><h3>Duty Cycle/h — Worst Node ({worst_name})</h3>'
                f'<div id="dc-avg-val" class="kpi {dc_color_w}">{worst_dc}%</div>'
                f'<div class="bar-wrap"><div class="bar-bg">'
                f'<div class="bar-fill" style="width:{dc_pct_w}%;background:{bar_c_w}"></div></div></div>'
                f'<div class="kpi-sub"><b>Per-node metric</b> (TX of that node) · airUtilTx×6 · EU limit: 10%/hour · {dc_label_w}</div></div>'
            )
        else:
            duty_kpi = '<div class="card"><h3>Duty Cycle/h per Node</h3><div class="kpi" style="color:#8b949e">—</div><div class="kpi-sub">Waiting for airUtilTx data...</div></div>'

        air_avg = round(sum(self._air_tx.values()) / len(self._air_tx), 2) if self._air_tx else None
        air_color = "green" if air_avg and air_avg < 10 else ("orange" if air_avg else "")
        air_kpi = (
            f'<div class="card"><h3>Airtime TX (10 min, avg)</h3>'
            f'<div class="kpi {air_color}">{air_avg if air_avg is not None else "—"}'
            f'{"%" if air_avg is not None else ""}</div>'
            f'<div class="kpi-sub">Avg TX of all nodes in the last 10 min</div></div>'
        )

        n_ts = len(ts_vals) or 1
        body = f"""
<div class="subtitle">LoRa Channel · Airtime TX · Hourly Duty Cycle · {self._now_str()}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #39d353;padding:8px 14px">
  <span style="color:#39d353;font-size:12px;font-weight:bold">🌐 Network Metric</span><span style="color:#8b949e;font-size:11px"> — data below is passively observed from all packets received by the local node. Reflects the state of the entire visible network, not just the local node.</span>
</div>
<div class="grid-3">{ch_kpi}{duty_kpi}{air_kpi}</div>
<div class="card" style="margin-top:16px">
  <h3>Channel Utilization Over Time</h3>
  <div class="chart-wrap-lg"><canvas id="chChart"></canvas></div>
</div>
<div class="card" style="margin-top:16px">
  <h3>Per Node — Ch. Util · Airtime TX · Duty Cycle/h</h3>
  <table><tr><th>Node</th><th>Ch. Util.</th><th>Air TX (10m)</th><th>Duty Cycle/h</th><th>Status</th></tr>{rows}</table>
  <div style="color:#8b949e;font-size:10px;margin-top:8px;padding-top:8px;border-top:1px solid #21262d">
    ⚙️ Estimated hourly duty cycle = airUtilTx × 6. EU limit433/EU_868: 10%/hora (ETSI EN300.220).
  </div>
</div>
<script>
window._chChart = new Chart(document.getElementById('chChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(ts_labels)},
    datasets: [
      {{ label: 'Ch. Utilization (%)', data: {json.dumps(ts_vals)},
         borderColor: '#39d353', backgroundColor: 'rgba(57,211,83,0.08)',
         fill: true, tension: 0.3, pointRadius: 2 }},
      {{ label: 'Optimal limit (25%)', data: Array({n_ts}).fill(25),
         borderColor: '#f0883e', borderDash: [4,4], pointRadius: 0, fill: false }},
      {{ label: 'Critical limit (50%)', data: Array({n_ts}).fill(50),
         borderColor: '#f85149', borderDash: [4,4], pointRadius: 0, fill: false }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ min: 0, max: 100, grid: {{ color: '#21262d' }},
            ticks: {{ color: '#8b949e', callback: v => v + '%' }} }},
      x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxTicksLimit: 10 }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#8b949e', boxWidth: 12 }} }},
                tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%' }} }} }}
  }}
}});
</script>
<script>
window._metricsUpdateData = function(d) {{
  function set(id, v) {{ var e=document.getElementById(id); if(e) e.textContent=v; }}
  set('ch-net-val', d.ch_net_avg !== null && d.ch_net_avg !== undefined ? d.ch_net_avg + '%' : '—');
  set('dc-avg-val', d.duty_avg !== null ? d.duty_avg + '%' : '—');
  set('air-avg-val', d.air_avg !== null ? d.air_avg + '%' : '—');
  set('ch-updated', d.now);
  if(window._chChart && d.ts_vals && d.ts_vals.length > 0) {{
    window._chChart.data.labels = d.ts_labels;
    window._chChart.data.datasets[0].data = d.ts_vals;
    var n = d.ts_vals.length || 1;
    window._chChart.data.datasets[1].data = Array(n).fill(25);
    window._chChart.data.datasets[2].data = Array(n).fill(50);
    window._chChart.update('none');
  }}
}};
</script>"""
        return self._base_html("📡 Channel & Airtime", body)

    # ── 3. Qualidade RF ───────────────────────────────────────────────────
    def _html_rf(self) -> str:
        if not self._snr_values and not self._hops_values:
            body = '<div class="no-data">⏳ Waiting for RF packets...</div>'
            return self._base_html("📶 RF Quality", body)

        # Histograma SNR em buckets de 2dB
        def histogram(vals, bucket=2, mn=-20, mx=14):
            buckets = list(range(mn, mx + bucket, bucket))
            counts  = [0] * len(buckets)
            for v in vals:
                idx = min(int((v - mn) // bucket), len(counts) - 1)
                idx = max(0, idx)
                counts[idx] += 1
            labels = [f"{b}" for b in buckets]
            return labels, counts

        snr_labels, snr_counts = histogram(self._snr_values, 2, -20, 14)

        # Histograma hops
        max_hops = max(self._hops_values) if self._hops_values else 7
        hop_labels = [str(i) for i in range(0, min(max_hops + 2, 9))]
        hop_counts = [self._hops_values.count(i) for i in range(len(hop_labels))]

        # Stats SNR
        snr_sorted = sorted(self._snr_values)
        n = len(snr_sorted)
        snr_avg  = round(sum(snr_sorted) / n, 1)         if n else None
        snr_med  = round(snr_sorted[n // 2], 1)          if n else None
        snr_p10  = round(snr_sorted[max(0, n//10)], 1)   if n else None  # percentil 10 (pior)

        body = f"""
<div class="subtitle" id="snr-n">SNR and hop distribution · {len(self._snr_values)} samples</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #39d353;padding:8px 14px">
  <span style="color:#39d353;font-size:12px;font-weight:bold">🌐 Network Metric</span><span style="color:#8b949e;font-size:11px"> — data below is passively observed from all packets received by the local node. Reflects the state of the entire visible network, not just the local node.</span>
</div>
<div class="card" id="assessment-card" style="margin-bottom:16px;border-left:4px solid {
'#39d353' if snr_avg and snr_avg >= 5 else '#f0883e' if snr_avg and snr_avg >= 0 else '#f85149'
}">
  <h3>RF Quality Assessment</h3>
  <div id="rf-assessment" style="font-size:13px;line-height:1.7;color:#e6edf3">{self._rf_assessment(snr_avg, snr_med, snr_p10, self._hops_values)}</div>
</div>
<div class="grid-3">
  <div class="card"><h3>Avg SNR</h3>
    <div class="kpi {'green' if snr_avg and snr_avg>=5 else 'orange' if snr_avg and snr_avg>=0 else 'red'}">{snr_avg if snr_avg is not None else '—'} dB</div></div>
  <div class="card"><h3>Median SNR</h3>
    <div class="kpi">{snr_med if snr_med is not None else '—'} dB</div></div>
  <div class="card"><h3>SNR P10 (worst 10%)</h3>
    <div class="kpi red">{snr_p10 if snr_p10 is not None else '—'} dB</div></div>
</div>
<div class="grid">
  <div class="card">
    <h3>Distribution SNR (dB)</h3>
    <div class="chart-wrap"><canvas id="snrChart"></canvas></div>
  </div>
  <div class="card">
    <h3>Hop Distribution</h3>
    <div class="chart-wrap"><canvas id="hopsChart"></canvas></div>
  </div>
</div>
<script>
window._snrChart = new Chart(document.getElementById('snrChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(snr_labels)},
    datasets: [{{ label: 'Pacotes', data: {json.dumps(snr_counts)},
      backgroundColor: {json.dumps(
          ['rgba(248,81,73,0.7)' if i < 5 else 'rgba(240,136,62,0.7)' if i < 10 else 'rgba(57,211,83,0.7)'
           for i in range(len(snr_counts))])},
      borderRadius: 3 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
      x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }},
             title: {{ display: true, text: 'SNR (dB)', color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
window._hopsChart = new Chart(document.getElementById('hopsChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(hop_labels)},
    datasets: [{{ label: 'Pacotes', data: {json.dumps(hop_counts)},
      backgroundColor: 'rgba(88,166,255,0.7)', borderRadius: 3 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
      x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }},
             title: {{ display: true, text: 'Hops', color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
</script>
<script>
window._metricsUpdateData = function(d) {{
  function set(id, v) {{ var e=document.getElementById(id); if(e) e.textContent=v; }}
  function setHtml(id, v) {{ var e=document.getElementById(id); if(e) e.innerHTML=v; }}
  set('snr-avg', d.snr_avg !== null ? d.snr_avg + ' dB' : '—');
  set('snr-med', d.snr_med !== null ? d.snr_med + ' dB' : '—');
  set('snr-p10', d.snr_p10 !== null ? d.snr_p10 + ' dB' : '—');
  set('snr-n', d.n + ' samples');
  if(d.assessment) setHtml('rf-assessment', d.assessment);
  if(window._snrChart && d.snr_counts.length > 0) {{
    window._snrChart.data.labels = d.snr_labels;
    window._snrChart.data.datasets[0].data = d.snr_counts;
    window._snrChart.update('none');
  }}
  if(window._hopsChart && d.hop_counts.length > 0) {{
    window._hopsChart.data.labels = d.hop_labels;
    window._hopsChart.data.datasets[0].data = d.hop_counts;
    window._hopsChart.update('none');
  }}
}};
</script>"""
        return self._base_html("📶 RF Quality", body)

    # ── 4. Tráfego ────────────────────────────────────────────────────────
    def _html_traffic(self) -> str:
        now = time.time()
        if not self._packets:
            body = '<div class="no-data">⏳ Waiting for packets...</div>'
            return self._base_html("📦 Network Traffic", body)

        label_map = {
            'TEXT_MESSAGE_APP':       '💬 Mensagem',
            'NODEINFO_APP':           '🆔 NodeInfo',
            'POSITION_APP':           '📍 Position',
            'TELEMETRY_APP':          '📊 Telemetria',
            'TRACEROUTE_APP':         '🔍 Traceroute',
            'ROUTING_APP':            '🔀 Routing',
            'NEIGHBORINFO_APP':       '🔗 NeighborInfo',
            'ADMIN_APP':              '⚙ Admin',
            'RANGE_TEST_APP':         '📏 Range Test',
            'STORE_AND_FORWARD_APP':  '📦 S&F',
        }
        bar_colors = ['#58a6ff','#39d353','#f0883e','#bc8cff','#f85149',
                      '#56d364','#ffa657','#79c0ff','#d2a8ff','#ff7b72']

        # ── Sessão inteira — barras ────────────────────────────────────
        counts = {}
        for pname, cnt in self._portnum_counts.items():
            lbl = label_map.get(pname, pname.replace('_APP','').replace('_',' ').title())
            counts[lbl] = counts.get(lbl, 0) + cnt
        sc     = sorted(counts.items(), key=lambda x: -x[1])
        labels = [k for k, _ in sc]
        values = [v for _, v in sc]

        # ── RF vs MQTT ─────────────────────────────────────────────────
        n_rf   = len([p for p in self._packets if not p[5]])
        n_mqtt = len([p for p in self._packets if p[5]])
        total  = n_rf + n_mqtt
        rf_pct   = round(n_rf   / total * 100) if total else 0
        mqtt_pct = round(n_mqtt / total * 100) if total else 0

        # ── Pattern of routing ──────────────────────────────────────────
        n_direct  = sum(1 for p in self._packets if p[4] == 0)
        n_1hop    = sum(1 for p in self._packets if p[4] == 1)
        n_multi   = sum(1 for p in self._packets if p[4] is not None and p[4] >= 2)
        n_unknown = sum(1 for p in self._packets if p[4] is None)
        total_hop = n_direct + n_1hop + n_multi + n_unknown
        d_pct = round(n_direct  / total_hop * 100) if total_hop else 0
        h_pct = round(n_1hop    / total_hop * 100) if total_hop else 0
        m_pct = round(n_multi   / total_hop * 100) if total_hop else 0
        u_pct = round(n_unknown / total_hop * 100) if total_hop else 0
        routing_vals   = [n_direct, n_1hop, n_multi, n_unknown] if total_hop else [1,0,0,0]
        routing_labels = ['🟢 Direct', '🔵 1 Hop', '🟠 Multi-hop', '⚫ Unknown']
        routing_colors = ['#39d353', '#58a6ff', '#f0883e', '#8b949e']

        # ── Série temporal ─────────────────────────────────────────────
        bins_60 = []
        for i in range(29, -1, -1):
            t0 = now - (i + 1) * 60
            t1 = now - i * 60
            cnt = len([p for p in self._packets if t0 <= p[0] < t1])
            bins_60.append((datetime.fromtimestamp(t1).strftime('%H:%M'), cnt))
        ppm_labels = [b[0] for b in bins_60]
        ppm_vals   = [b[1] for b in bins_60]

        body = f"""
<div class="subtitle">Session traffic distribution</div>

<!-- Linha 1: dois donuts em cima -->
<div class="grid">
  <div class="card">
    <h3>RF vs MQTT</h3>
    <div style="display:flex;gap:16px;align-items:center;min-height:160px">
      <canvas id="rfChart" width="150" height="150" style="flex-shrink:0"></canvas>
      <div style="font-size:12px;color:#8b949e;line-height:2.2">
        <div><span style="color:#2b7cd3;font-size:15px">■</span> RF &nbsp;<b style="color:#e6edf3">{n_rf}</b> ({rf_pct}%)</div>
        <div><span style="color:#f0883e;font-size:15px">■</span> MQTT &nbsp;<b style="color:#e6edf3">{n_mqtt}</b> ({mqtt_pct}%)</div>
      </div>
    </div>
  </div>
  <div class="card">
    <h3>Pattern of Routing</h3>
    <div style="display:flex;gap:16px;align-items:center;min-height:160px">
      <canvas id="routingChart" width="150" height="150" style="flex-shrink:0"></canvas>
      <div style="font-size:12px;color:#8b949e;line-height:2.2">
        <div id="rd-direct"><span style="color:#39d353;font-size:15px">■</span> Direct &nbsp;<b style="color:#e6edf3">{n_direct}</b> ({d_pct}%)</div>
        <div id="rd-1hop"><span style="color:#58a6ff;font-size:15px">■</span> 1 Hop &nbsp;<b style="color:#e6edf3">{n_1hop}</b> ({h_pct}%)</div>
        <div id="rd-multi"><span style="color:#f0883e;font-size:15px">■</span> Multi-hop ≥2 &nbsp;<b style="color:#e6edf3">{n_multi}</b> ({m_pct}%)</div>
        <div id="rd-unknown"><span style="color:#8b949e;font-size:15px">■</span> Unknown &nbsp;<b style="color:#e6edf3">{n_unknown}</b> ({u_pct}%)</div>
      </div>
    </div>
  </div>
</div>

<!-- Row 2: bars by type -->
<div class="card" style="margin-top:16px">
  <h3>Packets by Type — Session</h3>
  <div class="chart-wrap"><canvas id="typeChart"></canvas></div>
</div>

<!-- Linha 3: PPM -->
<div class="card" style="margin-top:16px">
  <h3>Packets per Minute (last 30 min)</h3>
  <div class="chart-wrap-lg"><canvas id="ppmChart"></canvas></div>
</div>

<script>
window._rfChart = new Chart(document.getElementById('rfChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['RF', 'MQTT'],
    datasets: [{{ data: [{n_rf}, {n_mqtt}],
      backgroundColor: ['#2b7cd3','#f0883e'], borderWidth: 0 }}]
  }},
  options: {{
    responsive: false,
    cutout: '60%',
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
window._routingChart = new Chart(document.getElementById('routingChart'), {{
  type: 'doughnut',
  data: {{
    labels: {json.dumps(routing_labels)},
    datasets: [{{ data: {json.dumps(routing_vals)},
      backgroundColor: {json.dumps(routing_colors)}, borderWidth: 0 }}]
  }},
  options: {{
    responsive: false,
    cutout: '60%',
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
window._typeChart = new Chart(document.getElementById('typeChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(labels)},
    datasets: [{{ data: {json.dumps(values)},
      backgroundColor: {json.dumps(bar_colors[:len(values)])}, borderRadius: 3 }}]
  }},
  options: {{
    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    scales: {{
      x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
      y: {{ grid: {{ display: false }}, ticks: {{ color: '#e6edf3', font: {{ size: 11 }} }} }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
window._ppmChart = new Chart(document.getElementById('ppmChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(ppm_labels)},
    datasets: [{{ label: 'Packets/min', data: {json.dumps(ppm_vals)},
      borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)',
      fill: true, tension: 0.3, pointRadius: 1 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ min: 0, grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
      x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxTicksLimit: 10 }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#8b949e' }} }} }}
  }}
}});
</script>
<script>
window._metricsUpdateData = function(d) {{
  function setHtml(id, v) {{ var e=document.getElementById(id); if(e) e.innerHTML=v; }}
  // RF vs MQTT donut
  if(window._rfChart) {{
    var rfSum = d.n_rf + d.n_mqtt;
    if(rfSum > 0) {{
      window._rfChart.data.datasets[0].data = [d.n_rf, d.n_mqtt];
      window._rfChart.update('none');
    }}
  }}
  // Routing donut + legendas
  if(window._routingChart) {{
    var rs = d.n_direct + d.n_1hop + d.n_multi + d.n_unknown;
    if(rs > 0) {{
      window._routingChart.data.datasets[0].data = [d.n_direct, d.n_1hop, d.n_multi, d.n_unknown];
      window._routingChart.update('none');
    }}
    var tot = rs || 1;
    setHtml('rd-direct',  '<span style="color:#39d353;font-size:15px">■</span> Direct &nbsp;<b style="color:#e6edf3">' + d.n_direct + '</b> (' + Math.round(d.n_direct/tot*100) + '%)');
    setHtml('rd-1hop',    '<span style="color:#58a6ff;font-size:15px">■</span> 1 Hop &nbsp;<b style="color:#e6edf3">' + d.n_1hop + '</b> (' + Math.round(d.n_1hop/tot*100) + '%)');
    setHtml('rd-multi',   '<span style="color:#f0883e;font-size:15px">■</span> Multi-hop ≥2 &nbsp;<b style="color:#e6edf3">' + d.n_multi + '</b> (' + Math.round(d.n_multi/tot*100) + '%)');
    setHtml('rd-unknown', '<span style="color:#8b949e;font-size:15px">■</span> Unknown &nbsp;<b style="color:#e6edf3">' + d.n_unknown + '</b> (' + Math.round(d.n_unknown/tot*100) + '%)');
  }}
  // Barras por tipo
  if(window._typeChart && d.labels && d.labels.length > 0) {{
    window._typeChart.data.labels = d.labels;
    window._typeChart.data.datasets[0].data = d.values;
    window._typeChart.update('none');
  }}
  // PPM
  if(window._ppmChart) {{
    window._ppmChart.data.labels = d.ppm_labels;
    window._ppmChart.data.datasets[0].data = d.ppm_vals;
    window._ppmChart.update('none');
  }}
}};
</script>"""
        return self._base_html("📦 Network Traffic", body)

    # ── 5. Nós & Bateria ──────────────────────────────────────────────────
    def _html_nodes(self) -> str:
        now      = time.time()
        cutoff2h = now - 7200

        active_nids = set(p[1] for p in self._packets if p[0] >= cutoff2h and p[1])
        n_active    = len(active_nids)

        # batteryLevel=101 → alimentação externa (Powered); 0 → sem dados
        batt_real  = {nid: v for nid, v in self._battery.items() if 1 <= v <= 100}
        batt_power = [nid for nid, v in self._battery.items() if v == 101]
        n_powered  = len(batt_power)
        n_battery  = len(batt_real)
        batt_avg   = round(sum(batt_real.values()) / len(batt_real), 0) if batt_real else None

        ts_labels = [self._ts_label(t) for t, _ in self._nodes_active_ts]
        ts_vals   = [v for _, v in self._nodes_active_ts]

        batt_bucket_labels = ['0–20%', '21–40%', '41–60%', '61–80%', '81–100%']
        batt_counts        = [0, 0, 0, 0, 0]
        for v in batt_real.values():
            batt_counts[min(int(v // 20), 4)] += 1

        # Hardware model distribution
        hw_model = self._hw_model
        hw_counts: dict = {}
        for hw in hw_model.values():
            hw_counts[hw] = hw_counts.get(hw, 0) + 1
        hw_sorted = sorted(hw_counts.items(), key=lambda x: -x[1])[:10]
        hw_labels = [h for h, _ in hw_sorted]
        hw_values = [c for _, c in hw_sorted]

        # Nós unique with GPS
        n_gps_unique = len(set(p[1] for p in self._packets
                               if p[2] == 'POSITION_APP' and p[1]))

        # Tabela de nodes com bateria (tensão e uptime incluídos)
        batt_rows = ""
        for nid, batt in sorted(self._battery.items(), key=lambda x: x[1]):
            if batt == 101:
                disp = "<span class='tag tag-blue'>⚡ Powered</span>"
                bar  = ""
            elif batt == 0:
                disp = "<span class='tag tag-gray'>—</span>"
                bar  = ""
            else:
                color = "green" if batt > 60 else ("orange" if batt > 20 else "red")
                bar_c = {"green": "#39d353", "orange": "#f0883e", "red": "#f85149"}[color]
                disp  = f"<span class='tag tag-{color}'>{batt}%</span>"
                bar   = (f"<div class='bar-bg' style='margin-top:3px'>"
                         f"<div class='bar-fill' style='width:{batt}%;background:{bar_c}'>"
                         f"</div></div>")
            volt = self._voltage.get(nid)
            volt_str = f"{volt:.3f}V" if volt else "—"
            uptm = self._uptime.get(nid)
            if uptm:
                h, m = divmod(uptm // 60, 60)
                d2, h = divmod(h, 24)
                uptm_str = f"{d2}d{h:02d}h" if d2 else f"{h:02d}h{m:02d}m"
            else:
                uptm_str = "—"
            batt_rows += (
                f"<tr><td>{self._name(nid)}</td><td>{disp}{bar}</td>"
                f"<td style='color:#8b949e'>{volt_str}</td>"
                f"<td style='color:#8b949e'>{uptm_str}</td></tr>"
            )
        if not batt_rows:
            batt_rows = "<tr><td colspan='4' class='no-data'>No battery data yet</td></tr>"

        hw_chart_js = ""
        if hw_labels:
            hw_chart_js = f"""
window._hwChart = new Chart(document.getElementById('hwChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(hw_labels)},
    datasets: [{{ data: {json.dumps(hw_values)},
      backgroundColor: '#58a6ff', borderRadius: 3 }}]
  }},
  options: {{
    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    scales: {{
      x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
      y: {{ grid: {{ display: false }}, ticks: {{ color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});"""

        body = f"""
<div class="subtitle">Node health, batteries and hardware · {self._now_str()}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #39d353;padding:8px 14px">
  <span style="color:#39d353;font-size:12px;font-weight:bold">🌐 Network Metric</span><span style="color:#8b949e;font-size:11px"> — data below is passively observed from all packets received by the local node. Reflects the state of the entire visible network, not just the local node.</span>
</div>
<div class="grid-3">
  <div class="card"><h3>Active Nodes (2h)</h3>
    <div class="kpi green" id="nodes-active">{n_active}</div></div>
  <div class="card"><h3>Battery / Powered</h3>
    <div class="kpi blue" id="nodes-batt-count">{n_battery}</div>
    <div class="kpi-sub" id="nodes-powered">⚡ {n_powered} with external power · 📍 {n_gps_unique} with GPS</div></div>
  <div class="card"><h3>Avg Battery</h3>
    <div class="kpi {'green' if batt_avg and batt_avg>60 else 'orange'}" id="nodes-batt-avg">
      {f'{batt_avg:.0f}%' if batt_avg is not None else '—'}</div></div>
</div>
<div class="grid" style="margin-top:16px">
  <div class="card">
    <h3>Active Nodes Over Time</h3>
    <div class="chart-wrap"><canvas id="nodesChart"></canvas></div>
  </div>
  <div class="card">
    <h3>Battery Distribution</h3>
    <div class="chart-wrap"><canvas id="battDistChart"></canvas></div>
  </div>
</div>
{f'<div class="card" style="margin-top:16px"><h3>Hardware by Model ({len(hw_model)} nodes)</h3><div class="chart-wrap-lg"><canvas id="hwChart"></canvas></div></div>' if hw_labels else ''}
<div class="card" style="margin-top:16px">
  <h3>Battery per Node</h3>
  <table><tr><th>Node</th><th>Battery</th><th>Voltage</th><th>Uptime</th></tr>{batt_rows}</table>
</div>
<script>
window._nodesChart = new Chart(document.getElementById('nodesChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(ts_labels)},
    datasets: [{{ label: 'Active nodes', data: {json.dumps(ts_vals)},
      borderColor: '#39d353', backgroundColor: 'rgba(57,211,83,0.1)',
      fill: true, tension: 0.3, pointRadius: 2 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ min: 0, grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
      x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxTicksLimit: 8 }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#8b949e' }} }} }}
  }}
}});
window._battDistChart = new Chart(document.getElementById('battDistChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(batt_bucket_labels)},
    datasets: [{{ data: {json.dumps(batt_counts)},
      backgroundColor: ['#f85149','#f0883e','#ffa657','#56d364','#39d353'],
      borderRadius: 3 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
      x: {{ grid: {{ display: false }}, ticks: {{ color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
{hw_chart_js}
</script>
<script>
window._metricsUpdateData = function(d) {{
  function set(id, v) {{ var e=document.getElementById(id); if(e) e.textContent=v; }}
  set('nodes-active',    d.n_active);
  set('nodes-batt-count', d.n_battery);
  set('nodes-batt-avg',  d.batt_avg !== null ? d.batt_avg + '%' : '—');
  set('nodes-powered',   '⚡ ' + (d.n_powered||0) + ' with external power · 📍 ' + (d.n_gps_unique||0) + ' with GPS');
  if(window._nodesChart && d.ts_vals && d.ts_vals.length > 0) {{
    window._nodesChart.data.labels = d.ts_labels;
    window._nodesChart.data.datasets[0].data = d.ts_vals;
    window._nodesChart.update('none');
  }}
  if(window._battDistChart && d.batt_buckets) {{
    window._battDistChart.data.datasets[0].data = d.batt_buckets;
    window._battDistChart.update('none');
  }}
}};
</script>"""
        return self._base_html("🔋 Nodes & Battery", body)

    # ── 6. Reliability ────────────────────────────────────────────────────
    def _data_latency(self) -> dict:
        n = len(self._rtt_values)
        if n == 0:
            return {"n": 0, "avg": None, "med": None,
                    "min": None, "max": None, "p90": None,
                    "hist_labels": [], "hist_counts": [], "now": self._now_str()}
        s = sorted(self._rtt_values)
        avg = round(sum(s) / n, 1)
        med = round(s[n // 2], 1)
        mn  = round(s[0], 1)
        mx  = round(s[-1], 1)
        p90 = round(s[int(n * 0.9)], 1)
        # Histograma em buckets de 5s até 60s, depois um bucket ">60s"
        buckets = list(range(0, 65, 5))
        counts  = [0] * len(buckets)
        over    = 0
        for v in s:
            if v >= 60:
                over += 1
            else:
                idx = min(int(v // 5), len(counts) - 1)
                counts[idx] += 1
        hist_labels = [f"{b}–{b+5}s" for b in buckets]
        if over:
            hist_labels.append(">60s")
            counts.append(over)
        return {"n": n, "avg": avg, "med": med, "min": mn, "max": mx, "p90": p90,
                "hist_labels": hist_labels, "hist_counts": counts, "now": self._now_str()}

    def _html_latency(self) -> str:
        d = self._data_latency()
        if d["n"] == 0:
            body = ('<div class="no-data">⏳ No latency data yet.<br><br>'
                    'Send messages with wantAck=True to measure the RTT '
                    '(time between send and recipient ACK).</div>')
            return self._base_html("⏱ Latency (RTT)", body)

        def kpi(val, unit, label, color=""):
            v = f"{val}{unit}" if val is not None else "—"
            return f'<div class="card"><h3>{label}</h3><div class="kpi {color}">{v}</div></div>'

        avg_color = ("green" if d["avg"] and d["avg"] < 10
                     else "orange" if d["avg"] and d["avg"] < 30 else "red")

        body = f"""
<div class="subtitle">RTT (Round-Trip Time) — time between send and ACK · {d['n']} samples · {d['now']}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #f0883e;padding:8px 14px">
  <span style="color:#f0883e;font-size:12px;font-weight:bold">🏠 Local Node Metric</span><span style="color:#8b949e;font-size:11px"> — data below refers exclusively to the local node (sent messages e respectivos ACK/NAK). Other network nodes do not contribute to these values.</span>
</div>
<div class="grid-3">
  {kpi(d['avg'], 's', 'Avg RTT', avg_color)}
  {kpi(d['med'], 's', 'RTT Median', '')}
  {kpi(d['p90'], 's', 'RTT P90 (worst 10%)', 'orange')}
</div>
<div class="grid">
  {kpi(d['min'], 's', 'RTT Minimum', 'green')}
  {kpi(d['max'], 's', 'RTT Maximum', '')}
</div>
<div class="card" style="margin-top:16px">
  <h3>RTT Distribution</h3>
  <div class="chart-wrap-lg"><canvas id="rttChart"></canvas></div>
</div>
<div class="card" style="margin-top:16px">
  <h3>Interpretation</h3>
  <p style="color:#8b949e;font-size:12px;line-height:1.8">
    <b style="color:#e6edf3">RTT &lt; 5s:</b> Excellent direct link (0 hops).<br>
    <b style="color:#e6edf3">RTT 5–15s:</b> Normal for 1–2 hops in LoRa.<br>
    <b style="color:#e6edf3">RTT 15–30s:</b> Possible congestion or 3+ hops.<br>
    <b style="color:#e6edf3">RTT &gt; 30s:</b> Congested network or long route.<br>
    <br>
    RTT includes: slot wait time · LoRa transmission · relay retransmissions
    · recipient processing · ACK back. In LONG_FAST, the transmission of a
    packet takes ~300ms; each hop adds a random contention window.
  </p>
</div>
<script>
window._rttChart = new Chart(document.getElementById('rttChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(d['hist_labels'])},
    datasets: [{{ label: 'Message count', data: {json.dumps(d['hist_counts'])},
      backgroundColor: '#58a6ff', borderRadius: 3 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ min: 0, grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
      x: {{ grid: {{ display: false }}, ticks: {{ color: '#8b949e' }} }}
    }},
    plugins: {{ legend: {{ display: false }},
                tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y + ' mensagens' }} }} }}
  }}
}});
</script>
<script>
window._metricsUpdateData = function(d) {{
  if (!d || d.n === undefined) return;
  function set(id, v) {{ var e=document.getElementById(id); if(e) e.textContent=v; }}
  // Actualização via dados do servidor — rtt chart actualizado no próximo reload
}};
</script>"""
        return self._base_html("⏱ Latency (RTT)", body)

    def _html_reliability(self) -> str:
        now = time.time()

        # ── Rede — observação passiva ──────────────────────────────────
        total_pkt      = len(self._pkt_ids)
        total_seen     = sum(v['count'] for v in self._pkt_ids.values()) if self._pkt_ids else 0
        # Dup rate: % de pacotes unique vistos mais de 1 vez (flood activo)
        dup_rate       = round(self._duplicates / max(total_pkt, 1) * 100, 1) if total_pkt > 0 else None
        net_ack_total  = self._routing_acks + self._routing_naks
        net_nak_rate   = round(self._routing_naks / net_ack_total * 100, 1) if net_ack_total > 0 else None
        active_senders = len(set(v['from'] for v in self._pkt_ids.values()))

        if dup_rate is None:
            dup_color, dup_label = "", "No data"
        elif dup_rate < 10:
            dup_color, dup_label = "orange", "⚠ Reduced flood"
        elif dup_rate <= 60:
            dup_color, dup_label = "green",  "✅ Healthy flood"
        else:
            dup_color, dup_label = "red",    "🚨 Possible congestion"

        nak_net_color = ("" if net_nak_rate is None else
                         "green" if net_nak_rate < 5 else
                         "orange" if net_nak_rate < 20 else "red")

        # ── Taxa de Colisões estimada ──────────────────────────────────
        # Meshtastic usa CAD (Channel Activity Detection) + contention window
        # aleatória baseada em SNR — é slotted ALOHA com listen-before-talk.
        # Estimativa: P_col = 1 - e^(-G) onde G = channelUtilization/100
        # (modelo de Poisson para slotted ALOHA — conservador e honesto).
        # Só calculável se temos dados de channelUtilization.
        # Nota: não é um contador real — o firmware não expõe colisões directamente.
        ch_util_avg = (sum(self._ch_util.values()) / len(self._ch_util)
                       if self._ch_util else None)
        if ch_util_avg is not None:
            _math = math
            G = ch_util_avg / 100.0
            p_col = round((1 - _math.exp(-G)) * 100, 1)
            # Com CAD o Meshtastic mitiga parcialmente — factor de correcção 0.5
            p_col_corrected = round(p_col * 0.5, 1)
            col_color = ("green"  if p_col_corrected < 5  else
                         "orange" if p_col_corrected < 15 else "red")
            col_label = ("✅ Low risk"    if p_col_corrected < 5  else
                         "⚠ Moderate risk" if p_col_corrected < 15 else
                         "🚨 Risco elevado")
        else:
            p_col_corrected, col_color, col_label = None, "", "No data de Ch. Util."

        # ── Nó local ──────────────────────────────────────────────────
        # ack       = ROUTING_APP de OUTRO nó → recipient confirmed
        # ack_impl  = ROUTING_APP do próprio nó → retransmissão local
        #             NÃO é confirmação de entrega; não entra na taxa de entrega
        # nak       = errorReason != NONE → falha definitiva
        sent       = self._msgs_sent
        acked      = self._msgs_acked
        ack_impl   = self._msgs_ack_implicit
        naked      = self._msgs_naked
        total_resp = acked + naked
        delivery   = round(acked / total_resp * 100, 1) if total_resp > 0 else None
        nak_rate   = round(naked / total_resp * 100, 1)  if total_resp > 0 else None
        pending    = max(sent - total_resp - ack_impl, 0)
        dr_color   = ("green"  if delivery and delivery >= 90 else
                      "orange" if delivery and delivery >= 70 else
                      "red"    if delivery else "")

        # Pie charts
        pie_net   = [self._routing_acks, self._routing_naks] if (self._routing_acks or self._routing_naks) else [1, 0]
        pie_local = [acked, naked, ack_impl, pending] if any([acked, naked, ack_impl, pending]) else [1, 0, 0, 0]

        no_net_data   = ("" if total_pkt > 0 else
                         '<div class="no-data" style="margin-bottom:12px">⏳ Waiting for ROUTING_APP packets na rede…</div>')
        no_local_data = ("" if sent > 0 else
                         '<div style="color:#8b949e;font-size:11px;margin-bottom:8px">⏳ Send messages to see local node metrics.</div>')

        body = f"""
<div class="subtitle">Meshtastic network reliability — passive observation + local node</div>

<h3 style="color:#58a6ff;font-size:13px;margin:0 0 10px 0">🌐 Reliability da Rede (todos os nodes)</h3>
{no_net_data}
<div class="grid" style="margin-bottom:12px">
  <div class="card">
    <h3>Flood Rate (5 min)</h3>
    <div id="rel-dup" class="kpi {dup_color}">{dup_rate if dup_rate is not None else '—'}{'%' if dup_rate is not None else ''}</div>
    <div id="rel-dup-label" class="kpi-sub">{dup_label}<br>% of unique packets forwarded by ≥2 nodes</div>
  </div>
  <div class="card">
    <h3>Estimated Collisions (CAD)</h3>
    <div id="rel-col" class="kpi {col_color}">{p_col_corrected if p_col_corrected is not None else '—'}{'%' if p_col_corrected is not None else ''}</div>
    <div id="rel-col-label" class="kpi-sub">{col_label}<br>Poisson model × 0.5 (CAD mitigates) · base: Ch.Util {round(ch_util_avg,1) if ch_util_avg else '—'}%</div>
  </div>
</div>
<div class="grid">
  <div class="card">
    <h3>Network NAK (ROUTING_APP)</h3>
    <div id="rel-net-nak" class="kpi {nak_net_color}">{net_nak_rate if net_nak_rate is not None else '—'}{'%' if net_nak_rate is not None else ''}</div>
    <div id="rel-net-sub" class="kpi-sub">ACK: {self._routing_acks} · NAK: {self._routing_naks}<br>Includes NO_ROUTE and MAX_RETRANSMIT</div>
  </div>
  <div class="card">
    <h3>Unique packets (5 min)</h3>
    <div id="rel-pkt" class="kpi blue">{total_pkt}</div>
    <div id="rel-pkt-sub" class="kpi-sub">{active_senders} sender nodes · {self._duplicates} duplicates seen</div>
  </div>
</div>
<div class="grid" style="margin-top:14px">
  <div class="card">
    <h3>ACK vs NAK — Rede</h3>
    <div style="display:flex;align-items:center;justify-content:center;height:150px">
      <canvas id="relNetChart" width="150" height="150"></canvas>
    </div>
  </div>
  <div class="card">
    <h3>References</h3>
    <table>
      <tr><th>Metric</th><th>Reference</th></tr>
      <tr><td>Flood rate</td><td><span class='tag tag-orange'>&lt;10% Weak</span> <span class='tag tag-green'>10-60% Normal</span> <span class='tag tag-red'>&gt;60% Congested</span></td></tr>
      <tr><td>Network NAK</td><td><span class='tag tag-green'>&lt;5% Normal</span> <span class='tag tag-orange'>5-20% Warning</span> <span class='tag tag-red'>&gt;20% Critical</span></td></tr>
      <tr><td>Local delivery</td><td><span class='tag tag-green'>&ge;90% Real ACK</span> <span class='tag tag-orange'>70-90%</span> <span class='tag tag-red'>&lt;70%</span></td></tr>
    </table>
  </div>
</div>

<h3 style="color:#58a6ff;font-size:13px;margin:16px 0 10px 0">📍 Local Node (sent messages)</h3>
{no_local_data}
<div class="grid-3">
  <div class="card">
    <h3>Real Delivery Rate</h3>
    <div id="rel-delivery" class="kpi {dr_color}">{delivery if delivery is not None else '—'}{'%' if delivery is not None else ''}</div>
    <div class="kpi-sub">Recipient ACK ÷ (ACK+NAK)<br><i>Does not include local retransmissions</i></div>
  </div>
  <div class="card">
    <h3>Local NAK Rate</h3>
    <div id="rel-nak" class="kpi {'red' if nak_rate and nak_rate>20 else 'orange' if nak_rate else ''}">{nak_rate if nak_rate is not None else '—'}{'%' if nak_rate is not None else ''}</div>
    <div class="kpi-sub">Definitive failures with errorReason</div>
  </div>
  <div class="card">
    <h3>Messages Sent</h3>
    <div id="rel-sent" class="kpi blue">{sent}</div>
    <div id="rel-sub" class="kpi-sub">ACK: {acked} · NAK: {naked} · Relay: {ack_impl} · Pend.: {pending}</div>
  </div>
</div>
<div style="margin-top:12px">
  <div class="card">
    <h3>Distribution — Local Node</h3>
    <div style="display:flex;gap:16px;align-items:center;padding:8px 0">
      <canvas id="relChart" width="140" height="140"></canvas>
      <div style="font-size:11px;color:#8b949e;line-height:2">
        <div><span style="color:#39d353">■</span> Real ACK ({acked}) — recipient confirmed</div>
        <div><span style="color:#f85149">■</span> NAK ({naked}) — falha definitiva</div>
        <div><span style="color:#f0883e">■</span> Local relay ({ack_impl}) — retransmit, no delivery confirm.</div>
        <div><span style="color:#8b949e">■</span> Pending ({pending}) — no response yet</div>
      </div>
    </div>
  </div>
</div>
<script>
window._relNetChart = new Chart(document.getElementById('relNetChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['ACK ✓', 'NAK ✗'],
    datasets: [{{ data: {json.dumps(pie_net)},
      backgroundColor: ['#39d353','#f85149'], borderWidth: 0 }}]
  }},
  options: {{
    responsive: false,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#8b949e', boxWidth: 12, padding: 8 }} }} }}
  }}
}});
window._relChart = new Chart(document.getElementById('relChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['Real ACK ✓', 'NAK ✗', 'Local relay', 'Pending'],
    datasets: [{{ data: {json.dumps(pie_local)},
      backgroundColor: ['#39d353','#f85149','#f0883e','#8b949e'], borderWidth: 0 }}]
  }},
  options: {{
    responsive: false,
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
</script>
<script>
window._metricsUpdateData = function(d) {{
  function set(id, v) {{ var e=document.getElementById(id); if(e) e.textContent=v; }}
  function setClass(id, cls) {{ var e=document.getElementById(id); if(e) e.className='kpi '+cls; }}

  // Rede
  var dupLbl = d.dup_rate === null ? 'No data' :
               d.dup_rate < 10  ? '\u26a0\ufe0f Flood reduzido' :
               d.dup_rate <= 60 ? '\u2705 Healthy flood' : '\U0001f6a8 Possible congestion';
  set('rel-dup',       d.dup_rate !== null ? d.dup_rate + '%' : '\u2014');
  setClass('rel-dup',  d.dup_rate === null ? '' : d.dup_rate < 10 ? 'orange' : d.dup_rate <= 60 ? 'green' : 'red');
  set('rel-dup-label', dupLbl + '\n% de pacotes unique reencaminhados por \u22652 nodes');
  var colLbl = d.p_col === null || d.p_col === undefined ? 'No data de Ch.Util.' :
               d.p_col < 5  ? '\u2705 Risco baixo' :
               d.p_col < 15 ? '⚠️ Moderate risk' : '🚨 High risk';
  set('rel-col', d.p_col !== null && d.p_col !== undefined ? d.p_col + '%' : '\u2014');
  setClass('rel-col', d.p_col === null ? '' : d.p_col < 5 ? 'green' : d.p_col < 15 ? 'orange' : 'red');
  set('rel-col-label', colLbl + '\nPoisson model \xd70.5 (CAD mitiga) \xb7 base: Ch.Util ' + (d.ch_util_avg !== null ? d.ch_util_avg + '%' : '\u2014'));
  set('rel-net-nak',   d.net_nak_rate !== null ? d.net_nak_rate + '%' : '\u2014');
  setClass('rel-net-nak', d.net_nak_rate === null ? '' : d.net_nak_rate < 5 ? 'green' : d.net_nak_rate < 20 ? 'orange' : 'red');
  set('rel-net-sub',   'ACK: ' + d.net_acks + ' \xb7 NAK: ' + d.net_naks + '\nIncludes NO_ROUTE and MAX_RETRANSMIT');
  set('rel-pkt',       d.total_pkt);
  set('rel-pkt-sub',   d.active_senders + ' sender nodes · ' + d.duplicates + ' duplicates seen');

  // Local node
  set('rel-delivery',  d.delivery !== null ? d.delivery + '%' : '\u2014');
  setClass('rel-delivery', d.delivery === null ? '' : d.delivery >= 90 ? 'green' : d.delivery >= 70 ? 'orange' : 'red');
  set('rel-nak',       d.nak_rate !== null ? d.nak_rate + '%' : '\u2014');
  setClass('rel-nak',  d.nak_rate === null ? '' : d.nak_rate > 20 ? 'red' : d.nak_rate > 0 ? 'orange' : 'green');
  set('rel-sent',      d.sent);
  set('rel-sub',       'ACK: ' + d.acked + ' \xb7 NAK: ' + d.naked + ' \xb7 Relay: ' + d.ack_implicit + ' \xb7 Pend.: ' + d.pending);

  // Charts
  if(window._relNetChart) {{
    var netVals = [d.net_acks, d.net_naks];
    var netSum  = netVals.reduce(function(a,b){{return a+b;}},0);
    if(netSum > 0) {{ window._relNetChart.data.datasets[0].data = netVals; window._relNetChart.update('none'); }}
  }}
  if(window._relChart) {{
    var localVals = [d.acked, d.naked, d.ack_implicit, d.pending];
    var localSum  = localVals.reduce(function(a,b){{return a+b;}},0);
    if(localSum > 0) {{ window._relChart.data.datasets[0].data = localVals; window._relChart.update('none'); }}
  }}
}};
</script>"""
        return self._base_html("✅ Reliability", body)

    # ── 8. Vizinhança ─────────────────────────────────────────────────────
    def _data_neighbors(self) -> dict:
        rows = []
        seen = set()
        for from_id, neighbors in self._nb_links.items():
            for nb_id, snr in neighbors:
                key = tuple(sorted([from_id.lower(), nb_id.lower()]))
                if key in seen:
                    continue
                seen.add(key)
                snr_str = f"{snr:+.1f}" if snr else "—"
                rows.append([self._name(from_id), self._name(nb_id), snr_str, float(snr) if snr else None])
        rows.sort(key=lambda r: r[2], reverse=True)
        return {"rows": rows, "n_links": len(rows), "n_nodes": len(self._nb_links), "now": self._now_str()}

    def _html_neighbors(self) -> str:
        if not self._nb_links:
            body = ('<div class="no-data">⏳ No NeighborInfo data yet.<br><br>'
                    'Network nodes automatically send packets <b>NEIGHBORINFO_APP</b> '
                    'with the list of direct neighbours and their SNR.<br>'
                    'This data typically appears after 1–2 minutes of operation.</div>')
            return self._base_html("🔗 Neighbourhood", body)

        d = self._data_neighbors()
        rows_html = ""
        for from_n, nb_n, snr_str, snr_val in d["rows"]:
            if snr_val is not None:
                color = "green" if snr_val >= 5 else ("orange" if snr_val >= 0 else "red")
            else:
                color = "gray"
            rows_html += (
                f"<tr><td>{from_n}</td><td style='color:#8b949e'>↔</td>"
                f"<td>{nb_n}</td>"
                f"<td><span class='tag tag-{color}'>{snr_str} dB</span></td></tr>"
            )
        if not rows_html:
            rows_html = "<tr><td colspan='4' class='no-data'>No pairs</td></tr>"

        body = f"""
<div class="subtitle">Nodes that see each other via LoRa · {d['n_nodes']} nodes reportaram · {d['n_links']} unique pairs · {d['now']}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #8b949e;padding:8px 14px">
  <span style="color:#8b949e;font-size:11px">
    ⚙️ This data comes from <b>NEIGHBORINFO_APP</b> packets seniados pelos nodes da rede —
    representing direct links observed by each node (not the local node).
    The purple dashed lines on the map show the same pairs.
  </span>
</div>
<div class="card">
  <h3>Direct Neighbour Pairs</h3>
  <table>
    <tr><th>Node A</th><th></th><th>Node B</th><th>SNR</th></tr>
    {rows_html}
  </table>
</div>
<script>
window._metricsUpdateData = function(d) {{
  // Neighbour table: no incremental update — rerenders on next cycle
}};
</script>"""
        return self._base_html("🔗 Neighbourhood", body)

    # ── 9. Alcance & Links ────────────────────────────────────────────────
    def _data_range_links(self) -> dict:
        """Calcula distância entre pares de nodes vizinhos with GPS."""
        import math as _m
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = _m.radians(lat2 - lat1)
            dlon = _m.radians(lon2 - lon1)
            a = (_m.sin(dlat/2)**2 +
                 _m.cos(_m.radians(lat1)) * _m.cos(_m.radians(lat2)) * _m.sin(dlon/2)**2)
            return R * 2 * _m.atan2(_m.sqrt(a), _m.sqrt(1-a))

        # Usa posições dos nodes nos pacotes recebidos
        node_pos = {}  # nid → (lat, lon)
        for p in self._packets:
            nid = p[1]
            if nid and nid not in node_pos:
                # Tenta encontrar posição nos dados acumulados
                # (serão injectados via ingest_packet se o node_data tiver coords)
                pass

        # Usa _nb_links para pares + posições do node_short (limitado)
        # Calcula para cada par de vizinhos se ambos tiverem lat/lon no _node_pos
        rows = []
        max_range = None
        max_pair  = ("—", "—")

        # Nota: posições vêm de self._node_pos injectado em ingest_packet
        node_pos = getattr(self, '_node_pos', {})
        seen = set()
        for from_id, neighbors in self._nb_links.items():
            pos_a = node_pos.get(from_id)
            if not pos_a:
                continue
            for nb_id, snr in neighbors:
                key = tuple(sorted([from_id.lower(), nb_id.lower()]))
                if key in seen:
                    continue
                seen.add(key)
                pos_b = node_pos.get(nb_id)
                if not pos_b:
                    continue
                dist = round(haversine(pos_a[0], pos_a[1], pos_b[0], pos_b[1]), 3)
                snr_str = f"{snr:+.1f}" if snr else "—"
                rows.append([self._name(from_id), self._name(nb_id), dist, snr_str, snr])
                if max_range is None or dist > max_range:
                    max_range = dist
                    max_pair = (self._name(from_id), self._name(nb_id))

        rows.sort(key=lambda r: r[2], reverse=True)
        return {"rows": rows, "max_range": max_range, "max_pair": max_pair,
                "n_with_gps": len(node_pos), "now": self._now_str()}

    def ingest_node_position(self, nid: str, lat: float, lon: float):
        """Regista posição GPS de um nó para cálculo de alcance."""
        if nid and lat is not None and lon is not None:
            if not hasattr(self, '_node_pos'):
                self._node_pos = {}
            self._node_pos[nid] = (lat, lon)

    def _html_range_links(self) -> str:
        d = self._data_range_links()
        if not d["rows"]:
            n_gps   = d["n_with_gps"]
            n_nb    = len(self._nb_links)
            has_gps = n_gps > 0
            has_nb  = n_nb > 0
            if not has_gps and not has_nb:
                detail = "⏳ Waiting for GPS positions (POSITION_APP) and neighbour data (NEIGHBORINFO_APP)."
            elif not has_gps:
                detail = (f"✅ Neighbour data received ({n_nb} nodes). "
                          "⏳ Waiting for GPS positions (POSITION_APP).")
            elif not has_nb:
                detail = (f"✅ GPS positions known ({n_gps} nodes). "
                          "⏳ Waiting for neighbour data (NEIGHBORINFO_APP).")
            else:
                detail = (f"✅ GPS: {n_gps} nodes · Neighbours: {n_nb} nodes. "
                          "No pairs with GPS on both ends yet.")
            body = (f'<div class="no-data">📏 Range & Links<br><br>{detail}<br><br>'
                    'Both POSITION_APP and NEIGHBORINFO_APP data are required '
                    '— both nodes in a neighbour pair must have GPS.'
                    f'<br><br>GPS-equipped nodes known: {n_gps} · Neighbour pairs: {n_nb}</div>')
            return self._base_html("📏 Range & Links", body)

        def kpi(val, unit, label, color=""):
            v = f"{val}{unit}" if val is not None else "—"
            return f'<div class="card"><h3>{label}</h3><div class="kpi {color}">{v}</div></div>'

        rows_html = ""
        for from_n, nb_n, dist, snr_str, snr_val in d["rows"]:
            dist_color = "green" if dist < 2 else ("orange" if dist < 10 else "blue")
            if snr_val is not None:
                snr_color = "green" if snr_val >= 5 else ("orange" if snr_val >= 0 else "red")
            else:
                snr_color = "gray"
            rows_html += (
                f"<tr><td>{from_n}</td><td>{nb_n}</td>"
                f"<td><span class='tag tag-{dist_color}'>{dist} km</span></td>"
                f"<td><span class='tag tag-{snr_color}'>{snr_str} dB</span></td></tr>"
            )

        body = f"""
<div class="subtitle">Range of direct LoRa links (requires GPS + NeighborInfo) · {d['now']}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #8b949e;padding:8px 14px">
  <span style="color:#8b949e;font-size:11px">
    ⚙️ Network metric — calculates the real distance between neighbouring nodes via
    <b>NEIGHBORINFO_APP</b>, using each node's GPS coordinates (Haversine formula).
    Does not involve the local node unless it is in the pairs.
  </span>
</div>
<div class="grid-3" style="margin-bottom:16px">
  {kpi(f"{d['max_range']:.2f}" if d['max_range'] else None, " km", "Max Range", "blue")}
  <div class="card"><h3>Longest range pair</h3>
    <div style="font-size:14px;font-weight:bold;color:#58a6ff">
      {d['max_pair'][0]} ↔ {d['max_pair'][1]}
    </div></div>
  {kpi(d['n_with_gps'], " nodes", "Nodes with GPS", "")}
</div>
<div class="card">
  <h3>Links by Range</h3>
  <table>
    <tr><th>Node A</th><th>Node B</th><th>Distance</th><th>SNR</th></tr>
    {rows_html}
  </table>
</div>
<script>window._metricsUpdateData=function(d){{}};</script>"""
        return self._base_html("📏 Range & Links", body)

    # ── 10. Intervalos entre pacotes ─────────────────────────────────────
    def _data_intervals(self) -> dict:
        rows = []
        for nid, entry in self._pkt_intervals.items():
            vals = entry['vals']
            if len(vals) < 2:
                continue
            avg = round(sum(vals) / len(vals), 1)
            mn  = round(min(vals), 1)
            mx  = round(max(vals), 1)
            rows.append([self._name(nid), avg, mn, mx, len(vals)])
        rows.sort(key=lambda r: r[1])
        return {"rows": rows, "now": self._now_str()}

    def _html_intervals(self) -> str:
        d = self._data_intervals()
        if not d["rows"]:
            body = ('<div class="no-data">⏳ No interval data yet.<br><br>'
                    'Requires at least 2 packets per node to calculate the average interval.</div>')
            return self._base_html("⏰ Intervals", body)

        rows_html = ""
        for nid_n, avg, mn, mx, count in d["rows"]:
            # Cores: verde <60s (activo), laranja 60-300s, vermelho >300s
            color = "green" if avg < 60 else ("orange" if avg < 300 else "red")
            freq_label = "High frequency" if avg < 30 else ("Normal" if avg < 180 else "Low frequency")
            rows_html += (
                f"<tr><td>{nid_n}</td>"
                f"<td><span class='tag tag-{color}'>{avg}s</span></td>"
                f"<td style='color:#8b949e'>{mn}s</td>"
                f"<td style='color:#8b949e'>{mx}s</td>"
                f"<td style='color:#8b949e'>{count}</td>"
                f"<td style='font-size:11px;color:#8b949e'>{freq_label}</td></tr>"
            )

        body = f"""
<div class="subtitle">Real interval between packets per node · {d['now']}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #8b949e;padding:8px 14px">
  <span style="color:#8b949e;font-size:11px">
    ℹ️ Network metric — measures the real time between consecutive packets from each observed node.
    UA very low interval may indicate a misconfigured node congesting the channel.
    A very high interval may indicate a node with coverage issues or low batteryraca.
    Does not involve the local node unless it also sends observable packets.
  </span>
</div>
<div class="card">
  <h3>Average Packet Interval per Node</h3>
  <table>
    <tr><th>Node</th><th>Average</th><th>Min.</th><th>Max.</th><th>Samples</th><th>Frequency</th></tr>
    {rows_html}
  </table>
  <div style="color:#8b949e;font-size:10px;margin-top:8px;padding-top:8px;border-top:1px solid #21262d">
    ⚙️ Intervals &lt;30s = high frequency · 30–180s = normal · &gt;180s = low frequency
  </div>
</div>
<script>window._metricsUpdateData=function(d){{}};</script>"""
        return self._base_html("⏰ Intervals", body)

