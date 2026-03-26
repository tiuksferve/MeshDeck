"""
tabs/metrics_data.py — MetricsDataMixin: estruturas de dados, ingestão de
pacotes e cálculo de métricas para a aba de métricas em tempo real.

Separado de tab_metrics.py para facilitar manutenção.
Importado exclusivamente por MetricsTab (tabs/tab_metrics.py).
"""
import math
import time
from collections import deque
from datetime import datetime
from i18n import tr


class MetricsDataMixin:
    """Mixin com toda a lógica de dados: reset, ingestão e cálculo.

    Não tem dependência de Qt — pode ser testado isoladamente.
    Assume que a classe que herdar tem:
      - self._node_short (dict)  — preenchido em ingest_packet
    """

    def _reset_data(self):
        """Inicializa / limpa todas as estruturas de dados de métricas."""
        from collections import deque
        self._start_time  = time.time()

        # Mapa de nomes curtos: nid → short_name (actualizado em cada pacote)
        self._node_short: dict = {}   # nid → short_name ou nid se desconhecido

        # Pacotes recebidos — lista de (timestamp, from_id, portnum, snr, hops, via_mqtt)
        self._packets: list = []

        # Canal & Airtime — por nó: {nid: [{'ts':..,'ch_util':..,'air_tx':..}]}
        self._ch_util: dict  = {}   # nid → último channelUtilization (%)
        self._air_tx: dict   = {}   # nid → último airUtilTx (%)
        self._ch_util_ts: list = [] # [(ts, valor_médio)]  — série temporal 30 pontos

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

        # Fiabilidade — nó local (mensagens enviadas)
        self._msgs_sent         = 0
        self._msgs_acked        = 0    # ACK real do destinatário
        self._msgs_ack_implicit = 0    # retransmissão local confirmada (não é entrega)
        self._msgs_naked        = 0
        self._sent_packet_ids: set = set()   # IDs dos nossos pacotes enviados (filtro)

        # Fiabilidade — rede (observação passiva de todos os pacotes)
        # Packet IDs vistos: {packet_id → (from_id, timestamp, count_seen)}
        # Duplicados = mesmo ID visto mais de uma vez (sinal de flood saudável)
        self._pkt_ids: dict    = {}    # packet_id → {'from': nid, 'ts': t, 'count': n}
        self._pkt_ids_ever: int = 0    # total ever seen (never resets, for "has data" check)
        self._duplicates: int  = 0     # pacotes recebidos com ID já visto
        self._routing_acks: int = 0    # ROUTING_APP com ACK recebidos na rede
        self._routing_naks: int = 0    # ROUTING_APP com NAK recebidos na rede
        # Série temporal de PDR observado (janela 30 min)
        self._pdr_ts: list     = []    # [(ts, pct_unique)]

        # Série temporal de nós activos (janela 60 min, ponto a cada 5s)
        self._nodes_active_ts: list = []  # [(ts, count)]

        # Vizinhança (NeighborInfo) — {nid: [(nb_id, snr), ...]}
        self._nb_links:   dict = {}   # nid → lista de (neighbor_id, snr)

        # Intervalo entre pacotes por nó — {nid: [last_ts, [interval_secs, ...]]}
        self._pkt_intervals: dict = {}  # nid → {'last': ts, 'vals': [s,...]}

        # Alcance por link (calculado de POSITION_APP + GPS coords)
        # {canonical_pair: {'dist_km': float, 'snr': float, 'count': int}}
        self._link_range: dict = {}   # (nid_a, nid_b) → stats

    # ── UI ────────────────────────────────────────────────────────────────
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

        # hopsAway do node_data (mais fiável)
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
            if len(self._hops_values) > 2000:
                self._hops_values = self._hops_values[-1500:]

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
                # Série temporal: média de todos os nós
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

        # Série temporal de nós activos (a cada 60s)
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

        # ── Fiabilidade da rede — processada em ingest_raw_packet ─────────

    def ingest_message_status(self, req_id: int, status: str):
        """Regista ACK/NAK APENAS para mensagens enviadas pelo nó local."""
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
        """Regista mensagem enviada pelo nó local com o seu packet_id."""
        self._msgs_sent += 1
        if packet_id:
            self._sent_packet_ids.add(packet_id)
            self._sent_ts[packet_id] = time.time()   # regista timestamp para RTT
        # Força refresh imediato na secção Fiabilidade
        self._refresh_if_reliability()

    def _refresh_if_reliability(self):
        """Dispara refresh imediato se a secção activa for Fiabilidade."""
        if getattr(self, '_current_key', None) != 'reliability':
            return
        self._refresh_current()


    def ingest_neighbor_info(self, from_id: str, neighbors: list):
        """Regista dados de NeighborInfo para a tabela de vizinhança nas métricas."""
        if from_id and neighbors:
            self._nb_links[from_id] = neighbors

    def ingest_raw_packet(self, packet: dict):
        """Processa pacote raw para métricas de fiabilidade da rede (todos os nós)."""
        ts      = time.time()
        pkt_id  = packet.get('id')
        nid     = packet.get('fromId', '')
        decoded = packet.get('decoded') or {}
        portnum = decoded.get('portnum', '')

        # ── Duplicados (flood) ─────────────────────────────────────────
        # Rastreia IDs únicos; duplicados = mesmo ID recebido via múltiplos nós
        # Indica flood activo (saudável) vs congestionamento (excessivo)
        if pkt_id and nid:
            if pkt_id in self._pkt_ids:
                self._duplicates += 1
                self._pkt_ids[pkt_id]['count'] += 1
                # Actualiza ts para o mais recente (mantém o ID vivo na janela)
                self._pkt_ids[pkt_id]['ts'] = ts
            else:
                self._pkt_ids[pkt_id] = {'from': nid, 'ts': ts, 'count': 1}
                self._pkt_ids_ever += 1
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
        table_rows = [[nid, self._name(nid), cnt, round(self._ch_util.get(nid,0),1),
                       self._battery.get(nid)] for nid,cnt in top]
        return {"total_pkts":total_pkts,"n_active":len(active_nids),"ppm":ppm,
                "snr_avg":snr_avg,"hops_avg":hops_avg,"ch_avg":ch_avg,"air_avg":air_avg,
                "delivery":delivery,"table_rows":table_rows,"now":self._now_str(),
                "unit_nos": " " + tr("nós"),
                "now_label": tr("Actualizado:")}

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
            rows.append([nid, self._name(nid), round(ch,1), round(air,2), dc])
        return {"duty_avg":duty_avg,"air_avg":air_avg,"ch_net_avg":ch_net_avg,
                "ts_labels":ts_labels,"ts_vals":ts_vals,"rows":rows,"now":self._now_str(),
                "lbl_exceed": tr("🚨 Excede limite"),
                "lbl_warn":   tr("⚠ Atenção"),
                "lbl_ok":     "✅ OK"}

    def _name(self, nid: str) -> str:
        """Devolve o nome curto do nó se disponível, senão o ID."""
        return self._node_short.get(nid, nid) if nid else nid

    def _rf_assessment(self, snr_avg, snr_med, snr_p10, hops_values) -> str:
        """Avaliação da qualidade RF da rede baseada em distribuição de pacotes por faixa de SNR."""
        if snr_avg is None or not self._snr_values:
            return tr("⏳ Aguardando dados suficientes para avaliação...")

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
            f"<b>{tr('Distribuição de qualidade em {n} pacotes:', n=n)}</b> "
            f"<span style='color:#39d353'>{pct_exc}% {tr('excelente')} (≥8dB)</span> · "
            f"<span style='color:#56d364'>{pct_good}% {tr('bom')} (5–8dB)</span> · "
            f"<span style='color:#f0883e'>{pct_marg}% {tr('marginal')} (0–5dB)</span> · "
            f"<span style='color:#f85149'>{pct_weak}% {tr('fraco')} (&lt;0dB)</span>"
        )

        # ── Avaliação global ─────────────────────────────────────────────
        if pct_ok >= 80:
            lines.append(tr("✅ Rede em excelentes condições RF. A grande maioria dos pacotes chega com sinal forte."))
        elif pct_ok >= 60:
            lines.append(tr("✅ Qualidade RF boa. A maioria das ligações é estável, com algumas margens."))
        elif pct_ok >= 40:
            lines.append(tr("⚠️ Qualidade RF moderada."))
        else:
            lines.append(tr("🚨 Qualidade RF fraca."))

        # ── SNR P10 (pior 10%) ───────────────────────────────────────────
        if snr_p10 is not None:
            if snr_p10 < -10:
                lines.append(tr("⚠️ Pior decil SNR fraco", snr_p10=snr_p10))
            elif snr_p10 < 0:
                lines.append(tr("ℹ️ Pior decil SNR marginal", snr_p10=snr_p10))
            else:
                lines.append(tr("✅ Pior decil SNR ok", snr_p10=snr_p10))

        # ── Análise de hops ──────────────────────────────────────────────
        if hops_values:
            avg_hops = sum(hops_values) / len(hops_values)
            pct_direct = round(hops_values.count(0) / len(hops_values) * 100)
            pct_1hop   = round(hops_values.count(1) / len(hops_values) * 100)
            max_hops   = max(hops_values)
            lines.append(
                tr("topologia", pct_direct=f"{pct_direct:.0f}", pct_1hop=f"{pct_1hop:.0f}", avg_hops=avg_hops, max_hops=max_hops)
            )
            if avg_hops > 2.5:
                lines.append(tr("⚠️ Média de hops elevada"))
            if max_hops >= 6:
                lines.append(tr("⚠️ Máximo de hops", max_hops=max_hops))

        # ── Conclusão ────────────────────────────────────────────────────
        if pct_ok >= 70 and (not hops_values or sum(hops_values)/len(hops_values) < 2):
            lines.append(tr("conclusao_verde"))
        elif pct_ok >= 50:
            lines.append(tr("conclusao_amarela"))
        else:
            lines.append(tr("conclusao_vermelha"))

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
                "assessment": assessment,
                "unit_amostras": tr("amostras")}

    def _data_traffic(self) -> dict:
        now = time.time()
        label_map={"TEXT_MESSAGE_APP":tr("💬 Mensagem"),"NODEINFO_APP":"🆔 NodeInfo",
                   "POSITION_APP":tr("📍 Posição"),"TELEMETRY_APP":tr("📊 Telemetria"),
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
        # Padrão de routing
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
                "ppm_labels":[b[0] for b in bins],"ppm_vals":[b[1] for b in bins],
                "lbl_direct":  tr("🟢 Directo"),
                "lbl_1hop":    tr("🔵 1 Hop"),
                "lbl_multi":   tr("🟠 Multi-hop"),
                "lbl_unknown": tr("⚫ Desconhecido")}

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

        # Nós com GPS
        # Contados da lista de pacotes únicos que tiveram um POSITION_APP
        n_gps = sum(1 for p in self._packets
                    if p[2] == 'POSITION_APP' and p[1])
        n_gps_unique = len(set(p[1] for p in self._packets
                               if p[2] == 'POSITION_APP' and p[1]))

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
            # Translated JS labels
            "lbl_dup": (
                tr("Sem dados") if dup_rate is None else
                tr("⚠ Atenção") if dup_rate < 10 else
                tr("✅ Flood saudável") if dup_rate <= 60 else
                tr("[!] Possível congestionamento")
            ),
            "lbl_col": (
                tr("Sem dados de Ch.Util.") if p_col is None else
                tr("✅ Flood saudável") if p_col < 5 else
                tr("⚠ Próximo do limite") if p_col < 15 else
                tr("[!] Risco elevado")
            ),
            "lbl_pkt_sub": tr("{n} nós emissores · {m} duplicados vistos",
                              n=active_senders, m=self._duplicates),
            "ever_seen": getattr(self, '_pkt_ids_ever', 0) > 0,
        }

    # ── 1. Visão Geral ────────────────────────────────────────────────────
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
                rows.append([from_id, self._name(from_id), nb_id, self._name(nb_id), snr_str, float(snr) if snr else None])
        rows.sort(key=lambda r: r[2], reverse=True)
        return {"rows": rows, "n_links": len(rows), "n_nodes": len(self._nb_links), "now": self._now_str()}

    # ── 9. Alcance & Links ────────────────────────────────────────────────
    def _data_range_links(self) -> dict:
        """Calcula distância entre pares de nós vizinhos com GPS."""
        import math as _m
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = _m.radians(lat2 - lat1)
            dlon = _m.radians(lon2 - lon1)
            a = (_m.sin(dlat/2)**2 +
                 _m.cos(_m.radians(lat1)) * _m.cos(_m.radians(lat2)) * _m.sin(dlon/2)**2)
            return R * 2 * _m.atan2(_m.sqrt(a), _m.sqrt(1-a))

        # Usa posições dos nós nos pacotes recebidos
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
                rows.append([from_id, self._name(from_id), nb_id, self._name(nb_id), dist, snr_str, snr])
                if max_range is None or dist > max_range:
                    max_range = dist
                    max_pair = (self._name(from_id), self._name(nb_id))  # para KPI

        rows.sort(key=lambda r: r[2], reverse=True)
        return {"rows": rows, "max_range": max_range, "max_pair": max_pair,
                "n_with_gps": len(node_pos), "now": self._now_str()}

    def ingest_node_position(self, nid: str, lat: float, lon: float):
        """Regista posição GPS de um nó para cálculo de alcance."""
        if nid and lat is not None and lon is not None:
            if not hasattr(self, '_node_pos'):
                self._node_pos = {}
            self._node_pos[nid] = (lat, lon)


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
                "lbl_freq": {
                    "high":   tr("Alta frequência"),
                    "normal": "Normal",
                    "low":    tr("Baixa frequência")
                }}

