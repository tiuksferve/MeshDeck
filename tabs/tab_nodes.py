"""
tabs/tab_nodes.py — Aba de lista de nós: MapWidget com suporte a
traceroutes, NeighborInfo e temas de mapa Leaflet.
"""
import json
import logging
import time
from typing import Optional, Callable
import functools
import html
from collections import defaultdict
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QUrl
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QSplitter, QFrame, QMessageBox
)
from PyQt5.QtWebEngineWidgets import QWebEngineView

from models import _FAVORITES
from constants import (
    logger, DARK_BG, PANEL_BG, BORDER_COLOR, ACCENT_GREEN, ACCENT_BLUE,
    ACCENT_ORANGE, ACCENT_RED, TEXT_PRIMARY, TEXT_MUTED, INPUT_BG
)

class MapWidget(QWidget):
    node_deselected = pyqtSignal()

    TILE_URLS = {
        "🌑 Escuro":        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "☀ Claro":         "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "🗺 OpenStreetMap": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "🛰 Satélite":     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_nodes:    list          = []
        self._current_filter:   str           = ""
        self._theme_idx:        int           = 0
        self._map_initialized:  bool          = False
        self._last_marker_data: list          = []
        self._selected_node_id: Optional[str] = None
        self._pan_to_selected:  bool          = False
        self._selection_stable_time: float    = 0.0

        # Último nó que recebeu um pacote real — fica vermelho até outro tomar o lugar
        self._last_active_id:   str   = ""

        self._tr_records:         list = []
        self._tr_show_all:        bool = True
        self._tr_blocking_signals: bool = False
        self._tr_nodes:           list = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Painel esquerdo — lista de traceroutes ───────────────────────
        left = QWidget()
        left.setFixedWidth(220)
        left.setStyleSheet(
            f"background:{PANEL_BG};border-right:1px solid {BORDER_COLOR};"
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        hdr = QLabel("📡  Traceroutes")
        hdr.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:11px;font-weight:bold;"
            f"padding:6px 10px;border-bottom:1px solid {BORDER_COLOR};"
        )
        left_layout.addWidget(hdr)

        # Botão "Mostrar todas" — toggle verdadeiro ON/OFF
        self.btn_tr_all = QPushButton("◉  Mostrar todas")
        self.btn_tr_all.setCheckable(True)
        self.btn_tr_all.setChecked(True)
        self.btn_tr_all.setStyleSheet(
            f"QPushButton{{background:{DARK_BG};color:{ACCENT_GREEN};"
            f"border:none;border-bottom:1px solid {BORDER_COLOR};"
            f"font-size:11px;padding:5px 10px;text-align:left;}}"
            f"QPushButton:checked{{background:#1a3a2a;color:{ACCENT_GREEN};}}"
            f"QPushButton:hover{{background:#1e2d1e;}}"
        )
        self.btn_tr_all.clicked.connect(self._on_tr_all_toggled)
        left_layout.addWidget(self.btn_tr_all)

        # Botão "Limpar"
        btn_clear = QPushButton("🗑  Limpar lista")
        btn_clear.setStyleSheet(
            f"QPushButton{{background:{PANEL_BG};color:#cc3333;"
            f"border:none;border-bottom:1px solid {BORDER_COLOR};"
            f"font-size:10px;padding:4px 10px;text-align:left;font-weight:bold;}}"
            f"QPushButton:hover{{background:#2a1010;color:#ff5555;}}"
        )
        btn_clear.clicked.connect(self._on_tr_clear)
        left_layout.addWidget(btn_clear)

        # Lista scrollável de registos — cada item tem checkbox para multi-selecção
        self._tr_list_widget = QListWidget()
        self._tr_list_widget.setStyleSheet(
            f"QListWidget{{background:{DARK_BG};border:none;outline:none;"
            f"color:{TEXT_PRIMARY};font-size:11px;}}"
            f"QListWidget::item{{padding:5px 8px;"
            f"border-bottom:1px solid {BORDER_COLOR};}}"
            f"QListWidget::item:hover{{background:#1e2828;}}"
        )
        self._tr_list_widget.setWordWrap(True)
        self._tr_list_widget.setSelectionMode(QListWidget.NoSelection)
        self._tr_list_widget.itemChanged.connect(self._on_tr_item_changed)
        left_layout.addWidget(self._tr_list_widget, stretch=1)

        outer.addWidget(left)

        # ── Painel direito — mapa com barra de controlo ──────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        ctrl_bar = QWidget()
        ctrl_bar.setFixedHeight(40)
        ctrl_bar.setStyleSheet(
            f"background:{PANEL_BG};border-bottom:1px solid {BORDER_COLOR};"
        )
        ctrl_layout = QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(12, 4, 12, 4)
        ctrl_layout.setSpacing(6)

        lbl = QLabel("🎨  Tema:")
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        ctrl_layout.addWidget(lbl)

        theme_names = list(self.TILE_URLS.keys())
        self._theme_buttons: List[QPushButton] = []
        for i, name in enumerate(theme_names):
            btn = QPushButton(name)
            btn.setObjectName("btn_map_theme")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(functools.partial(self._on_theme_clicked, i))
            ctrl_layout.addWidget(btn)
            self._theme_buttons.append(btn)

        ctrl_layout.addStretch()

        # Legenda dos marcadores (sempre visível)
        self._legend_markers = QLabel(
            "<span style='color:#00ff88;font-size:13px;'>●</span> Seleccionado &nbsp;"
            "<span style='color:#ff4444;font-size:13px;'>●</span> Último pacote &nbsp;"
            "<span style='color:#2b7cd3;font-size:13px;'>●</span> RF &nbsp;"
            "<span style='color:#ff8800;font-size:13px;'>●</span> MQTT &nbsp;"
            "<span style='color:#555566;font-size:13px;'>●</span> Inativos"
        )
        self._legend_markers.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        ctrl_layout.addWidget(self._legend_markers)

        right_layout.addWidget(ctrl_bar)

        self.web = QWebEngineView()
        from PyQt5.QtWebEngineWidgets import QWebEnginePage
        class _SilentPage(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):
                if 'webkit' in message.lower() or 'deprecated' in message.lower():
                    return
                logger.debug(f"[MapJS] {message}")
        self.web.setPage(_SilentPage(self.web))
        right_layout.addWidget(self.web, stretch=1)

        outer.addWidget(right, stretch=1)

        self._show_placeholder()

        self._popup_check_timer = QTimer(self)
        self._popup_check_timer.setInterval(600)
        self._popup_check_timer.timeout.connect(self._check_popup_closed)

        # Poll para cliques no botão Traceroute dentro dos popups do mapa
        self._traceroute_cb = None
        self._tr_poll_timer = QTimer(self)
        self._tr_poll_timer.setInterval(1000)  # 1s — suficiente para detectar clique
        self._tr_poll_timer.timeout.connect(self._check_traceroute_request)
        self._tr_poll_timer.start()

    def _show_placeholder(self):
        self.web.setHtml(
            f"<html><body style='background:{DARK_BG};color:{TEXT_PRIMARY};"
            "font-family:monospace;display:flex;align-items:center;"
            "justify-content:center;height:100vh;margin:0;font-size:18px;'>"
            "📡 Aguardando dados de posição...</body></html>"
        )
        self._map_initialized = False

    def _map_html(self, center_lat: float, center_lon: float,
                  zoom: int, tile_url: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body,#map{{height:100%;margin:0;padding:0;background:{DARK_BG};}}
  .custom-tooltip{{
    background:{PANEL_BG} !important;
    border:1px solid {BORDER_COLOR} !important;
    color:{TEXT_PRIMARY} !important;
    font-family:monospace;font-size:12px;
    padding:6px 10px;border-radius:6px;
    box-shadow:0 2px 8px rgba(0,0,0,.6);
    white-space:nowrap;
  }}
  .custom-tooltip-tr{{
    background:{PANEL_BG} !important;
    border:1px solid {BORDER_COLOR} !important;
    color:{TEXT_PRIMARY} !important;
    font-family:monospace;font-size:12px;
    padding:6px 10px;border-radius:6px;
    box-shadow:0 2px 8px rgba(0,0,0,.6);
    white-space:pre;
  }}
  .custom-popup .leaflet-popup-content-wrapper{{
    background:{PANEL_BG};border:1px solid {BORDER_COLOR};
    color:{TEXT_PRIMARY};border-radius:8px;font-family:monospace;font-size:12px;
  }}
  .custom-popup .leaflet-popup-tip{{background:{PANEL_BG};}}
</style>
</head>
<body>
<div id="map"></div>
<script>
(function(){{
  var map = L.map('map', {{
    center: [{center_lat}, {center_lon}],
    zoom: {zoom},
    zoomControl: true
  }});
  var tileUrl = {json.dumps(tile_url)};
  L.tileLayer(tileUrl, {{maxZoom:19, attribution:''}}).addTo(map);
  window._map         = map;
  window._markerLayer = L.layerGroup().addTo(map);
  window._trLayer     = null;
  window._selPopupClosed = false;
  window._mapReady    = true;
  // Redesenha rotas ao mudar zoom (offset em px precisa de recalculo)
  map.on('zoomend', function() {{
    if(window._trLayer && window._trRedraw) {{ window._trRedraw(); }}
  }});
  console.log('MapWidget: Leaflet ready');
}})();
</script>
</body>
</html>"""

    def _init_map(self, center_lat: float, center_lon: float, zoom: int):
        tile_url = list(self.TILE_URLS.values())[self._theme_idx]
        html_str = self._map_html(center_lat, center_lon, zoom, tile_url)
        self._map_initialized = False
        self.web.loadFinished.connect(self._on_load_finished)
        self.web.setHtml(html_str, QUrl("about:blank"))

    def _on_load_finished(self, ok: bool):
        try:
            self.web.loadFinished.disconnect(self._on_load_finished)
        except Exception:
            pass
        if not ok:
            logger.warning("MapWidget: loadFinished ok=False")
            return
        QTimer.singleShot(50, self._after_load)

    def _after_load(self):
        self._map_initialized = True
        nodes_loc = [n for n in self._current_nodes
                     if n.get('latitude') is not None and n.get('longitude') is not None]
        if nodes_loc:
            most_recent = max(
                (n for n in nodes_loc if isinstance(n.get('last_heard'), datetime)),
                key=lambda n: n['last_heard'], default=None
            )
            self._inject_markers_js(nodes_loc, most_recent)
        if self._tr_records:
            self._draw_traceroute_js()

    def set_selected_node(self, node_id: Optional[str]):
        self._selected_node_id      = node_id
        self._pan_to_selected       = node_id is not None
        self._selection_stable_time = time.time()
        if node_id:
            self._popup_check_timer.start()

    def clear_auto_pan(self):
        self._pan_to_selected = False

    def mark_node_active(self, node_id: str):
        """Marca nó como o mais recentemente activo (vermelho no mapa).
        Apenas um nó fica vermelho de cada vez. Persiste até outro pacote chegar."""
        if not node_id:
            return
        self._last_active_id = node_id.lower()

    def clear_active_node(self):
        """Limpa o marcador vermelho (ex: ao desligar)."""
        self._last_active_id = ""

    def update_map(self, nodes: list, filter_text: str = ""):
        self._current_nodes  = nodes
        self._current_filter = filter_text

        nodes_loc = [n for n in nodes
                     if n.get('latitude') is not None and n.get('longitude') is not None]

        if filter_text:
            fl = filter_text.lower()
            nodes_loc = [n for n in nodes_loc if any(
                fl in str(n.get(k, "")).lower()
                for k in ('id_string', 'long_name', 'short_name')
            )]

        if not nodes_loc:
            self._show_placeholder()
            return

        most_recent = max(
            (n for n in nodes_loc if isinstance(n.get('last_heard'), datetime)),
            key=lambda n: n['last_heard'], default=None
        )
        new_marker_data = self._build_marker_data(nodes_loc, most_recent)

        if not self._map_initialized:
            if self._pan_to_selected and self._selected_node_id:
                sel = next((n for n in nodes_loc
                            if n.get('id_string') == self._selected_node_id), None)
            else:
                sel = None

            if sel:
                clat, clon, zoom = sel['latitude'], sel['longitude'], 13
            else:
                clat = sum(n['latitude']  for n in nodes_loc) / len(nodes_loc)
                clon = sum(n['longitude'] for n in nodes_loc) / len(nodes_loc)
                zoom = 8

            self._last_marker_data = new_marker_data
            self._init_map(clat, clon, zoom)
            return

        self._last_marker_data = new_marker_data

        if self._pan_to_selected and self._selected_node_id:
            sel = next((n for n in nodes_loc
                        if n.get('id_string') == self._selected_node_id), None)
            if sel:
                js_pan = (f"window._map.setView([{sel['latitude']},"
                          f"{sel['longitude']}],13);")
                self.web.page().runJavaScript(js_pan)

        self._inject_markers_js(nodes_loc, most_recent)

    def _build_marker_data(self, nodes_loc: list, most_recent) -> list:
        markers = []
        for node in nodes_loc:
            is_selected = (node.get('id_string') == self._selected_node_id
                           and self._selected_node_id is not None)
            via_mqtt    = node.get('via_mqtt')
            via         = "☁ MQTT" if via_mqtt is True else "RF"
            snr         = node.get('snr')
            batt        = node.get('battery_level')
            snr_str     = f"{snr:.1f} dB" if snr is not None else "—"
            batt_str    = f"{batt}%"       if batt is not None else "—"
            name        = node.get('long_name') or node.get('id_string', '')
            short       = node.get('short_name') or node.get('id_string', '')
            has_key     = bool(node.get('public_key', ''))
            enc_icon    = "🔒" if has_key else "🔓"
            node_id     = node.get('id_string', '')
            is_fav      = _FAVORITES.is_favorite(node_id)
            fav_star    = "⭐ " if is_fav else ""

            # Nó inactivo se last_heard > 2 horas (ou sem last_heard)
            last_heard     = node.get('last_heard')
            is_inactive    = True
            if isinstance(last_heard, datetime):
                is_inactive = (datetime.now() - last_heard) > timedelta(hours=2)

            # Nó activo recentemente: o último a enviar um pacote
            is_active_now = node_id.lower() == self._last_active_id

            # Formato legível para o popup
            if isinstance(last_heard, datetime):
                lh_str = last_heard.strftime("%H:%M:%S  %d/%m/%Y")
            else:
                lh_str = "—"

            # Prioridade de cor:
            # 1. Seleccionado (verde)
            # 2. Pacote recebido agora (vermelho) — prevalece sobre cinzento
            # 3. Inactivo >2h (cinzento)
            # 4. MQTT (laranja)  5. RF (azul)
            if is_selected:
                color, border_color, radius = "#00ff88", "#00cc66", 9
            elif is_active_now:
                color, border_color, radius = "#ff4444", "#cc0000", 7
            elif is_inactive:
                color, border_color, radius = "#555566", "#444455", 5
            elif via_mqtt is True:
                color, border_color, radius = "#ff8800", "#cc6600", 6
            else:
                color, border_color, radius = "#2b7cd3", "#1050aa", 6

            # Popup com botão de traceroute embutido
            popup_html = (
                f"<div style='font-family:monospace;font-size:12px;min-width:200px'>"
                f"<b>{'★ ' if is_selected else ''}{fav_star}{html.escape(name)}</b>"
                f"<hr style='margin:4px 0;border-color:#30363d'>"
                f"<table style='border-spacing:2px 2px;width:100%'>"
                f"<tr><td>🆔</td><td>{html.escape(str(node_id))}</td></tr>"
                f"<tr><td>📡</td><td>Via: <b>{via}</b></td></tr>"
                f"<tr><td>📶</td><td>SNR: {snr_str}</td></tr>"
                f"<tr><td>🔋</td><td>{batt_str}</td></tr>"
                f"<tr><td>{enc_icon}</td><td>DM: {'PKI' if has_key else 'PSK'}</td></tr>"
                f"<tr><td>🕐</td><td>{html.escape(lh_str)}</td></tr>"
                f"</table>"
                + (f"<div style='color:#00ff88;font-size:11px;margin-top:4px'>● Seleccionado</div>"
                   if is_selected else "")
                + f"<div style='margin-top:8px;text-align:center'>"
                  f"<a href='traceroute:{node_id}' style='color:#58a6ff;text-decoration:none;"
                  f"border:1px solid #58a6ff;border-radius:4px;padding:2px 8px;font-size:11px'>"
                  f"📡 Traceroute</a></div>"
                f"</div>"
            )

            tooltip = (f"{'⭐ ' if is_fav else ''}{short}  ·  {via}  ·  SNR:{snr_str}  ·  🔋{batt_str}")

            markers.append({
                "lat": node['latitude'], "lon": node['longitude'],
                "color": color, "border_color": border_color,
                "radius": radius, "selected": is_selected,
                "tooltip": ("★ " if is_selected else "") + tooltip,
                "popup": popup_html,
                "node_id": node_id,
            })
        return markers

    def set_traceroute_callback(self, fn):
        """Regista callback para quando o utilizador clica em 'Traceroute' no popup do mapa."""
        self._traceroute_cb = fn

    def _inject_markers_js(self, nodes_loc: list, most_recent):
        markers_data = self._build_marker_data(nodes_loc, most_recent)
        markers_json = json.dumps(markers_data, ensure_ascii=False)
        js = (
            "(function(){"
            "if(!window._mapReady){console.warn('map not ready');return;}"
            "window._selPopupClosed=false;"
            "window._markerLayer.clearLayers();"
            "var pins=" + markers_json + ";"
            "pins.forEach(function(p){"
            "var c=L.circleMarker([p.lat,p.lon],{"
            "radius:p.radius,fillColor:p.color,color:p.border_color,"
            "weight:p.selected?4:2,opacity:1,fillOpacity:p.selected?1.0:0.85});"
            # Tooltip numa linha — sem white-space:pre-line no CSS para tooltips de markers
            "c.bindTooltip(p.tooltip,{permanent:p.selected,direction:'top',"
            "className:'custom-tooltip',sticky:false});"
            "c.bindPopup(p.popup,{maxWidth:300,className:'custom-popup'});"
            "if(p.selected){"
            "c.on('popupclose',function(){window._selPopupClosed=true;});"
            "}"
            "c.on('popupopen',function(){"
            "setTimeout(function(){"
            "var links=document.querySelectorAll('a[href^=\"traceroute:\"]');"
            "links.forEach(function(a){"
            "if(!a._trBound){"
            "a._trBound=true;"
            "a.addEventListener('click',function(e){"
            "e.preventDefault();"
            "if(!window._trPendingLock){"
            "window._trPendingLock=true;"
            "window.qt_traceroute_request=a.getAttribute('href').replace('traceroute:','');"
            "setTimeout(function(){window._trPendingLock=false;},2000);"
            "}"
            "});"
            "}"
            "});"
            "},100);"
            "});"
            "window._markerLayer.addLayer(c);"
            "if(p.selected){c.openPopup();}"
            "});"
            "})();"
        )
        self.web.page().runJavaScript(js)

    def _check_popup_closed(self):
        if not self._selected_node_id or not self._map_initialized:
            self._popup_check_timer.stop()
            return
        if self._selection_stable_time == 0.0 or \
                (time.time() - self._selection_stable_time) < 1.0:
            return
        self.web.page().runJavaScript(
            "window._selPopupClosed===true?'yes':'no';",
            self._on_popup_check_result
        )

    def _on_popup_check_result(self, result):
        if result == 'yes':
            self.web.page().runJavaScript("window._selPopupClosed=false;")
            self.deselect_node()

    def deselect_node(self):
        self._selected_node_id = None
        self._pan_to_selected  = False
        self._last_marker_data = []
        self._popup_check_timer.stop()
        self.node_deselected.emit()
        if self._map_initialized and self._current_nodes:
            nodes_loc = [n for n in self._current_nodes
                         if n.get('latitude') is not None and n.get('longitude') is not None]
            if nodes_loc:
                most_recent = max(
                    (n for n in nodes_loc if isinstance(n.get('last_heard'), datetime)),
                    key=lambda n: n['last_heard'], default=None
                )
                self._inject_markers_js(nodes_loc, most_recent)

    def _on_tr_all_toggled(self, checked: bool):
        """Botão 'Mostrar todas': ON → marca todos os itens; OFF → desmarca todos."""
        self._tr_show_all = checked
        self.btn_tr_all.setText("◉  Mostrar todas" if checked else "○  Mostrar todas")

        # Actualiza checkboxes de todos os itens sem disparar _on_tr_item_changed
        self._tr_blocking_signals = True
        for i in range(self._tr_list_widget.count()):
            item = self._tr_list_widget.item(i)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._tr_blocking_signals = False

        if checked:
            self._draw_traceroute_js()
        else:
            self._clear_traceroute_js()

    def _on_tr_item_changed(self, item: QListWidgetItem):
        """Checkbox de um item mudou — redesenha o mapa com os itens marcados."""
        if self._tr_blocking_signals:
            return

        # Actualiza _tr_show_all conforme o estado actual de todos os itens
        all_checked  = all(
            self._tr_list_widget.item(i).checkState() == Qt.Checked
            for i in range(self._tr_list_widget.count())
        )
        none_checked = all(
            self._tr_list_widget.item(i).checkState() == Qt.Unchecked
            for i in range(self._tr_list_widget.count())
        )
        self._tr_show_all = all_checked
        # Actualiza botão sem disparar o seu slot
        self.btn_tr_all.blockSignals(True)
        self.btn_tr_all.setChecked(all_checked)
        self.btn_tr_all.setText("◉  Mostrar todas" if all_checked else "○  Mostrar todas")
        self.btn_tr_all.blockSignals(False)

        if none_checked:
            self._clear_traceroute_js()
        else:
            self._draw_traceroute_js()

    def _on_tr_clear(self):
        """Limpa todos os registos de traceroute — pede confirmação primeiro."""
        if not self._tr_records:
            return
        reply = QMessageBox.question(
            self, "Limpar lista de traceroutes",
            f"Tem a certeza que deseja remover todos os {len(self._tr_records)} "
            f"traceroute(s) da lista?\n\nAs linhas de rota no mapa também serão removidas.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return
        self._tr_records          = []
        self._tr_show_all         = True
        self._tr_blocking_signals = True
        self._tr_list_widget.clear()
        self._tr_blocking_signals = False
        self.btn_tr_all.setChecked(True)
        self.btn_tr_all.setText("◉  Mostrar todas")
        self._clear_traceroute_js()

    def show_traceroute_on_map(self, forward_edges: list, back_edges: list,
                               all_nodes: list, origin_id: str = "",
                               dest_id: str = "", origin_name: str = "",
                               dest_name: str = ""):
        """Adiciona um novo registo de traceroute à lista e redesenha."""
        ts = datetime.now().strftime("%H:%M:%S")

        # Verifica se o destino tem coords (se não tiver, não vale a pena no mapa)
        node_idx = {n.get('id_string', ''): n for n in all_nodes}
        def _has_coords(nid):
            n = node_idx.get(nid) or node_idx.get(nid.lower() if nid else '')
            return bool(n and n.get('latitude') is not None)

        dest_has_loc = _has_coords(dest_id)

        rec = {
            'id':            len(self._tr_records),
            'ts':            ts,
            'origin_id':     origin_id,
            'origin_name':   origin_name or origin_id,
            'dest_id':       dest_id,
            'dest_name':     dest_name or dest_id,
            'forward_edges': list(forward_edges),
            'back_edges':    list(back_edges),
            'all_nodes':     list(all_nodes),
            'dest_has_loc':  dest_has_loc,
        }
        self._tr_records.append(rec)
        self._tr_nodes = list(all_nodes)

        # Adiciona item à lista com checkbox marcado por omissão
        # Usa short_name do nó se disponível, senão primeiras 8 chars do id
        def _short(nid, name):
            n = node_idx.get(nid) or node_idx.get(nid.lower() if nid else '')
            sn = (n.get('short_name') or '').strip() if n else ''
            if sn:
                return sn
            return name.split(' ')[0][:8] if name else nid[:8]

        origin_short = _short(origin_id, origin_name)
        dest_short   = _short(dest_id, dest_name)
        loc_tag      = "📍" if dest_has_loc else "❓"
        label        = f"{ts}\n→ {origin_short}\n  {loc_tag} {dest_short}"
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, rec['id'])
        item.setToolTip(f"{origin_name} → {dest_name}\n{ts}")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)   # marcado por omissão
        self._tr_blocking_signals = True
        self._tr_list_widget.addItem(item)
        self._tr_blocking_signals = False
        self._tr_list_widget.scrollToBottom()

        if self._map_initialized:
            self._draw_traceroute_js()

    def _build_node_cache(self) -> dict:
        """Constrói índice id_string→node em O(N) — usado por todas as operações de traceroute.
        Cobre nós actuais do mapa + nós de todos os registos de traceroute.
        """
        cache: dict = {}
        def _add(n):
            ids = (n.get('id_string') or '').strip().lower()
            if ids:
                cache.setdefault(ids, n)

        for n in self._current_nodes:
            _add(n)
        for rec in self._tr_records:
            for n in rec.get('all_nodes', []):
                _add(n)
        return cache

    def _node_idx(self) -> dict:
        """Alias para compatibilidade — usa _build_node_cache."""
        return self._build_node_cache()

    def _get_active_records(self) -> list:
        """Retorna os registos cujo item na lista está marcado (checked)."""
        if not self._tr_records:
            return []
        checked_ids = set()
        for i in range(self._tr_list_widget.count()):
            item = self._tr_list_widget.item(i)
            if item and item.checkState() == Qt.Checked:
                rid = item.data(Qt.UserRole)
                if rid is not None:
                    checked_ids.add(rid)
        return [rec for rec in self._tr_records if rec['id'] in checked_ids]

    def _get_active_edges(self) -> list:
        """Retorna segmentos entre nós com GPS dos registos activos.
        Constrói o cache de nós uma única vez para toda a operação.
        """
        active = self._get_active_records()
        if not active:
            return []

        # Cache único — O(1) por lookup; sem scan linear por nó
        cache = self._build_node_cache()

        def has_gps(nid):
            n = cache.get(nid.lower()) if nid else None
            return bool(n and n.get('latitude') is not None)

        result = []
        seen   = set()

        for rec in active:
            for direction, edge_list in (('ida',   rec['forward_edges']),
                                         ('volta', rec['back_edges'])):
                if not edge_list:
                    continue

                # Cadeia ordenada de nós
                chain = []
                for a, b, snr in edge_list:
                    if not chain:
                        chain.append((a, None))
                    chain.append((b, snr))

                gps_idx = [i for i, (nid, _) in enumerate(chain) if has_gps(nid)]
                if len(gps_idx) < 2:
                    continue

                for k in range(len(gps_idx) - 1):
                    i_from, i_to = gps_idx[k], gps_idx[k + 1]
                    nid_a   = chain[i_from][0]
                    nid_b   = chain[i_to][0]
                    snr     = chain[i_to][1] or 0.0
                    skipped = [chain[j][0] for j in range(i_from + 1, i_to)]
                    key = (nid_a, nid_b, direction)
                    if key not in seen:
                        result.append((nid_a, nid_b, snr, direction, skipped))
                        seen.add(key)

        return result

    def _find_node(self, nid: str):
        """Lookup pontual — para uso esporádico. Usar _build_node_cache em loops."""
        if not nid:
            return None
        nid_l = nid.lower()
        for n in self._current_nodes:
            if (n.get('id_string') or '').strip().lower() == nid_l:
                return n
        for rec in self._tr_records:
            for n in rec.get('all_nodes', []):
                if (n.get('id_string') or '').strip().lower() == nid_l:
                    return n
        return None

    def _draw_traceroute_js(self):
        """Desenha os segmentos entre nós com GPS. Cache construído uma única vez."""
        if not self._map_initialized:
            return

        edges = self._get_active_edges()
        if not edges:
            self._clear_traceroute_js()
            return

        # Reutiliza o mesmo cache — não reconstrói
        cache = self._build_node_cache()

        def find(nid):
            return cache.get(nid.lower()) if nid else None

        def pos(nid):
            n = find(nid)
            if not n:
                return None, None
            lat, lon = n.get('latitude'), n.get('longitude')
            return (float(lat), float(lon)) if lat is not None and lon is not None else (None, None)

        def node_info(nid):
            n = find(nid)
            if not n:
                return f"❓ {nid}"
            sn  = (n.get('short_name') or n.get('long_name') or nid).strip()
            via = "MQTT" if n.get('via_mqtt') else "RF"
            gps = "📍" if n.get('latitude') is not None else "❓"
            return f"{gps} {sn}  {via}"


        # Separa cada segmento por direcção — ida e volta ficam em linhas distintas.
        # Constrói lista de segmentos normalizados.
        # Chave canónica: par de coords ordenado — independente da direcção.
        raw_segments = []
        canonical_count = {}   # (lat1,lon1,lat2,lon2) → quantas direcções usam este segmento

        for a, b, snr, direction, skipped in edges:
            la, loa = pos(a)
            lb, lob = pos(b)
            if la is None or lb is None:
                continue
            snr_str   = f"{snr:+.1f} dB" if snr != 0.0 else "SNR desconhecido"
            dir_arrow = "→" if direction == 'ida' else "←"
            skip_str  = ""
            if skipped:
                skip_str = f"\n⚠ Via (sem GPS): {', '.join(node_info(s) for s in skipped)}"
            dir_label = "Ida" if direction == 'ida' else "Volta"
            tip = (f"{dir_arrow} {dir_label}: {node_info(a)}  {dir_arrow}  {node_info(b)}"
                   f"  |  SNR: {snr_str}{skip_str}")
            col = '#00cc44' if direction == 'ida' else '#007a29'
            # off base: ida=+1, volta=-1
            off_base = 1 if direction == 'ida' else -1

            # Chave canónica: sempre o ponto de menor coordenada primeiro
            if (la, loa) <= (lb, lob):
                ck = (round(la,6), round(loa,6), round(lb,6), round(lob,6))
                flipped = False
            else:
                ck = (round(lb,6), round(lob,6), round(la,6), round(loa,6))
                flipped = True

            canonical_count[ck] = canonical_count.get(ck, 0) + 1
            raw_segments.append({
                'la': la, 'loa': loa, 'lb': lb, 'lob': lob,
                'tip': tip, 'col': col, 'off_base': off_base,
                'ck': ck, 'flipped': flipped,
            })

        if not raw_segments:
            self._clear_traceroute_js()
            return

        # Constrói segment_list final:
        # - segmentos únicos (só ida ou só volta): off=0 (linha centrada)
        # - segmentos partilhados (ida E volta): offset lateral de ±4px
        segment_list = []
        for seg in raw_segments:
            ck      = seg['ck']
            shared  = canonical_count[ck] >= 2   # mesmo caminho em ambas as direcções

            if not shared:
                off = 0   # linha centrada — sem offset
                la, loa, lb, lob = seg['la'], seg['loa'], seg['lb'], seg['lob']
            else:
                # Normaliza para direcção canónica SEM inverter off_base —
                # o off_base (±1) mantém-se: ida sempre +1, volta sempre -1,
                # independentemente de qual endpoint é maior/menor
                if seg['flipped']:
                    la, loa = seg['lb'], seg['lob']
                    lb, lob = seg['la'], seg['loa']
                else:
                    la, loa = seg['la'], seg['loa']
                    lb, lob = seg['lb'], seg['lob']
                off = seg['off_base']   # +1 ou -1, não invertido

            segment_list.append({
                'lat1': la, 'lon1': loa, 'lat2': lb, 'lon2': lob,
                'tip': seg['tip'], 'col': seg['col'], 'off': off,
            })

        if not segment_list:
            self._clear_traceroute_js()
            return

        js = (
            "(function(){"
            "if(!window._mapReady){return;}"
            "var segs=" + json.dumps(segment_list, ensure_ascii=False) + ";"
            "window._trSegs=segs;"
            "function drawSegs(){"
            "if(window._trLayer){window._map.removeLayer(window._trLayer);}"
            "window._trLayer=L.layerGroup().addTo(window._map);"
            "segs.forEach(function(e){"
            # Normaliza sempre de lat1→lat2 para o cálculo do perpendicular
            # O off (+1 ida, -1 volta) é aplicado ao perpendicular normalizado
            # Assim ida e volta ficam sempre em lados opostos independentemente
            # de qual endpoint é origem/destino
            "var p1=window._map.latLngToLayerPoint([e.lat1,e.lon1]);"
            "var p2=window._map.latLngToLayerPoint([e.lat2,e.lon2]);"
            "var dx=p2.x-p1.x,dy=p2.y-p1.y;"
            "var len=Math.sqrt(dx*dx+dy*dy)||1e-9;"
            # Perpendicular: roda 90° para a esquerda — sempre o mesmo sentido
            "var nx=-dy/len,ny=dx/len;"
            "var off=3*e.off;"
            "var q1=window._map.layerPointToLatLng([p1.x+nx*off,p1.y+ny*off]);"
            "var q2=window._map.layerPointToLatLng([p2.x+nx*off,p2.y+ny*off]);"
            "L.polyline([[q1.lat,q1.lng],[q2.lat,q2.lng]],"
            "{color:e.col,weight:2,opacity:0.90,interactive:true})"
            ".bindTooltip(e.tip,{sticky:true,className:'custom-tooltip-tr'})"
            ".addTo(window._trLayer);"
            "});"
            "}"
            "window._trRedraw=drawSegs;"
            "drawSegs();"
            "})();"
        )
        self.web.page().runJavaScript(js)

    def _clear_traceroute_js(self):
        if not self._map_initialized:
            return
        self.web.page().runJavaScript(
            "if(window._trLayer){window._map.removeLayer(window._trLayer);"
            "window._trLayer=null;}"
        )

    def clear_traceroute_layer(self):
        self._tr_records          = []
        self._tr_show_all         = True
        self._tr_blocking_signals = True
        self._tr_list_widget.clear()
        self._tr_blocking_signals = False
        self.btn_tr_all.setChecked(True)
        self.btn_tr_all.setText("◉  Mostrar todas")
        self._clear_traceroute_js()

    def _on_theme_clicked(self, idx: int):
        self._theme_idx = idx
        for i, btn in enumerate(self._theme_buttons):
            btn.setChecked(i == idx)
        self._map_initialized  = False
        self._last_marker_data = []
        if self._current_nodes:
            self.update_map(self._current_nodes)  # sem filtro — mapa mostra sempre tudo

    def _check_traceroute_request(self):
        """Verifica se o utilizador clicou em 'Traceroute' num popup do mapa."""
        if not self._map_initialized or not self._traceroute_cb:
            return
        if not self.isVisible():
            return
        self.web.page().runJavaScript(
            "(function(){var id=window.qt_traceroute_request||null;"
            "window.qt_traceroute_request=null;return id;})();",
            self._on_traceroute_request_result
        )

    def _on_traceroute_request_result(self, node_id):
        if node_id and self._traceroute_cb:
            self._traceroute_cb(node_id)

    def closeEvent(self, event):
        self._tr_poll_timer.stop()
        super().closeEvent(event)
