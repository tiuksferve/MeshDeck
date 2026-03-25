"""
worker.py — MeshtasticWorker: comunicação TCP com o daemon meshtasticd,
subscrição pubsub, processamento de pacotes e emissão de sinais Qt.
Também contém _LogHandler para a ConsoleWindow.
"""
import logging
import functools
import base64
import time
from typing import Optional, Dict, Any, Set, List
from datetime import datetime

from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, QTimer, QMetaObject, Qt
from pubsub import pub
from meshtastic.tcp_interface import TCPInterface
from meshtastic import BROADCAST_ADDR, BROADCAST_NUM
from meshtastic.protobuf import mesh_pb2, portnums_pb2, admin_pb2

from constants import logger, _BROADCAST_NUMS, _is_broadcast
from i18n import tr
from dialogs import _LogHandler



class MeshtasticWorker(QObject):
    connection_changed      = pyqtSignal(bool)
    node_updated            = pyqtSignal(str, dict, object)
    error_occurred          = pyqtSignal(str)
    message_received        = pyqtSignal(int, str, str, object)
    channels_updated        = pyqtSignal(list)
    my_node_id_ready        = pyqtSignal(str)
    interface_ready         = pyqtSignal(object)
    dm_sent                 = pyqtSignal(str, str, bool, int)
    channel_message_sent    = pyqtSignal(int, str, int)
    message_status_updated  = pyqtSignal(int, str, str)
    traceroute_result       = pyqtSignal(list, list, str, str)
    local_node_ready        = pyqtSignal(str, str, str, bool, bool)
    nodes_batch             = pyqtSignal(list)
    nodedb_reset            = pyqtSignal()
    # FIX-6: sinal formalmente declarado
    neighbor_info_received  = pyqtSignal(str, list)   # (from_id, [(neighbor_id, snr), ...])
    # resultado do envio de posição: (sucesso, mensagem_para_ui)
    position_sent           = pyqtSignal(bool, str)
    # Pacote raw para métricas — emitido para TODOS os pacotes recebidos
    raw_packet_received     = pyqtSignal(dict)
    # Reconexão automática: (tentativa, delay_s)  |  tentativa=0 → reconectado
    reconnect_status        = pyqtSignal(int, int)

    NODE_POLL_INTERVAL_MS = 30_000   # 30s — safety-net para CM4; pubsub cobre updates em tempo real

    def __init__(self, hostname="localhost", port=4403, parent=None):
        super().__init__(parent)
        self.hostname   = hostname
        self.port       = port
        self.iface: Optional[TCPInterface] = None
        self._connected = False
        self._known_nodes: Set[str] = set()
        self._channels:    Dict[int, tuple] = {}
        self._poll_last_seen: Dict[str, int] = {}   # nid → lastHeard timestamp
        self._reconnect_attempts = 0
        self._reconnect_timer    = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_reconnect)
        # Watchdog: se após 12s de _do_reconnect _connected ainda for False,
        # o TCPInterface ficou pendurado sem lançar excepção nem evento pubsub.
        # Força nova tentativa via _schedule_reconnect.
        self._connect_watchdog   = QTimer(self)
        self._connect_watchdog.setSingleShot(True)
        self._connect_watchdog.timeout.connect(self._on_connect_watchdog)
        # ID do nó local — usado por _emit_node para evitar inserção na tabela
        self._local_id_known:  Optional[str] = None
        self._local_num_known: Optional[int] = None

    def start(self):
        if self.iface is not None:
            return
        try:
            logger.info(f"Conectando a {self.hostname}:{self.port} …")
            self._known_nodes.clear()
            self._poll_last_seen.clear()
            self._reconnect_attempts = 0
            pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
            pub.subscribe(self._on_connection_lost,        "meshtastic.connection.lost")
            pub.subscribe(self._on_node_updated,           "meshtastic.node.updated")
            pub.subscribe(self._on_text_message,           "meshtastic.receive.text")
            pub.subscribe(self._on_receive_user,           "meshtastic.receive.user")
            pub.subscribe(self._on_packet_received,        "meshtastic.receive")
            self.iface = TCPInterface(self.hostname, self.port)
        except Exception as e:
            self.error_occurred.emit(
                f"Falha ao criar interface TCP ({self.hostname}:{self.port}): {e}"
            )
            logger.exception("Erro ao iniciar worker")

    def stop(self):
        self._reconnect_timer.stop()
        self._connect_watchdog.stop()
        for topic, handler in [
            ("meshtastic.connection.established", self._on_connection_established),
            ("meshtastic.connection.lost",        self._on_connection_lost),
            ("meshtastic.node.updated",           self._on_node_updated),
            ("meshtastic.receive.text",           self._on_text_message),
            ("meshtastic.receive.user",           self._on_receive_user),
            ("meshtastic.receive",                self._on_packet_received),
        ]:
            try:
                pub.unsubscribe(handler, topic)
            except Exception:
                pass
        self._known_nodes.clear()
        if self.iface:
            try:
                self.iface.close()
            except Exception as e:
                logger.error(f"Erro ao fechar: {e}")
            finally:
                self.iface      = None
                self._connected = False
                self.connection_changed.emit(False)

    def _on_connection_lost(self, interface=None):
        """Chamado pela thread interna do TCPInterface — delega para thread Qt."""
        logger.warning("Ligação perdida — a delegar para thread Qt…")
        QMetaObject.invokeMethod(self, "_handle_connection_lost", Qt.QueuedConnection)

    @pyqtSlot()
    def _handle_connection_lost(self):
        """Executado na thread Qt — seguro para QTimer e sinais."""
        if self._connected:
            self._connected = False
            self.connection_changed.emit(False)
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        """Backoff exponencial: 15s → 30s → 60s → 120s (máx)."""
        delays = [15_000, 30_000, 60_000, 120_000]
        idx    = min(self._reconnect_attempts, len(delays) - 1)
        delay  = delays[idx]
        self._reconnect_attempts += 1
        logger.info(f"Reconexão #{self._reconnect_attempts} em {delay//1000}s…")
        self.reconnect_status.emit(self._reconnect_attempts, delay // 1000)
        self._reconnect_timer.start(delay)

    def _do_reconnect(self):
        """Tenta fechar a interface antiga e criar uma nova.
        Re-subscreve os handlers pubsub antes de criar o TCPInterface.
        Após criar a interface arranca um watchdog de 12s: se _connected
        ainda for False no timeout, o TCPInterface ficou pendurado sem
        lançar excepção nem disparar o evento pubsub — forçamos nova tentativa.
        """
        if self._connected:
            return
        try:
            if self.iface:
                try:
                    self.iface.close()
                except Exception:
                    pass
                self.iface = None
            self._known_nodes.clear()
            self._poll_last_seen.clear()
            # Re-subscreve handlers pubsub
            for topic, handler in [
                ("meshtastic.connection.established", self._on_connection_established),
                ("meshtastic.connection.lost",        self._on_connection_lost),
                ("meshtastic.node.updated",           self._on_node_updated),
                ("meshtastic.receive.text",           self._on_text_message),
                ("meshtastic.receive.user",           self._on_receive_user),
                ("meshtastic.receive",                self._on_packet_received),
            ]:
                try:
                    pub.unsubscribe(handler, topic)
                except Exception:
                    pass
                pub.subscribe(handler, topic)
            logger.info(f"A reconectar a {self.hostname}:{self.port}…")
            self.iface = TCPInterface(self.hostname, self.port)
            # Watchdog: 12s para o evento pubsub chegar; caso contrário tenta de novo
            self._connect_watchdog.start(12_000)
        except Exception as e:
            logger.warning(f"Reconexão falhada: {e}")
            self._connect_watchdog.stop()
            self._schedule_reconnect()

    def _on_connect_watchdog(self):
        """Chamado 12s após _do_reconnect se _connected ainda for False.
        O TCPInterface criou o socket mas o handshake Meshtastic não completou
        (daemon lento, rede instável). Fecha e agenda nova tentativa.
        """
        if self._connected:
            return
        logger.warning("Watchdog: sem conexão após 12s — a reagendar tentativa…")
        if self.iface:
            try:
                self.iface.close()
            except Exception:
                pass
            self.iface = None
        self._schedule_reconnect()

    def send_message(self, channel_index: int, text: str):
        if not self.iface or not self._connected:
            self.error_occurred.emit("Não conectado — impossível enviar mensagem.")
            return
        try:
            result = self.iface.sendText(text, channelIndex=channel_index, wantAck=True)
            pkt_id = result.id if result and hasattr(result, 'id') else 0
            logger.info(f"Canal {channel_index} msg enviada (pkt_id={pkt_id:#010x})")
            self.channel_message_sent.emit(channel_index, text, pkt_id)
        except Exception as e:
            self.error_occurred.emit(f"Erro ao enviar mensagem: {e}")

    def reset_nodedb(self):
        if not self.iface or not self._connected:
            self.error_occurred.emit("Não conectado — impossível resetar NodeDB.")
            return
        try:
            local_node = self.iface.localNode
            if hasattr(local_node, 'resetNodeDb'):
                local_node.resetNodeDb()
                logger.info("NodeDB resetado via localNode.resetNodeDb()")
            else:
                p = admin_pb2.AdminMessage()
                p.nodedb_reset = 1
                self.iface.localNode._sendAdmin(p)
                logger.info("NodeDB resetado via admin packet")
            self.nodedb_reset.emit()
        except Exception as e:
            logger.error(f"Erro ao resetar NodeDB: {e}", exc_info=True)
            self.error_occurred.emit(f"Erro ao resetar NodeDB: {e}")

    def send_traceroute(self, dest_id: str, hop_limit: int = 3):
        if not self.iface or not self._connected:
            self.error_occurred.emit("Não conectado — impossível enviar traceroute.")
            return
        try:
            r = mesh_pb2.RouteDiscovery()
            self.iface.sendData(
                r,
                destinationId=dest_id,
                portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                wantResponse=True,
                hopLimit=hop_limit,
                channelIndex=0,
            )
            logger.info(f"Traceroute enviado para {dest_id} (hopLimit={hop_limit})")
        except Exception as e:
            logger.error(f"Erro ao enviar traceroute: {e}", exc_info=True)
            self.error_occurred.emit(f"Erro ao enviar traceroute: {e}")

    def send_position(self):
        """
        Envia a posição do nó local para a rede.

        Estratégia (por ordem de preferência):
          1. localNode.setPosition() — a biblioteca lê lat/lon da config interna
             e faz o broadcast directamente via firmware.
          2. Fallback manual: lê latitudeI/longitudeI do nodesByNum e constrói
             o pacote POSITION_APP à mão.

        Em ambos os casos emite position_sent(True/False, mensagem) para que
        _on_send_position possa actualizar a statusBar *apenas* após saber
        o resultado real.
        """
        if not self.iface or not self._connected:
            self.position_sent.emit(False, tr("Não conectado."))
            return
        try:

            local_node = self.iface.localNode
            local_num  = local_node.nodeNum

            # ── Tentativa 1: API de alto nível da biblioteca ──────────────
            # localNode.setPosition() envia directamente sem precisar de
            # ler coordenadas da cache TCP — funciona mesmo que nodesByNum
            # ainda não tenha recebido a posição do firmware.
            sent_via_api = False
            try:
                local_node.setPosition(
                    lat=None, lon=None, alt=None,
                    # Sem argumentos → firmware usa a posição interna (GPS ou fixa)
                )
                sent_via_api = True
                logger.info("send_position: enviado via localNode.setPosition()")
                self.position_sent.emit(True, tr("📍 Posição enviada para a rede (via firmware)."))
                return
            except TypeError:
                # Versões mais antigas da lib exigem lat/lon explícitos
                pass
            except Exception as api_err:
                logger.debug(f"send_position: setPosition() falhou ({api_err}), tentando fallback")

            # ── Tentativa 2: lê coordenadas da cache e envia manualmente ──
            # Procura em nodesByNum (cache do daemon) e também na config fixa
            pos_data: dict = {}
            if hasattr(self.iface, 'nodesByNum'):
                pos_data = self.iface.nodesByNum.get(local_num, {}).get('position', {})

            lat_i = pos_data.get('latitudeI')
            lon_i = pos_data.get('longitudeI')

            # Tenta também a posição fixa na configuração do localNode
            if not lat_i or not lon_i:
                try:
                    pos_cfg = getattr(local_node, 'localConfig', None)
                    if pos_cfg:
                        pos_cfg = getattr(pos_cfg, 'position', None)
                    if pos_cfg:
                        fixed_lat = getattr(pos_cfg, 'fixed_lat',  None)
                        fixed_lon = getattr(pos_cfg, 'fixed_lon',  None)
                        fixed_alt = getattr(pos_cfg, 'fixed_alt',  None)
                        if fixed_lat and fixed_lon:
                            # Converte graus → inteiros × 1e7 se necessário
                            lat_i = int(fixed_lat * 1e7) if isinstance(fixed_lat, float) else int(fixed_lat)
                            lon_i = int(fixed_lon * 1e7) if isinstance(fixed_lon, float) else int(fixed_lon)
                            if fixed_alt:
                                pos_data['altitude'] = int(fixed_alt)
                            logger.info(f"send_position: usando posição fixa da config ({lat_i/1e7:.6f}, {lon_i/1e7:.6f})")
                except Exception as cfg_err:
                    logger.debug(f"send_position: não leu posição fixa da config: {cfg_err}")

            if not lat_i or not lon_i:
                msg = tr("pos_no_coords_msg")
                logger.warning("send_position: sem coordenadas — abortar")
                self.position_sent.emit(False, msg)
                return

            pos             = mesh_pb2.Position()
            pos.latitude_i  = int(lat_i)
            pos.longitude_i = int(lon_i)
            alt = pos_data.get('altitude')
            if alt:
                pos.altitude = int(alt)
            pos.time      = int(time.time())
            pos.timestamp = pos.time

            self.iface.sendData(
                pos,
                destinationId=BROADCAST_NUM,
                portNum=portnums_pb2.PortNum.POSITION_APP,
                wantAck=False,
                wantResponse=False,
                channelIndex=0,
            )
            msg = tr("📍 Posição enviada ({lat}, {lon}).", lat=f"{lat_i/1e7:.6f}", lon=f"{lon_i/1e7:.6f}")
            logger.info(msg)
            self.position_sent.emit(True, msg)

        except Exception as e:
            logger.error(f"Erro ao enviar posição: {e}", exc_info=True)
            self.position_sent.emit(False, tr("Erro ao enviar posição: {msg}", msg=str(e)))

    def send_node_info(self):
        if not self.iface or not self._connected:
            return
        try:
            local_node = self.iface.localNode
            if not local_node:
                self.error_occurred.emit("Nó local não disponível.")
                return
            local_num  = local_node.nodeNum
            me         = (self.iface.nodesByNum.get(local_num, {})
                          if hasattr(self.iface, 'nodesByNum') else {})
            user_data  = me.get('user', {})
            long_name  = user_data.get('longName', '')
            short_name = user_data.get('shortName', '')
            # setOwner reenvia o NODEINFO_APP broadcast com os dados actuais
            local_node.setOwner(long_name=long_name, short_name=short_name)
            logger.info(f"send_node_info: via setOwner ('{long_name}' / '{short_name}')")
        except Exception as e:
            logger.error(f"Erro ao enviar NODEINFO: {e}", exc_info=True)
            self.error_occurred.emit(f"Erro ao enviar Info do Nó: {e}")

    def send_direct_message(self, dest_id: str, text: str):
        if not self.iface or not self._connected:
            self.error_occurred.emit("Não conectado — impossível enviar DM.")
            return
        try:

            dest_num: Optional[int] = None
            if dest_id.startswith('!'):
                try:
                    dest_num = int(dest_id[1:], 16) & 0xFFFFFFFF
                except ValueError:
                    pass

            dest_node = None
            if dest_num is not None and hasattr(self.iface, 'nodesByNum'):
                dest_node = self.iface.nodesByNum.get(dest_num)
            if dest_node is None and hasattr(self.iface, 'nodes'):
                dest_node = self.iface.nodes.get(dest_id)

            has_pubkey = bool(dest_node and dest_node.get('user', {}).get('publicKey', ''))

            if has_pubkey:
                try:
                    result = self.iface.sendData(
                        text.encode("utf-8"),
                        destinationId=dest_id,
                        portNum=portnums_pb2.PortNum.TEXT_MESSAGE_APP,
                        wantAck=True,
                        channelIndex=0,
                        pkiEncrypted=True,
                    )
                    pkt_id = result.id if result and hasattr(result, 'id') else 0
                    logger.info(f"DM PKI enviado para {dest_id} (pkt_id={pkt_id:#010x})")
                    self.dm_sent.emit(dest_id, text, True, pkt_id)
                    return
                except Exception as pki_err:
                    err_str = str(pki_err)
                    if 'PKI_UNKNOWN_PUBKEY' in err_str or 'unknown' in err_str.lower():
                        # FIX-3: mensagem de erro simplificada
                        logger.warning(f"DM PKI falhou para {dest_id}: {pki_err}")
                        self.error_occurred.emit(
                            f"Não foi possível enviar DM encriptado (PKI) para {dest_id}.\n\n"
                            "O rádio ainda não tem a chave pública deste nó.\n"
                            "Aguarde que ele se anuncie na rede (pode demorar alguns minutos)\n"
                            "ou clique em  📡 Nó → Enviar Info do Nó  para anunciar a sua chave."
                        )
                        return
                    raise

            # Fallback PSK
            logger.info(f"DM para {dest_id}: sem publicKey → PSK canal 0")
            result = self.iface.sendText(
                text, destinationId=dest_id, wantAck=True, channelIndex=0,
            )
            pkt_id = result.id if result and hasattr(result, 'id') else 0
            self.dm_sent.emit(dest_id, text, False, pkt_id)

        except Exception as e:
            logger.error(f"Erro ao enviar DM para {dest_id}: {e}", exc_info=True)
            self.error_occurred.emit(f"Erro ao enviar DM: {e}")

    def _on_text_message(self, packet, interface=None):
        try:
            from_id = packet.get('fromId', '')
            if not from_id:
                from_num = packet.get('from')
                if from_num:
                    if self.iface and hasattr(self.iface, 'nodesByNum'):
                        node    = self.iface.nodesByNum.get(int(from_num), {})
                        from_id = node.get('user', {}).get('id', '')
                    if not from_id and self.iface and hasattr(self.iface, 'nodes'):
                        node    = self.iface.nodes.get(from_num, {})
                        from_id = node.get('user', {}).get('id', '')
                    if not from_id:
                        from_id = f"!{int(from_num):08x}"
            if not from_id:
                return

            text = packet.get('decoded', {}).get('text', '')
            if not text:
                return

            pki_encrypted = bool(packet.get('pkiEncrypted', False))
            channel       = int(packet.get('channel', 0))
            to_raw        = packet.get('to', 0xFFFFFFFF)
            try:
                to_num = int(to_raw) & 0xFFFFFFFF
            except (TypeError, ValueError):
                to_num = 0xFFFFFFFF

            logger.info(
                f"MSG: from={from_id} to_raw={to_raw!r} to_num=0x{to_num:08x} "
                f"ch={channel} pki={pki_encrypted} txt={text[:40]!r}"
            )

            to_id = packet.get('toId', '')
            if not to_id and not _is_broadcast(to_num):
                if self.iface and hasattr(self.iface, 'nodesByNum'):
                    to_node = self.iface.nodesByNum.get(to_num, {})
                    to_id   = to_node.get('user', {}).get('id', '')
                if not to_id:
                    to_id = f"!{to_num:08x}"

            if pki_encrypted:
                pk_raw = packet.get('publicKey')
                if pk_raw and self.iface:
                    try:
                        from_num_int = packet.get('from')
                        if from_num_int:
                            from_num_int = int(from_num_int)
                            node_entry   = None
                            if hasattr(self.iface, 'nodesByNum'):
                                node_entry = self.iface.nodesByNum.get(from_num_int)
                            if node_entry is None and hasattr(self.iface, 'nodes'):
                                node_entry = self.iface.nodes.get(from_id)
                            if node_entry and 'user' in node_entry:
                                if isinstance(pk_raw, bytes):
                                    node_entry['user']['publicKey'] = base64.b64encode(pk_raw).decode()
                                else:
                                    node_entry['user']['publicKey'] = str(pk_raw)
                    except Exception as e:
                        logger.debug(f"Não actualizou publicKey de {from_id}: {e}")

            _rx = packet.get('rxTime') or 0
            pkt_safe = {
                'fromId':       from_id,
                'toId':         to_id,
                'to':           to_num,
                'channel':      channel,
                'rxTime':       _rx if _rx else int(time.time()),
                'viaMqtt':      packet.get('viaMqtt', False),
                'pkiEncrypted': pki_encrypted,
                'decoded':      {'text': text},
                'hopsAway':     None,
            }
            # Tenta obter hopsAway do NodeDB (mais fiável que hopLimit do pacote)
            try:
                from_num_int = packet.get('from')
                if from_num_int and self.iface:
                    nd = (getattr(self.iface, 'nodesByNum', {}) or {}).get(from_num_int, {})
                    ha = nd.get('hopsAway')
                    if ha is not None:
                        pkt_safe['hopsAway'] = ha
                    elif packet.get('hopStart') is not None and packet.get('hopLimit') is not None:
                        pkt_safe['hopsAway'] = int(packet['hopStart']) - int(packet['hopLimit'])
            except Exception:
                pass

            if pki_encrypted:
                pk_raw = packet.get('publicKey')
                if pk_raw and from_id:
                    try:
                        pk_b64 = base64.b64encode(pk_raw).decode() if isinstance(pk_raw, bytes) else str(pk_raw)
                        self.node_updated.emit(from_id, {'public_key': pk_b64}, None)
                    except Exception:
                        pass

            self.message_received.emit(channel, from_id, text, pkt_safe)
        except Exception as e:
            logger.error(f"Erro no handler de texto: {e}", exc_info=True)

    def _sync_nodedb(self) -> int:
        if not self.iface or not self._connected:
            return 0

        nodes_src = getattr(self.iface, 'nodesByNum', None) or {}
        if not nodes_src:
            nodes_str = getattr(self.iface, 'nodes', None) or {}
            nodes_src = {}
            for k, v in nodes_str.items():
                try:
                    nodes_src[int(str(k).lstrip('!'), 16)] = v
                except Exception:
                    pass

        deduped: Dict[int, dict] = {}
        for raw_key, node in nodes_src.items():
            if not isinstance(node, dict):
                continue
            try:
                num = int(node.get('num') or raw_key)
            except (TypeError, ValueError):
                continue
            if num not in deduped:
                deduped[num] = node
            else:
                if (node.get('user', {}).get('publicKey') and
                        not deduped[num].get('user', {}).get('publicKey')):
                    deduped[num] = node

        if deduped:
            self.nodes_batch.emit(list(deduped.items()))
        return len(deduped)

    def _poll_nodedb(self):
        """
        Safety-net polling — sincroniza o NodeDB completo a cada 30s.
        Equivalente ao comportamento das apps iOS/Android: lê iface.nodesByNum
        e emite updates para todos os nós. Apanha nós novos e actualizações
        que a biblioteca não emitiu via pubsub (frequente com meshtasticd via TCP).
        """
        if not self.iface or not self._connected:
            return
        try:
            nodes_src = getattr(self.iface, 'nodesByNum', None) or {}
            count = 0
            for raw_key, node in nodes_src.items():
                if not isinstance(node, dict):
                    continue
                self._emit_node(node.get('num') or raw_key, node)
                count += 1
            logger.debug(f"Poll NodeDB: {count} nós sincronizados")
        except Exception as e:
            logger.debug(f"Erro no poll NodeDB: {e}")

    def _on_connection_established(self, interface=None):
        """Chamado pela thread interna do TCPInterface — delega para thread Qt."""
        logger.info("Conexão estabelecida — a delegar para thread Qt…")
        QMetaObject.invokeMethod(self, "_handle_connection_established", Qt.QueuedConnection)

    @pyqtSlot()
    def _handle_connection_established(self):
        """Executado na thread Qt — seguro para QTimer e sinais."""
        self._connected          = True
        self._reconnect_attempts = 0
        self._reconnect_timer.stop()
        self._connect_watchdog.stop()
        self._known_nodes.clear()
        self._poll_last_seen.clear()
        self.reconnect_status.emit(0, 0)   # 0 = reconectado com sucesso
        self.connection_changed.emit(True)

        # FIX-4: bloqueia inserção do nó local ANTES do batch inicial
        try:
            if self.iface and self.iface.localNode:
                local_num  = self.iface.localNode.nodeNum
                local_id   = f"!{int(local_num):08x}" if local_num else None
                logger.info(f"Nó local: num={local_num} id={local_id}")
                # Emite sinal auxiliar para que MainWindow configure os modelos imediatamente
                if local_id:
                    self._local_num_known = local_num
                    self._local_id_known  = local_id
                    self.my_node_id_ready.emit(local_id)   # bloqueia proxy antes do batch
        except Exception as e:
            logger.warning(f"Não foi possível determinar nodeNum local: {e}")

        # Carga inicial completa
        try:
            loaded = self._sync_nodedb()
            logger.info(f"NodeDB inicial: {loaded} nós carregados")
        except Exception as e:
            logger.error(f"Erro ao carregar NodeDB inicial: {e}", exc_info=True)

        # FIX-6: NeighborInfo inicial do NodeDB
        try:
            nodes_src = getattr(self.iface, 'nodesByNum', None) or {}
            for raw_key, node in nodes_src.items():
                if not isinstance(node, dict):
                    continue
                neighbors_raw = node.get('neighborInfo', {}).get('neighbors', [])
                if not neighbors_raw:
                    continue
                try:
                    num     = int(node.get('num') or raw_key)
                    from_id = node.get('user', {}).get('id') or f"!{num:08x}"
                except (TypeError, ValueError):
                    continue
                neighbors = []
                for nb in neighbors_raw:
                    nb_num = nb.get('nodeId') or nb.get('node_id')
                    if nb_num:
                        neighbors.append((f"!{int(nb_num):08x}", float(nb.get('snr', 0.0))))
                if neighbors:
                    self.neighbor_info_received.emit(from_id, neighbors)
        except Exception as e:
            logger.debug(f"Erro ao carregar NeighborInfo inicial: {e}")

        # Metadados do nó local
        try:
            my_id = self._get_my_node_id()
            if my_id:
                self.my_node_id_ready.emit(my_id)

            local_num  = self.iface.localNode.nodeNum if self.iface and self.iface.localNode else None
            local_user = {}
            if local_num and hasattr(self.iface, "nodesByNum"):
                local_user = self.iface.nodesByNum.get(local_num, {}).get("user", {})
            if not local_user and my_id and hasattr(self.iface, "nodes"):
                local_user = self.iface.nodes.get(my_id, {}).get("user", {})
            ln  = local_user.get("longName", "")
            sn  = local_user.get("shortName", "")
            nid = local_user.get("id", my_id or "")

            gps_enabled  = False
            has_position = False
            try:
                local_node_obj = self.iface.localNode if self.iface else None
                if local_node_obj:
                    pos_cfg = getattr(local_node_obj, 'localConfig', None)
                    if pos_cfg:
                        pos_cfg = getattr(pos_cfg, 'position', None)
                    if pos_cfg:
                        gps_mode    = getattr(pos_cfg, 'gps_mode', None)
                        gps_enabled = (gps_mode == 1) if gps_mode is not None else False
            except Exception:
                pass
            try:
                if local_num and hasattr(self.iface, 'nodesByNum'):
                    pos          = self.iface.nodesByNum.get(local_num, {}).get('position', {})
                    has_position = bool(pos and pos.get('latitudeI') and pos.get('longitudeI'))
            except Exception:
                pass

            self.local_node_ready.emit(ln, sn, nid, gps_enabled, has_position)
        except Exception as e:
            logger.error(f"Erro ao obter metadados locais: {e}")

        self.interface_ready.emit(self.iface)
        self._attempt_load_channels(retry_count=0)

    def _get_my_node_id(self):
        try:
            if not self.iface:
                return None
            my_info = self.iface.getMyNodeInfo()
            if my_info and 'user' in my_info:
                return my_info['user'].get('id')
            for node_id, node in self.iface.nodes.items():
                if node.get('user', {}).get('id') and node.get('isMe'):
                    return node['user']['id']
        except Exception as e:
            logger.error(f"Erro ao obter ID local: {e}")
        return None

    def _attempt_load_channels(self, retry_count=0):
        if not self._load_channels_from_node() and retry_count < 5:
            QTimer.singleShot(2000,
                              functools.partial(self._attempt_load_channels, retry_count + 1))

    def _on_node_updated(self, node, interface=None):
        if not isinstance(node, dict):
            return
        num = node.get('num')
        nid = node.get('user', {}).get('id')
        if not nid and num:
            try:
                nid = f"!{int(num):08x}"
            except (TypeError, ValueError):
                return
        if not nid:
            return
        self._emit_node(num, node)

    def _on_receive_user(self, packet, interface=None):
        """
        Handler dedicado para meshtastic.receive.user (NODEINFO_APP).
        A biblioteca publica este tópico específico com o protobuf já decodificado.
        Garante que publicKey e hwModel são extraídos mesmo antes do batch completo.
        """
        try:
            from_id_num    = packet.get('from')
            from_id_string = packet.get('fromId', '')
            if not from_id_string and from_id_num:
                try:
                    from_id_string = f"!{int(from_id_num):08x}"
                except (TypeError, ValueError):
                    return
            if not from_id_string:
                return

            decoded  = packet.get('decoded') or {}
            user     = decoded.get('user', {})
            if not user:
                return

            updates = {
                'long_name':  user.get('longName', ''),
                'short_name': user.get('shortName', ''),
                'hw_model':   user.get('hwModel', ''),
                'id_num':     from_id_num,
            }
            # publicKey — tenta várias representações
            pk = user.get('publicKey') or user.get('public_key')
            if pk:
                try:
                    _b64 = base64
                    if isinstance(pk, bytes):
                        updates['public_key'] = base64.b64encode(pk).decode()
                    else:
                        updates['public_key'] = str(pk)
                except Exception:
                    pass

            for key, pkt_key in (('snr', 'rxSnr'), ('via_mqtt', 'viaMqtt')):
                val = packet.get(pkt_key)
                if val is not None:
                    updates[key] = val

            rx_time = packet.get('rxTime')
            updates['last_heard'] = (datetime.fromtimestamp(int(rx_time))
                                     if rx_time else datetime.now())

            updates['last_packet_type'] = 'NODEINFO_APP'
            self.node_updated.emit(from_id_string, updates, packet)
        except Exception as e:
            logger.debug(f"Erro em _on_receive_user: {e}")

    def _on_packet_received(self, packet, interface=None):
        try:
            from_id_num    = packet.get('from')
            from_id_string = packet.get('fromId')
            if not from_id_string and from_id_num and self.iface:
                from_id_string = (self.iface.nodes.get(from_id_num, {})
                                  .get('user', {}).get('id'))

            # Emite o pacote raw para métricas com fromId resolvido
            # (feito após resolução de ID para garantir fromId correcto)
            try:
                pkt_copy = dict(packet)
                if from_id_string and not pkt_copy.get('fromId'):
                    pkt_copy['fromId'] = from_id_string
                self.raw_packet_received.emit(pkt_copy)
            except Exception:
                pass

            if not from_id_string:
                return

            decoded = packet.get('decoded') or {}
            portnum = decoded.get('portnum')

            if portnum != 'ROUTING_APP':
                if self.iface and self.iface.localNode:
                    local_num = self.iface.localNode.nodeNum
                    is_local  = False
                    if from_id_num is not None and local_num is not None:
                        try:
                            is_local = int(from_id_num) == int(local_num)
                        except (TypeError, ValueError):
                            pass
                    if not is_local and local_num is not None and from_id_string:
                        try:
                            is_local = from_id_string.lower() == f'!{int(local_num):08x}'
                        except (TypeError, ValueError):
                            pass
                    if is_local:
                        logger.debug(f'Loopback ignorado: portnum={portnum} from={from_id_string}')
                        return

            if portnum == 'TEXT_MESSAGE_APP':
                # Actualiza lastHeard/snr/last_packet_type do remetente
                _txt_updates: Dict[str, Any] = {}
                for key, pkt_key in (('snr', 'rxSnr'), ('via_mqtt', 'viaMqtt')):
                    val = packet.get(pkt_key)
                    if val is not None:
                        _txt_updates[key] = val
                if self.iface:
                    _num = packet.get('from')
                    if _num:
                        _nd = (getattr(self.iface, 'nodesByNum', {}) or {}).get(_num, {})
                        _ha = _nd.get('hopsAway')
                        if _ha is not None:
                            _txt_updates['hops_away'] = _ha
                rx_time = packet.get('rxTime')
                _txt_updates['last_heard'] = (datetime.fromtimestamp(int(rx_time))
                                              if rx_time else datetime.now())
                _txt_updates['last_packet_type'] = 'TEXT_MESSAGE_APP'
                if 'id_num' not in _txt_updates and from_id_num:
                    _txt_updates['id_num'] = from_id_num
                if _txt_updates:
                    self.node_updated.emit(from_id_string, _txt_updates, packet)
                return

            if portnum == 'ROUTING_APP':
                try:
                    routing    = decoded.get('routing', {})
                    request_id = decoded.get('requestId', 0)
                    if request_id:
                        error_reason = routing.get('errorReason', 'NONE')
                        if error_reason and error_reason != 'NONE':
                            status = 'nak'
                        else:
                            from_num  = packet.get('from')
                            local_num = self.iface.localNode.nodeNum if self.iface else None
                            if from_num and local_num and int(from_num) == int(local_num):
                                status = 'ack_implicit'
                            else:
                                status = 'ack'
                        self.message_status_updated.emit(request_id, status, error_reason or 'NONE')
                except Exception as e:
                    logger.debug(f"Erro ao processar ROUTING_APP: {e}")
                # Actualiza last_heard e last_packet_type do remetente
                _rout_updates: Dict[str, Any] = {'last_packet_type': 'ROUTING_APP'}
                if from_id_num:
                    _rout_updates['id_num'] = from_id_num
                for key, pkt_key in (('snr', 'rxSnr'), ('via_mqtt', 'viaMqtt')):
                    val = packet.get(pkt_key)
                    if val is not None:
                        _rout_updates[key] = val
                rx_time = packet.get('rxTime')
                _rout_updates['last_heard'] = (datetime.fromtimestamp(int(rx_time))
                                               if rx_time else datetime.now())
                if from_id_string:
                    self.node_updated.emit(from_id_string, _rout_updates, packet)
                return

            if portnum == 'TRACEROUTE_APP':
                try:
                    want_response = packet.get('wantResponse', False)
                    if want_response:
                        return

                    tr = decoded.get('traceroute', {})
                    if not tr:
                        return

                    origin_num = packet.get('to')
                    dest_num   = packet.get('from')

                    def num_to_id(n):
                        try:
                            ni = int(n)
                            if ni == 0 or ni == 0xFFFFFFFF:
                                return None
                            if self.iface and hasattr(self.iface, 'nodesByNum'):
                                uid = self.iface.nodesByNum.get(ni, {}).get('user', {}).get('id', '')
                                if uid:
                                    return uid
                            return f"!{ni:08x}"
                        except (TypeError, ValueError):
                            return None

                    forward_edges = []
                    back_edges    = []

                    route_toward = [r for r in (tr.get('route') or []) if r]
                    snr_toward   = list(tr.get('snrTowards') or tr.get('snrToward') or [])
                    full_toward  = [origin_num] + route_toward + [dest_num]
                    for i in range(len(full_toward) - 1):
                        a_id = num_to_id(full_toward[i])
                        b_id = num_to_id(full_toward[i + 1])
                        if not a_id or not b_id:
                            continue
                        snr = float(snr_toward[i]) / 4.0 if i < len(snr_toward) else 0.0
                        forward_edges.append((a_id, b_id, snr))

                    route_back = [r for r in (tr.get('routeBack') or []) if r]
                    snr_back   = list(tr.get('snrBack') or [])
                    full_back  = [dest_num] + route_back + [origin_num]
                    for i in range(len(full_back) - 1):
                        a_id = num_to_id(full_back[i])
                        b_id = num_to_id(full_back[i + 1])
                        if not a_id or not b_id:
                            continue
                        snr = float(snr_back[i]) / 4.0 if i < len(snr_back) else 0.0
                        back_edges.append((a_id, b_id, snr))

                    if forward_edges or back_edges:
                        origin_str = num_to_id(origin_num) or '?'
                        dest_str   = num_to_id(dest_num) or '?'
                        self.traceroute_result.emit(forward_edges, back_edges, origin_str, dest_str)
                except Exception as e:
                    logger.debug(f"Erro ao processar TRACEROUTE_APP: {e}", exc_info=True)
                # Actualiza last_heard e last_packet_type do remetente
                _tr_updates: Dict[str, Any] = {'last_packet_type': 'TRACEROUTE_APP'}
                if from_id_num:
                    _tr_updates['id_num'] = from_id_num
                for key, pkt_key in (('snr', 'rxSnr'), ('via_mqtt', 'viaMqtt')):
                    val = packet.get(pkt_key)
                    if val is not None:
                        _tr_updates[key] = val
                rx_time = packet.get('rxTime')
                _tr_updates['last_heard'] = (datetime.fromtimestamp(int(rx_time))
                                             if rx_time else datetime.now())
                if from_id_string:
                    self.node_updated.emit(from_id_string, _tr_updates, packet)
                return

            # FIX-2: processa NEIGHBORINFO_APP em tempo real
            if portnum == 'NEIGHBORINFO_APP':
                try:
                    ni_data   = decoded.get('neighborinfo', {})
                    if not ni_data:
                        ni_data = decoded.get('neighborInfo', {})
                    neighbors_raw = ni_data.get('neighbors', [])
                    if neighbors_raw:
                        neighbors = []
                        for nb in neighbors_raw:
                            nb_num = nb.get('nodeId') or nb.get('node_id')
                            if nb_num:
                                neighbors.append((f"!{int(nb_num):08x}",
                                                  float(nb.get('snr', 0.0))))
                        if neighbors:
                            self.neighbor_info_received.emit(from_id_string, neighbors)
                            logger.info(
                                f"NeighborInfo de {from_id_string}: "
                                f"{len(neighbors)} vizinhos"
                            )
                except Exception as e:
                    logger.debug(f"Erro ao processar NEIGHBORINFO_APP: {e}")
                # Continua para o processamento genérico de updates

            updates: Dict[str, Any] = {}

            if portnum == 'NODEINFO_APP':
                user = decoded.get('user', {})
                updates.update({
                    'long_name':  user.get('longName', ''),
                    'short_name': user.get('shortName', ''),
                    'hw_model':   user.get('hwModel', ''),
                    'id_num':     from_id_num,
                })
                # Extrai publicKey — necessário para DM PKI
                pk = user.get('publicKey') or user.get('public_key')
                if pk:
                    try:
                        updates['public_key'] = (base64.b64encode(pk).decode()
                                                 if isinstance(pk, bytes) else str(pk))
                    except Exception:
                        pass
                self._extract_position(decoded.get('position', {}), updates)
                self._known_nodes.add(from_id_string)

            elif portnum == 'POSITION_APP':
                self._extract_position(decoded.get('position', {}), updates)
                if from_id_string not in self._known_nodes:
                    self._known_nodes.add(from_id_string)

            elif portnum == 'TELEMETRY_APP':
                tel = decoded.get('telemetry', {})
                dm  = tel.get('deviceMetrics', {})
                if dm:
                    batt = dm.get('batteryLevel')
                    if batt is not None:
                        updates['battery_level'] = batt
                    ch_util = dm.get('channelUtilization')
                    if ch_util is not None:
                        updates['channel_utilization'] = float(ch_util)
                    air_tx = dm.get('airUtilTx')
                    if air_tx is not None:
                        updates['air_util_tx'] = float(air_tx)
                    voltage = dm.get('voltage')
                    if voltage is not None:
                        updates['voltage'] = float(voltage)
                    uptm = dm.get('uptimeSeconds')
                    if uptm is not None:
                        updates['uptime_seconds'] = int(uptm)
                em = tel.get('environmentMetrics', {})
                if em:
                    for field in ('temperature', 'relativeHumidity', 'barometricPressure',
                                  'gasResistance', 'iaq', 'distance', 'lux',
                                  'windSpeed', 'windDirection', 'windGust',
                                  'radiation', 'rainfall1h', 'rainfall24h'):
                        val = em.get(field)
                        if val is not None:
                            updates[f'env_{field}'] = val
                pm = tel.get('powerMetrics', {})
                if pm:
                    for field in ('ch1Voltage', 'ch1Current', 'ch2Voltage', 'ch2Current',
                                  'ch3Voltage', 'ch3Current'):
                        val = pm.get(field)
                        if val is not None:
                            updates[f'pwr_{field}'] = val
                hm = tel.get('healthMetrics', {})
                if hm:
                    for field in ('heartBpm', 'spO2', 'temperature'):
                        val = hm.get(field)
                        if val is not None:
                            updates[f'health_{field}'] = val

            for key, pkt_key in (('snr', 'rxSnr'), ('via_mqtt', 'viaMqtt')):
                val = packet.get(pkt_key)
                if val is not None:
                    updates[key] = val

            # hopsAway vem do NodeDB actualizado pela biblioteca (não do hopLimit do pacote)
            if self.iface and from_id_num:
                _nd = (getattr(self.iface, 'nodesByNum', {}) or {}).get(from_id_num, {})
                _ha = _nd.get('hopsAway')
                if _ha is not None:
                    updates['hops_away'] = _ha

            # last_heard: usa rxTime do pacote quando disponível; cai para now() como
            # fallback — rxTime pode ser 0 ou ausente em pacotes via TCP/daemon
            rx_time = packet.get('rxTime')
            if rx_time:
                try:
                    updates['last_heard'] = datetime.fromtimestamp(int(rx_time))
                except Exception:
                    updates['last_heard'] = datetime.now()
            else:
                # Sem rxTime — o pacote chegou agora via TCP, usa tempo actual
                updates['last_heard'] = datetime.now()

            updates['last_packet_type'] = portnum or 'desconhecido'
            if 'id_num' not in updates and from_id_num:
                updates['id_num'] = from_id_num

            # Para nós MQTT que não enviam NODEINFO/POSITION/TELEMETRY frequentemente,
            # garantimos que pelo menos o last_heard e via_mqtt são actualizados
            # mesmo que não haja mais nenhum campo relevante.
            if updates:
                self.node_updated.emit(from_id_string, updates, packet)

        except Exception as e:
            logger.error(f"Erro no processamento de pacote: {e}", exc_info=True)

    @staticmethod
    def _extract_position(pos: dict, updates: dict):
        lat_i = pos.get('latitudeI')
        lon_i = pos.get('longitudeI')
        if lat_i is not None: updates['latitude']  = lat_i / 1e7
        if lon_i is not None: updates['longitude'] = lon_i / 1e7
        alt = pos.get('altitude')
        if alt is not None:   updates['altitude']  = alt

    def _emit_node(self, node_id_num, node_obj: dict, packet=None):
        user = node_obj.get('user', {})
        nid  = user.get('id')
        if not nid:
            if node_id_num:
                try:
                    nid = f"!{int(node_id_num):08x}"
                except (TypeError, ValueError):
                    return
            else:
                return

        # Não emite o nó local — ele é gerido por local_node_ready
        if self._local_id_known and nid.lower() == self._local_id_known.lower():
            return
        if self._local_num_known is not None and node_id_num is not None:
            try:
                if int(node_id_num) == self._local_num_known:
                    return
            except (TypeError, ValueError):
                pass

        self._known_nodes.add(nid)
        # lastHeard=0 significa "desconhecido" — converte para None
        last_heard_raw = node_obj.get('lastHeard')
        last_heard = None
        if last_heard_raw:
            try:
                last_heard = datetime.fromtimestamp(int(last_heard_raw))
            except Exception:
                pass

        pos   = node_obj.get('position', {})
        lat_i = pos.get('latitudeI')
        lon_i = pos.get('longitudeI')

        data = {
            "id_num":        node_id_num,
            "long_name":     user.get('longName', ''),
            "short_name":    user.get('shortName', ''),
            "last_heard":    last_heard,
            "snr":           node_obj.get('snr'),
            "hops_away":     node_obj.get('hopsAway'),
            "via_mqtt":      node_obj.get('viaMqtt'),
            "latitude":      lat_i / 1e7 if lat_i is not None else None,
            "longitude":     lon_i / 1e7 if lon_i is not None else None,
            "altitude":      pos.get('altitude'),
            "battery_level": node_obj.get('deviceMetrics', {}).get('batteryLevel'),
            "hw_model":      user.get('hwModel', ''),
            "public_key":    user.get('publicKey', ''),
        }
        self.node_updated.emit(nid, data, packet)

    def _load_channels_from_node(self) -> bool:
        try:
            if not self.iface:
                return False
            local_node = self.iface.getNode("^local")
            if not local_node or not getattr(local_node, 'channels', None):
                return False

            self._channels.clear()
            for ch in local_node.channels:
                index    = ch.index
                raw_name = (ch.settings.name if ch.settings else "") or ""
                name     = raw_name if raw_name else ("Primary" if index == 0 else f"Canal {index}")
                psk      = ch.settings.psk if ch.settings else b""
                self._channels[index] = (name, psk)

            if not self._channels:
                return False

            self.channels_updated.emit([
                (idx, name, psk) for idx, (name, psk) in self._channels.items()
            ])
            return True
        except Exception as e:
            logger.error(f"Erro ao carregar canais: {e}", exc_info=True)
            return False
