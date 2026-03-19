"""
tabs/metrics_render.py — MetricsRenderMixin: geração de HTML/JS para cada
secção de métricas (Chart.js, tabelas, KPIs).

Separado de tab_metrics.py para facilitar manutenção.
Importado exclusivamente por MetricsTab (tabs/tab_metrics.py).
"""
import json
import math
import time
from datetime import datetime

from constants import (
    logger,
    DARK_BG, PANEL_BG, BORDER_COLOR, ACCENT_GREEN, ACCENT_BLUE,
    ACCENT_ORANGE, ACCENT_RED, TEXT_PRIMARY, TEXT_MUTED
)


class MetricsRenderMixin:
    """Mixin com toda a geração de HTML/JS para as secções de métricas.

    Depende dos atributos de dados definidos em MetricsDataMixin.
    """

    def _base_html(self, title: str, body: str) -> str:
        """Template HTML base com Chart.js e estilos."""
        return f"""<!DOCTYPE html><html><head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script>if(window.Chart){{Chart.defaults.animation=false;}}</script>
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

        # Taxa de entrega
        total_r = self._msgs_acked + self._msgs_naked
        delivery = round(self._msgs_acked / total_r * 100, 1) if total_r > 0 else None

        def kpi(val, unit, label, color="", kid=""):
            v = f"{val}{unit}" if val is not None else "—"
            id_attr = f' id="{kid}"' if kid else ""
            return f'<div class="card"><h3>{label}</h3><div{id_attr} class="kpi {color}">{v}</div></div>'

        def ch_kpi(val):
            if val is None: return kpi(None, "", "Utiliz. Canal (avg)")
            color = "green" if val < self.CH_UTIL_OK else ("orange" if val < self.CH_UTIL_WARN else "red")
            bar_color = "#39d353" if val < self.CH_UTIL_OK else ("#f0883e" if val < self.CH_UTIL_WARN else "#f85149")
            pct = min(int(val), 100)
            return f'''<div class="card"><h3>Utiliz. Canal (avg)</h3>
              <div id="ov-chutil" class="kpi {color}">{val}%</div>
              <div class="bar-wrap"><div class="bar-bg">
              <div class="bar-fill" style="width:{pct}%;background:{bar_color}"></div>
              </div></div>
              <div class="kpi-sub">&lt;25% óptimo · &lt;50% aceitável · &gt;50% crítico</div>
            </div>'''

        # Tabela top nós por pacotes
        nid_counts = {}
        for p in self._packets:
            if p[1]: nid_counts[p[1]] = nid_counts.get(p[1], 0) + 1
        top = sorted(nid_counts.items(), key=lambda x: -x[1])[:8]
        rows = "".join(
            f"<tr><td>{self._name(nid)}</td><td>{cnt}</td>"
            f"<td>{round(self._ch_util.get(nid, 0), 1)}%</td>"
            f"<td>{self._battery.get(nid, '—')}{'%' if self._battery.get(nid) is not None else ''}</td></tr>"
            for nid, cnt in top
        ) or "<tr><td colspan='4' class='no-data'>Sem dados ainda</td></tr>"

        body = f"""
<div class="subtitle">Resumo da sessão · Actualizado: {self._now_str()}</div>
<div class="grid-3">
  {kpi(total_pkts, "", "Total Pacotes", "blue", "ov-pkts")}
  {kpi(n_active, " nós", "Nós Activos (2h)", "green", "ov-active")}
  {kpi(ppm, "/min", "Pacotes/min", "", "ov-ppm")}
</div>
<div class="grid-3">
  {kpi(snr_avg, " dB", "SNR Médio", "green" if snr_avg and snr_avg >= 0 else "orange", "ov-snr")}
  {kpi(hops_avg, " hops", "Hops Médio", "", "ov-hops")}
  {kpi(delivery, "%", "Taxa Entrega", "green" if delivery and delivery >= 80 else "orange", "ov-delivery")}
</div>
<div class="grid">
  {ch_kpi(ch_util_avg)}
  {kpi(air_avg, "%", "Airtime TX (avg)", "green" if air_avg and air_avg < 10 else "orange", "ov-air")}
</div>
<div class="card" style="margin-top:16px">
  <h3>Top Nós por Pacotes</h3>
  <table><tr><th>ID</th><th>Nome</th><th>Pacotes</th><th>Ch. Util.</th><th>Bateria</th></tr><tbody id="ov-node-tbody">{rows}</tbody></table>
</div>
<div class="updated" id="ov-updated">Sessão iniciada · {datetime.fromtimestamp(self._start_time).strftime('%H:%M:%S %d/%m/%Y')} · Actualizado: {self._now_str()}</div>
<script>
window._metricsUpdateData = function(d) {{
  function kpiColor(val, thresholds) {{
    if(val===null||val===undefined) return '';
    for(var i=0;i<thresholds.length;i++) if(val<=thresholds[i][0]) return thresholds[i][1];
    return thresholds[thresholds.length-1][1];
  }}
  function setKpi(id, val, unit) {{
    var e=document.getElementById(id); if(!e) return;
    e.textContent = val!==null&&val!==undefined ? val+unit : '—';
  }}
  function setKpiClass(id, cls) {{
    var e=document.getElementById(id); if(e) e.className='kpi '+(cls||'')+' ov-kpi';
  }}
  setKpi('ov-pkts', d.total_pkts, '');
  setKpi('ov-active', d.n_active, ' nós');
  setKpi('ov-ppm', d.ppm, '/min');
  setKpi('ov-snr', d.snr_avg, ' dB');
  setKpiClass('ov-snr', d.snr_avg!==null&&d.snr_avg>=0?'green':'orange');
  setKpi('ov-hops', d.hops_avg, ' hops');
  setKpi('ov-delivery', d.delivery, '%');
  setKpiClass('ov-delivery', d.delivery!==null&&d.delivery>=80?'green':'orange');
  setKpi('ov-chutil', d.ch_avg, '%');
  setKpiClass('ov-chutil', d.ch_avg===null?'':d.ch_avg<25?'green':d.ch_avg<50?'orange':'red');
  setKpi('ov-air', d.air_avg, '%');
  setKpiClass('ov-air', d.air_avg!==null&&d.air_avg<10?'green':'orange');
  var e=document.getElementById('ov-updated'); if(e) e.textContent='Actualizado: '+d.now;
  var tb=document.getElementById('ov-node-tbody');
  if(tb && d.table_rows && d.table_rows.length) {{
    var h='';
    d.table_rows.forEach(function(r) {{
      var nid=r[0],nm=r[1],cnt=r[2],ch=r[3],batt=r[4];
      var b=batt===101?'⚡':batt!==null&&batt!==undefined?batt+'%':'—';
      h+='<tr><td>'+nid+'</td><td>'+nm+'</td><td>'+cnt+'</td><td>'+ch+'%</td><td>'+b+'</td></tr>';
    }});
    tb.innerHTML=h;
  }}
}};
</script>"""
        return self._base_html("📊 Visão Geral", body)

    # ── 2. Canal & Airtime ────────────────────────────────────────────────
    # Limites de duty cycle horário (EU_433 / EU_868 — ETSI EN300.220)
    DUTY_CYCLE_LIMIT_EU = 10.0   # 10%/hora — limite legal EU
    DUTY_CYCLE_WARN_EU  =  7.0   # 7%/hora — aviso preventivo

    def _html_channel(self) -> str:
        if not self._ch_util and not self._ch_util_ts and not self._air_tx:
            body = '<div class="no-data">⏳ Aguardando dados de telemetria (TELEMETRY_APP)...<br><br>Os nós devem ter o módulo de telemetria activado.</div>'
            return self._base_html("📡 Canal & Airtime", body)

        # Hourly Duty Cycle estimado: airUtilTx (10 min) × 6 = estimativa 1h
        # airUtilTx é uma métrica POR NÓ (tx daquele nó).
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
            if dc >= self.DUTY_CYCLE_LIMIT_EU: return "red",    "🚨 LIMITE EXCEDIDO"
            if dc >= self.DUTY_CYCLE_WARN_EU:  return "orange", "⚠ Próximo do limite"
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
            rows = "<tr><td colspan='5' class='no-data'>Sem dados</td></tr>"

        # KPI: pior nó (mais relevante para conformidade EU)
        # KPI principal: channelUtilization médio da rede
        # (cada nó reporta o que VÊ no canal — é a métrica da rede, não do nó)
        ch_net_avg = round(sum(self._ch_util.values()) / len(self._ch_util), 1) if self._ch_util else None
        if ch_net_avg is not None:
            ch_color = "green" if ch_net_avg < self.CH_UTIL_OK else ("orange" if ch_net_avg < self.CH_UTIL_WARN else "red")
            ch_bar_c = {"green": "#39d353", "orange": "#f0883e", "red": "#f85149"}[ch_color]
            ch_pct   = min(int(ch_net_avg), 100)
            ch_label = "✅ Óptimo (<25%)" if ch_net_avg < self.CH_UTIL_OK else ("⚠ Aceitável (<50%)" if ch_net_avg < self.CH_UTIL_WARN else "🚨 Crítico (>50%)")
            ch_kpi = (
                f'<div class="card"><h3>Channel Utilization da Rede</h3>'
                f'<div id="ch-net-val" class="kpi {ch_color}">{ch_net_avg}%</div>'
                f'<div class="bar-wrap"><div class="bar-bg">'
                f'<div class="bar-fill" style="width:{ch_pct}%;background:{ch_bar_c}"></div></div></div>'
                f'<div class="kpi-sub"><b>Métrica da rede</b> — airtime observado por cada nó (RX+TX de todos) · {ch_label}<br>'
                f'Firmware atrasa envios acima de 25% · Para GPS: limite 40%</div></div>'
            )
        else:
            ch_kpi = '<div class="card"><h3>Channel Utilization da Rede</h3><div class="kpi" style="color:#8b949e">—</div><div class="kpi-sub">Aguardando dados de telemetria...</div></div>'

        # KPI secundário: duty cycle do pior nó (airUtilTx por nó — conformidade EU)
        if worst_dc is not None:
            worst_name = self._name(worst_nid)
            dc_color_w, dc_label_w = duty_status(worst_dc)
            dc_pct_w = min(int(worst_dc / self.DUTY_CYCLE_LIMIT_EU * 100), 100)
            bar_c_w  = {"green": "#39d353", "orange": "#f0883e", "red": "#f85149"}[dc_color_w]
            duty_kpi = (
                f'<div class="card"><h3>Duty Cycle/h — Pior Nó ({worst_name})</h3>'
                f'<div id="dc-avg-val" class="kpi {dc_color_w}">{worst_dc}%</div>'
                f'<div class="bar-wrap"><div class="bar-bg">'
                f'<div class="bar-fill" style="width:{dc_pct_w}%;background:{bar_c_w}"></div></div></div>'
                f'<div class="kpi-sub"><b>Métrica por nó</b> (TX daquele nó) · airUtilTx×6 · Limite EU: 10%/hora · {dc_label_w}</div></div>'
            )
        else:
            duty_kpi = '<div class="card"><h3>Duty Cycle/h por Nó</h3><div class="kpi" style="color:#8b949e">—</div><div class="kpi-sub">Aguardando dados de airUtilTx...</div></div>'

        air_avg = round(sum(self._air_tx.values()) / len(self._air_tx), 2) if self._air_tx else None
        air_color = "green" if air_avg and air_avg < 10 else ("orange" if air_avg else "")
        air_kpi = (
            f'<div class="card"><h3>Airtime TX (10 min, avg)</h3>'
            f'<div class="kpi {air_color}">{air_avg if air_avg is not None else "—"}'
            f'{"%" if air_avg is not None else ""}</div>'
            f'<div class="kpi-sub">Média de TX de todos os nós nos últimos 10 min</div></div>'
        )

        n_ts = len(ts_vals) or 1
        body = f"""
<div class="subtitle">Canal LoRa · Airtime TX · Hourly Duty Cycle · {self._now_str()}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #39d353;padding:8px 14px">
  <span style="color:#39d353;font-size:12px;font-weight:bold">🌐 Métrica da Rede</span><span style="color:#8b949e;font-size:11px"> — os dados abaixo são observados passivamente a partir de todos os pacotes recebidos pelo nó local. Refletem o estado de toda a rede visível, não apenas o nó local.</span>
</div>
<div class="grid-3">{ch_kpi}{duty_kpi}{air_kpi}</div>
<div class="card" style="margin-top:16px">
  <h3>Channel Utilization ao Longo do Tempo</h3>
  <div class="chart-wrap-lg"><canvas id="chChart"></canvas></div>
</div>
<div class="card" style="margin-top:16px">
  <h3>Por Nó — Ch. Util · Airtime TX · Duty Cycle/h</h3>
  <table><tr><th>ID</th><th>Nome</th><th>Ch. Util.</th><th>Air TX (10m)</th><th>Duty Cycle/h</th><th>Estado</th></tr><tbody id="ch-node-tbody">{rows}</tbody></table>
  <div style="color:#8b949e;font-size:10px;margin-top:8px;padding-top:8px;border-top:1px solid #21262d">
    ℹ️ Duty cycle horário estimado = airUtilTx × 6. Limite EU_433/EU_868: 10%/hora (ETSI EN300.220).
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
      {{ label: 'Limite óptimo (25%)', data: Array({n_ts}).fill(25),
         borderColor: '#f0883e', borderDash: [4,4], pointRadius: 0, fill: false }},
      {{ label: 'Limite crítico (50%)', data: Array({n_ts}).fill(50),
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
  // Actualiza tabela por nó
  var tbody = document.getElementById('ch-node-tbody');
  if(tbody && d.rows && d.rows.length > 0) {{
    var DUTY_WARN=7, DUTY_LIMIT=10;
    var html='';
    d.rows.forEach(function(r) {{
      var nid=r[0], nm=r[1], ch=r[2], air=r[3], dc=r[4];
      var chTag = ch>50?'red':ch>25?'orange':'green';
      var airTag = air<10?'green':air<25?'orange':'red';
      var dcColor = dc>=DUTY_LIMIT?'red':dc>=DUTY_WARN?'orange':'green';
      var dcPct = Math.min(Math.round(dc/DUTY_LIMIT*100),100);
      var barC = dcColor==='green'?'#39d353':dcColor==='orange'?'#f0883e':'#f85149';
      html += '<tr><td>'+nid+'</td><td>'+nm+'</td>'
            + '<td><span class="tag tag-'+chTag+'">'+ch+'%</span></td>'
            + '<td><span class="tag tag-'+airTag+'">'+air+'%</span></td>'
            + '<td><span class="tag tag-'+dcColor+'">'+dc+'%</span>'
            + '<div class="bar-bg" style="margin-top:3px"><div class="bar-fill" style="width:'+dcPct+'%;background:'+barC+'"></div></div></td>'
            + '<td><span class="tag tag-'+dcColor+'">'
            + (dc>=DUTY_LIMIT?'🚨 Excede limite':dc>=DUTY_WARN?'⚠ Atenção':'✅ OK')
            + '</span></td></tr>';
    }});
    tbody.innerHTML = html;
  }}
}};
</script>"""
        return self._base_html("📡 Canal & Airtime", body)

    # ── 3. Qualidade RF ───────────────────────────────────────────────────
    def _html_rf(self) -> str:
        if not self._snr_values and not self._hops_values:
            body = '<div class="no-data">⏳ Aguardando pacotes RF...</div>'
            return self._base_html("📶 Qualidade RF", body)

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
<div class="subtitle" id="snr-n">Distribuição de SNR e hops · {len(self._snr_values)} amostras</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #39d353;padding:8px 14px">
  <span style="color:#39d353;font-size:12px;font-weight:bold">🌐 Métrica da Rede</span><span style="color:#8b949e;font-size:11px"> — os dados abaixo são observados passivamente a partir de todos os pacotes recebidos pelo nó local. Refletem o estado de toda a rede visível, não apenas o nó local.</span>
</div>
<div class="card" id="assessment-card" style="margin-bottom:16px;border-left:4px solid {
'#39d353' if snr_avg and snr_avg >= 5 else '#f0883e' if snr_avg and snr_avg >= 0 else '#f85149'
}">
  <h3>Avaliação da Qualidade RF</h3>
  <div id="rf-assessment" style="font-size:13px;line-height:1.7;color:#e6edf3">{self._rf_assessment(snr_avg, snr_med, snr_p10, self._hops_values)}</div>
</div>
<div class="grid-3">
  <div class="card"><h3>SNR Médio</h3>
    <div class="kpi {'green' if snr_avg and snr_avg>=5 else 'orange' if snr_avg and snr_avg>=0 else 'red'}">{snr_avg if snr_avg is not None else '—'} dB</div></div>
  <div class="card"><h3>SNR Mediano</h3>
    <div class="kpi">{snr_med if snr_med is not None else '—'} dB</div></div>
  <div class="card"><h3>SNR P10 (pior 10%)</h3>
    <div class="kpi red">{snr_p10 if snr_p10 is not None else '—'} dB</div></div>
</div>
<div class="grid">
  <div class="card">
    <h3>Distribuição SNR (dB)</h3>
    <div class="chart-wrap"><canvas id="snrChart"></canvas></div>
  </div>
  <div class="card">
    <h3>Distribuição de Hops</h3>
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
  set('snr-n', d.n + ' amostras');
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
        return self._base_html("📶 Qualidade RF", body)

    # ── 4. Tráfego ────────────────────────────────────────────────────────
    def _html_traffic(self) -> str:
        now = time.time()
        if not self._packets:
            body = '<div class="no-data">⏳ Aguardando pacotes...</div>'
            return self._base_html("📦 Tráfego de Rede", body)

        label_map = {
            'TEXT_MESSAGE_APP':       '💬 Mensagem',
            'NODEINFO_APP':           '🆔 NodeInfo',
            'POSITION_APP':           '📍 Posição',
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

        # ── Padrão de routing ──────────────────────────────────────────
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
        routing_labels = ['🟢 Directo', '🔵 1 Hop', '🟠 Multi-hop', '⚫ Desconhecido']
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
<div class="subtitle">Distribuição de tráfego da sessão</div>

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
    <h3>Padrão de Routing</h3>
    <div style="display:flex;gap:16px;align-items:center;min-height:160px">
      <canvas id="routingChart" width="150" height="150" style="flex-shrink:0"></canvas>
      <div style="font-size:12px;color:#8b949e;line-height:2.2">
        <div id="rd-direct"><span style="color:#39d353;font-size:15px">■</span> Directo &nbsp;<b style="color:#e6edf3">{n_direct}</b> ({d_pct}%)</div>
        <div id="rd-1hop"><span style="color:#58a6ff;font-size:15px">■</span> 1 Hop &nbsp;<b style="color:#e6edf3">{n_1hop}</b> ({h_pct}%)</div>
        <div id="rd-multi"><span style="color:#f0883e;font-size:15px">■</span> Multi-hop ≥2 &nbsp;<b style="color:#e6edf3">{n_multi}</b> ({m_pct}%)</div>
        <div id="rd-unknown"><span style="color:#8b949e;font-size:15px">■</span> Desconhecido &nbsp;<b style="color:#e6edf3">{n_unknown}</b> ({u_pct}%)</div>
      </div>
    </div>
  </div>
</div>

<!-- Linha 2: barras por tipo -->
<div class="card" style="margin-top:16px">
  <h3>Pacotes por Tipo — Sessão</h3>
  <div class="chart-wrap"><canvas id="typeChart"></canvas></div>
</div>

<!-- Linha 3: PPM -->
<div class="card" style="margin-top:16px">
  <h3>Pacotes por Minuto (últimos 30 min)</h3>
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
    datasets: [{{ label: 'Pacotes/min', data: {json.dumps(ppm_vals)},
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
    setHtml('rd-direct',  '<span style="color:#39d353;font-size:15px">■</span> Directo &nbsp;<b style="color:#e6edf3">' + d.n_direct + '</b> (' + Math.round(d.n_direct/tot*100) + '%)');
    setHtml('rd-1hop',    '<span style="color:#58a6ff;font-size:15px">■</span> 1 Hop &nbsp;<b style="color:#e6edf3">' + d.n_1hop + '</b> (' + Math.round(d.n_1hop/tot*100) + '%)');
    setHtml('rd-multi',   '<span style="color:#f0883e;font-size:15px">■</span> Multi-hop ≥2 &nbsp;<b style="color:#e6edf3">' + d.n_multi + '</b> (' + Math.round(d.n_multi/tot*100) + '%)');
    setHtml('rd-unknown', '<span style="color:#8b949e;font-size:15px">■</span> Desconhecido &nbsp;<b style="color:#e6edf3">' + d.n_unknown + '</b> (' + Math.round(d.n_unknown/tot*100) + '%)');
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
        return self._base_html("📦 Tráfego de Rede", body)

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

        # Nós únicos com GPS
        n_gps_unique = len(set(p[1] for p in self._packets
                               if p[2] == 'POSITION_APP' and p[1]))

        # Tabela de nós com bateria (tensão e uptime incluídos)
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
                f"<tr><td>{nid}</td><td>{self._name(nid)}</td><td>{disp}{bar}</td>"
                f"<td style='color:#8b949e'>{volt_str}</td>"
                f"<td style='color:#8b949e'>{uptm_str}</td></tr>"
            )
        if not batt_rows:
            batt_rows = "<tr><td colspan='5' class='no-data'>Sem dados de bateria ainda</td></tr>"

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
<div class="subtitle">Saúde dos nós, baterias e hardware · {self._now_str()}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #39d353;padding:8px 14px">
  <span style="color:#39d353;font-size:12px;font-weight:bold">🌐 Métrica da Rede</span><span style="color:#8b949e;font-size:11px"> — os dados abaixo são observados passivamente a partir de todos os pacotes recebidos pelo nó local. Refletem o estado de toda a rede visível, não apenas o nó local.</span>
</div>
<div class="grid-3">
  <div class="card"><h3>Nós Activos (2h)</h3>
    <div class="kpi green" id="nodes-active">{n_active}</div></div>
  <div class="card"><h3>Bateria / Powered</h3>
    <div class="kpi blue" id="nodes-batt-count">{n_battery}</div>
    <div class="kpi-sub" id="nodes-powered">⚡ {n_powered} com alimentação externa · 📍 {n_gps_unique} com GPS</div></div>
  <div class="card"><h3>Bateria Média</h3>
    <div class="kpi {'green' if batt_avg and batt_avg>60 else 'orange'}" id="nodes-batt-avg">
      {f'{batt_avg:.0f}%' if batt_avg is not None else '—'}</div></div>
</div>
<div class="grid" style="margin-top:16px">
  <div class="card">
    <h3>Nós Activos ao Longo do Tempo</h3>
    <div class="chart-wrap"><canvas id="nodesChart"></canvas></div>
  </div>
  <div class="card">
    <h3>Distribuição de Bateria</h3>
    <div class="chart-wrap"><canvas id="battDistChart"></canvas></div>
  </div>
</div>
{f'<div class="card" style="margin-top:16px"><h3>Hardware por Modelo ({len(hw_model)} nós)</h3><div class="chart-wrap-lg"><canvas id="hwChart"></canvas></div></div>' if hw_labels else ''}
<div class="card" style="margin-top:16px">
  <h3>Bateria por Nó</h3>
  <table><tr><th>ID</th><th>Nome</th><th>Bateria</th><th>Tensão</th><th>Uptime</th></tr>{batt_rows}</table>
</div>
<script>
window._nodesChart = new Chart(document.getElementById('nodesChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(ts_labels)},
    datasets: [{{ label: 'Nós activos', data: {json.dumps(ts_vals)},
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
  set('nodes-powered',   '⚡ ' + (d.n_powered||0) + ' com alimentação externa · 📍 ' + (d.n_gps_unique||0) + ' com GPS');
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
        return self._base_html("🔋 Nós & Bateria", body)

    # ── 6. Fiabilidade ────────────────────────────────────────────────────
    def _html_latency(self) -> str:
        d = self._data_latency()
        if d["n"] == 0:
            body = ('<div class="no-data">⏳ Sem dados de latência ainda.<br><br>'
                    'Envie mensagens com wantAck=True para medir o RTT '
                    '(tempo entre envio e ACK do destinatário).</div>')
            return self._base_html("⏱ Latência (RTT)", body)

        def kpi(val, unit, label, color="", kid=""):
            v = f"{val}{unit}" if val is not None else "—"
            id_attr = f' id="{kid}"' if kid else ""
            return f'<div class="card"><h3>{label}</h3><div{id_attr} class="kpi {color}">{v}</div></div>'

        avg_color = ("green" if d["avg"] and d["avg"] < 10
                     else "orange" if d["avg"] and d["avg"] < 30 else "red")

        body = f"""
<div class="subtitle">RTT (Round-Trip Time) — tempo entre envio e ACK · {d['n']} amostras · {d['now']}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #f0883e;padding:8px 14px">
  <span style="color:#f0883e;font-size:12px;font-weight:bold">🏠 Métrica do Nó Local</span><span style="color:#8b949e;font-size:11px"> — os dados abaixo referem-se exclusivamente ao nó local (mensagens enviadas e respectivos ACK/NAK). Os outros nós da rede não contribuem para estes valores.</span>
</div>
<div class="grid-3">
  {kpi(d['avg'], 's', 'RTT Médio', avg_color)}
  {kpi(d['med'], 's', 'RTT Mediana', '')}
  {kpi(d['p90'], 's', 'RTT P90 (pior 10%)', 'orange')}
</div>
<div class="grid">
  {kpi(d['min'], 's', 'RTT Mínimo', 'green')}
  {kpi(d['max'], 's', 'RTT Máximo', '')}
</div>
<div class="card" style="margin-top:16px">
  <h3>Distribuição de RTT</h3>
  <div class="chart-wrap-lg"><canvas id="rttChart"></canvas></div>
</div>
<div class="card" style="margin-top:16px">
  <h3>Interpretação</h3>
  <p style="color:#8b949e;font-size:12px;line-height:1.8">
    <b style="color:#e6edf3">RTT &lt; 5s:</b> Ligação directa excelente (0 hops).<br>
    <b style="color:#e6edf3">RTT 5–15s:</b> Normal para 1–2 hops em LoRa.<br>
    <b style="color:#e6edf3">RTT 15–30s:</b> Possível congestão ou 3+ hops.<br>
    <b style="color:#e6edf3">RTT &gt; 30s:</b> Rede congestionada ou rota longa.<br>
    <br>
    O RTT inclui: tempo de espera de slot · transmissão LoRa · retransmissões de relay
    · processamento do destinatário · ACK de volta. Em LONG_FAST a transmissão de um
    pacote demora ~300ms; cada hop acrescenta janela de contenção aleatória.
  </p>
</div>
<script>
window._rttChart = new Chart(document.getElementById('rttChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(d['hist_labels'])},
    datasets: [{{ label: 'Nº de mensagens', data: {json.dumps(d['hist_counts'])},
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
        return self._base_html("⏱ Latência (RTT)", body)

    def _html_reliability(self) -> str:
        now = time.time()

        # ── Rede — observação passiva ──────────────────────────────────
        total_pkt      = len(self._pkt_ids)
        total_seen     = sum(v['count'] for v in self._pkt_ids.values()) if self._pkt_ids else 0
        # Dup rate: % de pacotes únicos vistos mais de 1 vez (flood activo)
        dup_rate       = round(self._duplicates / max(total_pkt, 1) * 100, 1) if total_pkt > 0 else None
        net_ack_total  = self._routing_acks + self._routing_naks
        net_nak_rate   = round(self._routing_naks / net_ack_total * 100, 1) if net_ack_total > 0 else None
        active_senders = len(set(v['from'] for v in self._pkt_ids.values()))

        if dup_rate is None:
            dup_color, dup_label = "", "Sem dados"
        elif dup_rate < 10:
            dup_color, dup_label = "orange", "⚠ Flood reduzido"
        elif dup_rate <= 60:
            dup_color, dup_label = "green",  "✅ Flood saudável"
        else:
            dup_color, dup_label = "red",    "🚨 Possível congestionamento"

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
            col_label = ("✅ Risco baixo"    if p_col_corrected < 5  else
                         "⚠ Risco moderado" if p_col_corrected < 15 else
                         "🚨 Risco elevado")
        else:
            p_col_corrected, col_color, col_label = None, "", "Sem dados de Ch. Util."

        # ── Nó local ──────────────────────────────────────────────────
        # ack       = ROUTING_APP de OUTRO nó → destinatário confirmou
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
                         '<div class="no-data" style="margin-bottom:12px">⏳ Aguardando pacotes ROUTING_APP na rede…</div>')
        no_local_data = ("" if sent > 0 else
                         '<div style="color:#8b949e;font-size:11px;margin-bottom:8px">⏳ Envie mensagens para ver métricas do nó local.</div>')

        body = f"""
<div class="subtitle">Fiabilidade da rede Meshtastic — observação passiva + nó local</div>

<h3 style="color:#58a6ff;font-size:13px;margin:0 0 10px 0">🌐 Fiabilidade da Rede (todos os nós)</h3>
{no_net_data}
<div class="grid" style="margin-bottom:12px">
  <div class="card">
    <h3>Taxa de Flood (5 min)</h3>
    <div id="rel-dup" class="kpi {dup_color}">{dup_rate if dup_rate is not None else '—'}{'%' if dup_rate is not None else ''}</div>
    <div id="rel-dup-label" class="kpi-sub">{dup_label}<br>% de pacotes únicos reencaminhados por ≥2 nós</div>
  </div>
  <div class="card">
    <h3>Colisões Estimadas (CAD)</h3>
    <div id="rel-col" class="kpi {col_color}">{p_col_corrected if p_col_corrected is not None else '—'}{'%' if p_col_corrected is not None else ''}</div>
    <div id="rel-col-label" class="kpi-sub">{col_label}<br>Modelo Poisson × 0.5 (CAD mitiga) · base: Ch.Util {round(ch_util_avg,1) if ch_util_avg else '—'}%</div>
  </div>
</div>
<div class="grid">
  <div class="card">
    <h3>NAK da Rede (ROUTING_APP)</h3>
    <div id="rel-net-nak" class="kpi {nak_net_color}">{net_nak_rate if net_nak_rate is not None else '—'}{'%' if net_nak_rate is not None else ''}</div>
    <div id="rel-net-sub" class="kpi-sub">ACK: {self._routing_acks} · NAK: {self._routing_naks}<br>Inclui NO_ROUTE e MAX_RETRANSMIT</div>
  </div>
  <div class="card">
    <h3>Pacotes únicos (5 min)</h3>
    <div id="rel-pkt" class="kpi blue">{total_pkt}</div>
    <div id="rel-pkt-sub" class="kpi-sub">{active_senders} nós emissores · {self._duplicates} duplicados vistos</div>
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
    <h3>Referências</h3>
    <table>
      <tr><th>Métrica</th><th>Referência</th></tr>
      <tr><td>Taxa de flood</td><td><span class='tag tag-orange'>&lt;10% Fraco</span> <span class='tag tag-green'>10-60% Normal</span> <span class='tag tag-red'>&gt;60% Congestionado</span></td></tr>
      <tr><td>NAK da rede</td><td><span class='tag tag-green'>&lt;5% Normal</span> <span class='tag tag-orange'>5-20% Atenção</span> <span class='tag tag-red'>&gt;20% Crítico</span></td></tr>
      <tr><td>Entrega local</td><td><span class='tag tag-green'>&ge;90% ACK real</span> <span class='tag tag-orange'>70-90%</span> <span class='tag tag-red'>&lt;70%</span></td></tr>
    </table>
  </div>
</div>

<h3 style="color:#58a6ff;font-size:13px;margin:16px 0 10px 0">📍 Nó Local (mensagens enviadas)</h3>
{no_local_data}
<div class="grid-3">
  <div class="card">
    <h3>Taxa de Entrega Real</h3>
    <div id="rel-delivery" class="kpi {dr_color}">{delivery if delivery is not None else '—'}{'%' if delivery is not None else ''}</div>
    <div class="kpi-sub">ACK do destinatário ÷ (ACK+NAK)<br><i>Não inclui retransmissões locais</i></div>
  </div>
  <div class="card">
    <h3>Taxa NAK Local</h3>
    <div id="rel-nak" class="kpi {'red' if nak_rate and nak_rate>20 else 'orange' if nak_rate else ''}">{nak_rate if nak_rate is not None else '—'}{'%' if nak_rate is not None else ''}</div>
    <div class="kpi-sub">Falhas definitivas com errorReason</div>
  </div>
  <div class="card">
    <h3>Mensagens Enviadas</h3>
    <div id="rel-sent" class="kpi blue">{sent}</div>
    <div id="rel-sub" class="kpi-sub">ACK: {acked} · NAK: {naked} · Relay: {ack_impl} · Pend.: {pending}</div>
  </div>
</div>
<div style="margin-top:12px">
  <div class="card">
    <h3>Distribuição — Nó Local</h3>
    <div style="display:flex;gap:16px;align-items:center;padding:8px 0">
      <canvas id="relChart" width="140" height="140"></canvas>
      <div style="font-size:11px;color:#8b949e;line-height:2">
        <div><span style="color:#39d353">■</span> ACK real ({acked}) — destinatário confirmou</div>
        <div><span style="color:#f85149">■</span> NAK ({naked}) — falha definitiva</div>
        <div><span style="color:#f0883e">■</span> Relay local ({ack_impl}) — retransmissão, sem confirm. de entrega</div>
        <div><span style="color:#8b949e">■</span> Pendente ({pending}) — sem resposta ainda</div>
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
    labels: ['ACK real ✓', 'NAK ✗', 'Relay local', 'Pendente'],
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
  var dupLbl = d.dup_rate === null ? 'Sem dados' :
               d.dup_rate < 10  ? '\u26a0\ufe0f Flood reduzido' :
               d.dup_rate <= 60 ? '\u2705 Flood saudável' : '\ud83d\udea8 Poss\u00edvel congestionamento';
  set('rel-dup',       d.dup_rate !== null ? d.dup_rate + '%' : '\u2014');
  setClass('rel-dup',  d.dup_rate === null ? '' : d.dup_rate < 10 ? 'orange' : d.dup_rate <= 60 ? 'green' : 'red');
  set('rel-dup-label', dupLbl + '\n% de pacotes únicos reencaminhados por \u22652 nós');
  var colLbl = d.p_col === null || d.p_col === undefined ? 'Sem dados de Ch.Util.' :
               d.p_col < 5  ? '\u2705 Risco baixo' :
               d.p_col < 15 ? '\u26a0\ufe0f Risco moderado' : '\ud83d\udea8 Risco elevado';
  set('rel-col', d.p_col !== null && d.p_col !== undefined ? d.p_col + '%' : '\u2014');
  setClass('rel-col', d.p_col === null ? '' : d.p_col < 5 ? 'green' : d.p_col < 15 ? 'orange' : 'red');
  set('rel-col-label', colLbl + '\nModelo Poisson \xd70.5 (CAD mitiga) \xb7 base: Ch.Util ' + (d.ch_util_avg !== null ? d.ch_util_avg + '%' : '\u2014'));
  set('rel-net-nak',   d.net_nak_rate !== null ? d.net_nak_rate + '%' : '\u2014');
  setClass('rel-net-nak', d.net_nak_rate === null ? '' : d.net_nak_rate < 5 ? 'green' : d.net_nak_rate < 20 ? 'orange' : 'red');
  set('rel-net-sub',   'ACK: ' + d.net_acks + ' \xb7 NAK: ' + d.net_naks + '\nInclui NO_ROUTE e MAX_RETRANSMIT');
  set('rel-pkt',       d.total_pkt);
  set('rel-pkt-sub',   d.active_senders + ' nós emissores \xb7 ' + d.duplicates + ' duplicados vistos');

  // Nó local
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
        return self._base_html("✅ Fiabilidade", body)

    # ── 8. Vizinhança ─────────────────────────────────────────────────────
    def _html_neighbors(self) -> str:
        if not self._nb_links:
            body = ('<div class="no-data">⏳ Sem dados de NeighborInfo ainda.<br><br>'
                    'Os nós da rede enviam automaticamente pacotes <b>NEIGHBORINFO_APP</b> '
                    'com a lista de vizinhos directos e respectivo SNR.<br>'
                    'Estes dados aparecem normalmente após 1–2 minutos de operação.</div>')
            return self._base_html("🔗 Vizinhança", body)

        d = self._data_neighbors()
        rows_html = ""
        for from_id, from_n, nb_id, nb_n, snr_str, snr_val in d["rows"]:
            if snr_val is not None:
                color = "green" if snr_val >= 5 else ("orange" if snr_val >= 0 else "red")
            else:
                color = "gray"
            rows_html += (
                f"<tr><td>{from_id}</td><td>{from_n}</td>"
                f"<td style='color:#8b949e'>↔</td>"
                f"<td>{nb_id}</td><td>{nb_n}</td>"
                f"<td><span class='tag tag-{color}'>{snr_str} dB</span></td></tr>"
            )
        if not rows_html:
            rows_html = "<tr><td colspan='6' class='no-data'>Sem pares</td></tr>"

        body = f"""
<div class="subtitle">Nós que se vêem mutuamente via LoRa · {d['n_nodes']} nós reportaram · {d['n_links']} pares únicos · {d['now']}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #8b949e;padding:8px 14px">
  <span style="color:#8b949e;font-size:11px">
    ℹ️ Estes dados provêm de pacotes <b>NEIGHBORINFO_APP</b> enviados pelos nós da rede —
    representam ligações directas observadas por cada nó (não pelo nó local).
    As linhas roxas pontilhadas no mapa mostram os mesmos pares.
  </span>
</div>
<div class="card">
  <h3>Pares de Vizinhos Directos</h3>
  <table>
    <tr><th>ID A</th><th>Nome A</th><th></th><th>ID B</th><th>Nome B</th><th>SNR</th></tr>
    {rows_html}
  </table>
</div>
<script>
window._metricsUpdateData = function(d) {{
  // Tabela de vizinhos não tem update incremental — actualiza no próximo render
}};
</script>"""
        return self._base_html("🔗 Vizinhança", body)

    # ── 9. Alcance & Links ────────────────────────────────────────────────
    def _html_range_links(self) -> str:
        d = self._data_range_links()
        if not d["rows"]:
            body = ('<div class="no-data">⏳ Sem dados de alcance ainda.<br><br>'
                    'Requer que os nós reportem posição GPS (<b>POSITION_APP</b>) '
                    'e que os dados de vizinhança (<b>NEIGHBORINFO_APP</b>) estejam disponíveis.<br>'
                    f'Nós com GPS conhecidos: {d["n_with_gps"]}</div>')
            return self._base_html("📏 Alcance & Links", body)

        def kpi(val, unit, label, color="", kid=""):
            v = f"{val}{unit}" if val is not None else "—"
            id_attr = f' id="{kid}"' if kid else ""
            return f'<div class="card"><h3>{label}</h3><div{id_attr} class="kpi {color}">{v}</div></div>'

        rows_html = ""
        for from_id, from_n, nb_id, nb_n, dist, snr_str, snr_val in d["rows"]:
            dist_color = "green" if dist < 2 else ("orange" if dist < 10 else "blue")
            if snr_val is not None:
                snr_color = "green" if snr_val >= 5 else ("orange" if snr_val >= 0 else "red")
            else:
                snr_color = "gray"
            rows_html += (
                f"<tr><td>{from_id}</td><td>{from_n}</td>"
                f"<td>{nb_id}</td><td>{nb_n}</td>"
                f"<td><span class='tag tag-{dist_color}'>{dist} km</span></td>"
                f"<td><span class='tag tag-{snr_color}'>{snr_str} dB</span></td></tr>"
            )

        body = f"""
<div class="subtitle">Alcance dos links LoRa directos (requer GPS + NeighborInfo) · {d['now']}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #8b949e;padding:8px 14px">
  <span style="color:#8b949e;font-size:11px">
    ℹ️ Métrica da rede — calcula a distância real entre nós vizinhos reportados via
    <b>NEIGHBORINFO_APP</b>, usando as coordenadas GPS de cada nó (fórmula de Haversine).
    Não envolve o nó local a não ser que ele também esteja nos pares.
  </span>
</div>
<div class="grid-3" style="margin-bottom:16px">
  {kpi(f"{d['max_range']:.2f}" if d['max_range'] else None, " km", "Maior Alcance", "blue")}
  <div class="card"><h3>Par de maior alcance</h3>
    <div style="font-size:14px;font-weight:bold;color:#58a6ff">
      {d['max_pair'][0]} ↔ {d['max_pair'][1]}
    </div></div>
  {kpi(d['n_with_gps'], " nós", "Nós com GPS", "")}
</div>
<div class="card">
  <h3>Links por Alcance</h3>
  <table>
    <tr><th>ID A</th><th>Nome A</th><th>ID B</th><th>Nome B</th><th>Distância</th><th>SNR</th></tr>
    {rows_html}
  </table>
</div>
<script>window._metricsUpdateData=function(d){{}};</script>"""
        return self._base_html("📏 Alcance & Links", body)

    # ── 10. Intervalos entre pacotes ─────────────────────────────────────
    def _html_intervals(self) -> str:
        d = self._data_intervals()
        if not d["rows"]:
            body = ('<div class="no-data">⏳ Sem dados de intervalos ainda.<br><br>'
                    'Requer pelo menos 2 pacotes por nó para calcular o intervalo médio.</div>')
            return self._base_html("⏰ Intervalos", body)

        rows_html = ""
        for nid, nid_n, avg, mn, mx, count in d["rows"]:
            # Cores: verde <60s (activo), laranja 60-300s, vermelho >300s
            color = "green" if avg < 60 else ("orange" if avg < 300 else "red")
            freq_label = "Alta frequência" if avg < 30 else ("Normal" if avg < 180 else "Baixa frequência")
            rows_html += (
                f"<tr><td>{nid}</td><td>{nid_n}</td>"
                f"<td><span class='tag tag-{color}'>{avg}s</span></td>"
                f"<td style='color:#8b949e'>{mn}s</td>"
                f"<td style='color:#8b949e'>{mx}s</td>"
                f"<td style='color:#8b949e'>{count}</td>"
                f"<td style='font-size:11px;color:#8b949e'>{freq_label}</td></tr>"
            )

        body = f"""
<div class="subtitle">Intervalo real entre pacotes recebidos de cada nó · {d['now']}</div>
<div class="card" style="margin-bottom:16px;border-left:4px solid #8b949e;padding:8px 14px">
  <span style="color:#8b949e;font-size:11px">
    ℹ️ Métrica da rede — mede o tempo real entre pacotes consecutivos de cada nó observado.
    Um intervalo muito baixo pode indicar um nó mal configurado a congestionar o canal.
    Um intervalo muito alto pode indicar um nó com problemas de cobertura ou bateria fraca.
    Não envolve o nó local a não ser que ele também envie pacotes observáveis.
  </span>
</div>
<div class="card">
  <h3>Intervalo Médio entre Pacotes por Nó</h3>
  <table>
    <tr><th>ID</th><th>Nome</th><th>Média</th><th>Mín.</th><th>Máx.</th><th>Amostras</th><th>Frequência</th></tr>
    {rows_html}
  </table>
  <div style="color:#8b949e;font-size:10px;margin-top:8px;padding-top:8px;border-top:1px solid #21262d">
    ℹ️ Intervalos &lt;30s = alta frequência · 30–180s = normal · &gt;180s = baixa frequência
  </div>
</div>
<script>window._metricsUpdateData=function(d){{}};</script>"""
        return self._base_html("⏰ Intervalos", body)