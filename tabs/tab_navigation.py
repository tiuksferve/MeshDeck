"""
tabs/tab_navigation.py — NavigationTab: aba de navegação com bússola e tabela
de nós com localização GPS conhecida.

Layout do painel superior:
  [Nó Local]  |  [Bússola — centro, maior]  |  [Alvo]

Tabela inferior: todos os nós com GPS, ordenados por distância crescente,
filtrados pela barra de pesquisa global.
"""
import math
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QByteArray
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QAbstractItemView, QFrame
)
from PyQt5.QtGui import QColor
from PyQt5.QtSvg import QSvgWidget

from i18n import tr
from constants import (
    DARK_BG, PANEL_BG, BORDER_COLOR, ACCENT_GREEN, ACCENT_BLUE,
    ACCENT_ORANGE, ACCENT_RED, TEXT_PRIMARY, TEXT_MUTED
)


# ── Geo helpers ───────────────────────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing_deg(lat1, lon1, lat2, lon2):
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2r)
    y = (math.cos(lat1r) * math.sin(lat2r) -
         math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _cardinal(b):
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((b + 22.5) / 45) % 8]


# ── Compass SVG ───────────────────────────────────────────────────────────────

def _compass_svg(bearing_deg: Optional[float], size: int = 280) -> bytes:
    """
    Draws a compass rose with a diamond needle.
    bearing_deg: direction to target. None = no selection (no needle).
    Red half → target. Grey half → opposite.
    """
    cx = cy = size // 2
    r  = size // 2 - 10

    # Tick marks every 30°
    ticks = ""
    for deg in range(0, 360, 30):
        rad     = math.radians(deg - 90)
        is_card = (deg % 90 == 0)
        r_in    = r - (12 if is_card else 7)
        x1 = cx + r_in * math.cos(rad)
        y1 = cy + r_in * math.sin(rad)
        x2 = cx + r   * math.cos(rad)
        y2 = cy + r   * math.sin(rad)
        ticks += (
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{"#8b949e" if is_card else "#30363d"}" '
            f'stroke-width="{"2.5" if is_card else "1"}"/>'
        )

    # Cardinal letters
    cards = ""
    lr = r - 24
    for deg, lbl, col, fw in [
        (0,   "N", "#39d353", "bold"),
        (90,  "E", "#8b949e", "normal"),
        (180, "S", "#8b949e", "normal"),
        (270, "W", "#8b949e", "normal"),
    ]:
        rad = math.radians(deg - 90)
        lx  = cx + lr * math.cos(rad)
        ly  = cy + lr * math.sin(rad)
        cards += (
            f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="middle" '
            f'dominant-baseline="middle" fill="{col}" '
            f'font-size="15" font-weight="{fw}" '
            f'font-family="Arial,sans-serif">{lbl}</text>'
        )

    # Degree marks (every 10°, small dots)
    dots = ""
    for deg in range(0, 360, 10):
        if deg % 30 == 0:
            continue
        rad = math.radians(deg - 90)
        dx  = cx + (r - 4) * math.cos(rad)
        dy  = cy + (r - 4) * math.sin(rad)
        dots += f'<circle cx="{dx:.2f}" cy="{dy:.2f}" r="1.2" fill="#30363d"/>'

    # Needle
    if bearing_deg is not None:
        a_rad = math.radians(bearing_deg - 90)
        p_rad = a_rad + math.pi / 2

        tip_d  = r - 30
        base_d = 24
        wing_d = 7

        tip_x  = cx + tip_d  * math.cos(a_rad)
        tip_y  = cy + tip_d  * math.sin(a_rad)
        base_x = cx + base_d * math.cos(a_rad + math.pi)
        base_y = cy + base_d * math.sin(a_rad + math.pi)
        lw_x   = cx + wing_d * math.cos(p_rad)
        lw_y   = cy + wing_d * math.sin(p_rad)
        rw_x   = cx - wing_d * math.cos(p_rad)
        rw_y   = cy - wing_d * math.sin(p_rad)

        needle = (
            f'<polygon points="{tip_x:.2f},{tip_y:.2f} '
            f'{lw_x:.2f},{lw_y:.2f} {rw_x:.2f},{rw_y:.2f}" '
            f'fill="#f85149" stroke="#0d1117" stroke-width="1.2"/>'
            f'<polygon points="{base_x:.2f},{base_y:.2f} '
            f'{lw_x:.2f},{lw_y:.2f} {rw_x:.2f},{rw_y:.2f}" '
            f'fill="#6e7681" stroke="#0d1117" stroke-width="1.2"/>'
            f'<circle cx="{cx}" cy="{cy}" r="5.5" '
            f'fill="#21262d" stroke="#8b949e" stroke-width="2"/>'
        )
    else:
        needle = (
            f'<circle cx="{cx}" cy="{cy}" r="5.5" '
            f'fill="#30363d" stroke="#8b949e" stroke-width="2"/>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        # Outer glow ring
        f'<circle cx="{cx}" cy="{cy}" r="{r+2}" '
        f'fill="none" stroke="#30363d" stroke-width="1" opacity="0.4"/>'
        # Main ring
        f'<circle cx="{cx}" cy="{cy}" r="{r}" '
        f'fill="#161b22" stroke="#30363d" stroke-width="2"/>'
        # Inner face with subtle gradient feel
        f'<circle cx="{cx}" cy="{cy}" r="{r-13}" fill="#0d1117"/>'
        f'{dots}{ticks}{cards}{needle}'
        f'</svg>'
    ).encode('utf-8')


# ── Column indices ─────────────────────────────────────────────────────────────
COL_LONG    = 0
COL_SHORT   = 1
COL_HOPS    = 2
COL_VIA     = 3
COL_SNR     = 4
COL_DIST    = 5
COL_BEARING = 6
COL_LAT     = 7
COL_LON     = 8
COL_ALT     = 9
COL_BATT    = 10
N_COLS      = 11

# Balanced column widths — all headers readable, no column dominates.
# setStretchLastSection=False + Interactive so user can resize.
# Values tuned for a ~900px total table width (uConsole landscape).
_COL_WIDTHS = {
    COL_LONG:     130,   # Nome Longo   — slightly wider
    COL_SHORT:     62,   # Nome Curto
    COL_HOPS:      52,   # Hops
    COL_VIA:       66,   # Via
    COL_SNR:       72,   # SNR
    COL_DIST:      78,   # Distância
    COL_BEARING:   70,   # Bearing
    COL_LAT:       82,   # Lat
    COL_LON:       82,   # Lon
    COL_ALT:       54,   # Alt (m)
    COL_BATT:      60,   # Bateria
}


class NavigationTab(QWidget):
    """Navigation tab — 3-panel compass area + GPS node table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes:             Dict[str, Dict[str, Any]] = {}
        self._selected_id:       Optional[str]   = None
        self._local_lat:         Optional[float]  = None
        self._local_lon:         Optional[float]  = None
        self._local_alt:         Optional[float]  = None
        self._local_long_name:   str  = ""
        self._local_short_name:  str  = ""
        self._local_node_id:     str  = ""
        self._local_gps_enabled: bool = False
        self._filter_text:       str  = ""
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(
            f"QSplitter::handle {{background:{BORDER_COLOR};}}"
        )

        # ── TOP: [Local Node] | [Compass] | [Target] ─────────────────────
        top = QWidget()
        top.setStyleSheet(f"background:{DARK_BG};")
        top.setMinimumHeight(320)
        top.setMaximumHeight(380)

        top_h = QHBoxLayout(top)
        top_h.setContentsMargins(12, 10, 12, 10)
        top_h.setSpacing(12)

        # ── LEFT: Local Node panel ────────────────────────────────────────
        local_frame = self._make_info_frame()
        local_lyt   = QVBoxLayout(local_frame)
        local_lyt.setContentsMargins(14, 10, 14, 10)
        local_lyt.setSpacing(6)

        self._local_hdr = self._make_hdr_label()
        local_lyt.addWidget(self._local_hdr)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet(f"color:{BORDER_COLOR};margin:0;")
        local_lyt.addWidget(sep1)

        self._local_name_lbl = QLabel("—")
        self._local_name_lbl.setWordWrap(True)
        self._local_name_lbl.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:14px;font-weight:bold;"
            f"background:transparent;border:none;"
        )
        local_lyt.addWidget(self._local_name_lbl)

        self._local_id_lbl = QLabel()
        self._local_id_lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;"
            f"background:transparent;border:none;"
        )
        local_lyt.addWidget(self._local_id_lbl)

        self._local_pos_lbl = QLabel("—")
        self._local_pos_lbl.setWordWrap(True)
        self._local_pos_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:11px;"
            f"background:transparent;border:none;"
        )
        local_lyt.addWidget(self._local_pos_lbl)

        self._local_gps_lbl = QLabel()
        self._local_gps_lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;"
            f"background:transparent;border:none;"
        )
        local_lyt.addWidget(self._local_gps_lbl)
        local_lyt.addStretch()

        top_h.addWidget(local_frame, stretch=2)

        # ── CENTRE: Compass ───────────────────────────────────────────────
        compass_col = QVBoxLayout()
        compass_col.setSpacing(4)
        compass_col.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self._compass_widget = QSvgWidget()
        self._compass_widget.setFixedSize(280, 280)
        self._compass_widget.setStyleSheet("background:transparent;")
        compass_col.addWidget(self._compass_widget, alignment=Qt.AlignHCenter)

        self._bearing_label = QLabel("—")
        self._bearing_label.setAlignment(Qt.AlignCenter)
        self._bearing_label.setStyleSheet(
            f"color:{ACCENT_BLUE};font-size:13px;font-weight:bold;"
            f"padding:2px 0;"
        )
        compass_col.addWidget(self._bearing_label)

        top_h.addLayout(compass_col, stretch=3)

        # ── RIGHT: Target panel ───────────────────────────────────────────
        target_frame = self._make_info_frame()
        target_lyt   = QVBoxLayout(target_frame)
        target_lyt.setContentsMargins(14, 10, 14, 10)
        target_lyt.setSpacing(6)

        self._target_hdr = self._make_hdr_label()
        target_lyt.addWidget(self._target_hdr)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color:{BORDER_COLOR};margin:0;")
        target_lyt.addWidget(sep2)

        self._target_name_lbl = QLabel("—")
        self._target_name_lbl.setWordWrap(True)
        self._target_name_lbl.setStyleSheet(
            f"color:{ACCENT_BLUE};font-size:14px;font-weight:bold;"
            f"background:transparent;border:none;"
        )
        target_lyt.addWidget(self._target_name_lbl)

        self._dist_label = QLabel("—")
        self._dist_label.setStyleSheet(
            f"color:{ACCENT_GREEN};font-size:26px;font-weight:bold;"
            f"background:transparent;border:none;"
        )
        target_lyt.addWidget(self._dist_label)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;"
            f"background:transparent;border:none;"
        )
        target_lyt.addWidget(self._status_label)
        target_lyt.addStretch()

        top_h.addWidget(target_frame, stretch=2)

        splitter.addWidget(top)

        # ── BOTTOM: table ─────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setStyleSheet(f"background:{PANEL_BG};")
        bot_lyt = QVBoxLayout(bottom)
        bot_lyt.setContentsMargins(8, 6, 8, 8)
        bot_lyt.setSpacing(4)

        self._table_title = QLabel(tr("📍  Nós com localização GPS"))
        self._table_title.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;font-weight:bold;letter-spacing:1px;"
        )
        bot_lyt.addWidget(self._table_title)

        self._table = QTableWidget(0, N_COLS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.setStyleSheet(
            f"QTableWidget {{background:{PANEL_BG};"
            f"alternate-background-color:{DARK_BG};"
            f"color:{TEXT_PRIMARY};gridline-color:{BORDER_COLOR};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;"
            f"selection-background-color:#1f3a5f;"
            f"selection-color:{TEXT_PRIMARY};}}"
            f"QHeaderView::section {{background:{DARK_BG};color:{ACCENT_BLUE};"
            f"padding:4px 6px;border:none;"
            f"border-right:1px solid {BORDER_COLOR};"
            f"border-bottom:1px solid {BORDER_COLOR};"
            f"font-weight:bold;font-size:10px;"
            f"text-transform:uppercase;letter-spacing:0.5px;}}"
        )

        hh = self._table.horizontalHeader()
        hh.setMinimumSectionSize(46)
        hh.setDefaultSectionSize(70)
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        for col, w in _COL_WIDTHS.items():
            self._table.setColumnWidth(col, w)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        bot_lyt.addWidget(self._table)

        splitter.addWidget(bottom)
        splitter.setSizes([340, 380])
        root.addWidget(splitter)

        self._refresh_headers()
        self._refresh_local_panel()
        self._refresh_compass()

    # ── Widget factories ──────────────────────────────────────────────────────
    def _make_info_frame(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(
            f"QFrame {{background:{PANEL_BG};border:1px solid {BORDER_COLOR};"
            f"border-radius:8px;}}"
        )
        return f

    def _make_hdr_label(self) -> QLabel:
        lbl = QLabel()
        lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;font-weight:bold;"
            f"letter-spacing:1.5px;background:transparent;border:none;"
        )
        return lbl

    # ── Public API ────────────────────────────────────────────────────────────
    def set_local_node(self, node_id: str, long_name: str, short_name: str):
        self._local_node_id    = node_id
        self._local_long_name  = long_name
        self._local_short_name = short_name
        self._refresh_local_panel()

    def set_local_gps_enabled(self, enabled: bool):
        self._local_gps_enabled = enabled
        self._refresh_local_panel()
        self._refresh_compass()

    def update_local_position(self, lat: float, lon: float,
                              alt: Optional[float] = None):
        self._local_lat = lat
        self._local_lon = lon
        if alt is not None:
            self._local_alt = alt
        self._local_gps_enabled = True
        self._refresh_local_panel()
        self._rebuild_table()
        self._refresh_compass()

    def update_node(self, node_id: str, node_data: dict):
        lat = node_data.get('latitude')
        lon = node_data.get('longitude')
        if lat is None or lon is None:
            if node_id in self._nodes:
                del self._nodes[node_id]
                self._rebuild_table()
            return
        if node_id not in self._nodes:
            self._nodes[node_id] = {}
        stored = self._nodes[node_id]
        for key in ('long_name', 'short_name', 'via_mqtt', 'snr', 'hops_away',
                    'latitude', 'longitude', 'altitude', 'battery_level'):
            val = node_data.get(key)
            if val is not None:
                stored[key] = val
            elif key not in stored:
                stored[key] = None
        stored['id'] = node_id
        self._rebuild_table()
        if node_id == self._selected_id:
            self._refresh_compass()

    def set_filter_text(self, text: str):
        self._filter_text = text.lower().strip()
        self._rebuild_table()

    def retranslate(self):
        self._refresh_headers()
        self._refresh_local_panel()
        self._refresh_compass()
        self._table_title.setText(tr("📍  Nós com localização GPS"))

    def clear(self):
        self._nodes.clear()
        self._selected_id        = None
        self._local_lat          = None
        self._local_lon          = None
        self._local_alt          = None
        self._local_gps_enabled  = False
        self._local_long_name    = ""
        self._local_short_name   = ""
        self._local_node_id      = ""
        self._filter_text        = ""
        self._table.setRowCount(0)
        self._refresh_local_panel()
        self._refresh_compass()

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _refresh_headers(self):
        self._table.setHorizontalHeaderLabels([
            tr("Nome Longo"), tr("Nome Curto"),
            "Hops", "Via", "SNR",
            tr("Distância"), "Bearing",
            "Lat", "Lon", "Alt (m)", tr("Bateria (%)"),
        ])

    def _refresh_local_panel(self):
        self._local_hdr.setText(tr("🏠  NÓ LOCAL"))
        name  = self._local_long_name  or self._local_node_id or "—"
        short = (f" [{self._local_short_name}]"
                 if self._local_short_name else "")
        self._local_name_lbl.setText(f"{name}{short}")
        self._local_id_lbl.setText(self._local_node_id or "")

        if self._local_lat is not None and self._local_lon is not None:
            alt_str = (f"\n⬆ {int(self._local_alt)} m"
                       if self._local_alt is not None else "")
            self._local_pos_lbl.setText(
                f"📍 {self._local_lat:.5f}\n    {self._local_lon:.5f}{alt_str}"
            )
        else:
            self._local_pos_lbl.setText(tr("nav_waiting_local_short"))

        if self._local_gps_enabled:
            self._local_gps_lbl.setText("GPS  ✅  active")
            self._local_gps_lbl.setStyleSheet(
                f"color:{ACCENT_GREEN};font-size:11px;"
                f"background:transparent;border:none;"
            )
        else:
            self._local_gps_lbl.setText(f"GPS  ⚠  {tr('nav_gps_off')}")
            self._local_gps_lbl.setStyleSheet(
                f"color:{ACCENT_ORANGE};font-size:11px;"
                f"background:transparent;border:none;"
            )

    def _dist_km(self, nd) -> Optional[float]:
        if self._local_lat is None or self._local_lon is None:
            return None
        lat = nd.get('latitude')
        lon = nd.get('longitude')
        if lat is None or lon is None:
            return None
        return _haversine_km(self._local_lat, self._local_lon, lat, lon)

    def _dist_str(self, nd) -> str:
        d = self._dist_km(nd)
        if d is None:
            return "—"
        return f"{d*1000:.0f} m" if d < 1.0 else f"{d:.2f} km"

    def _bearing_str(self, nd) -> str:
        if self._local_lat is None or self._local_lon is None:
            return "—"
        lat = nd.get('latitude')
        lon = nd.get('longitude')
        if lat is None or lon is None:
            return "—"
        b = _bearing_deg(self._local_lat, self._local_lon, lat, lon)
        return f"{b:.0f}° {_cardinal(b)}"

    def _matches_filter(self, nd) -> bool:
        if not self._filter_text:
            return True
        ft = self._filter_text
        return (ft in (nd.get('long_name')  or '').lower() or
                ft in (nd.get('short_name') or '').lower() or
                ft in (nd.get('id')         or '').lower())

    def _rebuild_table(self):
        visible = [(nid, nd) for nid, nd in self._nodes.items()
                   if self._matches_filter(nd)]
        visible.sort(key=lambda x: (self._dist_km(x[1]) or float('inf')))

        self._table.setRowCount(len(visible))
        for row, (node_id, nd) in enumerate(visible):
            via_mqtt = nd.get('via_mqtt')
            snr      = nd.get('snr')
            hops     = nd.get('hops_away')
            lat      = nd.get('latitude')
            lon      = nd.get('longitude')
            alt      = nd.get('altitude')
            batt     = nd.get('battery_level')

            cells = [
                nd.get('long_name') or node_id,
                nd.get('short_name') or "",
                str(int(hops)) if hops is not None else "—",
                "☁ MQTT" if via_mqtt else "RF",
                f"{snr:.1f} dB" if snr is not None else "—",
                self._dist_str(nd),
                self._bearing_str(nd),
                f"{lat:.5f}" if lat is not None else "—",
                f"{lon:.5f}" if lon is not None else "—",
                f"{int(alt)}" if alt is not None else "—",
                ("⚡" if batt == 101
                 else f"{batt}%" if batt is not None else "—"),
            ]

            is_sel = (node_id == self._selected_id)
            bg     = QColor("#1f3a5f") if is_sel else None
            d      = self._dist_km(nd)

            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                item.setData(Qt.UserRole, node_id)
                if bg:
                    item.setBackground(bg)
                # Colour coding
                if col == COL_DIST and d is not None:
                    item.setForeground(QColor(
                        ACCENT_GREEN  if d < 1   else
                        ACCENT_BLUE   if d < 10  else
                        ACCENT_ORANGE
                    ))
                elif col == COL_SNR and snr is not None:
                    item.setForeground(QColor(
                        ACCENT_GREEN  if snr >= 5  else
                        ACCENT_ORANGE if snr >= 0  else
                        ACCENT_RED
                    ))
                elif col == COL_BATT and batt is not None and batt != 101:
                    item.setForeground(QColor(
                        ACCENT_GREEN  if batt > 60 else
                        ACCENT_ORANGE if batt > 20 else
                        ACCENT_RED
                    ))
                elif col == COL_VIA and via_mqtt:
                    item.setForeground(QColor(ACCENT_ORANGE))
                self._table.setItem(row, col, item)

    def _on_selection_changed(self):
        items = self._table.selectedItems()
        self._selected_id = items[0].data(Qt.UserRole) if items else None
        self._refresh_compass()

    def _refresh_compass(self):
        self._target_hdr.setText(tr("🎯  ALVO"))
        has_local = (self._local_lat is not None and
                     self._local_lon is not None)

        def _clear(msg=""):
            self._compass_widget.load(QByteArray(_compass_svg(None)))
            self._dist_label.setText("—")
            self._bearing_label.setText("—")
            self._target_name_lbl.setText("—")
            self._status_label.setText(msg)

        if not self._local_gps_enabled:
            _clear(tr("nav_no_gps_short"))
            return
        if not has_local:
            _clear(tr("nav_waiting_local_short"))
            return
        if self._selected_id is None:
            _clear(tr("nav_select_node"))
            return

        nd = self._nodes.get(self._selected_id)
        if nd is None or nd.get('latitude') is None:
            _clear(tr("nav_no_target_gps"))
            return

        lat  = nd['latitude']
        lon  = nd['longitude']
        bear = _bearing_deg(self._local_lat, self._local_lon, lat, lon)
        dist = _haversine_km(self._local_lat, self._local_lon, lat, lon)
        name = nd.get('long_name') or self._selected_id

        dist_str = (f"{dist*1000:.0f} m" if dist < 1.0
                    else f"{dist:.2f} km")

        self._compass_widget.load(QByteArray(_compass_svg(bear)))
        self._dist_label.setText(dist_str)
        self._bearing_label.setText(f"{bear:.1f}°  {_cardinal(bear)}")
        self._target_name_lbl.setText(name)
        self._status_label.setText(
            tr("nav_target", name="", bearing=f"{bear:.1f}").strip()
            .replace("  ·  ", "").replace("➤", "").strip()
            or f"{_cardinal(bear)}"
        )