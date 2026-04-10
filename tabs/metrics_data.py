"""
tabs/metrics_data.py — MetricsDataMixin: estruturas de dados, ingestão de
pacotes e cálculo de métricas para a aba de métricas em tempo real.

CORRECÇÕES (v1.0.3):
  - BUG: dupla ingestão de TELEMETRY_APP eliminada
  - BUG: _node_pos inicializado em _reset_data()
  - BUG: _duplicates windowed (mesma janela de 5 min que _pkt_ids)
  - IMPRECISÃO: P10 corrigido para int(0.1*(n-1))
  - IMPRECISÃO: _ch_util/_air_tx expiram com TTL de 30 min
  - IMPRECISÃO: NAK da rede separado (entrega vs erros de firmware)
  - IMPRECISÃO: n_gps_unique usa _node_pos (coords validadas)
  - MELHORIA: nova secção "Nó Local"
"""
import math
import time
from datetime import datetime
from i18n import tr

_CH_TTL_S = 1800   # 30 min sem actualização → expirar valor de ch_util/air_tx


class MetricsDataMixin:

    def _reset_data(self):
        self._start_time = time.time()
        self._node_short: dict = {}
        self._packets: list = []

        # ch_util/air_tx agora guardam {'val': float, 'ts': float} para TTL
        self._ch_util: dict  = {}
        self._air_tx: dict   = {}
        self._ch_util_ts: list = []

        self._snr_values: list = []
        self._hops_values: list = []
        self._portnum_counts: dict = {}

        self._battery: dict = {}
        self._voltage: dict = {}
        self._uptime:  dict = {}

        self._sent_ts: dict   = {}
        self._rtt_values: list = []
        self._hw_model: dict  = {}

        self._msgs_sent         = 0
        self._msgs_acked        = 0
        self._msgs_ack_implicit = 0
        self._msgs_naked        = 0
        self._sent_packet_ids: set = set()

        self._pkt_ids: dict    = {}
        self._pkt_ids_ever: int = 0

        # Contadores separados para fiabilidade de rede
        self._routing_acks: int     = 0   # ACK de entrega (requestId, sem erro)
        self._routing_naks: int     = 0   # NAK de entrega (requestId + errorReason)
        self._routing_fw_errs: int  = 0   # Erros internos firmware (sem requestId)

        self._nodes_active_ts: list = []
        self._nb_links: dict  = {}
        self._pkt_intervals: dict = {}

        # FIX: inicializado aqui — antes era lazy-init e não era limpo em reset
        self._node_pos: dict = {}

        # Métricas do nó local
        self._local_nid: str        = ''
        self._local_ch_util: float  = 0.0
        self._local_air_tx: float   = 0.0
        self._local_battery: int    = 0
        self._local_voltage: float  = 0.0
        self._local_uptime: int     = 0
        self._local_hw_model: str   = ''
        self._local_snr_rx: list    = []
        self._local_dc_ts: list     = []

    # ── helpers TTL ──────────────────────────────────────────────────────
    def _ch_val(self, nid: str) -> float:
        e = self._ch_util.get(nid)
        if e is None or time.time() - e['ts'] > _CH_TTL_S:
            return 0.0
        return e['val']

    def _air_val(self, nid: str) -> float:
        e = self._air_tx.get(nid)
        if e is None or time.time() - e['ts'] > _CH_TTL_S:
            return 0.0
        return e['val']

    def _ch_util_active(self) -> dict:
        now = time.time()
        return {nid: e['val'] for nid, e in self._ch_util.items()
                if now - e['ts'] <= _CH_TTL_S}

    def _air_tx_active(self) -> dict:
        now = time.time()
        return {nid: e['val'] for nid, e in self._air_tx.items()
                if now - e['ts'] <= _CH_TTL_S}

    def _count_duplicates(self) -> int:
        """Duplicados na janela actual de _pkt_ids (windowed, não cumulativo)."""
        return sum(max(v['count'] - 1, 0) for v in self._pkt_ids.values())

    # ── configuração nó local ─────────────────────────────────────────────
    def set_local_node_id(self, nid: str):
        if nid:
            self._local_nid = nid
            # Invalida o hash para que o próximo tick do timer force setHtml.
            # Não manipula _was_waiting — local_node não está em _WAITING_SECTIONS.
            if hasattr(self, '_local_node_sig'):
                self._local_node_sig = None

    # ── ingestão ─────────────────────────────────────────────────────────
    def ingest_packet(self, packet: dict, node_data: dict):
        ts      = time.time()
        nid     = packet.get('fromId', '')
        portnum = (packet.get('decoded') or {}).get('portnum', 'UNKNOWN_APP')
        snr     = packet.get('rxSnr')
        via_mqtt = packet.get('viaMqtt', False)

        sn = (node_data.get('short_name') or '').strip()
        if nid and sn:
            self._node_short[nid] = sn

        hops = node_data.get('hops_away')
        self._packets.append((ts, nid, portnum, snr, hops, via_mqtt))
        if len(self._packets) > 5000:
            self._packets = self._packets[-4000:]

        if snr is not None:
            self._snr_values.append(float(snr))
            if len(self._snr_values) > 2000:
                self._snr_values = self._snr_values[-1500:]

        if hops is not None:
            self._hops_values.append(int(hops))
            if len(self._hops_values) > 2000:
                self._hops_values = self._hops_values[-1500:]

        self._portnum_counts[portnum] = self._portnum_counts.get(portnum, 0) + 1

        # FIX: fonte única — node_data (já mergeado pelo worker).
        # Antes havia dupla leitura: raw protobuf + node_data; a série
        # _ch_util_ts era appendada antes do merge, com valor possivelmente errado.
        batt    = node_data.get('battery_level')
        ch_util = node_data.get('channel_utilization')
        air_tx  = node_data.get('air_util_tx')
        volt    = node_data.get('voltage')
        uptm    = node_data.get('uptime_seconds')
        hw      = node_data.get('hw_model', '')

        if nid:
            if batt    is not None: self._battery[nid] = int(batt)
            if volt    is not None: self._voltage[nid] = round(float(volt), 3)
            if uptm    is not None: self._uptime[nid]  = int(uptm)
            if hw:                  self._hw_model[nid] = hw
            if ch_util is not None: self._ch_util[nid] = {'val': float(ch_util), 'ts': ts}
            if air_tx  is not None: self._air_tx[nid]  = {'val': float(air_tx),  'ts': ts}

        # Série temporal ch_util — appendada APÓS merge completo
        if ch_util is not None and nid:
            active_ch = self._ch_util_active()
            if active_ch:
                avg = sum(active_ch.values()) / len(active_ch)
                self._ch_util_ts.append((ts, round(avg, 1)))
                if len(self._ch_util_ts) > 120:
                    self._ch_util_ts = self._ch_util_ts[-120:]

        # Métricas específicas do nó local
        if self._local_nid and nid == self._local_nid:
            if ch_util is not None: self._local_ch_util = float(ch_util)
            if air_tx  is not None:
                self._local_air_tx = float(air_tx)
                dc = round(min(float(air_tx) * 6, 100.0), 2)
                self._local_dc_ts.append((ts, dc))
                if len(self._local_dc_ts) > 120:
                    self._local_dc_ts = self._local_dc_ts[-120:]
            if batt is not None: self._local_battery  = int(batt)
            if volt is not None: self._local_voltage   = round(float(volt), 3)
            if uptm is not None: self._local_uptime    = int(uptm)
            if hw:               self._local_hw_model  = hw

        # SNR de pacotes recebidos (perspectiva do nó local = rxSnr)
        if snr is not None:
            self._local_snr_rx.append(float(snr))
            if len(self._local_snr_rx) > 500:
                self._local_snr_rx = self._local_snr_rx[-400:]

        # Nós activos (a cada 60s)
        if not self._nodes_active_ts or ts - self._nodes_active_ts[-1][0] >= 60:
            cutoff = ts - 7200
            active = len(set(p[1] for p in self._packets if p[0] >= cutoff))
            self._nodes_active_ts.append((ts, active))
            if len(self._nodes_active_ts) > 120:
                self._nodes_active_ts = self._nodes_active_ts[-120:]

        # Intervalo entre pacotes por nó
        if nid:
            entry = self._pkt_intervals.setdefault(nid, {'last': None, 'vals': []})
            if entry['last'] is not None:
                interval = ts - entry['last']
                if 1 < interval < 3600:
                    entry['vals'].append(round(interval, 1))
                    if len(entry['vals']) > 100:
                        entry['vals'] = entry['vals'][-80:]
            entry['last'] = ts

    def ingest_message_status(self, req_id: int, status: str):
        if req_id not in self._sent_packet_ids:
            return
        if status == 'nak':
            self._msgs_naked += 1
            self._sent_packet_ids.discard(req_id)
            self._sent_ts.pop(req_id, None)
        elif status == 'ack':
            self._msgs_acked += 1
            sent_at = self._sent_ts.pop(req_id, None)
            if sent_at is not None:
                rtt = round(time.time() - sent_at, 2)
                if 0 < rtt < 300:
                    self._rtt_values.append(rtt)
                    if len(self._rtt_values) > 200:
                        self._rtt_values = self._rtt_values[-150:]
            self._sent_packet_ids.discard(req_id)
        elif status == 'ack_implicit':
            self._msgs_ack_implicit += 1
        self._refresh_if_reliability()

    def ingest_message_sent(self, packet_id: int):
        self._msgs_sent += 1
        if packet_id:
            self._sent_packet_ids.add(packet_id)
            self._sent_ts[packet_id] = time.time()
        self._refresh_if_reliability()

    def _refresh_if_reliability(self):
        if getattr(self, '_current_key', None) in ('reliability', 'local_node'):
            self._refresh_current()

    def ingest_neighbor_info(self, from_id: str, neighbors: list):
        if from_id and neighbors:
            self._nb_links[from_id] = neighbors

    def ingest_raw_packet(self, packet: dict):
        """FIX: separação de NAK de entrega vs erros internos de firmware."""
        ts      = time.time()
        pkt_id  = packet.get('id')
        nid     = packet.get('fromId', '')
        decoded = packet.get('decoded') or {}
        portnum = decoded.get('portnum', '')

        # Duplicados — FIX: _count_duplicates() recalcula dinamicamente
        if pkt_id and nid:
            if pkt_id in self._pkt_ids:
                self._pkt_ids[pkt_id]['count'] += 1
                self._pkt_ids[pkt_id]['ts'] = ts
            else:
                self._pkt_ids[pkt_id] = {'from': nid, 'ts': ts, 'count': 1}
                self._pkt_ids_ever += 1
            cutoff_ids = ts - 300
            self._pkt_ids = {k: v for k, v in self._pkt_ids.items()
                             if v['ts'] >= cutoff_ids}

        # ACK/NAK da rede — separação correcta
        if portnum == 'ROUTING_APP':
            routing    = decoded.get('routing', {}) or {}
            err        = (routing.get('errorReason', 'NONE') or 'NONE').upper()
            request_id = decoded.get('requestId', 0)
            has_err    = (err != 'NONE' and err != '')

            if has_err:
                if request_id:
                    self._routing_naks += 1      # NAK de entrega (tem destinatário)
                else:
                    self._routing_fw_errs += 1   # Erro interno firmware
            elif request_id:
                self._routing_acks += 1          # ACK de entrega

    def ingest_node_position(self, nid: str, lat: float, lon: float):
        """FIX: _node_pos inicializado em _reset_data; filtra coords (0,0)."""
        if nid and lat is not None and lon is not None:
            if abs(lat) > 0.001 or abs(lon) > 0.001:
                self._node_pos[nid] = (lat, lon)

    # ── helpers ──────────────────────────────────────────────────────────
    def _ts_label(self, ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime('%H:%M')

    def _now_str(self) -> str:
        return datetime.now().strftime('%H:%M:%S')

    def _name(self, nid: str) -> str:
        return self._node_short.get(nid, nid) if nid else nid

    # ── data functions ────────────────────────────────────────────────────
    def _data_overview(self) -> dict:
        now        = time.time()
        total_pkts = len(self._packets)
        active_nids = set(p[1] for p in self._packets if p[0] >= now-7200 and p[1])
        ppm        = len([p for p in self._packets if p[0] >= now-60])
        snr_avg    = round(sum(self._snr_values)/len(self._snr_values), 1) if self._snr_values else None
        hops_avg   = round(sum(self._hops_values)/len(self._hops_values), 2) if self._hops_values else None
        ch_active  = self._ch_util_active()
        air_active = self._air_tx_active()
        ch_avg     = round(sum(ch_active.values())/len(ch_active), 1) if ch_active else None
        air_avg    = round(sum(air_active.values())/len(air_active), 1) if air_active else None
        total_r    = self._msgs_acked + self._msgs_naked
        delivery   = round(self._msgs_acked/total_r*100, 1) if total_r > 0 else None
        nid_counts = {}
        for p in self._packets:
            if p[1]: nid_counts[p[1]] = nid_counts.get(p[1], 0) + 1
        top = sorted(nid_counts.items(), key=lambda x: -x[1])[:8]
        # FIX: 5 colunas — nid, nome, pacotes, ch_util, bateria
        table_rows = [
            [nid, self._name(nid), cnt, round(self._ch_val(nid), 1), self._battery.get(nid)]
            for nid, cnt in top
        ]
        return {"total_pkts":total_pkts, "n_active":len(active_nids), "ppm":ppm,
                "snr_avg":snr_avg, "hops_avg":hops_avg, "ch_avg":ch_avg, "air_avg":air_avg,
                "delivery":delivery, "table_rows":table_rows, "now":self._now_str(),
                "unit_nos": " " + tr("nós"), "now_label": tr("Actualizado:")}

    def _data_channel(self) -> dict:
        ch_active  = self._ch_util_active()
        air_active = self._air_tx_active()
        duty       = {nid: round(min(a*6, 100.0), 2) for nid, a in air_active.items()}
        duty_avg   = round(sum(duty.values())/len(duty), 2) if duty else None
        worst_nid  = max(duty, key=duty.get) if duty else None
        worst_dc   = duty[worst_nid] if worst_nid else None
        worst_name = self._name(worst_nid) if worst_nid else "—"
        air_avg    = round(sum(air_active.values())/len(air_active), 2) if air_active else None
        ch_net_avg = round(sum(ch_active.values())/len(ch_active), 1) if ch_active else None
        ts_labels  = [self._ts_label(t) for t,_ in self._ch_util_ts]
        ts_vals    = [v for _,v in self._ch_util_ts]
        rows = []
        all_nids = sorted(set(list(ch_active.keys()) + list(air_active.keys())))
        for nid in all_nids:
            ch  = ch_active.get(nid, 0)
            air = air_active.get(nid, 0)
            dc  = duty.get(nid, round(min(air*6, 100.0), 2))
            rows.append([nid, self._name(nid), round(ch,1), round(air,2), dc])
        return {"duty_avg":duty_avg, "worst_dc":worst_dc, "worst_name":worst_name,
                "air_avg":air_avg, "ch_net_avg":ch_net_avg,
                "ts_labels":ts_labels, "ts_vals":ts_vals, "rows":rows, "now":self._now_str(),
                "lbl_exceed": tr("🚨 Excede limite"), "lbl_warn": tr("⚠ Atenção"), "lbl_ok": "✅ OK"}

    def _rf_assessment(self, snr_avg, snr_med, snr_p10, hops_values) -> str:
        if snr_avg is None or not self._snr_values:
            return tr("⏳ Aguardando dados suficientes para avaliação...")
        n = len(self._snr_values)
        pct_exc  = round(sum(1 for v in self._snr_values if v >= 8)     / n * 100)
        pct_good = round(sum(1 for v in self._snr_values if 5 <= v < 8) / n * 100)
        pct_marg = round(sum(1 for v in self._snr_values if 0 <= v < 5) / n * 100)
        pct_weak = round(sum(1 for v in self._snr_values if v < 0)      / n * 100)
        pct_ok   = pct_exc + pct_good
        lines = []
        lines.append(
            f"<b>{tr('Distribuição de qualidade em {n} pacotes:', n=n)}</b> "
            f"<span style='color:#39d353'>{pct_exc}% {tr('excelente')} (≥8dB)</span> · "
            f"<span style='color:#56d364'>{pct_good}% {tr('bom')} (5–8dB)</span> · "
            f"<span style='color:#f0883e'>{pct_marg}% {tr('marginal')} (0–5dB)</span> · "
            f"<span style='color:#f85149'>{pct_weak}% {tr('fraco')} (&lt;0dB)</span>"
        )
        if pct_ok >= 80:
            lines.append(tr("✅ Rede em excelentes condições RF. A grande maioria dos pacotes chega com sinal forte."))
        elif pct_ok >= 60:
            lines.append(tr("✅ Qualidade RF boa. A maioria das ligações é estável, com algumas margens."))
        elif pct_ok >= 40:
            lines.append(tr("⚠️ Qualidade RF moderada."))
        else:
            lines.append(tr("🚨 Qualidade RF fraca."))
        if snr_p10 is not None:
            if snr_p10 < -10: lines.append(tr("⚠️ Pior decil SNR fraco", snr_p10=snr_p10))
            elif snr_p10 < 0: lines.append(tr("ℹ️ Pior decil SNR marginal", snr_p10=snr_p10))
            else:             lines.append(tr("✅ Pior decil SNR ok", snr_p10=snr_p10))
        if hops_values:
            avg_hops   = sum(hops_values) / len(hops_values)
            pct_direct = round(hops_values.count(0) / len(hops_values) * 100)
            pct_1hop   = round(hops_values.count(1) / len(hops_values) * 100)
            max_hops   = max(hops_values)
            lines.append(tr("topologia", pct_direct=f"{pct_direct:.0f}", pct_1hop=f"{pct_1hop:.0f}",
                            avg_hops=avg_hops, max_hops=max_hops))
            if avg_hops > 2.5: lines.append(tr("⚠️ Média de hops elevada"))
            if max_hops >= 6:  lines.append(tr("⚠️ Máximo de hops", max_hops=max_hops))
        if pct_ok >= 70 and (not hops_values or sum(hops_values)/len(hops_values) < 2):
            lines.append(tr("conclusao_verde"))
        elif pct_ok >= 50:
            lines.append(tr("conclusao_amarela"))
        else:
            lines.append(tr("conclusao_vermelha"))
        return "<br>".join(lines)

    def _data_rf(self) -> dict:
        def histogram(vals, bucket=2, mn=-20, mx=14):
            buckets = list(range(mn, mx+bucket, bucket))
            counts  = [0]*len(buckets)
            for v in vals:
                idx = min(int((v-mn)//bucket), len(counts)-1)
                idx = max(0, idx)
                counts[idx] += 1
            return [str(b) for b in buckets], counts
        snr_labels, snr_counts = histogram(self._snr_values) if self._snr_values else ([], [])
        max_hops  = max(self._hops_values) if self._hops_values else 7
        hop_labels = [str(i) for i in range(0, min(max_hops+2, 9))]
        hop_counts = [self._hops_values.count(i) for i in range(len(hop_labels))]
        n          = len(self._snr_values)
        snr_sorted = sorted(self._snr_values)
        snr_avg    = round(sum(snr_sorted)/n, 1) if n else None
        snr_med    = round(snr_sorted[n//2], 1)  if n else None
        # FIX: percentil correcto — int(0.1*(n-1)) em vez de n//10
        snr_p10    = round(snr_sorted[int(0.1*(n-1))], 1) if n else None
        assessment = self._rf_assessment(snr_avg, snr_med, snr_p10, self._hops_values)
        return {"n":n, "snr_avg":snr_avg, "snr_med":snr_med, "snr_p10":snr_p10,
                "snr_labels":snr_labels, "snr_counts":snr_counts,
                "hop_labels":hop_labels, "hop_counts":hop_counts,
                "assessment": assessment, "unit_amostras": tr("amostras"),
                "p10_note": tr("(mínimo se n<10)") if n and n < 10 else ""}

    def _data_traffic(self) -> dict:
        now = time.time()
        label_map = {
            "TEXT_MESSAGE_APP":      tr("💬 Mensagem"),
            "NODEINFO_APP":          "🆔 NodeInfo",
            "POSITION_APP":          tr("📍 Posição"),
            "TELEMETRY_APP":         tr("📊 Telemetria"),
            "TRACEROUTE_APP":        "🔍 Traceroute",
            "ROUTING_APP":           "🔀 Routing",
            "NEIGHBORINFO_APP":      "🔗 NeighborInfo",
            "ADMIN_APP":             "⚙ Admin",
            "RANGE_TEST_APP":        "📏 Range Test",
            "STORE_AND_FORWARD_APP": "📦 S&F",
        }
        counts = {}
        for pname, cnt in self._portnum_counts.items():
            lbl = label_map.get(pname, pname.replace("_APP","").replace("_"," ").title())
            counts[lbl] = counts.get(lbl, 0) + cnt
        sc     = sorted(counts.items(), key=lambda x: -x[1])
        labels = [k for k,_ in sc]
        values = [v for _,v in sc]
        n_direct  = sum(1 for p in self._packets if p[4] == 0)
        n_1hop    = sum(1 for p in self._packets if p[4] == 1)
        n_multi   = sum(1 for p in self._packets if p[4] is not None and p[4] >= 2)
        n_unknown = sum(1 for p in self._packets if p[4] is None)
        n_rf   = len([p for p in self._packets if not p[5]])
        n_mqtt = len([p for p in self._packets if p[5]])
        bins = []
        for i in range(29, -1, -1):
            t0 = now-(i+1)*60; t1 = now-i*60
            cnt = len([p for p in self._packets if t0 <= p[0] < t1])
            bins.append((datetime.fromtimestamp(t1).strftime("%H:%M"), cnt))
        return {"labels":labels, "values":values,
                "n_direct":n_direct, "n_1hop":n_1hop, "n_multi":n_multi, "n_unknown":n_unknown,
                "n_rf":n_rf, "n_mqtt":n_mqtt,
                "ppm_labels":[b[0] for b in bins], "ppm_vals":[b[1] for b in bins],
                "lbl_direct": tr("🟢 Directo"), "lbl_1hop": tr("🔵 1 Hop"),
                "lbl_multi":  tr("🟠 Multi-hop"), "lbl_unknown": tr("⚫ Desconhecido")}

    def _data_nodes(self) -> dict:
        now      = time.time()
        cutoff2h = now - 7200
        n_active = len(set(p[1] for p in self._packets if p[0] >= cutoff2h and p[1]))
        batt_real  = {nid: v for nid, v in self._battery.items() if 1 <= v <= 100}
        batt_power = {nid for nid, v in self._battery.items() if v == 101}
        batt_buckets = [0, 0, 0, 0, 0]
        for v in batt_real.values():
            batt_buckets[min(int(v // 20), 4)] += 1
        batt_avg = round(sum(batt_real.values()) / len(batt_real), 0) if batt_real else None
        batt_rows = []
        for nid, v in sorted(self._battery.items(), key=lambda x: x[1]):
            volt = self._voltage.get(nid)
            uptm = self._uptime.get(nid)
            batt_rows.append([nid, v, volt, uptm])
        hw_counts: dict = {}
        for nid, hw in self._hw_model.items():
            hw_counts[hw] = hw_counts.get(hw, 0) + 1
        hw_sorted = sorted(hw_counts.items(), key=lambda x: -x[1])
        # FIX: usa _node_pos (coords validadas) em vez de contar POSITION_APP packets
        n_gps_unique = len(self._node_pos)
        ts_labels = [self._ts_label(t) for t, _ in self._nodes_active_ts]
        ts_vals   = [v for _, v in self._nodes_active_ts]
        return {
            "n_active": n_active,
            "n_battery": len(batt_real), "n_powered": len(batt_power),
            "batt_avg": batt_avg,
            "ts_labels": ts_labels, "ts_vals": ts_vals,
            "batt_buckets": batt_buckets, "batt_rows": batt_rows,
            "hw_labels": [h for h, _ in hw_sorted],
            "hw_values": [c for _, c in hw_sorted],
            "n_gps_unique": n_gps_unique,
            "lbl_powered": tr("{n} com alimentação externa · 📍 {m} com GPS",
                              n=len(batt_power), m=n_gps_unique),
        }

    def _data_reliability(self) -> dict:
        total_resp = self._msgs_acked + self._msgs_naked
        delivery   = round(self._msgs_acked / total_resp * 100, 1) if total_resp > 0 else None
        nak_rate   = round(self._msgs_naked / total_resp * 100, 1) if total_resp > 0 else None
        pending    = max(self._msgs_sent - self._msgs_acked - self._msgs_naked, 0)
        rtt_avg    = round(sum(self._rtt_values)/len(self._rtt_values), 1)      if self._rtt_values else None
        rtt_min    = round(min(self._rtt_values), 1)                             if self._rtt_values else None
        rtt_max    = round(max(self._rtt_values), 1)                             if self._rtt_values else None
        rtt_med    = round(sorted(self._rtt_values)[len(self._rtt_values)//2], 1) if self._rtt_values else None
        total_pkt  = len(self._pkt_ids)
        # FIX: windowed
        duplicates = self._count_duplicates()
        dup_rate   = round(duplicates / max(total_pkt, 1) * 100, 1) if total_pkt > 0 else None
        # FIX: NAK separados
        net_ack_total = self._routing_acks + self._routing_naks
        net_nak_rate  = round(self._routing_naks / net_ack_total * 100, 1) if net_ack_total > 0 else None
        active_senders = len(set(v["from"] for v in self._pkt_ids.values()))
        ch_active  = self._ch_util_active()
        ch_util_avg = (sum(ch_active.values()) / len(ch_active) if ch_active else None)
        p_col = round((1 - math.exp(-ch_util_avg / 100.0)) * 100 * 0.5, 1) if ch_util_avg is not None else None
        return {
            "sent": self._msgs_sent, "acked": self._msgs_acked,
            "ack_implicit": self._msgs_ack_implicit,
            "naked": self._msgs_naked, "pending": pending,
            "delivery": delivery, "nak_rate": nak_rate,
            "rtt_avg": rtt_avg, "rtt_min": rtt_min, "rtt_max": rtt_max, "rtt_med": rtt_med,
            "n_rtt": len(self._rtt_values),
            "total_pkt": total_pkt, "duplicates": duplicates, "dup_rate": dup_rate,
            "net_acks": self._routing_acks, "net_naks": self._routing_naks,
            "fw_errs": self._routing_fw_errs,
            "net_nak_rate": net_nak_rate, "active_senders": active_senders,
            "p_col": p_col,
            "ch_util_avg": round(ch_util_avg, 1) if ch_util_avg is not None else None,
            "lbl_dup": (
                tr("Sem dados") if dup_rate is None else
                tr("⚠ Atenção")  if dup_rate < 10 else
                tr("✅ Flood saudável") if dup_rate <= 60 else
                tr("[!] Possível congestionamento")
            ),
            "lbl_col": (
                tr("Sem dados de Ch.Util.") if p_col is None else
                tr("✅ Flood saudável")      if p_col < 5  else
                tr("⚠ Próximo do limite")   if p_col < 15 else
                tr("[!] Risco elevado")
            ),
            "lbl_pkt_sub": tr("{n} nós emissores · {m} duplicados vistos",
                              n=active_senders, m=duplicates),
            "ever_seen": self._pkt_ids_ever > 0,
        }

    def _data_latency(self) -> dict:
        n = len(self._rtt_values)
        if n == 0:
            return {"n": 0, "avg": None, "med": None,
                    "min": None, "max": None, "p90": None,
                    "hist_labels": [], "hist_counts": [], "now": self._now_str()}
        s   = sorted(self._rtt_values)
        avg = round(sum(s) / n, 1)
        med = round(s[n // 2], 1)
        mn  = round(s[0], 1)
        mx  = round(s[-1], 1)
        p90 = round(s[int(n * 0.9)], 1)
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
                rows.append([from_id, self._name(from_id), nb_id, self._name(nb_id),
                              snr_str, float(snr) if snr else None])
        rows.sort(key=lambda r: r[2], reverse=True)
        return {"rows": rows, "n_links": len(rows), "n_nodes": len(self._nb_links),
                "now": self._now_str()}

    def _data_range_links(self) -> dict:
        import math as _m
        def haversine(lat1, lon1, lat2, lon2):
            R    = 6371.0
            dlat = _m.radians(lat2 - lat1)
            dlon = _m.radians(lon2 - lon1)
            a    = (_m.sin(dlat/2)**2 +
                    _m.cos(_m.radians(lat1)) * _m.cos(_m.radians(lat2)) * _m.sin(dlon/2)**2)
            return R * 2 * _m.atan2(_m.sqrt(a), _m.sqrt(1-a))
        node_pos  = self._node_pos   # FIX: atributo inicializado em _reset_data
        rows      = []
        max_range = None
        max_pair  = ("—", "—")
        seen      = set()
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
                dist    = round(haversine(pos_a[0], pos_a[1], pos_b[0], pos_b[1]), 3)
                snr_str = f"{snr:+.1f}" if snr else "—"
                rows.append([from_id, self._name(from_id), nb_id, self._name(nb_id),
                              dist, snr_str, snr])
                if max_range is None or dist > max_range:
                    max_range = dist
                    max_pair  = (self._name(from_id), self._name(nb_id))
        rows.sort(key=lambda r: r[4], reverse=True)
        return {"rows": rows, "max_range": max_range, "max_pair": max_pair,
                "n_with_gps": len(node_pos), "now": self._now_str()}

    def _data_intervals(self) -> dict:
        rows = []
        for nid, entry in self._pkt_intervals.items():
            vals = entry['vals']
            if len(vals) < 2:
                continue
            avg = round(sum(vals) / len(vals), 1)
            mn  = round(min(vals), 1)
            mx  = round(max(vals), 1)
            rows.append([nid, self._name(nid), avg, mn, mx, len(vals)])
        rows.sort(key=lambda r: r[1])
        return {"rows": rows, "now": self._now_str(),
                "lbl_freq": {"high": tr("Alta frequência"), "normal": "Normal",
                             "low": tr("Baixa frequência")}}

    def _data_local_node(self) -> dict:
        """Dados da secção dedicada ao nó local."""
        dc_est  = round(min(self._local_air_tx * 6, 100.0), 2)
        snr_avg = (round(sum(self._local_snr_rx)/len(self._local_snr_rx), 1)
                   if self._local_snr_rx else None)
        snr_min = round(min(self._local_snr_rx), 1) if self._local_snr_rx else None
        snr_max = round(max(self._local_snr_rx), 1) if self._local_snr_rx else None

        def fmt_uptime(s):
            if not s: return "—"
            d, rem = divmod(int(s), 86400)
            h, rem = divmod(rem, 3600)
            m, sec = divmod(rem, 60)
            if d: return f"{d}d {h:02d}h {m:02d}m"
            if h: return f"{h}h {m:02d}m"
            return f"{m}m {sec:02d}s"

        total_resp = self._msgs_acked + self._msgs_naked
        delivery   = round(self._msgs_acked / total_resp * 100, 1) if total_resp > 0 else None
        nak_rate   = round(self._msgs_naked / total_resp * 100, 1) if total_resp > 0 else None
        pending    = max(self._msgs_sent - self._msgs_acked - self._msgs_naked, 0)
        rtt_avg    = (round(sum(self._rtt_values)/len(self._rtt_values), 1)
                     if self._rtt_values else None)
        rtt_med    = (round(sorted(self._rtt_values)[len(self._rtt_values)//2], 1)
                     if self._rtt_values else None)

        local_pos    = self._node_pos.get(self._local_nid) if self._local_nid else None
        dc_ts_labels = [self._ts_label(t) for t, _ in self._local_dc_ts]
        dc_ts_vals   = [v for _, v in self._local_dc_ts]

        # Pacotes do nó local observados na rede (loopback pode filtrar alguns)
        local_tx_pkts = (sum(1 for p in self._packets if p[1] == self._local_nid)
                         if self._local_nid else 0)

        return {
            "nid":           self._local_nid or "—",
            "name":          self._name(self._local_nid) if self._local_nid else "—",
            "hw_model":      self._local_hw_model or "—",
            "battery":       self._local_battery,
            "voltage":       self._local_voltage,
            "uptime_fmt":    fmt_uptime(self._local_uptime),
            "uptime_raw":    self._local_uptime,   # segundos — JS incrementa dinamicamente
            "uptime_ts":     round(time.time()),   # quando o uptime_raw foi lido
            "ch_util":       round(self._local_ch_util, 1),
            "air_tx":        round(self._local_air_tx, 2),
            "dc_est":        dc_est,
            "dc_ts_labels":  dc_ts_labels,
            "dc_ts_vals":    dc_ts_vals,
            "snr_rx_avg":    snr_avg,
            "snr_rx_min":    snr_min,
            "snr_rx_max":    snr_max,
            "n_snr_rx":      len(self._local_snr_rx),
            "msgs_sent":     self._msgs_sent,
            "msgs_acked":    self._msgs_acked,
            "msgs_naked":    self._msgs_naked,
            "msgs_implicit": self._msgs_ack_implicit,
            "msgs_pending":  pending,
            "delivery":      delivery,
            "nak_rate":      nak_rate,
            "rtt_avg":       rtt_avg,
            "rtt_med":       rtt_med,
            "n_rtt":         len(self._rtt_values),
            "lat":           local_pos[0] if local_pos else None,
            "lon":           local_pos[1] if local_pos else None,
            "local_tx_pkts": local_tx_pkts,
            "now":           self._now_str(),
            # Labels traduzidos para uso no JS (update sem reload)
            "lbl_dc_optimal":  tr("lbl_dc_optimal"),
            "lbl_dc_warn":     tr("lbl_dc_warn"),
            "lbl_dc_exceeded": tr("lbl_dc_exceeded"),
            "lbl_packets":     tr("pacotes"),
            "lbl_rtt_avg":     tr("RTT médio"),
            "lbl_median":      tr("mediana"),
        }
