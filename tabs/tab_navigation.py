"""
tabs/tab_navigation.py — NavigationTab: aba de navegação com bússola e tabela
de nós com localização GPS conhecida.

Optimizações de performance para CM4:
  - Debounce de 500ms: acumula actualizações e reconstrói a tabela apenas uma
    vez no final de um burst de updates (ex: batch inicial de 50+ nós)
  - update_node() apenas actualiza o dicionário interno e agenda o rebuild
  - _rebuild_table() nunca chama _refresh_compass() — compass só actualiza
    quando a selecção muda ou a posição local muda
  - SVG da bússola só é regenerado quando bearing/estado realmente mudam
  - Tab inactiva: debounce não dispara rebuild até tab ficar activa
"""
import math
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QByteArray, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QAbstractItemView, QFrame, QPushButton
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
    return ["N","NE","E","SE","S","SW","W","NW"][int((b+22.5)/45)%8]


# ── Compass SVG ───────────────────────────────────────────────────────────────

def _compass_svg(bearing_deg: Optional[float], size: int = 280) -> bytes:
    cx = cy = size // 2
    r  = size // 2 - 10

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
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{"#8b949e" if is_card else "#30363d"}" '
            f'stroke-width="{"2" if is_card else "1"}"/>'
        )

    cards = ""
    lr = r - 24
    for deg, lbl, col, fw in [
        (0,"N","#39d353","bold"),(90,"E","#8b949e","normal"),
        (180,"S","#8b949e","normal"),(270,"W","#8b949e","normal"),
    ]:
        rad = math.radians(deg - 90)
        lx  = cx + lr * math.cos(rad)
        ly  = cy + lr * math.sin(rad)
        cards += (
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" fill="{col}" '
            f'font-size="15" font-weight="{fw}" '
            f'font-family="Arial,sans-serif">{lbl}</text>'
        )

    if bearing_deg is not None:
        a_rad = math.radians(bearing_deg - 90)
        p_rad = a_rad + math.pi / 2
        tip_x  = cx + (r-30) * math.cos(a_rad)
        tip_y  = cy + (r-30) * math.sin(a_rad)
        base_x = cx + 24 * math.cos(a_rad + math.pi)
        base_y = cy + 24 * math.sin(a_rad + math.pi)
        lw_x   = cx + 7 * math.cos(p_rad)
        lw_y   = cy + 7 * math.sin(p_rad)
        rw_x   = cx - 7 * math.cos(p_rad)
        rw_y   = cy - 7 * math.sin(p_rad)
        needle = (
            f'<polygon points="{tip_x:.1f},{tip_y:.1f} '
            f'{lw_x:.1f},{lw_y:.1f} {rw_x:.1f},{rw_y:.1f}" '
            f'fill="#f85149" stroke="#0d1117" stroke-width="1.2"/>'
            f'<polygon points="{base_x:.1f},{base_y:.1f} '
            f'{lw_x:.1f},{lw_y:.1f} {rw_x:.1f},{rw_y:.1f}" '
            f'fill="#6e7681" stroke="#0d1117" stroke-width="1.2"/>'
            f'<circle cx="{cx}" cy="{cy}" r="5" '
            f'fill="#21262d" stroke="#8b949e" stroke-width="2"/>'
        )
    else:
        needle = (
            f'<circle cx="{cx}" cy="{cy}" r="5" '
            f'fill="#30363d" stroke="#8b949e" stroke-width="2"/>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" '
        f'fill="#161b22" stroke="#30363d" stroke-width="2"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r-13}" fill="#0d1117"/>'
        f'{ticks}{cards}{needle}'
        f'</svg>'
    ).encode('utf-8')


# ── Column indices ─────────────────────────────────────────────────────────────
COL_LONG=0; COL_SHORT=1; COL_HOPS=2; COL_VIA=3; COL_SNR=4
COL_DIST=5; COL_BEARING=6; COL_LAT=7; COL_LON=8; COL_ALT=9
COL_BATT=10; N_COLS=11


class NavigationTab(QWidget):
    """Navigation tab — compass + GPS node table. CM4-optimised."""
    refresh_position_requested = pyqtSignal()   # emitido pelo botão 🔄

    _DEBOUNCE_MS = 800   # 800ms on CM4 — coalesces bursts of 50+ node updates into one rebuild

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
        self._last_bearing:      Optional[float]  = None  # avoid redundant SVG regen
        self._rebuild_pending:   bool = False  # set when rebuild skipped while hidden

        # Debounce timer — fires _rebuild_table() once after a burst of updates
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(self._DEBOUNCE_MS)
        self._rebuild_timer.timeout.connect(self._rebuild_table)

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(f"QSplitter::handle{{background:{BORDER_COLOR};}}")

        # ── TOP: [Local Node] | [Compass] | [Target] ─────────────────────
        top = QWidget()
        top.setStyleSheet(f"background:{DARK_BG};")
        top.setMinimumHeight(320)
        top.setMaximumHeight(380)
        top_h = QHBoxLayout(top)
        top_h.setContentsMargins(12, 10, 12, 10)
        top_h.setSpacing(12)

        # LEFT — Local Node
        local_frame = self._make_frame()
        ll = QVBoxLayout(local_frame)
        ll.setContentsMargins(12, 8, 12, 8)
        ll.setSpacing(6)
        self._local_hdr      = self._make_hdr(center=True)
        self._local_name_lbl = self._make_val(ACCENT_GREEN, 15, bold=True, wrap=True, center=True)
        self._local_id_lbl   = self._make_val(TEXT_MUTED, 11, center=True)
        self._local_pos_lbl  = self._make_val(TEXT_PRIMARY, 12, wrap=True, center=True)
        self._local_gps_lbl  = self._make_val(TEXT_MUTED, 11, center=True)
        ll.addStretch(1)
        for w in (self._local_hdr, self._make_sep(),
                  self._local_name_lbl, self._local_id_lbl,
                  self._local_pos_lbl, self._local_gps_lbl):
            ll.addWidget(w)
        # Botão 🔄 para reler posição GPS do nó local
        self._btn_refresh_pos = QPushButton(tr("nav_refresh_pos"))
        self._btn_refresh_pos.setToolTip(tr("nav_refresh_pos_tooltip"))
        self._btn_refresh_pos.setStyleSheet(
            f"QPushButton{{background:{PANEL_BG};color:{ACCENT_BLUE};"
            f"border:1px solid {ACCENT_BLUE};border-radius:6px;"
            f"padding:4px 8px;font-size:11px;margin-top:4px;}}"
            f"QPushButton:hover{{background:{ACCENT_BLUE};color:#000;}}"
            f"QPushButton:disabled{{color:{TEXT_MUTED};"
            f"border-color:{TEXT_MUTED};background:{PANEL_BG};}}"
        )
        self._btn_refresh_pos.clicked.connect(self._on_refresh_pos_clicked)
        ll.addWidget(self._btn_refresh_pos)
        ll.addStretch(1)
        top_h.addWidget(local_frame, stretch=2)

        # CENTRE — Compass
        cc = QVBoxLayout()
        cc.setSpacing(4)
        cc.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self._compass_widget = QSvgWidget()
        self._compass_widget.setFixedSize(280, 280)
        self._compass_widget.setStyleSheet("background:transparent;")
        self._bearing_label = QLabel("—")
        self._bearing_label.setAlignment(Qt.AlignCenter)
        self._bearing_label.setStyleSheet(
            f"color:{ACCENT_BLUE};font-size:13px;font-weight:bold;padding:2px 0;"
        )
        cc.addWidget(self._compass_widget, alignment=Qt.AlignHCenter)
        cc.addWidget(self._bearing_label)
        top_h.addLayout(cc, stretch=3)

        # RIGHT — Target
        target_frame = self._make_frame()
        tl = QVBoxLayout(target_frame)
        tl.setContentsMargins(12, 8, 12, 8)
        tl.setSpacing(6)
        self._target_hdr      = self._make_hdr(center=True)
        self._target_name_lbl = self._make_val(ACCENT_BLUE, 15, bold=True, wrap=True, center=True)
        self._dist_label      = self._make_val(ACCENT_GREEN, 26, bold=True, center=True)
        self._target_snr_lbl  = self._make_val(TEXT_MUTED, 12, center=True)
        self._target_alt_lbl  = self._make_val(TEXT_MUTED, 12, center=True)
        self._status_label    = self._make_val(TEXT_MUTED, 11, wrap=True, center=True)
        tl.addStretch(1)
        for w in (self._target_hdr, self._make_sep(),
                  self._target_name_lbl, self._dist_label,
                  self._target_snr_lbl, self._target_alt_lbl,
                  self._status_label):
            tl.addWidget(w)
        tl.addStretch(1)
        top_h.addWidget(target_frame, stretch=2)

        splitter.addWidget(top)

        # ── BOTTOM: table ─────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setStyleSheet(f"background:{PANEL_BG};")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(8, 6, 8, 8)
        bl.setSpacing(4)

        self._table_title = QLabel(tr("📍  Nós com localização GPS"))
        self._table_title.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;font-weight:bold;letter-spacing:1px;"
        )
        bl.addWidget(self._table_title)

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
            f"QTableWidget{{background:{PANEL_BG};"
            f"alternate-background-color:{DARK_BG};"
            f"color:{TEXT_PRIMARY};gridline-color:{BORDER_COLOR};"
            f"border:1px solid {BORDER_COLOR};border-radius:6px;"
            f"selection-background-color:#1f3a5f;"
            f"selection-color:{TEXT_PRIMARY};}}"
            f"QHeaderView::section{{background:{DARK_BG};color:{ACCENT_BLUE};"
            f"padding:4px 6px;border:none;"
            f"border-right:1px solid {BORDER_COLOR};"
            f"border-bottom:1px solid {BORDER_COLOR};"
            f"font-weight:bold;font-size:10px;"
            f"text-transform:uppercase;letter-spacing:0.5px;}}"
        )
        hh = self._table.horizontalHeader()
        hh.setMinimumSectionSize(40)
        # Equal-width columns that fill the full table width
        hh.setSectionResizeMode(QHeaderView.Stretch)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        bl.addWidget(self._table)

        splitter.addWidget(bottom)
        splitter.setSizes([340, 380])
        root.addWidget(splitter)

        self._refresh_headers()
        self._refresh_local_panel()
        # Load empty compass immediately so widget has content from the start
        self._compass_widget.load(QByteArray(_compass_svg(None)))
        self._refresh_compass()

    # ── Widget helpers ────────────────────────────────────────────────────────
    def _make_frame(self):
        f = QFrame()
        f.setObjectName("infoFrame")
        # Use ID selector so style does NOT cascade to child QFrame separators
        f.setStyleSheet(
            f"QFrame#infoFrame{{background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:8px;}}"
        )
        return f

    def _make_hdr(self, center: bool = False):
        lbl = QLabel()
        lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;font-weight:bold;"
            f"letter-spacing:1.5px;background:transparent;border:none;"
        )
        if center:
            lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _make_sep(self):
        # Use a fixed-height QWidget instead of QFrame to avoid inheriting
        # the parent QFrame stylesheet (border-radius etc.)
        s = QFrame()
        s.setFrameShape(QFrame.HLine)
        s.setFixedHeight(1)
        s.setStyleSheet("QFrame{background:" + BORDER_COLOR + ";border:none;margin:2px 0;}")
        return s

    def _make_val(self, color, size, bold=False, wrap=False, center=False):
        lbl = QLabel("—")
        fw  = "bold" if bold else "normal"
        lbl.setStyleSheet(
            f"color:{color};font-size:{size}px;font-weight:{fw};"
            f"background:transparent;border:none;"
        )
        if wrap:
            lbl.setWordWrap(True)
        if center:
            lbl.setAlignment(Qt.AlignCenter)
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
        # Only refresh UI if the navigation tab is currently visible
        if self.isVisible():
            self._refresh_local_panel()
            self._refresh_compass()
        # Distances changed — schedule one rebuild (debounced, cheap)
        self._schedule_rebuild()

    def _on_refresh_pos_clicked(self):
        """Desabilita o botão temporariamente e emite o sinal para o main."""
        self._btn_refresh_pos.setEnabled(False)
        self._btn_refresh_pos.setText(tr("nav_pos_refreshing"))
        self.refresh_position_requested.emit()

    def set_refresh_pos_result(self, found: bool):
        """Chamado por main.py após o worker responder ao refresh."""
        self._btn_refresh_pos.setEnabled(True)
        self._btn_refresh_pos.setText(tr("nav_refresh_pos"))
        if not found:
            # Pisca o label de posição brevemente para dar feedback
            self._local_pos_lbl.setText(f"⚠ {tr('nav_pos_not_found')}")
            self._local_pos_lbl.setStyleSheet(
                f"color:{ACCENT_RED};font-size:12px;"
                f"background:transparent;border:none;text-align:center;"
            )
            # Restaura o estado correcto após 3s
            QTimer.singleShot(3000, self._refresh_local_panel)

    def update_node(self, node_id: str, node_data: dict):
        """
        Store data and schedule a debounced rebuild.
        NEVER calls _rebuild_table() directly — that would cause
        one full table rebuild per node in a batch of 50+ nodes.
        """
        lat = node_data.get('latitude')
        lon = node_data.get('longitude')
        if lat is None or lon is None:
            if node_id in self._nodes:
                del self._nodes[node_id]
                self._schedule_rebuild()
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

        self._schedule_rebuild()

        # If the selected node moved, refresh compass (cheap — only if needed)
        if node_id == self._selected_id:
            self._refresh_compass()

    def set_filter_text(self, text: str):
        self._filter_text = text.lower().strip()
        self._schedule_rebuild()

    def showEvent(self, event):
        """Flush any deferred work when the navigation tab becomes visible."""
        super().showEvent(event)
        # Rebuild table if it was skipped while the tab was hidden
        if self._rebuild_pending:
            self._rebuild_pending = False
            self._rebuild_table()
        # Always refresh the local panel and compass on show — they may
        # have been skipped during batch updates while the tab was hidden.
        self._refresh_local_panel()
        self._refresh_compass()

    def retranslate(self):
        self._refresh_headers()
        self._refresh_local_panel()
        self._refresh_compass()
        self._table_title.setText(tr("📍  Nós com localização GPS"))
        if hasattr(self, "_btn_refresh_pos") and self._btn_refresh_pos.isEnabled():
            self._btn_refresh_pos.setText(tr("nav_refresh_pos"))
            self._btn_refresh_pos.setToolTip(tr("nav_refresh_pos_tooltip"))

    def clear(self):
        self._rebuild_timer.stop()
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
        self._last_bearing       = None
        self._rebuild_pending    = False
        self._table.setRowCount(0)
        self._refresh_local_panel()
        self._refresh_compass()

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _schedule_rebuild(self):
        """Start (or restart) the debounce timer. Table rebuilds once after burst."""
        self._rebuild_timer.start()  # restarts if already running

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
        short = f" [{self._local_short_name}]" if self._local_short_name else ""
        self._local_name_lbl.setText(f"{name}{short}")
        self._local_id_lbl.setText(self._local_node_id or "")

        _base = "background:transparent;border:none;text-align:center;"

        if self._local_lat is not None and self._local_lon is not None:
            alt_str = (f"\n⬆ {int(self._local_alt)} m"
                       if self._local_alt is not None else "")
            self._local_pos_lbl.setText(
                f"📍 {self._local_lat:.5f}\n    {self._local_lon:.5f}{alt_str}"
            )
            self._local_pos_lbl.setStyleSheet(
                f"color:{TEXT_PRIMARY};font-size:12px;{_base}"
            )
        elif self._local_gps_enabled:
            self._local_pos_lbl.setText(f"⏳ {tr('nav_waiting_local_short')}")
            self._local_pos_lbl.setStyleSheet(
                f"color:{ACCENT_ORANGE};font-size:12px;{_base}"
            )
        else:
            self._local_pos_lbl.setText(f"⚠ {tr('nav_no_gps_short')}")
            self._local_pos_lbl.setStyleSheet(
                f"color:{ACCENT_RED};font-size:12px;{_base}"
            )

        if self._local_gps_enabled:
            if self._local_lat is not None and self._local_lon is not None:
                self._local_gps_lbl.setText(f"📡 {tr('nav_gps_active')}")
                self._local_gps_lbl.setStyleSheet(
                    f"color:{ACCENT_GREEN};font-size:11px;{_base}"
                )
            else:
                self._local_gps_lbl.setText(f"📡 {tr('nav_gps_active')}  ·  ⏳ {tr('nav_waiting_local_short')}")
                self._local_gps_lbl.setStyleSheet(
                    f"color:{ACCENT_ORANGE};font-size:11px;{_base}"
                )
        else:
            self._local_gps_lbl.setText(f"GPS  ⚠  {tr('nav_gps_off')}")
            self._local_gps_lbl.setStyleSheet(
                f"color:{ACCENT_ORANGE};font-size:11px;{_base}"
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
        """Rebuilds the table once. Called only by the debounce timer.
        Skips work entirely when the widget is hidden — showEvent will
        re-trigger the debounce timer the next time the tab becomes visible."""
        if not self.isVisible():
            # Mark that a rebuild is pending; showEvent will reschedule.
            self._rebuild_pending = True
            return
        self._rebuild_pending = False
        visible = [(nid, nd) for nid, nd in self._nodes.items()
                   if self._matches_filter(nd)]
        visible.sort(key=lambda x: (self._dist_km(x[1]) or float('inf')))

        # Block signals during rebuild to prevent itemSelectionChanged from
        # firing on every setItem/setRowCount — avoids double-highlight and
        # spurious _refresh_compass() calls.
        self._table.blockSignals(True)
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(len(visible))
        for row, (node_id, nd) in enumerate(visible):
            via_mqtt = nd.get('via_mqtt')
            snr      = nd.get('snr')
            hops     = nd.get('hops_away')
            lat      = nd.get('latitude')
            lon      = nd.get('longitude')
            alt      = nd.get('altitude')
            batt     = nd.get('battery_level')
            d        = self._dist_km(nd)

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

            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                item.setData(Qt.UserRole, node_id)
                if bg:
                    item.setBackground(bg)
                if col == COL_DIST and d is not None:
                    item.setForeground(QColor(
                        ACCENT_GREEN if d < 1 else
                        ACCENT_BLUE  if d < 10 else ACCENT_ORANGE
                    ))
                elif col == COL_SNR and snr is not None:
                    item.setForeground(QColor(
                        ACCENT_GREEN  if snr >= 5  else
                        ACCENT_ORANGE if snr >= 0  else ACCENT_RED
                    ))
                elif col == COL_BATT and batt is not None and batt != 101:
                    item.setForeground(QColor(
                        ACCENT_GREEN  if batt > 60 else
                        ACCENT_ORANGE if batt > 20 else ACCENT_RED
                    ))
                elif col == COL_VIA and via_mqtt:
                    item.setForeground(QColor(ACCENT_ORANGE))
                self._table.setItem(row, col, item)

        self._table.setUpdatesEnabled(True)
        self._table.blockSignals(False)

        # Restore Qt selection to match _selected_id (signals were blocked above)
        if self._selected_id is not None:
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if item and item.data(Qt.UserRole) == self._selected_id:
                    self._table.selectRow(row)
                    break

    def _on_selection_changed(self):
        items = self._table.selectedItems()
        self._selected_id = items[0].data(Qt.UserRole) if items else None
        self._last_bearing = None   # force compass redraw on selection change
        self._refresh_compass()

    def _refresh_compass(self):
        """
        Redraws the compass SVG only if the bearing or state changed.
        Generating SVG is cheap but loading it into QSvgWidget triggers
        a repaint — skip if nothing changed.
        """
        self._target_hdr.setText(tr("🎯  ALVO"))
        has_local = (self._local_lat is not None and
                     self._local_lon is not None)

        def _clear(msg=""):
            # Always reload the empty compass (no needle) to ensure widget stays visible
            if self._last_bearing is not None:
                self._compass_widget.load(QByteArray(_compass_svg(None)))
                self._last_bearing = None
            self._dist_label.setText("—")
            self._bearing_label.setText("—")
            self._target_name_lbl.setText("—")
            self._target_snr_lbl.setText("")
            self._target_alt_lbl.setText("")
            self._status_label.setText(msg)

        if not self._local_gps_enabled:
            _clear(tr("nav_no_pos_warn")); return
        if not has_local:
            _clear(tr("nav_waiting_local_short")); return
        if self._selected_id is None:
            _clear(tr("nav_select_node")); return

        nd = self._nodes.get(self._selected_id)
        if nd is None or nd.get('latitude') is None:
            _clear(tr("nav_no_target_gps")); return

        lat  = nd['latitude']
        lon  = nd['longitude']
        bear = _bearing_deg(self._local_lat, self._local_lon, lat, lon)
        dist = _haversine_km(self._local_lat, self._local_lon, lat, lon)
        name = nd.get('long_name') or self._selected_id

        # Only reload SVG if bearing changed by more than 1°
        bear_rounded = round(bear)
        if self._last_bearing != bear_rounded:
            self._compass_widget.load(QByteArray(_compass_svg(bear)))
            self._last_bearing = bear_rounded

        dist_str = f"{dist*1000:.0f} m" if dist < 1.0 else f"{dist:.2f} km"
        self._dist_label.setText(dist_str)
        self._bearing_label.setText(f"{bear:.1f}°  {_cardinal(bear)}")
        self._target_name_lbl.setText(name)
        self._status_label.setText(_cardinal(bear))

        # SNR
        snr = nd.get('snr')
        if snr is not None:
            if snr >= 5:
                snr_color = ACCENT_GREEN
            elif snr >= 0:
                snr_color = ACCENT_ORANGE
            else:
                snr_color = ACCENT_RED
            self._target_snr_lbl.setText(f"📶 SNR: {snr:+.1f} dB")
            self._target_snr_lbl.setStyleSheet(
                f"color:{snr_color};font-size:12px;background:transparent;border:none;text-align:center;"
            )
        else:
            self._target_snr_lbl.setText("")

        # Altitude
        alt = nd.get('altitude')
        if alt is not None:
            self._target_alt_lbl.setText(f"⬆ {int(alt)} m")
            self._target_alt_lbl.setStyleSheet(
                f"color:{TEXT_MUTED};font-size:12px;background:transparent;border:none;text-align:center;"
            )
        else:
            self._target_alt_lbl.setText("")