"""
models.py — Modelos de dados: FavoritesStore, NodeTableModel,
NodeFilterProxyModel e a função auxiliar _safe_update.
"""
import json
import os
import logging
from typing import Optional, Dict, Any, Set, List
from datetime import datetime, timedelta

from PyQt5.QtCore import (
    Qt, QAbstractTableModel, QSortFilterProxyModel,
    QModelIndex, pyqtSignal
)
from PyQt5.QtGui import QColor

from constants import (
    ACCENT_GREEN, ACCENT_BLUE, ACCENT_ORANGE, ACCENT_RED,
    ACCENT_PURPLE, TEXT_MUTED, BORDER_COLOR
)

logger = logging.getLogger("MeshtasticGUI")



class FavoritesStore:
    """
    Guarda os dados completos de nós favoritos num ficheiro JSON local.
    Ao conectar, os favoritos são injectados na lista mesmo que o NodeDB
    do firmware não os inclua (ex: nós de outras redes já vistos).
    """
    _PATH = os.path.join(
        os.path.expanduser("~"), ".meshtastic_monitor_favorites.json"
    )
    _FIELDS = [
        "id_string", "id_num", "long_name", "short_name", "hw_model",
        "public_key", "latitude", "longitude", "altitude",
        "battery_level", "snr", "hops_away", "via_mqtt", "last_heard",
    ]

    def __init__(self):
        self._nodes: Dict[str, Dict] = {}   # id_string → dados completos
        self._load()

    # ── persistência ────────────────────────────────────────────────────
    def _load(self):
        try:
            if not os.path.exists(self._PATH):
                return
            with open(self._PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("nodes", data.get("favorites", []))
            if isinstance(raw, list):          # formato antigo (lista de IDs)
                for item in raw:
                    if isinstance(item, str):
                        self._nodes[item] = {"id_string": item}
                    elif isinstance(item, dict) and item.get("id_string"):
                        self._nodes[item["id_string"]] = item
            elif isinstance(raw, dict):
                self._nodes = raw
            # Reconverte last_heard guardado como string ISO
            for nd in self._nodes.values():
                lh = nd.get("last_heard")
                if isinstance(lh, str):
                    try:
                        nd["last_heard"] = datetime.fromisoformat(lh)
                    except Exception:
                        nd["last_heard"] = None
        except Exception as e:
            logger.warning(f"FavoritesStore.load: {e}")
            self._nodes = {}

    def _save(self):
        try:
            def _serial(v):
                return v.isoformat() if isinstance(v, datetime) else v
            out = {nid: {k: _serial(v) for k, v in nd.items()}
                   for nid, nd in self._nodes.items()}
            with open(self._PATH, "w", encoding="utf-8") as f:
                json.dump({"nodes": out}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"FavoritesStore.save: {e}")

    # ── API pública ──────────────────────────────────────────────────────
    def is_favorite(self, node_id: str) -> bool:
        return node_id in self._nodes

    def toggle(self, node_id: str, node_data: Optional[Dict] = None) -> bool:
        """Alterna favorito. Retorna True se agora é favorito."""
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._save()
            return False
        entry: Dict = {"id_string": node_id}
        if node_data:
            for f in self._FIELDS:
                v = node_data.get(f)
                if v is not None:
                    entry[f] = v
        self._nodes[node_id] = entry
        self._save()
        return True

    def update_node_data(self, node_id: str, node_data: Dict):
        """Actualiza os campos persistidos de um favorito já existente."""
        if node_id not in self._nodes:
            return
        nd = self._nodes[node_id]
        for f in self._FIELDS:
            v = node_data.get(f)
            if v is not None:
                nd[f] = v
        self._save()

    def get_all(self) -> Set[str]:
        return set(self._nodes.keys())

    def get_node_data(self, node_id: str) -> Optional[Dict]:
        return dict(self._nodes[node_id]) if node_id in self._nodes else None

    def get_all_nodes_data(self) -> List[Dict]:
        return [dict(nd) for nd in self._nodes.values()]


_FAVORITES = FavoritesStore()

def _safe_update(target: dict, source: dict) -> None:
    """
    Aplica source a target com as seguintes regras:
    - last_heard: só actualiza se o novo valor é um datetime mais recente
      que o existente; nunca sobrescreve datetime com None, 0 ou outro tipo
    - Campos numéricos (snr, hops_away, battery_level, latitude, longitude,
      altitude): só actualiza se o novo valor não é None
    - Campos string (long_name, short_name, hw_model, public_key): só
      actualiza se o novo valor é não-vazio
    - Campos bool e outros campos simples: actualiza sempre
    - Campos técnicos internos (id_string, last_packet, _selected_highlight):
      actualiza sempre

    Esta função resolve o problema de _emit_node / _on_nodes_batch
    sobrescrever last_heard válido com lastHeard=0 do NodeDB, e de
    dict.update() apagar campos reais com None de actualizações parciais.
    """
    # Campos que nunca devem ser sobrescritos por None ou valor falsy
    _no_overwrite_none = {
        'snr', 'hops_away', 'battery_level',
        'latitude', 'longitude', 'altitude',
        'voltage', 'uptime_seconds', 'channel_utilization', 'air_util_tx',
    }
    # Campos string que não devem ser sobrescritos por strings vazias
    _no_overwrite_empty_str = {'long_name', 'short_name', 'hw_model', 'public_key'}

    for key, val in source.items():
        if key == 'last_heard':
            # Só actualiza last_heard se o novo valor é um datetime
            # e é mais recente que o existente (ou não há valor existente)
            existing = target.get('last_heard')
            if isinstance(val, datetime):
                if not isinstance(existing, datetime) or val > existing:
                    target['last_heard'] = val
            # Se val não é datetime (ex: 0, None, int) — ignora completamente
        elif key in _no_overwrite_none:
            if val is not None:
                target[key] = val
        elif key in _no_overwrite_empty_str:
            if val:  # ignora strings vazias
                target[key] = val
        else:
            target[key] = val


# ---------------------------------------------------------------------------
# Modelo de dados — tabela de nós
# ---------------------------------------------------------------------------
class NodeTableModel(QAbstractTableModel):
    HEADERS = [
        "⭐", "📩", "🗺", "📡",
        "ID String", "ID Num", "Nome Longo", "Nome Curto", "Último Contato",
        "SNR (dB)", "Hops", "Via", "Latitude", "Longitude", "Altitude (m)",
        "Bateria (%)", "Modelo", "Último Tipo",
    ]

    COL_FAV        = 0
    COL_DM         = 1
    COL_MAP        = 2
    COL_TRACEROUTE = 3
    COL_DATA_START = 4

    node_inserted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: List[Dict[str, Any]] = []
        self._node_index: Dict[str, int] = {}
        self._local_node_id:  Optional[str] = None   # ID canónico !hex
        self._local_node_num: Optional[int] = None   # FIX-4: nodeNum int bloqueado cedo

    def rowCount(self, parent=QModelIndex()):
        return len(self._nodes)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = self._nodes[index.row()]
        col  = index.column()

        if role == Qt.DisplayRole:
            return self._display_value(node, col)

        # ── Nó local — linha destacada ────────────────────────────────────
        node_id  = node.get("id_string", "")
        is_local = self._is_local_node(node_id, node.get("id_num"))

        if role == Qt.ForegroundRole:
            if is_local:
                return QColor(ACCENT_ORANGE)   # laranja para todos os campos do nó local
            if col == self.COL_FAV:
                return QColor("#f5c518") if _FAVORITES.is_favorite(node_id) else QColor(BORDER_COLOR)
            if col == self.COL_DM:
                # Só mostramos DM se o nó tem last_heard (é alcançável)
                if isinstance(node.get("last_heard"), datetime):
                    return QColor(ACCENT_PURPLE)
                return QColor(BORDER_COLOR)
            if col == self.COL_TRACEROUTE:
                return QColor(ACCENT_BLUE)
            if col == self.COL_MAP:
                has_gps = (node.get('latitude') is not None and node.get('longitude') is not None)
                return QColor(ACCENT_GREEN) if has_gps else QColor(BORDER_COLOR)
            if col == 7:  # Nome Curto — verde se online (<2h), cinza se inactivo
                lh = node.get("last_heard")
                if isinstance(lh, datetime) and (datetime.now() - lh) <= timedelta(hours=2):
                    return QColor(ACCENT_GREEN)
                return QColor(TEXT_MUTED)
            if col == 9:  # SNR
                snr = node.get("snr")
                if snr is not None:
                    if snr >= 5:  return QColor(ACCENT_GREEN)
                    if snr >= 0:  return QColor(ACCENT_ORANGE)
                    return QColor(ACCENT_RED)
            if col == 11:  # Via
                return QColor(ACCENT_ORANGE) if node.get("via_mqtt") is True else QColor(ACCENT_GREEN)
            if col == 15:  # Bateria
                batt = node.get("battery_level")
                if batt is not None:
                    if batt > 60: return QColor(ACCENT_GREEN)
                    if batt > 20: return QColor(ACCENT_ORANGE)
                    return QColor(ACCENT_RED)

        if role == Qt.BackgroundRole:
            if is_local:
                return QColor("#1a1000")   # fundo âmbar muito subtil para o nó local
            if _FAVORITES.is_favorite(node_id):
                return QColor("#2d2200")  # fundo âmbar para favoritos — mais visível
            if node.get("_selected_highlight"):
                return QColor("#1a3a1a")

        if role == Qt.TextAlignmentRole and col in (
            self.COL_FAV, self.COL_DM, self.COL_MAP, self.COL_TRACEROUTE
        ):
            return Qt.AlignCenter

        if role == Qt.ToolTipRole:
            if is_local:
                return f"🏠 Este é o seu nó local · {node_id}"
            if col == self.COL_FAV:
                return "Clique para remover dos favoritos" if _FAVORITES.is_favorite(node_id) \
                       else "Clique para adicionar aos favoritos"
            if col == self.COL_MAP:
                has_gps = (node.get('latitude') is not None and node.get('longitude') is not None)
                return "Ver no mapa" if has_gps else "Sem dados de posição"
            if col == self.COL_DM:
                if not isinstance(node.get("last_heard"), datetime):
                    return "DM indisponível — nó nunca contactado"
                has_key = bool(node.get('public_key', ''))
                return "Enviar DM 🔒 PKI (chave pública conhecida)" if has_key \
                       else "Enviar DM 🔓 PSK (chave de canal)"

        return None

    def _display_value(self, node, col):
        if col == self.COL_FAV:
            node_id = node.get("id_string", "")
            return "⭐" if _FAVORITES.is_favorite(node_id) else "☆"
        if col == self.COL_DM:
            # Só exibe ícone activo se o nó já foi contactado
            if not isinstance(node.get("last_heard"), datetime):
                return "·"
            has_key = bool(node.get('public_key', ''))
            return "🔒" if has_key else "📩"
        if col == self.COL_MAP:
            has_gps = (node.get('latitude') is not None and node.get('longitude') is not None)
            return "🗺" if has_gps else "·"
        if col == self.COL_TRACEROUTE:
            return "📡"
        is_local = self._is_local_node(node.get("id_string", ""), node.get("id_num"))
        m = {
            4:  lambda n: n.get("id_string", ""),
            5:  lambda n: str(n.get("id_num", "")),
            6:  lambda n: ("🏠 " + (n.get("long_name", "") or "—")) if is_local
                           else (n.get("long_name", "") or "⏳ Aguardando Info"),
            7:  lambda n: (n.get("short_name", "") or "--"),
            8:  lambda n: (n["last_heard"].strftime("%Y-%m-%d %H:%M:%S")
                           if isinstance(n.get("last_heard"), datetime)
                           else str(n.get("last_heard", "Nunca"))),
            9:  lambda n: f"{n['snr']:.1f}" if n.get("snr") is not None else "",
            10: lambda n: str(n["hops_away"]) if n.get("hops_away") is not None else "",
            11: lambda n: "☁ MQTT" if n.get("via_mqtt") is True else "RF",
            12: lambda n: f"{n['latitude']:.6f}" if n.get("latitude") is not None else "",
            13: lambda n: f"{n['longitude']:.6f}" if n.get("longitude") is not None else "",
            14: lambda n: str(n["altitude"]) if n.get("altitude") is not None else "",
            15: lambda n: str(n["battery_level"]) if n.get("battery_level") is not None else "",
            16: lambda n: n.get("hw_model", ""),
            17: lambda n: n.get("last_packet_type", ""),
        }
        fn = m.get(col)
        return fn(node) if fn else None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    # FIX-4: aceita também nodeNum int para bloqueio precoce
    def set_local_node_id(self, node_id: str, node_num: Optional[int] = None):
        self._local_node_id  = node_id.lower() if node_id else None
        self._local_node_num = node_num

    def _is_local_node(self, node_id_string: str, node_id_num=None) -> bool:
        if self._local_node_num is not None and node_id_num is not None:
            try:
                if int(node_id_num) == self._local_node_num:
                    return True
            except (TypeError, ValueError):
                pass
        return bool(self._local_node_id and node_id_string
                    and node_id_string.lower() == self._local_node_id)

    def update_node_silent(self, node_id_string: str, node_data: Dict[str, Any]) -> bool:
        if node_id_string in self._node_index:
            row = self._node_index[node_id_string]
            _safe_update(self._nodes[row], node_data)
            return False
        else:
            # Nó local é agora permitido — aparece no topo com destaque visual
            node_data["id_string"] = node_id_string
            row = len(self._nodes)
            self._nodes.append(node_data)
            self._node_index[node_id_string] = row
            return True

    def refresh_all(self):
        self.beginResetModel()
        self.endResetModel()
        self.node_inserted.emit()

    def update_node(self, node_id_string: str, node_data: Dict[str, Any], packet=None):
        if node_id_string in self._node_index:
            row = self._node_index[node_id_string]
            _safe_update(self._nodes[row], node_data)
            if packet is not None:
                self._nodes[row]["last_packet"] = packet
            tl = self.createIndex(row, 0)
            br = self.createIndex(row, len(self.HEADERS) - 1)
            self.dataChanged.emit(tl, br, [Qt.DisplayRole, Qt.ForegroundRole, Qt.BackgroundRole])
        else:
            row = len(self._nodes)
            self.beginInsertRows(QModelIndex(), row, row)
            node_data["id_string"] = node_id_string
            if packet is not None:
                node_data["last_packet"] = packet
            self._nodes.append(node_data)
            self._node_index[node_id_string] = row
            self.endInsertRows()
            is_local = self._is_local_node(node_id_string, node_data.get('id_num'))
            logger.info(f"Modelo: NOVO nó {node_id_string} inserido{'  [LOCAL]' if is_local else ''}")
            self.node_inserted.emit()

    def set_selected_highlight(self, node_id_string: Optional[str]):
        for node in self._nodes:
            node["_selected_highlight"] = (node.get("id_string") == node_id_string
                                            and node_id_string is not None)
        if self._nodes:
            tl = self.createIndex(0, 0)
            br = self.createIndex(len(self._nodes) - 1, len(self.HEADERS) - 1)
            self.dataChanged.emit(tl, br, [Qt.BackgroundRole])

    def get_node_count(self):
        return len(self._nodes)

    def get_visible_count(self) -> int:
        """
        FIX-8: Conta nós visíveis (com last_heard) excluindo o nó local.
        Este valor é sempre independente do filtro de pesquisa.
        """
        local_id = self._local_node_id
        return sum(
            1 for n in self._nodes
            if isinstance(n.get("last_heard"), datetime)
            and (not local_id or n.get("id_string", "").lower() != local_id)
        )

    def get_online_count(self) -> int:
        """Conta nós activos (last_heard < 2 horas) excluindo o nó local."""
        local_id = self._local_node_id
        cutoff   = datetime.now() - timedelta(hours=2)
        return sum(
            1 for n in self._nodes
            if isinstance(n.get("last_heard"), datetime)
            and n.get("last_heard") >= cutoff
            and (not local_id or n.get("id_string", "").lower() != local_id)
        )

    def get_node_data(self, r):
        return self._nodes[r] if 0 <= r < len(self._nodes) else None

    def get_all_nodes(self):
        return self._nodes

    def clear_all_nodes(self):
        if not self._nodes:
            return
        self.beginResetModel()
        self._nodes.clear()
        self._node_index.clear()
        self.endResetModel()

    def get_node_choices(self) -> List[tuple]:
        return [
            (n.get("id_string", ""), n.get("long_name", ""), n.get("short_name", ""))
            for n in self._nodes
        ]

# ---------------------------------------------------------------------------
# Proxy de pesquisa
# ---------------------------------------------------------------------------
class NodeFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text   = ""
        self._local_node_id: Optional[str] = None

    def set_filter_text(self, text: str):
        self._filter_text = text.lower()
        self.invalidateFilter()

    def get_filter_text(self):
        return self._filter_text

    def set_local_node_id(self, node_id: str):
        self._local_node_id = node_id
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        node  = model.get_node_data(source_row)
        if node is None:
            return False
        # Nó local: mostra sempre no topo (sem filtrar por last_heard nem por pesquisa)
        if self._local_node_id and node.get("id_string") == self._local_node_id:
            return True
        if not isinstance(node.get("last_heard"), datetime):
            return False
        if not self._filter_text:
            return True
        search_vals = [
            str(node.get("id_string", "")).lower(),
            str(node.get("long_name", "")).lower(),
            str(node.get("short_name", "")).lower(),
            str(node.get("id_num", "")).lower(),
        ]
        return any(self._filter_text in v for v in search_vals)

    def lessThan(self, left, right):
        """
        Ordem: nó local SEMPRE no topo, depois favoritos, depois restantes.
        Dentro de cada grupo aplica a ordenação normal da coluna.
        """
        model  = self.sourceModel()
        node_l = model.get_node_data(left.row())
        node_r = model.get_node_data(right.row())
        if node_l is None or node_r is None:
            return super().lessThan(left, right)

        # Nó local fixado no topo
        is_local_l = bool(self._local_node_id and
                          node_l.get("id_string") == self._local_node_id)
        is_local_r = bool(self._local_node_id and
                          node_r.get("id_string") == self._local_node_id)
        if is_local_l != is_local_r:
            asc = (self.sortOrder() == Qt.AscendingOrder)
            return is_local_l if asc else is_local_r

        fav_l = _FAVORITES.is_favorite(node_l.get("id_string", ""))
        fav_r = _FAVORITES.is_favorite(node_r.get("id_string", ""))
        if fav_l != fav_r:
            asc = (self.sortOrder() == Qt.AscendingOrder)
            return fav_l if asc else fav_r
        return super().lessThan(left, right)

    def get_visible_node_ids(self) -> Set[str]:
        ids = set()
        for proxy_row in range(self.rowCount()):
            src_row = self.mapToSource(self.index(proxy_row, 0)).row()
            node    = self.sourceModel().get_node_data(src_row)
            if node:
                ids.add(node.get("id_string", ""))
        return ids
