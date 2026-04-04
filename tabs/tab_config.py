"""
tabs/tab_config.py — Aba de configuração do nó: ConfigTab, ChannelsTab,
_ChannelRow e todas as definições de campos de configuração Meshtastic.
"""
import re
import logging
from typing import Optional, Dict, List

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread, QObject
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QScrollArea, QStackedWidget, QLabel, QPushButton, QFrame,
    QFormLayout, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QTextEdit, QMessageBox, QSizePolicy
)
from PyQt5.QtGui import QColor

import os
from i18n import tr
import base64
from meshtastic.protobuf.channel_pb2 import Channel
from meshtastic.protobuf import admin_pb2
import google.protobuf.descriptor as descriptor_module

from constants import (
    logger, DARK_BG, PANEL_BG, BORDER_COLOR, ACCENT_GREEN, ACCENT_BLUE,
    ACCENT_ORANGE, ACCENT_RED, TEXT_PRIMARY, TEXT_MUTED, INPUT_BG
)

import threading as _threading


# ---------------------------------------------------------------------------
# Module-level worker classes — must be at module level for Qt meta-object
# system to work correctly with moveToThread / pyqtSignal across threads.
# Defining them inside methods breaks signal delivery in PyQt5.
# ---------------------------------------------------------------------------

class _ChannelSaveWorker(QObject):
    """Runs writeChannel calls in a background thread."""
    finished = pyqtSignal(int, list)   # saved_count, errors

    def __init__(self, iface, channels):
        super().__init__()
        self._iface    = iface
        self._channels = channels

    def run(self):
        errors = []
        saved  = 0
        try:
            node            = self._iface.localNode
            present_indices = set()
            for ch in self._channels:
                try:
                    node.writeChannel(ch.index)
                    present_indices.add(ch.index)
                    saved += 1
                    logger.debug(f"writeChannel({ch.index}) OK")
                except Exception as e:
                    logger.error(f"writeChannel({getattr(ch,'index','?')}): {e}")
                    errors.append(f"Canal {getattr(ch, 'index', '?')}: {e}")
            # Clear any unused channel slots
            for idx in range(8):
                if idx not in present_indices and idx != 0:
                    try:
                        node.writeChannel(idx)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"_ChannelSaveWorker error: {e}", exc_info=True)
            errors.append(str(e))
        self.finished.emit(saved, errors)


class _ConfigSaveWorker(QObject):
    """Runs writeConfig / commitSettingsTransaction / setOwner in a background thread."""
    finished = pyqtSignal(object, int, list)   # saved_sections (set), write_config_count (int), errors (list)

    def __init__(self, node, iface, collected, owner_long, owner_short,
                 owner_licensed, owner_licensed_changed, errors_collect):
        super().__init__()
        self._node                   = node
        self._iface                  = iface
        self._collected              = collected
        self._owner_long             = owner_long
        self._owner_short            = owner_short
        self._owner_licensed         = owner_licensed
        self._owner_licensed_changed = owner_licensed_changed
        self._errors                 = list(errors_collect)

    def run(self):
        from tabs.tab_config import SECTION_WRITE_NAME as _SWN, _resolve_sub_obj as _rsub
        saved_sections = set()
        write_config_count = 0   # número real de writeConfig() bem-sucedidos
        logger.info(f"_ConfigSaveWorker.run() — {len(self._collected)} section(s) to save")
        try:
            # beginSettingsTransaction tells the firmware to accumulate all
            # writeConfig calls without rebooting between them. The single
            # reboot happens only when commitSettingsTransaction is sent.
            # Without this, the firmware reboots on the first writeConfig and
            # all subsequent ones are lost.
            try:
                self._node.beginSettingsTransaction()
                logger.debug("beginSettingsTransaction OK")
            except Exception as e:
                logger.debug(f"beginSettingsTransaction not supported: {e}")

            for sec_key, sec_fields in self._collected.items():
                parts = sec_key.split(".", 1)
                if len(parts) != 2:
                    continue
                config_attr, sub_attr = parts
                section_saved = False

                for field_name, payload in sec_fields.items():
                    if field_name == "__canned_messages__":
                        msgs_str = payload
                        if len(msgs_str) > 200:
                            self._errors.append(
                                f"Msgs pré-definidas: {len(msgs_str)} chars (máx 200)."
                            )
                            continue
                        try:
                            self._node.setCannedMessages(msgs_str)
                            saved_sections.add("canned_messages_text")
                        except AttributeError:
                            try:
                                p = admin_pb2.AdminMessage()
                                p.set_canned_message_module_messages = msgs_str
                                self._node._sendAdmin(p)
                                saved_sections.add("canned_messages_text")
                            except Exception as cm_err:
                                self._errors.append(f"Msgs pré-definidas: {cm_err}")
                        except Exception as cm_err:
                            self._errors.append(f"Msgs pré-definidas: {cm_err}")
                        continue

                    field_parts, coerced = payload

                    # Re-resolve o caminho a partir de self._node (o localNode vivo)
                    # em vez de usar o obj resolvido no UI thread.
                    # Isto é crítico: writeConfig faz internamente
                    #   p.set_module_config.mqtt.CopyFrom(self.moduleConfig.mqtt)
                    # ou seja, lê sempre de self._node.localConfig / self._node.moduleConfig.
                    # O setattr tem de operar sobre o MESMO objecto que o CopyFrom vai ler,
                    # caso contrário a alteração nunca chega ao nó.
                    cfg_root = getattr(self._node, config_attr, None)
                    if cfg_root is None:
                        logger.error(f"  [{sec_key}] config_attr {config_attr!r} not found on node")
                        self._errors.append(f"{sec_key}: config_attr {config_attr!r} inexistente")
                        continue

                    obj = _rsub(cfg_root, sec_key)
                    if obj is None:
                        logger.error(f"  [{sec_key}] sub_obj não resolvido no worker")
                        self._errors.append(f"{sec_key}: sub_obj não resolvido no worker")
                        continue

                    # Navega para o sub-objecto aninhado (ex: campos com ponto)
                    for part in field_parts[:-1]:
                        obj = getattr(obj, part, None)
                        if obj is None:
                            break
                    if obj is None:
                        logger.error(f"  [{sec_key}] {field_name}: nested obj is None")
                        self._errors.append(f"{sec_key}.{field_name}: nested obj is None")
                        continue
                    last = field_parts[-1]

                    logger.info(
                        f"  [{sec_key}] setattr(.{last}, {coerced!r}) "
                        f"[type={type(coerced).__name__}]"
                    )
                    try:
                        setattr(obj, last, coerced)
                        # Proto3 não serializa campos com valor igual ao default
                        # (False para bool, 0 para int, "" para string).
                        # Se o valor coerced é o default e precisamos de o enviar
                        # explicitamente (ex: proxy_to_client_enabled = False quando
                        # estava True), o CopyFrom pode não incluir o campo no wire.
                        # Verificamos se o campo ficou registado; se não, usamos
                        # a técnica de double-set: True → False para forçar a presença.
                        if isinstance(coerced, bool) and coerced is False:
                            # Verifica se o campo está em ListFields após setattr
                            try:
                                listed = [f.name for f, _ in obj.ListFields()]
                                if last not in listed:
                                    # Proto ignorou o False — forçar presença
                                    # definindo True primeiro (fica em ListFields)
                                    # e depois False (valor correcto)
                                    setattr(obj, last, True)
                                    setattr(obj, last, False)
                                    logger.debug(f"  [{sec_key}] {last}: forced False via double-set")
                            except Exception:
                                pass  # ListFields pode não existir em todos os objectos
                        section_saved = True
                    except Exception as e:
                        logger.error(f"  setattr FAILED: {e} "
                                     f"(last={last!r}, coerced={coerced!r} "
                                     f"[{type(coerced).__name__}])")
                        self._errors.append(f"{sec_key}.{field_name}: {e}")

                if section_saved:
                    write_name = _SWN.get(sec_key, sub_attr)
                    logger.info(f"  writeConfig({write_name!r})")
                    try:
                        self._node.writeConfig(write_name)
                        saved_sections.add(sec_key)
                        write_config_count += 1
                        logger.info(f"  writeConfig({write_name!r}) ✅")
                    except Exception as e:
                        logger.error(f"  writeConfig({write_name!r}) FAILED: {e}")
                        self._errors.append(f"writeConfig({write_name}): {e}")
                else:
                    logger.debug(f"  [{sec_key}] no fields changed — skipping writeConfig")

            # commitSettingsTransaction triggers the single reboot after all
            # writeConfig calls have been received by the firmware.
            try:
                self._node.commitSettingsTransaction()
                logger.info("commitSettingsTransaction OK — node will reboot once")
            except Exception as e:
                logger.debug(f"commitSettingsTransaction: {e}")

            if self._owner_long is not None or self._owner_short is not None or self._owner_licensed_changed:
                try:
                    self._node.setOwner(
                        long_name=self._owner_long or "",
                        short_name=self._owner_short or "",
                        is_licensed=self._owner_licensed
                    )
                    saved_sections.add("owner")
                    logger.debug("setOwner OK")
                except Exception as e:
                    logger.error(f"setOwner: {e}")
                    self._errors.append(f"setOwner: {e}")

        except Exception as e:
            logger.error(f"_ConfigSaveWorker error: {e}", exc_info=True)
            self._errors.append(str(e))

        self.finished.emit(saved_sections, write_config_count, self._errors)


class ChannelsTab(QWidget):
    ROLES        = ["PRIMARY", "SECONDARY", "DISABLED"]
    MODEM_PRESETS = [
        "LONG_FAST","LONG_SLOW","VERY_LONG_SLOW","MEDIUM_SLOW",
        "MEDIUM_FAST","SHORT_SLOW","SHORT_FAST","LONG_MODERATE",
    ]
    reboot_required = pyqtSignal()   # emitido após guardar com sucesso

    def __init__(self, parent=None):
        super().__init__(parent)
        self._iface    = None
        self._channels: list = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.status_lbl = QLabel(tr("⚠  Sem conexão"))
        self.status_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        top.addWidget(self.status_lbl)
        top.addStretch()

        btn_reload = QPushButton(tr("🔄  Recarregar"))
        btn_reload.clicked.connect(self._load_channels)
        top.addWidget(btn_reload)

        btn_add = QPushButton(tr("➕  Adicionar Canal"))
        btn_add.clicked.connect(self._add_channel)
        top.addWidget(btn_add)

        btn_save = QPushButton(tr("💾  Guardar Alterações"))
        btn_save.setObjectName("btn_connect")
        btn_save.clicked.connect(self._save_all)
        top.addWidget(btn_save)

        root.addLayout(top)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:{DARK_BG};}}")
        self._channels_container = QWidget()
        self._channels_container.setStyleSheet(f"background:{DARK_BG};")
        self._channels_layout = QVBoxLayout(self._channels_container)
        self._channels_layout.setSpacing(8)
        self._channels_layout.setContentsMargins(0, 0, 0, 0)
        self._channels_layout.addStretch()
        scroll.setWidget(self._channels_container)
        root.addWidget(scroll)

        self._channel_widgets: list = []

    def retranslate(self):
        """Update ChannelsTab labels after language change.
        Channel rows are rebuilt on reload; only static buttons need updating.
        """
        if hasattr(self, "status_lbl"):
            if self._iface:
                from i18n import tr as _tr
                loaded = self._channels
                self.status_lbl.setText(_tr("✅  {n} canal(ais) carregados", n=len(loaded)) if loaded else "")
            else:
                self.status_lbl.setText(tr("⚠  Sem conexão"))
        if hasattr(self, "btn_add") and self.btn_add:
            self.btn_add.setText(tr("➕  Adicionar Canal"))
        if hasattr(self, "btn_save_ch") and self.btn_save_ch:
            self.btn_save_ch.setText(tr("💾  Guardar Alterações"))
        if hasattr(self, "btn_reload_ch") and self.btn_reload_ch:
            self.btn_reload_ch.setText(tr("🔄  Recarregar"))

    def set_interface(self, iface):
        self._iface = iface
        self._load_channels()

    def clear_interface(self):
        self._iface = None
        self._channels = []
        self._clear_rows()
        self.status_lbl.setText(tr("⚠  Sem conexão"))

    def _load_channels(self):
        if not self._iface:
            self.status_lbl.setText(tr("⚠  Sem conexão"))
            return
        try:
            node = self._iface.localNode
            self._channels = list(node.channels) if node and node.channels else []
            self._rebuild_ui()
            self.status_lbl.setText(tr("✅  {n} canal(ais) carregados", n=len(self._channels)))
        except Exception as e:
            logger.error(f"Error loading channels: {e}", exc_info=True)
            self.status_lbl.setText(tr("err_generic", err=e))

    def _clear_rows(self):
        for row in self._channel_widgets:
            row.setParent(None)
            row.deleteLater()
        self._channel_widgets.clear()
        while self._channels_layout.count():
            item = self._channels_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_ui(self):
        self._clear_rows()
        for i, ch in enumerate(self._channels):
            row = _ChannelRow(i, ch, parent=self)
            row.remove_requested.connect(self._remove_channel)
            self._channels_layout.addWidget(row)
            self._channel_widgets.append(row)
        self._channels_layout.addStretch()

    def _add_channel(self):
        if not self._iface:
            QMessageBox.warning(self, tr("Sem Conexão"), tr("Conecte-se primeiro."))
            return
        used = {ch.index for ch in self._channels if hasattr(ch, 'index')}
        for idx in range(8):
            if idx not in used:
                break
        else:
            QMessageBox.warning(self, tr("Limite atingido"),
                                tr("O máximo de 8 canais (0-7) já foi atingido."))
            return

        try:
            new_ch = Channel()
            new_ch.index = idx
            new_ch.role  = 2
            new_ch.settings.name = tr("Canal {n}", n=idx)
            self._channels.append(new_ch)
            self._rebuild_ui()
            self.status_lbl.setText(tr("➕  Canal {n} adicionado — edite e guarde", n=idx))
        except Exception as e:
            logger.error(f"Error creating channel: {e}", exc_info=True)
            QMessageBox.critical(self, tr("Erro"), tr("Não foi possível criar canal:\n{e}", e=e))

    def _remove_channel(self, index: int):
        reply = QMessageBox.question(
            self, tr("Remover Canal"),
            tr("Remover o canal com índice {n}?", n=index),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self._channels = [ch for ch in self._channels
                          if getattr(ch, 'index', None) != index]
        self._rebuild_ui()
        self.status_lbl.setText(tr("🗑  Canal {n} marcado para remoção — guarde para aplicar", n=index))

    def _save_all(self):
        if not self._iface:
            QMessageBox.warning(self, tr("Sem Conexão"), "Não está conectado.")
            return
        reply = QMessageBox.question(
            self, tr("Guardar Canais"),
            (tr("Guardar todas as alterações de canais no nó?\n\n")
             + tr("⚠  O nó irá reiniciar para aplicar as alterações.\n")
             + tr("A ligação TCP será temporariamente perdida e restabelecida.")),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Apply widget values to channel objects BEFORE spawning the thread
        # (must happen in the UI thread while widgets are alive)
        for row in self._channel_widgets:
            row.apply_to_channel()

        self.status_lbl.setText(tr("A guardar…"))
        # Disable button to prevent double-save
        for btn in self.findChildren(QPushButton):
            if "Guardar" in btn.text():
                btn.setEnabled(False)
                break

        # Run writeChannel calls in a background thread.
        # Using module-level _ChannelSaveWorker (not a locally-defined class)
        # so PyQt5's meta-object system correctly delivers signals across threads.
        channels_snapshot = list(self._channels)
        iface_ref = self._iface

        self._save_thread = QThread()
        self._save_worker = _ChannelSaveWorker(iface_ref, channels_snapshot)
        self._save_worker.moveToThread(self._save_thread)
        self._save_thread.started.connect(self._save_worker.run)
        self._save_worker.finished.connect(self._on_save_finished)
        self._save_worker.finished.connect(self._save_thread.quit)
        self._save_worker.finished.connect(self._save_worker.deleteLater)
        self._save_thread.finished.connect(self._save_thread.deleteLater)
        self._save_thread.start()

    def _on_save_finished(self, saved: int, errors: list):
        # Re-enable save button
        for btn in self.findChildren(QPushButton):
            if "Guardar" in btn.text():
                btn.setEnabled(True)
                break

        msg = tr("✅  {n} canal(ais) guardados", n=saved)
        if errors:
            msg += f" | ⚠ {len(errors)} erro(s)"
        self.status_lbl.setText(msg)
        QMessageBox.information(
            self, tr("Canais Guardados"),
            tr("{n} canal(ais) guardados no nó.", n=saved) +
            (f"\n\nErros:\n" + "\n".join(errors[:5]) if errors else "")
        )
        if saved > 0:
            self.reboot_required.emit()
        else:
            self._load_channels()


class _ChannelRow(QWidget):
    remove_requested = pyqtSignal(int)

    def __init__(self, list_index: int, channel, parent=None):
        super().__init__(parent)
        self._channel  = channel
        self._ch_index = getattr(channel, 'index', list_index)
        self._build(channel)

    def _build(self, ch):
        self.setStyleSheet(
            f"background:{PANEL_BG};border:1px solid {BORDER_COLOR};border-radius:8px;"
        )
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 10, 12, 10)
        main.setSpacing(8)

        hdr        = QHBoxLayout()
        idx        = getattr(ch, 'index', 0)
        role_num   = getattr(ch, 'role', 0)
        role_names = {0: "DISABLED", 1: "PRIMARY", 2: "SECONDARY"}
        role_str   = role_names.get(role_num, str(role_num))
        color      = ACCENT_GREEN if role_num == 1 else (ACCENT_BLUE if role_num == 2 else TEXT_MUTED)

        lbl_idx = QLabel(tr("📻  Canal {n}", n=idx))
        lbl_idx.setStyleSheet(f"color:{color};font-weight:bold;font-size:13px;")
        hdr.addWidget(lbl_idx)
        hdr.addStretch()

        btn_remove = QPushButton("🗑")
        btn_remove.setFixedSize(28, 28)
        btn_remove.setStyleSheet(
            f"background:{DARK_BG};color:{ACCENT_RED};"
            f"border:1px solid {ACCENT_RED};border-radius:4px;"
        )
        btn_remove.clicked.connect(lambda: self.remove_requested.emit(self._ch_index))
        hdr.addWidget(btn_remove)
        main.addLayout(hdr)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        def mk_lbl(t):
            l = QLabel(t + ":")
            l.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
            return l

        settings = getattr(ch, 'settings', None)
        name_val  = getattr(settings, 'name', '') if settings else ''
        self.w_name = QLineEdit(name_val or "")
        self.w_name.setPlaceholderText(tr("Nome do canal"))
        self.w_name.setFixedWidth(240)
        form.addRow(mk_lbl(tr("Nome do canal")), self.w_name)

        self.w_role = QComboBox()
        self.w_role.addItems(["DISABLED", "PRIMARY", "SECONDARY"])
        self.w_role.setCurrentIndex(min(role_num, 2))
        form.addRow(mk_lbl(tr("Papel")), self.w_role)

        psk_bytes = getattr(settings, 'psk', b'') if settings else b''
        # Mostra como Base64 — formato standard das apps iOS/Android
        if isinstance(psk_bytes, (bytes, bytearray)) and len(psk_bytes) > 0:
                        psk_display = base64.b64encode(psk_bytes).decode('ascii')
        else:
            psk_display = ''
        self.w_psk = QLineEdit(psk_display)
        self.w_psk.setPlaceholderText(tr("Base64 (ex: AQ==)  ou  default / none / random"))

        self.w_psk_type = QComboBox()
        self.w_psk_type.addItems(["256-bit (32 bytes)", "128-bit (16 bytes)", "Default (AQ==)"])
        self.w_psk_type.setFixedWidth(180)
        self.w_psk_type.setStyleSheet(
            f"background:{DARK_BG};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;padding:2px 4px;font-size:11px;"
        )
        btn_gen_psk = QPushButton(tr("🔑 Gerar"))
        btn_gen_psk.setFixedWidth(70)
        btn_gen_psk.setStyleSheet(
            f"QPushButton{{background:{PANEL_BG};color:{ACCENT_BLUE};"
            f"border:1px solid {ACCENT_BLUE};border-radius:4px;padding:2px 6px;font-size:11px;}}"
            f"QPushButton:hover{{background:{ACCENT_BLUE};color:#000;}}"
        )
        btn_gen_psk.setToolTip(tr("Gera uma chave PSK aleatória do tipo seleccionado"))

        def _gen_psk():
            t = self.w_psk_type.currentIndex()
            if t == 0:
                key = os.urandom(32)
            elif t == 1:
                key = os.urandom(16)
            else:
                key = bytes([1])   # Default = AQ==
            self.w_psk.setText(base64.b64encode(key).decode('ascii'))

        btn_gen_psk.clicked.connect(_gen_psk)

        psk_row = QHBoxLayout()
        psk_row.setSpacing(4)
        psk_row.addWidget(self.w_psk)
        psk_row.addWidget(self.w_psk_type)
        psk_row.addWidget(btn_gen_psk)
        form.addRow(mk_lbl("PSK"), psk_row)

        self.w_uplink = QCheckBox(tr("Uplink MQTT habilitado"))
        self.w_uplink.setChecked(bool(getattr(settings, 'uplink_enabled', False) if settings else False))
        form.addRow(mk_lbl("Uplink MQTT"), self.w_uplink)

        self.w_downlink = QCheckBox(tr("Downlink MQTT habilitado"))
        self.w_downlink.setChecked(bool(getattr(settings, 'downlink_enabled', False) if settings else False))
        form.addRow(mk_lbl("Downlink MQTT"), self.w_downlink)

        mod_settings = getattr(settings, 'module_settings', None) if settings else None
        self.w_muted = QCheckBox(tr("Silenciar notificações (is_muted)"))
        self.w_muted.setChecked(bool(getattr(mod_settings, 'is_muted', False) if mod_settings else False))
        form.addRow(mk_lbl(tr("Silenciar")), self.w_muted)

        pos_prec     = getattr(settings, 'module_settings', None)
        pos_prec_val = getattr(pos_prec, 'position_precision', 0) if pos_prec else 0
        self.w_pos_prec = QSpinBox()
        self.w_pos_prec.setRange(0, 32)
        self.w_pos_prec.setValue(int(pos_prec_val))
        form.addRow(mk_lbl(tr("Precisão posição")), self.w_pos_prec)

        main.addLayout(form)

    def apply_to_channel(self):
        ch       = self._channel
        settings = getattr(ch, 'settings', None)
        if settings is None:
            return
        try:
            settings.name              = self.w_name.text().strip()
            role_map = {"DISABLED": 0, "PRIMARY": 1, "SECONDARY": 2}
            ch.role                    = role_map.get(self.w_role.currentText(), 2)
            settings.uplink_enabled    = self.w_uplink.isChecked()
            settings.downlink_enabled  = self.w_downlink.isChecked()
            if hasattr(settings, 'module_settings'):
                settings.module_settings.is_muted = self.w_muted.isChecked()
            psk_str = self.w_psk.text().strip()
            if psk_str:
                try:
                    ps = psk_str.lower()
                    if ps == 'default':
                        settings.psk = bytes([1])
                    elif ps == 'none':
                        settings.psk = bytes([0])
                    elif ps == 'random':
                        settings.psk = os.urandom(32)
                    elif psk_str.startswith('0x') or psk_str.startswith('0X'):
                        settings.psk = bytes.fromhex(psk_str[2:])
                    else:
                        # Assume Base64 (formato das apps iOS/Android)
                        settings.psk = base64.b64decode(psk_str)
                except Exception as _e:
                    logger.warning(f"Invalid PSK '{psk_str}': {_e}")
            if hasattr(settings, 'module_settings'):
                settings.module_settings.position_precision = self.w_pos_prec.value()
        except Exception as e:
            logger.warning(f"Error applying channel {self._ch_index}: {e}")



# ---------------------------------------------------------------------------
# Config definitions (unchanged)
# ---------------------------------------------------------------------------
MESHTASTIC_CONFIG_DEFS = {
    "localConfig.device": [
        ("Papel do nó",             "role",                    "combo",
         ["CLIENT","CLIENT_MUTE","CLIENT_HIDDEN","TRACKER","LOST_AND_FOUND",
          "SENSOR","TAK","TAK_TRACKER","REPEATER","ROUTER","ROUTER_CLIENT"]),
        ("Retransmitir mensagens",  "rebroadcast_mode",        "combo",
         ["ALL","ALL_SKIP_DECODING","LOCAL_ONLY","KNOWN_ONLY","NONE"]),
        ("Serial habilitado",       "serial_enabled",          "bool",   None),
        ("Debug via serial",        "debug_log_enabled",       "bool",   None),
        ("Botão GPIO",              "button_gpio",             "spin_int",(0,39)),
        ("Buzzer GPIO",             "buzzer_gpio",             "spin_int",(0,39)),
        ("Duplo clique alimentação","double_tap_as_button_press","bool",  None),
        ("LED em heartbeat",        "led_heartbeat_disabled",  "bool",   None),
        ("Intervalo broadcast NodeInfo (s)", "node_info_broadcast_secs","spin_int",(0,604800)),
        ("Fuso horário (TZ string)","tzdef",                   "text",   None),
        ("Disable triple-click",    "disable_triple_click",    "bool",   None),
        ("Quick chat button",       "quick_chat_button",       "bool",   None),
    ],
    "localConfig.position": [
        ("Modo GPS",                "gps_mode",                "combo",
         ["DISABLED","ENABLED","NOT_PRESENT"]),
        ("Intervalo update GPS (s)","gps_update_interval",     "spin_int",(0,86400)),
        ("Tentativa GPS (s)",       "gps_attempt_time",        "spin_int",(0,3600)),
        ("Intervalo broadcast pos (s)","position_broadcast_secs","spin_int",(0,86400)),
        ("Smart broadcast pos.",    "position_broadcast_smart_enabled","bool",None),
        ("Distância mínima smart (m)","broadcast_smart_minimum_distance","spin_int",(0,10000)),
        ("Intervalo mínimo smart (s)","broadcast_smart_minimum_interval_secs","spin_int",(0,3600)),
        ("Latitude fixa (graus)",   "fixed_lat",               "spin_float",(-90.0, 90.0)),
        ("Longitude fixa (graus)",  "fixed_lon",               "spin_float",(-180.0,180.0)),
        ("Altitude fixa (m)",       "fixed_alt",               "spin_int",  (-1000, 10000)),
        ("Precision de posição",    "position_flags",          "spin_int",(0,8191)),
        ("Receiver GPIO",           "rx_gpio",                 "spin_int",(0,39)),
        ("Transmitter GPIO",        "tx_gpio",                 "spin_int",(0,39)),
        ("Broadcast SBAS",          "gps_accept_2d",           "bool",   None),
        ("Max HDOP para aceitar",   "gps_max_dop",             "spin_int",(0,2000)),
    ],
    "localConfig.power": [
        ("Modo de economia",        "is_power_saving",         "bool",   None),
        ("Desligar na bateria (s)", "on_battery_shutdown_after_secs","spin_int",(0,86400)),
        ("Override ADC multiplicador","adc_multiplier_override","spin_float",(0.0,10.0)),
        ("Wait Bluetooth (s)",      "wait_bluetooth_secs",     "spin_int",(0,3600)),
        ("Modo SDS desligar (s)",   "sds_secs",                "spin_int",(0,86400)),
        ("Modo LS desligar (s)",    "ls_secs",                 "spin_int",(0,86400)),
        ("Tempo mínimo acordado (s)","min_wake_secs",          "spin_int",(0,3600)),
        ("INA endereço I2C bateria","device_battery_ina_address","spin_int",(0,127)),
        ("Powersave GPIO",          "powermon_enables",        "spin_int",(0,65535)),
    ],
    "localConfig.network": [
        ("WiFi habilitado",         "wifi_enabled",            "bool",   None),
        ("SSID WiFi",               "wifi_ssid",               "text",   None),
        ("Senha WiFi",              "wifi_psk",                "text",   None),
        ("Servidor NTP",            "ntp_server",              "text",   None),
        ("Ethernet habilitada",     "eth_enabled",             "bool",   None),
        ("Modo endereçamento",      "address_mode",            "combo",  ["DHCP","STATIC"]),
        ("IP estático",             "ipv4_config.ip",          "text",   None),
        ("Gateway",                 "ipv4_config.gateway",     "text",   None),
        ("Subnet",                  "ipv4_config.subnet",      "text",   None),
        ("DNS",                     "ipv4_config.dns",         "text",   None),
        ("RSync Server",            "rsync_server",            "text",   None),
    ],
    "localConfig.display": [
        ("Ecrã ligado (s)",         "screen_on_secs",          "spin_int",(0,3600)),
        ("Formato GPS",             "gps_format",              "combo",
         ["DEC","DMS","UTM","MGRS","OLC","OSGR"]),
        ("Múltiplo do auto dim.",   "auto_screen_carousel_secs","spin_int",(0,3600)),
        ("Unidades",                "units",                   "combo",  ["METRIC","IMPERIAL"]),
        ("OLED tipo",               "oled",                    "combo",
         ["OLED_AUTO","OLED_SSD1306","OLED_SH1106","OLED_SH1107"]),
        ("Modo do display",         "displaymode",             "combo",
         ["DEFAULT","TWOCOLOR","INVERTED","COLOR"]),
        ("Flip ecrã",               "flip_screen",             "bool",   None),
        ("Acord. por toque/mov.",   "wake_on_tap_or_motion",   "bool",   None),
        ("Cabeçalho negrito",       "heading_bold",            "bool",   None),
        # compass_north_top, backlight_secs, tft_brightness não existem no proto DisplayConfig
    ],
    "localConfig.lora": [
        ("Usar preset",             "use_preset",              "bool",   None),
        ("Modem preset",            "modem_preset",            "combo",
         ["LONG_FAST","LONG_SLOW","VERY_LONG_SLOW","MEDIUM_SLOW",
          "MEDIUM_FAST","SHORT_SLOW","SHORT_FAST","LONG_MODERATE"]),
        ("Região",                  "region",                  "combo",
         ["UNSET","US","EU_433","EU_868","CN","JP","ANZ","KR","TW",
          "RU","IN","NZ_865","TH","LORA_24","UA_433","UA_868",
          "MY_433","MY_919","SG_923","PH_433","PH_868","PH_915"]),
        ("Largura de banda",        "bandwidth",               "spin_int",(0,500)),
        ("Spreading factor",        "spread_factor",           "spin_int",(7,12)),
        ("Coding rate",             "coding_rate",             "spin_int",(5,8)),
        ("Offset frequência (MHz)", "frequency_offset",        "spin_float",(-100.0,100.0)),
        ("TX habilitado",           "tx_enabled",              "bool",   None),
        ("TX Power (dBm)",          "tx_power",                "spin_int",(0,30)),
        ("Hop limit",               "hop_limit",               "spin_int",(1,7)),
        ("Ignorar MQTT",            "ignore_mqtt",             "bool",   None),
        ("Override duty cycle",     "override_duty_cycle",     "bool",   None),
        ("Override frequency (MHz)","override_frequency",      "spin_float",(0.0,1000.0)),
        ("RX boosted gain (SX126x)","sx126x_rx_boosted_gain",  "bool",   None),
        ("PA fan GPIO",             "pa_fan_disabled",         "bool",   None),
        ("OK para MQTT",            "config_ok_to_mqtt",       "bool",   None),
        ("Número do canal (0-7)",   "channel_num",             "spin_int",(0,7)),
    ],
    "localConfig.bluetooth": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Modo de emparelhamento",  "mode",                    "combo",
         ["RANDOM_PIN","FIXED_PIN","NO_PIN"]),
        ("PIN fixo",                "fixed_pin",               "spin_int",(0,999999)),
    ],
    "moduleConfig.mqtt": [
        # Campos do proto MQTTConfig (module_config.proto)
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Servidor",                "address",                 "text",   None),
        ("Utilizador",              "username",                "text",   None),
        ("Senha",                   "password",                "text",   None),
        ("Encriptação habilitada",  "encryption_enabled",      "bool",   None),
        ("JSON habilitado",         "json_enabled",            "bool",   None),
        ("TLS habilitado",          "tls_enabled",             "bool",   None),
        ("Root topic",              "root",                    "text",   None),
        ("Proxy para cliente",      "proxy_to_client_enabled", "bool",   None),
        # map_reporting_enabled, map_report_settings, ok_to_mqtt não existem
        # nesta versão do proto (module_config.proto MQTTConfig field list).
    ],
    "moduleConfig.serial": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Echo",                    "echo",                    "bool",   None),
        ("Baud rate",               "baud",                    "combo",
         ["BAUD_DEFAULT","BAUD_110","BAUD_300","BAUD_600","BAUD_1200",
          "BAUD_2400","BAUD_4800","BAUD_9600","BAUD_19200","BAUD_38400",
          "BAUD_57600","BAUD_115200","BAUD_230400","BAUD_460800",
          "BAUD_576000","BAUD_921600"]),
        ("Timeout (ms)",            "timeout",                 "spin_int",(0,60000)),
        ("Modo",                    "mode",                    "combo",
         ["DEFAULT","SIMPLE","PROTO","TEXTMSG","NMEA","CALTOPO"]),
        ("RX GPIO",                 "rxd",                     "spin_int",(0,39)),
        ("TX GPIO",                 "txd",                     "spin_int",(0,39)),
        ("Somente RX",              "override_console_serial_port","bool",None),
    ],
    "moduleConfig.externalNotification": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Saída activa (ms)",       "output_ms",               "spin_int",(0,60000)),
        ("Saída GPIO",              "output",                  "spin_int",(0,39)),
        ("Saída vibra GPIO",        "output_vibra",            "spin_int",(0,39)),
        ("Saída buzzer GPIO",       "output_buzzer",           "spin_int",(0,39)),
        ("Alerta para mensagem",    "alert_message",           "bool",   None),
        ("Alerta msg pulso",        "alert_message_buzzer",    "bool",   None),
        ("Alerta msg vibra",        "alert_message_vibra",     "bool",   None),
        ("Alerta para bell",        "alert_bell",              "bool",   None),
        ("Alerta bell buzzer",      "alert_bell_buzzer",       "bool",   None),
        ("Alerta bell vibra",       "alert_bell_vibra",        "bool",   None),
        ("Usar PWM buzzer",         "use_pwm",                 "bool",   None),
        ("Nível activo GPIO",       "active",                  "bool",   None),
    ],
    "moduleConfig.storeForward": [
        # Campos do proto StoreForwardConfig
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Heartbeat",               "heartbeat",               "bool",   None),
        ("Num records",             "records",                 "spin_int",(0,300)),
        ("Histórico (s)",           "history_return_window",   "spin_int",(0,86400)),
        ("Max msgs histórico",      "history_return_max",      "spin_int",(0,300)),
        # is_server não existe no proto StoreForwardConfig
    ],
    "moduleConfig.rangeTest": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Intervalo sender (s)",    "sender",                  "spin_int",(0,86400)),
        ("Guardar em CSV",          "save",                    "bool",   None),
    ],
    "moduleConfig.telemetry": [
        # Campos do proto TelemetryConfig
        ("Intervalo dispositivo (s)","device_update_interval", "spin_int",(0,86400)),
        ("Intervalo ambiente (s)",  "environment_update_interval","spin_int",(0,86400)),
        ("Medição ambiente activa", "environment_measurement_enabled","bool",None),
        ("Ambiente no ecrã",        "environment_screen_enabled","bool",  None),
        ("Temperatura em Fahrenheit","environment_display_fahrenheit","bool",None),
        ("Air quality activo",      "air_quality_enabled",     "bool",   None),
        ("Intervalo air quality (s)","air_quality_interval",   "spin_int",(0,86400)),
        ("Medição potência activa", "power_measurement_enabled","bool",  None),
        ("Intervalo potência (s)",  "power_update_interval",   "spin_int",(0,86400)),
        # health_update_interval e health_telemetry_enabled não existem no proto
    ],
    "moduleConfig.cannedMessage": [
        # ── Campo especial: lista de mensagens (separadas por |, max 200 chars total) ──
        # Guardado via localNode.setCannedMessages(), não via writeConfig
        ("Mensagens pré-definidas", "__canned_messages__",     "canned_messages", None),
        # ── Configuração do módulo ──────────────────────────────────────────────────
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Enviar sinal Bell",       "send_bell",               "bool",   None),
        ("Fonte de entrada aceite", "allow_input_source",      "text",   None),
        # Rotary encoder #1
        ("Rotary encoder #1",       "rotary1_enabled",         "bool",   None),
        ("Up/Down encoder",         "updown1_enabled",         "bool",   None),
        ("GPIO encoder A",          "inputbroker_pin_a",       "spin_int",(0,39)),
        ("GPIO encoder B",          "inputbroker_pin_b",       "spin_int",(0,39)),
        ("GPIO encoder Press",      "inputbroker_pin_press",   "spin_int",(0,39)),
        # InputEventChar proto: NONE=0,UP=17,DOWN=18,LEFT=19,RIGHT=20,SELECT=10,BACK=27,CANCEL=24
        # FN_* e NUMPAD_* não existem no proto CannedMessageConfig.InputEventChar
        ("Evento CW (cima)",        "inputbroker_event_cw",    "combo",
         ["NONE","UP","DOWN","LEFT","RIGHT","SELECT","BACK","CANCEL"]),
        ("Evento CCW (baixo)",      "inputbroker_event_ccw",   "combo",
         ["NONE","UP","DOWN","LEFT","RIGHT","SELECT","BACK","CANCEL"]),
        ("Evento Press",            "inputbroker_event_press", "combo",
         ["NONE","UP","DOWN","LEFT","RIGHT","SELECT","BACK","CANCEL"]),
    ],
    "moduleConfig.audio": [
        ("Codec2 habilitado",       "codec2_enabled",          "bool",   None),
        ("GPIO PTT",                "ptt_pin",                 "spin_int",(0,39)),
        ("Modo codec2",             "bitrate",                 "combo",
         ["DEFAULT","CODEC2_3200","CODEC2_2400","CODEC2_1600","CODEC2_1400",
          "CODEC2_1300","CODEC2_1200","CODEC2_700","CODEC2_700B"]),
        ("I2S WS GPIO",             "i2s_ws",                  "spin_int",(0,39)),
        ("I2S SD GPIO",             "i2s_sd",                  "spin_int",(0,39)),
        ("I2S DIN GPIO",            "i2s_din",                 "spin_int",(0,39)),
        ("I2S SCK GPIO",            "i2s_sck",                 "spin_int",(0,39)),
    ],
    "moduleConfig.remotehardware": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Permitir input não seg.", "allow_undefined_pin_access","bool", None),
    ],
    "moduleConfig.neighborInfo": [
        # Campos do proto NeighborInfoConfig
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Intervalo update (s)",    "update_interval",         "spin_int",(0,86400)),
        # transmit_over_lora não existe no proto NeighborInfoConfig
    ],
    "moduleConfig.ambientLighting": [
        ("Habilitado LED",          "led_state",               "bool",   None),
        ("Corrente (mA)",           "current",                 "spin_int",(0,31)),
        ("Red",                     "red",                     "spin_int",(0,255)),
        ("Green",                   "green",                   "spin_int",(0,255)),
        ("Blue",                    "blue",                    "spin_int",(0,255)),
    ],
    "moduleConfig.detectionSensor": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Intervalo mínimo send (s)","minimum_broadcast_secs", "spin_int",(0,86400)),
        ("Intervalo estado (s)",    "state_broadcast_secs",    "spin_int",(0,86400)),
        ("Usar pull-up",            "use_pullup",              "bool",   None),
        ("Nome",                    "name",                    "text",   None),
        ("Monitor GPIO",            "monitor_pin",             "spin_int",(0,39)),
        ("Tipo de detecção",        "detection_triggered_high","bool",   None),
    ],
    "moduleConfig.paxcounter": [
        ("Habilitado",              "enabled",                 "bool",   None),
        ("Intervalo Paxcount (s)",  "paxcounter_update_interval","spin_int",(0,86400)),
    ],
    "localConfig.security": [
        ("Chave pública (readonly)","public_key",              "readonly",None),
        ("Admin via canal legacy",  "admin_channel_enabled",   "bool",   None),
        ("Managed mode",            "is_managed",              "bool",   None),
        ("Modo serial (debug)",     "serial_enabled",          "bool",   None),
        ("Log debug via serial",    "debug_log_api_enabled",   "bool",   None),
        ("Admin channel enabled",   "managed_admin_channel_enabled","bool",None),
        ("Bluetooth admin",         "bluetooth_logging_enabled","bool",  None),
    ],
}

def get_section_label(key: str) -> str:
    """Returns the translated section label for the given config key."""
    _map = {
        "localConfig.device":              "💻 Dispositivo",
        "localConfig.position":            "📍 Posição / GPS",
        "localConfig.power":               "🔋 Energia",
        "localConfig.network":             "🌐 Rede / WiFi",
        "localConfig.display":             "🖥 Display",
        "localConfig.lora":                "📡 LoRa",
        "localConfig.bluetooth":           "🔵 Bluetooth",
        "moduleConfig.mqtt":               "☁ MQTT",
        "moduleConfig.serial":             "🔌 Serial",
        "moduleConfig.externalNotification": "🔔 Notif. Externa",
        "moduleConfig.storeForward":       "📦 Store & Forward",
        "moduleConfig.rangeTest":          "📏 Range Test",
        "moduleConfig.telemetry":          "📊 Telemetria",
        "moduleConfig.cannedMessage":      "💬 Msgs Pre-definidas",
        "moduleConfig.audio":              "🎙 Audio / Codec2",
        "moduleConfig.remotehardware":     "🔧 Hardware Remoto",
        "moduleConfig.neighborInfo":       "🔗 Neighbor Info",
        "moduleConfig.ambientLighting":    "💡 Ilum. Ambiente",
        "moduleConfig.detectionSensor":    "🔍 Sensor Deteccao",
        "moduleConfig.paxcounter":         "🧮 Paxcounter",
        "localConfig.security":            "🔐 Segurança",
    }
    return tr(_map.get(key, key))


SECTION_WRITE_NAME = {
    "localConfig.device":              "device",
    "localConfig.position":            "position",
    "localConfig.power":               "power",
    "localConfig.network":             "network",
    "localConfig.display":             "display",
    "localConfig.lora":                "lora",
    "localConfig.bluetooth":           "bluetooth",
    "moduleConfig.mqtt":               "mqtt",
    "moduleConfig.serial":             "serial",
    "moduleConfig.externalNotification":"external_notification",
    "moduleConfig.storeForward":       "store_forward",
    "moduleConfig.rangeTest":          "range_test",
    "moduleConfig.telemetry":          "telemetry",
    "moduleConfig.cannedMessage":      "canned_message",
    "moduleConfig.audio":              "audio",
    "moduleConfig.remotehardware":     "remote_hardware",
    "moduleConfig.neighborInfo":       "neighbor_info",
    "moduleConfig.ambientLighting":    "ambient_lighting",
    "moduleConfig.detectionSensor":    "detection_sensor",
    "moduleConfig.paxcounter":         "paxcounter",
    "localConfig.security":            "security",
}

# Mapeamento explícito sec_key → nome do atributo real no objecto cfg_root.
# A biblioteca meshtastic-python usa nomes que nem sempre correspondem ao
# camelCase da chave nem ao snake_case do write_name.  Este mapa é a fonte
# de verdade e evita toda a lógica de tentativa-e-erro.
SECTION_ATTR_NAME = {
    "localConfig.device":                "device",
    "localConfig.position":              "position",
    "localConfig.power":                 "power",
    "localConfig.network":               "network",
    "localConfig.display":               "display",
    "localConfig.lora":                  "lora",
    "localConfig.bluetooth":             "bluetooth",
    "moduleConfig.mqtt":                 "mqtt",
    "moduleConfig.serial":               "serial",
    "moduleConfig.externalNotification": "externalNotification",
    "moduleConfig.storeForward":         "storeForward",
    "moduleConfig.rangeTest":            "rangeTest",
    "moduleConfig.telemetry":            "telemetry",
    "moduleConfig.cannedMessage":        "cannedMessage",
    "moduleConfig.audio":                "audio",
    "moduleConfig.remotehardware":       "remoteHardware",
    "moduleConfig.neighborInfo":         "neighborInfo",
    "moduleConfig.ambientLighting":      "ambientLighting",
    "moduleConfig.detectionSensor":      "detectionSensor",
    "moduleConfig.paxcounter":           "paxcounter",
    "localConfig.security":              "security",
}


def _resolve_sub_obj(cfg_root, sec_key: str):
    """
    Resolve o sub-objecto de configuração para `sec_key` em `cfg_root`.

    Estratégia (em ordem de prioridade):
      1. SECTION_ATTR_NAME — mapeamento explícito (fonte de verdade).
      2. sub_attr camelCase directo (ex: "device", "lora").
      3. snake_case derivado do camelCase (ex: "externalNotification" → "external_notification").
      4. write_name de SECTION_WRITE_NAME (ex: "external_notification").

    Retorna o objecto ou None se nenhuma tentativa funcionar.
    Regista em DEBUG qual estratégia foi bem-sucedida para facilitar diagnóstico.
    """
    _, sub_attr = sec_key.split('.', 1)

    # 1. Mapeamento explícito
    explicit = SECTION_ATTR_NAME.get(sec_key)
    if explicit:
        obj = getattr(cfg_root, explicit, None)
        if obj is not None:
            logger.debug(f"_resolve_sub_obj({sec_key}): explicit attr '{explicit}' ✅")
            return obj
        logger.debug(f"_resolve_sub_obj({sec_key}): explicit attr '{explicit}' not found, falling back")

    # 2. camelCase directo
    obj = getattr(cfg_root, sub_attr, None)
    if obj is not None:
        logger.debug(f"_resolve_sub_obj({sec_key}): camelCase '{sub_attr}' ✅")
        return obj

    # 3. snake_case
    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', sub_attr).lower()
    if snake != sub_attr:
        obj = getattr(cfg_root, snake, None)
        if obj is not None:
            logger.debug(f"_resolve_sub_obj({sec_key}): snake_case '{snake}' ✅")
            return obj

    # 4. write_name
    write_name = SECTION_WRITE_NAME.get(sec_key)
    if write_name and write_name not in (sub_attr, snake):
        obj = getattr(cfg_root, write_name, None)
        if obj is not None:
            logger.debug(f"_resolve_sub_obj({sec_key}): write_name '{write_name}' ✅")
            return obj

    logger.warning(f"_resolve_sub_obj({sec_key}): could not resolve sub-object "
                   f"(tried: {explicit!r}, {sub_attr!r}, {snake!r}, {write_name!r})")
    return None


# ---------------------------------------------------------------------------
# ConfigTab
# ---------------------------------------------------------------------------
class ConfigTab(QWidget):
    config_save_requested = pyqtSignal(dict)
    reboot_required       = pyqtSignal()   # emitido após guardar com sucesso

    def __init__(self, parent=None):
        super().__init__(parent)
        self._iface        = None
        self._local_node   = None
        self._config_widgets: Dict[str, Dict[str, QWidget]] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        hdr = QHBoxLayout()
        self._title_lbl = QLabel(tr("⚙ Config. do No Local"))
        self._title_lbl.setStyleSheet(f"color:{ACCENT_ORANGE};font-size:15px;font-weight:bold;")
        hdr.addWidget(self._title_lbl)
        hdr.addStretch()

        self.status_label = QLabel(tr("Não conectado"))
        self.status_label.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        hdr.addWidget(self.status_label)

        self._btn_reload = QPushButton(tr("🔄  Recarregar"))
        self._btn_reload.setObjectName("btn_reload_config")
        self._btn_reload.clicked.connect(self.reload_config)
        hdr.addWidget(self._btn_reload)

        self.btn_save = QPushButton(tr("💾  Guardar Alterações"))
        self.btn_save.setObjectName("btn_save_config")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_config)
        hdr.addWidget(self.btn_save)

        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER_COLOR};")
        root.addWidget(sep)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        left = QWidget()
        left.setMaximumWidth(200)
        left.setMinimumWidth(150)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)
        lv.setSpacing(4)

        self._sec_lbl = QLabel(tr("Secções"))
        sec_lbl = self._sec_lbl
        sec_lbl.setStyleSheet(
            f"color:{ACCENT_BLUE};font-weight:bold;font-size:11px;"
            f"padding:4px 8px;background:{PANEL_BG};"
            f"border:1px solid {BORDER_COLOR};border-radius:4px;"
        )
        lv.addWidget(sec_lbl)

        self.section_list = QListWidget()
        self.section_list.currentRowChanged.connect(self._on_section_changed)
        lv.addWidget(self.section_list)
        splitter.addWidget(left)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{PANEL_BG};")
        splitter.addWidget(self.stack)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self._show_placeholder(tr("Conecte-se a um nó para ver as configurações."))

    def retranslate(self):
        """Update all labels after language change.

        If the node is loaded, rebuilds the entire config UI so that all
        section pages and field labels appear in the new language.
        Static header widgets are always updated regardless.
        """
        # Always update static header widgets
        if hasattr(self, "_title_lbl"):  self._title_lbl.setText(tr("⚙ Config. do No Local"))
        if hasattr(self, "_btn_reload"): self._btn_reload.setText(tr("🔄  Recarregar"))
        if hasattr(self, "btn_save"):    self.btn_save.setText(tr("💾  Guardar Alterações"))
        if hasattr(self, "_sec_lbl"):    self._sec_lbl.setText(tr("Secções"))

        if hasattr(self, "_local_node") and self._local_node:
            # Node is loaded — rebuild all section pages in the new language
            current_row = self.section_list.currentRow()
            self._build_config_ui()
            # Restore selected section
            if current_row >= 0 and current_row < self.section_list.count():
                self.section_list.setCurrentRow(current_row)
            self.status_label.setText(tr("✅ Configuração carregada"))
            self.btn_save.setEnabled(True)
        else:
            if hasattr(self, "status_label"):
                self.status_label.setText(tr("Não conectado"))
            # Refresh the placeholder text in the new language
            self._show_placeholder(tr("Conecte-se a um nó para ver as configurações."))

    def set_interface(self, iface):
        self._iface = iface
        self.reload_config()
        if hasattr(self, '_channels_tab_widget') and self._channels_tab_widget:
            self._channels_tab_widget.set_interface(iface)

    def clear_interface(self):
        self._iface      = None
        self._local_node = None
        self.btn_save.setEnabled(False)
        self.status_label.setText(tr("Não conectado"))
        if hasattr(self, '_channels_tab_widget') and self._channels_tab_widget:
            self._channels_tab_widget.clear_interface()
        self.section_list.clear()
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
        self._show_placeholder(tr("Conecte-se a um nó para ver as configurações."))

    def reload_config(self):
        if not self._iface:
            self._show_placeholder(tr("Conecte-se a um nó para ver as configurações."))
            return
        self.status_label.setText(tr("A carregar configuração…"))
        QTimer.singleShot(100, self._do_reload)

    def _do_reload(self):
        try:
            # Usa iface.localNode (propriedade viva) em vez de getNode("^local")
            # que pode devolver uma cópia desactualizada da cache ou None em
            # algumas versões da biblioteca meshtastic-python.
            # iface.localNode é o mesmo objecto usado internamente por writeConfig /
            # beginSettingsTransaction / commitSettingsTransaction, garantindo
            # que leitura e escrita operam sempre sobre o mesmo objecto.
            self._local_node = getattr(self._iface, "localNode", None)
            if self._local_node is None:
                # Fallback para versões antigas da biblioteca que não expõem localNode
                self._local_node = self._iface.getNode("^local")
            if not self._local_node:
                self._show_placeholder(tr("Não foi possível obter o nó local."))
                self.status_label.setText(tr("Erro: nó local indisponível"))
                return
            self._build_config_ui()
            self.btn_save.setEnabled(True)
            self.status_label.setText(tr("✅ Configuração carregada"))
        except Exception as e:
            logger.error(f"Error loading configuration: {e}", exc_info=True)
            self._show_placeholder(tr("err_load_config", err=e))
            self.status_label.setText(tr("❌ Erro ao carregar"))

    def _build_config_ui(self):
        self.section_list.clear()
        self._config_widgets.clear()
        while self.stack.count():
            self.stack.removeWidget(self.stack.widget(0))

        self.section_list.addItem(tr("📻 Canais"))
        self._channels_tab_widget = ChannelsTab()
        if self._iface:
            self._channels_tab_widget.set_interface(self._iface)
        self._channels_tab_widget.reboot_required.connect(self.reboot_required)
        self.stack.addWidget(self._channels_tab_widget)

        self.section_list.addItem(tr("👤 Usuário"))
        self.stack.addWidget(self._build_device_info_page())

        for sec_key, field_defs in MESHTASTIC_CONFIG_DEFS.items():
            label = get_section_label(sec_key)
            self.section_list.addItem(label)
            fields_with_values = self._read_section_values(sec_key, field_defs)
            page = self._build_section_page(sec_key, fields_with_values)
            self.stack.addWidget(page)

        if self.section_list.count() > 0:
            self.section_list.setCurrentRow(0)

    def _read_section_values(self, sec_key: str, field_defs: list) -> list:
        parts = sec_key.split('.', 1)
        if len(parts) != 2:
            return [(lbl, ft, fn, None, ex) for lbl, fn, ft, ex in field_defs]
        config_attr, _sub_attr = parts
        sub_obj = None
        try:
            cfg_root = getattr(self._local_node, config_attr, None)
            if cfg_root is not None:
                sub_obj = _resolve_sub_obj(cfg_root, sec_key)
        except Exception as e:
            logger.warning(f"Error accessing {sec_key}: {e}")

        # Tenta carregar as mensagens pré-definidas (campo especial via AdminMessage).
        # A biblioteca meshtastic-python guarda as canned messages em vários atributos
        # dependendo da versão; tentamos todos por ordem de preferência.
        canned_msgs_value = None
        if sec_key == "moduleConfig.cannedMessage" and self._iface:
            try:
                ln = self._local_node
                # Ordem de tentativa conforme versões da biblioteca:
                # 1. cannedPluginMessage — atributo principal em versões recentes
                # 2. cannedPluginMessageMessages — versões antigas
                # 3. get_canned_message() — méttodo que faz pedido ao dispositivo
                # 4. getCannedMessages() — alias nalgumas versões
                val = None
                for attr in ('cannedPluginMessage', 'cannedPluginMessageMessages',
                             '_cannedMessageModuleMessages'):
                    v = getattr(ln, attr, None)
                    if v and isinstance(v, str) and v.strip():
                        val = v.strip()
                        logger.debug(f"Canned messages from attr {attr!r}: {val!r}")
                        break
                if not val:
                    for method in ('get_canned_message', 'getCannedMessages'):
                        fn = getattr(ln, method, None)
                        if callable(fn):
                            try:
                                v = fn()
                                if v and isinstance(v, str) and v.strip():
                                    val = v.strip()
                                    logger.debug(f"Canned messages from {method}(): {val!r}")
                                    break
                            except Exception as me:
                                logger.debug(f"{method}() failed: {me}")
                canned_msgs_value = val or ""
                logger.debug(f"Canned messages loaded: {canned_msgs_value!r}")
            except Exception as e:
                logger.debug(f"Could not load canned messages: {e}")

        result = []
        for label, field_name, field_type, extra in field_defs:
            if field_name == "__canned_messages__":
                result.append((label, field_type, field_name, canned_msgs_value, extra))
                continue
            current_val = None
            if sub_obj is not None:
                try:
                    obj = sub_obj
                    for part in field_name.split('.'):
                        if obj is None:
                            break
                        obj = getattr(obj, part, None)
                    current_val = obj
                except Exception as e:
                    logger.debug(f"Could not read {sec_key}.{field_name}: {e}")

            # Para campos combo (enum), converte o int devolvido pelo protobuf para
            # o nome string correspondente.  O QComboBox é preenchido com strings
            # (ex: "CLIENT", "ROUTER") — se passarmos um int, findText falha e o
            # widget fica no índice 0 independentemente do valor real do nó.
            if field_type == "combo" and isinstance(current_val, int) and sub_obj is not None:
                try:
                    desc = sub_obj.DESCRIPTOR.fields_by_name.get(field_name)
                    if desc is not None and desc.enum_type is not None:
                        ev = desc.enum_type.values_by_number.get(current_val)
                        if ev is not None:
                            # Preferir o sufixo curto se existir na lista de opções (extra)
                            # para corresponder ao que está definido em MESHTASTIC_CONFIG_DEFS.
                            full_name = ev.name          # ex: "ROLE_CLIENT"
                            short_name = full_name.split("_")[-1]  # ex: "CLIENT"
                            if extra and short_name in extra:
                                current_val = short_name
                            elif extra and full_name in extra:
                                current_val = full_name
                            else:
                                current_val = short_name  # melhor esforço
                            logger.debug(f"Enum int->str: {sec_key}.{field_name} "
                                         f"{obj!r} -> {current_val!r}")
                except Exception as e:
                    logger.debug(f"Enum int->str failed for {sec_key}.{field_name}: {e}")

            result.append((label, field_type, field_name, current_val, extra))
        return result

    def _build_device_info_page(self) -> QWidget:
        sec_key = "__device_info__"
        self._config_widgets[sec_key] = {}
        page    = QWidget()
        page.setStyleSheet(f"background:{PANEL_BG};")
        scroll  = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{border:none;background:{PANEL_BG};}}")
        content = QWidget()
        content.setStyleSheet(f"background:{PANEL_BG};")
        form    = QFormLayout(content)
        form.setSpacing(12)
        form.setContentsMargins(16, 16, 16, 16)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        fields_ro, fields_rw = [], []
        try:
            my_info = self._iface.getMyNodeInfo() if self._iface else None
            if my_info:
                user      = my_info.get('user', {})
                fields_ro = [
                    (tr("ID do Nó"),  "id",       user.get('id', '—')),
                    (tr("Modelo HW"), "hw_model", user.get('hwModel', '—')),
                    (tr("Firmware"),  "firmware", str(my_info.get('firmwareVersion', '—'))),
                ]
                fields_rw = [
                    (tr("Nome Longo"),       "long_name",   user.get('longName', '')),
                    (tr("Nome Curto"),       "short_name",  user.get('shortName', '')),
                    (tr("Licenciado (Ham)"), "is_licensed", user.get('isLicensed', False)),
                ]
        except Exception as e:
            logger.warning(f"Error reading device info: {e}")
        for label, key, val in fields_ro:
            lbl = QLabel(str(val) if val is not None else "—")
            lbl.setStyleSheet(
                f"color:{ACCENT_BLUE};background:{DARK_BG};"
                f"border:1px solid {BORDER_COLOR};border-radius:4px;padding:4px 8px;"
            )
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(self._make_label(tr(label)), lbl)
        if fields_rw:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"color:{BORDER_COLOR};")
            form.addRow(sep)
            note = QLabel(tr("✏  Campos editáveis — guardar usa setOwner()"))
            note.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;font-style:italic;")
            form.addRow(note)
        for label, key, val in fields_rw:
            if isinstance(val, bool):
                w = QCheckBox()
                w.setChecked(bool(val))
                w._original_value = bool(val)
            else:
                w = QLineEdit(str(val) if val is not None else "")
                w._original_value = str(val) if val is not None else ""
            form.addRow(self._make_label(label), w)
            self._config_widgets[sec_key][key] = w
        scroll.setWidget(content)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        return page

    def _build_section_page(self, sec_key: str, fields: list) -> QWidget:
        self._config_widgets[sec_key] = {}
        page    = QWidget()
        page.setStyleSheet(f"background:{PANEL_BG};")
        scroll  = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{border:none;background:{PANEL_BG};}}")
        content = QWidget()
        content.setStyleSheet(f"background:{PANEL_BG};")
        form    = QFormLayout(content)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        if not fields:
            form.addRow(QLabel(tr("Nenhum campo disponível para esta secção.")))
        else:
            for label, field_type, field_name, current_val, extra in fields:
                w = self._create_field_widget(field_type, current_val, extra)
                if w:
                    form.addRow(self._make_label(tr(label)), w)
                    self._config_widgets[sec_key][field_name] = w
        scroll.setWidget(content)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        return page

    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text + ":")
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        return lbl

    # FIX-7: conversão explícita de enums e validação antes de setattr
    @staticmethod
    def _coerce_value(obj, field_name: str, value):
        """
        Converte `value` para o tipo correcto do campo protobuf `field_name`
        em `obj`, usando a API de reflexão do protobuf quando disponível.
        Retorna (coerced_value, error_str_or_None).
        """

        if value is None:
            return None, None

        # Tenta obter o descriptor do campo para verificar o tipo
        try:
            desc = obj.DESCRIPTOR.fields_by_name.get(field_name)
        except Exception:
            desc = None

        if desc is not None:
            ftype = desc.type
            # ENUM: converte string para int usando o descriptor
            if ftype == descriptor_module.FieldDescriptor.TYPE_ENUM:
                enum_type = desc.enum_type
                if isinstance(value, str):
                    # 1. Tentativa directa
                    ev = enum_type.values_by_name.get(value)
                    if ev is not None:
                        return ev.number, None
                    # 2. Tenta com prefixos comuns do protobuf Meshtastic
                    #    ex: 'DEC' → 'GPS_FORMAT_DEC', 'DEFAULT' → 'CODEC2_DEFAULT'
                    uval = value.upper()
                    for v in enum_type.values:
                        vname = v.name.upper()
                        # Correspondência por sufixo: o nome do enum termina com _VALUE
                        if vname == uval or vname.endswith('_' + uval):
                            return v.number, None
                    # 3. Tenta por número
                    try:
                        int_val = int(value)
                        if any(v.number == int_val for v in enum_type.values):
                            return int_val, None
                    except (ValueError, TypeError):
                        pass
                    # 4. Usa o valor 0 (default do protobuf) e regista aviso leve
                    #    em vez de bloquear o save completo
                    default_v = next((v for v in enum_type.values if v.number == 0), None)
                    if default_v is not None:
                        logger.debug(f"Enum '{value}' not recognised for {field_name}, using default {default_v.name}")
                        return default_v.number, None
                    return None, f"Valor de enum inválido '{value}' para {field_name}"
                try:
                    return int(value), None
                except (ValueError, TypeError):
                    return None, f"Não foi possível converter '{value}' para enum {field_name}"

            # BOOL
            if ftype == descriptor_module.FieldDescriptor.TYPE_BOOL:
                if isinstance(value, bool):
                    return value, None
                if isinstance(value, str):
                    return value.lower() in ('true','1','yes'), None
                return bool(value), None

            # INT / UINT / SINT
            int_types = {
                descriptor_module.FieldDescriptor.TYPE_INT32,
                descriptor_module.FieldDescriptor.TYPE_INT64,
                descriptor_module.FieldDescriptor.TYPE_UINT32,
                descriptor_module.FieldDescriptor.TYPE_UINT64,
                descriptor_module.FieldDescriptor.TYPE_SINT32,
                descriptor_module.FieldDescriptor.TYPE_SINT64,
                descriptor_module.FieldDescriptor.TYPE_FIXED32,
                descriptor_module.FieldDescriptor.TYPE_FIXED64,
                descriptor_module.FieldDescriptor.TYPE_SFIXED32,
                descriptor_module.FieldDescriptor.TYPE_SFIXED64,
            }
            if ftype in int_types:
                try:
                    return int(value), None
                except (ValueError, TypeError):
                    return None, f"Valor inteiro inválido '{value}' para {field_name}"

            # FLOAT / DOUBLE
            if ftype in (descriptor_module.FieldDescriptor.TYPE_FLOAT,
                         descriptor_module.FieldDescriptor.TYPE_DOUBLE):
                try:
                    return float(value), None
                except (ValueError, TypeError):
                    return None, f"Valor float inválido '{value}' para {field_name}"

            # STRING / BYTES
            if ftype == descriptor_module.FieldDescriptor.TYPE_STRING:
                return str(value), None
            if ftype == descriptor_module.FieldDescriptor.TYPE_BYTES:
                if isinstance(value, (bytes, bytearray)):
                    return bytes(value), None
                try:
                    return bytes.fromhex(str(value)), None
                except ValueError:
                    return str(value).encode(), None

        # Sem descriptor protobuf — tenta inferir o tipo correcto pelo valor
        # actual do campo no objecto (ex: o nó já tem um int → convertemos para int).
        # Sem esta inferência, um QSpinBox devolve int (OK), um QComboBox devolve
        # string (não OK para campos enum), e um QCheckBox devolve bool (OK).
        # O setattr com o tipo errado pode falhar silenciosamente no protobuf.
        try:
            current_field_val = getattr(obj, field_name, None)
        except Exception:
            current_field_val = None

        if current_field_val is not None:
            target_type = type(current_field_val)
            if target_type == int and not isinstance(value, int):
                try:
                    return int(value), None
                except (ValueError, TypeError):
                    logger.debug(f"_coerce_value (no desc): cannot cast {value!r} to int "
                                 f"for {field_name}, passing as-is")
            elif target_type == float and not isinstance(value, float):
                try:
                    return float(value), None
                except (ValueError, TypeError):
                    logger.debug(f"_coerce_value (no desc): cannot cast {value!r} to float "
                                 f"for {field_name}, passing as-is")
            elif target_type == bool and not isinstance(value, bool):
                return bool(value), None
            elif target_type == str and not isinstance(value, str):
                return str(value), None
            # bytes/bytearray — sem conversão automática, passa tal qual
        else:
            logger.debug(f"_coerce_value (no desc): {field_name} not found on obj "
                         f"{type(obj).__name__}, passing {value!r} as-is")

        return value, None

    def _save_config(self):
        if not self._iface or not self._local_node:
            QMessageBox.warning(self, tr("Sem Conexão"), tr("Não está conectado a nenhum nó."))
            return
        reply = QMessageBox.question(
            self, tr("Guardar Configuração"),
            (tr("Deseja guardar todas as alterações de configuração no nó?\n\n")
             + tr("⚠  O nó irá reiniciar após guardar para aplicar as configurações.\n")
             + tr("A ligação TCP será temporariamente perdida e restabelecida.")),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # ── Collect all widget values in the UI thread ────────────────────
        # Widget access must happen here (UI thread). Only the blocking
        # network calls (writeConfig, commit, setOwner) go to the worker thread.
        collected = {}   # sec_key → {field_name: coerced_value}
        errors_collect = []
        owner_long = owner_short = None
        owner_licensed = False
        owner_licensed_changed = False

        dev_w = self._config_widgets.get("__device_info__", {})
        if dev_w:
            for key, w in dev_w.items():
                val = self._get_widget_value(w)
                original = getattr(w, '_original_value', None)
                # Só inclui se o valor foi realmente alterado pelo utilizador
                if key == "long_name":
                    if original is None or val != original:
                        owner_long = val
                elif key == "short_name":
                    if original is None or val != original:
                        owner_short = val
                elif key == "is_licensed":
                    licensed_val = bool(val)
                    if original is None or licensed_val != original:
                        owner_licensed = licensed_val
                        # marca que is_licensed mudou (usa flag separada)
                        owner_licensed_changed = True

        for sec_key, fields_widgets in self._config_widgets.items():
            if sec_key == "__device_info__" or not fields_widgets:
                continue
            parts = sec_key.split('.', 1)
            if len(parts) != 2:
                continue
            config_attr, sub_attr = parts
            cfg_root = getattr(self._local_node, config_attr, None)
            if cfg_root is None:
                continue
            sub_obj = _resolve_sub_obj(cfg_root, sec_key)
            if sub_obj is None:
                errors_collect.append(f"Secção {sec_key} não encontrada no nó")
                logger.warning(f"_save_config: could not resolve sub_obj for {sec_key}")
                continue

            sec_fields = {}
            for field_name, widget in fields_widgets.items():
                if field_name == "__canned_messages__":
                    raw_msgs = self._get_widget_value(widget)
                    if raw_msgs is None:
                        continue
                    raw_msgs = raw_msgs.strip()
                    # Compara com o valor original que foi carregado do nó.
                    # O container guarda _original_value (pipe-string) definido
                    # em _create_field_widget — se for igual, não há alteração.
                    original = getattr(widget, '_original_value', None)
                    if original is not None and raw_msgs == original:
                        logger.debug(f"  [{sec_key}] __canned_messages__: sem alteração, skipping")
                        continue
                    sec_fields[field_name] = raw_msgs
                    continue
                raw_value = self._get_widget_value(widget)
                if raw_value is None:
                    continue
                obj = sub_obj
                field_parts = field_name.split(".")
                for part in field_parts[:-1]:
                    obj = getattr(obj, part, None)
                    if obj is None:
                        break
                if obj is None:
                    logger.debug(f"  [{sec_key}] {field_name}: obj is None, skipping")
                    continue
                last = field_parts[-1]
                if not hasattr(obj, last):
                    logger.debug(f"  [{sec_key}] {field_name}: no attr {last!r}, skipping")
                    continue
                coerced, err = self._coerce_value(obj, last, raw_value)
                if err:
                    errors_collect.append(f"{sec_key}.{field_name}: {err}")
                    continue
                if coerced is None:
                    logger.debug(f"  [{sec_key}] {field_name}: coerced is None, skipping")
                    continue
                # Detecção de alteração: compara o valor actual do nó com o valor
                # coerced do widget.  Ambos devem ser do mesmo tipo após _coerce_value;
                # se não houver descritor protobuf disponível, _coerce_value devolve o
                # valor Python directo (pode ser string para combos) enquanto o nó
                # guarda um int — nesse caso forçamos conversão int para garantir
                # comparação correcta e evitar falsos "sem alteração".
                try:
                    current = getattr(obj, last)
                    # Normaliza tipos antes de comparar para evitar int != "CLIENT"
                    cur_cmp = current
                    coe_cmp = coerced
                    if type(current) != type(coerced):
                        try:
                            cur_cmp = type(coerced)(current)
                        except (ValueError, TypeError):
                            try:
                                coe_cmp = type(current)(coerced)
                            except (ValueError, TypeError):
                                pass  # compara como estão, melhor que nada
                    if cur_cmp == coe_cmp:
                        logger.debug(f"  [{sec_key}] {field_name}: sem alteração "
                                     f"({current!r} == {coerced!r}), skipping")
                        continue   # no change — skip this field
                except Exception:
                    pass
                logger.debug(f"  [{sec_key}] {field_name}: {getattr(obj, last, '?')!r} → {coerced!r}")
                # Guarda field_parts e coerced — NÃO o obj resolvido no UI thread.
                # O worker vai re-resolver o caminho a partir do seu self._node,
                # garantindo que o setattr e o CopyFrom dentro de writeConfig
                # operam sempre sobre o mesmo objecto em memória.
                sec_fields[field_name] = (field_parts, coerced)
            if sec_fields:
                collected[sec_key] = sec_fields
                logger.info(f"Collected section {sec_key} with changes: {list(sec_fields.keys())}")
            else:
                logger.debug(f"Section {sec_key}: no changes detected")

        self.status_label.setText(tr("A guardar…"))
        self.btn_save.setEnabled(False)

        # Resolve sempre iface.localNode no momento do save — garante que usamos
        # o mesmo objecto vivo que a biblioteca meshtastic-python usa para
        # writeConfig/commit, mesmo que _local_node tenha sido obtido num
        # momento anterior (ex: antes de um reboot do nó).
        iface_ref = self._iface
        local_node_ref = getattr(iface_ref, "localNode", None) or self._local_node

        # Using module-level _ConfigSaveWorker (not a locally-defined class)
        # so PyQt5's meta-object system correctly delivers signals across threads.
        self._cfg_save_thread = QThread()
        self._cfg_save_worker = _ConfigSaveWorker(
            local_node_ref, iface_ref, collected,
            owner_long, owner_short, owner_licensed, owner_licensed_changed, errors_collect
        )
        self._cfg_save_worker.moveToThread(self._cfg_save_thread)
        self._cfg_save_thread.started.connect(self._cfg_save_worker.run)
        self._cfg_save_worker.finished.connect(self._on_save_config_finished)
        self._cfg_save_worker.finished.connect(self._cfg_save_thread.quit)
        self._cfg_save_worker.finished.connect(self._cfg_save_worker.deleteLater)
        self._cfg_save_thread.finished.connect(self._cfg_save_thread.deleteLater)
        self._cfg_save_thread.start()

    def _on_save_config_finished(self, saved_sections: set, write_config_count: int, errors: list):
        self.btn_save.setEnabled(True)

        # Separa secções de configuração reais (que geraram writeConfig())
        # das entradas especiais que usam outras vias (setOwner, setCannedMessages)
        special = {"owner", "canned_messages_text"}
        config_sections = sorted(s for s in saved_sections if s not in special)
        extras = [s for s in saved_sections if s in special]

        if saved_sections:
            # Status bar: resumo compacto
            parts = []
            if write_config_count:
                parts.append(f"{write_config_count} writeConfig()")
            if "owner" in extras:
                parts.append(tr("nome"))
            if "canned_messages_text" in extras:
                parts.append(tr("msgs"))
            self.status_label.setText("✅ " + (" + ".join(parts) if parts else tr("guardado")))

            # Diálogo: detalhe completo do que foi enviado ao nó
            msg = tr("Configuração guardada com sucesso!")

            if write_config_count:
                names = [SECTION_WRITE_NAME.get(s, s.split(".")[-1])
                         for s in config_sections]
                msg += f"\n\n{tr('writeConfig() enviados')}: {write_config_count}"
                msg += "\n  • " + "\n  • ".join(names)

            if "owner" in extras:
                msg += f"\n  • {tr('setOwner (nome do nó)')}"
            if "canned_messages_text" in extras:
                msg += f"\n  • {tr('setCannedMessages')}"

            if errors:
                msg += f"\n\n⚠ {len(errors)} aviso(s):\n" + "\n".join(errors[:8])

            QMessageBox.information(self, tr("Configuração Guardada"), msg)
            self.reboot_required.emit()
        else:
            self.status_label.setText(tr("⚠ Nada guardado"))
            msg = tr("Não foram detectadas alterações para guardar.")
            if errors:
                msg += f"\n\n{tr('Erros')}:\n" + "\n".join(errors[:8])
            QMessageBox.information(self, tr("Sem Alterações"), msg)

    def _on_section_changed(self, row: int):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _create_field_widget(self, field_type: str, current_val, extra) -> Optional[QWidget]:
        if field_type == "readonly":
            lbl = QLabel(str(current_val) if current_val is not None else "—")
            lbl.setStyleSheet(
                f"color:{ACCENT_BLUE};background:{DARK_BG};"
                f"border:1px solid {BORDER_COLOR};border-radius:4px;padding:4px 8px;font-size:12px;"
            )
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            return lbl
        elif field_type == "text":
            w = QLineEdit()
            w.setText(str(current_val) if current_val is not None else "")
            return w
        elif field_type == "bool":
            w = QCheckBox()
            if current_val is not None:
                w.setChecked(bool(current_val))
            return w
        elif field_type == "spin_int":
            w  = QSpinBox()
            lo, hi = (extra[0], extra[1]) if extra and isinstance(extra, tuple) else (0, 2147483647)
            lo = max(lo, -2147483648)
            hi = min(hi,  2147483647)
            w.setRange(lo, hi)
            if current_val is not None:
                try:
                    v = int(current_val)
                    w.setValue(max(lo, min(hi, v)))
                except (TypeError, ValueError, OverflowError):
                    pass
            return w
        elif field_type == "spin_float":
            w = QDoubleSpinBox()
            if extra and isinstance(extra, tuple):
                w.setRange(extra[0], extra[1])
            else:
                w.setRange(-1e9, 1e9)
            w.setDecimals(4)
            if current_val is not None:
                try:
                    w.setValue(float(current_val))
                except (TypeError, ValueError):
                    pass
            return w
        elif field_type == "combo":
            w = QComboBox()
            if extra and isinstance(extra, list):
                w.addItems(extra)
            if current_val is not None:
                # current_val chega sempre como string após a conversão enum int→str
                # feita em _read_section_values.  Procura pelo texto exacto primeiro;
                # se não encontrar (enum desconhecido) tenta por índice numérico como
                # último recurso para não deixar o combo em branco.
                val_str = str(current_val)
                idx = w.findText(val_str)
                if idx >= 0:
                    w.setCurrentIndex(idx)
                else:
                    # Tentativa por sufixo: "ROLE_CLIENT" → encontra "CLIENT"
                    for i in range(w.count()):
                        if w.itemText(i) and val_str.endswith(w.itemText(i)):
                            w.setCurrentIndex(i)
                            break
                    else:
                        logger.debug(f"combo: no match for {val_str!r} in {extra}")
            return w
        elif field_type == "canned_messages":
            # Widget especial para mensagens pré-definidas separadas por '|'
            # Mostra em área de texto multiline, cada linha = uma mensagem
            container = QWidget()
            container.setObjectName("canned_messages_widget")
            vl = QVBoxLayout(container)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(4)

            note = QLabel(
                tr("canned_hint")
            )
            note.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;font-style:italic;")
            note.setWordWrap(True)
            vl.addWidget(note)

            te = QTextEdit()
            te.setObjectName("canned_te")
            te.setPlaceholderText(
                tr("canned_placeholder")
            )
            te.setFixedHeight(130)
            te.setStyleSheet(
                f"QTextEdit{{background:{INPUT_BG};color:{TEXT_PRIMARY};"
                f"border:1px solid {BORDER_COLOR};border-radius:6px;padding:6px;font-size:12px;}}"
            )
            # Popula com o valor actual (pipe-separated → newlines)
            if current_val and isinstance(current_val, str) and current_val.strip():
                msgs = [m.strip() for m in current_val.split('|') if m.strip()]
                te.setPlainText('\n'.join(msgs))

            char_label = QLabel(tr("0 / 200 caracteres"))
            char_label.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")

            def _update_count():
                pipe_str = '|'.join(
                    line.strip()
                    for line in te.toPlainText().split('\n')
                    if line.strip()
                )
                n = len(pipe_str)
                color = ACCENT_GREEN if n <= 200 else ACCENT_RED
                char_label.setText(tr("{n} / 200 caracteres", n=n))
                char_label.setStyleSheet(f"color:{color};font-size:10px;")

            te.textChanged.connect(_update_count)
            _update_count()

            vl.addWidget(te)
            vl.addWidget(char_label)
            container._te = te            # referência para _get_widget_value
            # Guarda o valor original (pipe-string) para detecção de alteração
            # em _save_config — sem isto qualquer save envia sempre as msgs mesmo
            # sem alteração, porque "" != None passa sempre na condição.
            original_pipe = '|'.join(
                [m.strip() for m in current_val.split('|') if m.strip()]
            ) if current_val and isinstance(current_val, str) else ''
            container._original_value = original_pipe
            return container
        return None

    def _get_widget_value(self, widget: QWidget):
        if isinstance(widget, QLabel):        return None
        elif isinstance(widget, QLineEdit):   return widget.text()
        elif isinstance(widget, QCheckBox):   return widget.isChecked()
        elif isinstance(widget, QSpinBox):    return widget.value()
        elif isinstance(widget, QDoubleSpinBox): return widget.value()
        elif isinstance(widget, QComboBox):   return widget.currentText()
        elif isinstance(widget, QTextEdit):   return widget.toPlainText()
        elif isinstance(widget, QWidget) and widget.objectName() == "canned_messages_widget":
            te = getattr(widget, '_te', None)
            if te is None:
                return None
            # Converte newlines → pipe, filtra linhas vazias
            lines = [l.strip() for l in te.toPlainText().split('\n') if l.strip()]
            return '|'.join(lines)
        return None

    def _show_placeholder(self, text: str):
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
        self.section_list.clear()
        placeholder = QWidget()
        layout      = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:14px;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        self.stack.addWidget(placeholder)