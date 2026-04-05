# Changelog

All notable changes to **MeshDeck** are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.2-beta.1] — 2026-04-05

### Added

- **GPS position refresh button (🔄) in the Navigation tab** — the Local Node
  card now has a dedicated button to re-read the GPS position from the node
  at any time, without reconnecting:
  - Reads from `nodesByNum[local_num]['position']` (daemon cache, updated with
    each POSITION_APP packet received from the firmware GPS)
  - Falls back to `localConfig.position.fixed_lat/lon` for nodes with a fixed
    position configured
  - Button shows `⏳ Reading position…` while active, re-enables on result
  - If no position is found, a 3-second warning is shown in the position label
  - New signal `local_position_updated(lat, lon, alt, found)` in `MeshtasticWorker`
  - New method `refresh_local_position()` in `MeshtasticWorker`
  - Full PT/EN i18n: `nav_refresh_pos`, `nav_refresh_pos_tooltip`,
    `nav_pos_refreshing`, `nav_pos_not_found`, `nav_pos_refreshed`

- **USB Serial connection mode** — the Connection dialog now has two tabs:
  - **🌐 TCP/IP Network** — existing behaviour, connect to any `meshtasticd`
    host/port (AIO board, remote daemon, etc.)
  - **🔌 USB Serial** — connect directly to a Meshtastic device plugged via USB,
    without requiring the AIO board or a running `meshtasticd` daemon
- **`meshtastic_bridge.py`** — USB-to-TCP bridge that reads the Meshtastic serial
  stream protocol from the device, strips debug/log noise, and re-emits clean
  frames to TCP clients on `127.0.0.1:4403`. Supports simultaneous TCP clients
  (broadcast mode). Compatible with all known Meshtastic hardware:
  - Espressif ESP32/S2/S3/C3 (VID `303a`)
  - Silicon Labs CP210x — HELTEC, LILYGO, RAK (VID `10c4`)
  - FTDI FT232 — DIY / dev boards (VID `0403`)
  - CH340 / CH341 — common Chinese boards (VID `1a86`)
  - Prolific PL2303 — older clones (VID `067b`)
  - Adafruit nRF52840 (VID `239a`)
  - RAK Wireless nRF52840 (VID `2fe3`)
  - Arduino (VID `2341`)
  - Device-name heuristics: `heltec`, `rak`, `lilygo`, `t-beam`, `meshtastic`
  - CLI flags: `--port`, `--baud`, `--host`, `--tcp-port`, `--verbose`, `--list`
- **Serial port auto-detection** in the connection dialog using
  `serial.tools.list_ports`; Meshtastic-likely ports appear first; refresh
  button (🔄) to rescan without reopening the dialog
- **Bridge lifecycle management:**
  - Bridge is launched as a subprocess from within MeshDeck
  - `_poll_bridge` verifies the TCP socket is accepting connections before
    enabling the Connect button
  - `closeEvent` in `MainWindow` terminates the bridge cleanly on normal exit
  - `_kill_stale_bridge` kills any orphaned bridge process from a previous abrupt
    session — cross-platform: `psutil` → `lsof` → `ss`/`fuser`/`/proc/net/tcp` → `netstat`
- **Serial mode indicator** in the connection status badge —
  `🟢 127.0.0.1:4403 · 🔌 Serial` when connected via Serial
- **1.5 s stabilisation delay** before `TCPInterface` creation in Serial mode
- **Bridge log file** written to the OS temp directory (`meshdeck_bridge.log`)
- `pyserial >= 3.5` added to `requirements.txt`

### Fixed

- **Configuration tab — critical save pipeline rewrite** (`tab_config.py`):
  - **Root cause fixed:** `writeConfig("mqtt")` does `CopyFrom(self.moduleConfig.mqtt)`
    internally — it reads from the node object, not from any external reference.
    Previously the worker received `(obj, last, coerced)` where `obj` was resolved
    in the UI thread and could diverge from the node's live object. Now the worker
    stores `(field_parts, coerced)` and re-resolves the path from `self._node` at
    save time, guaranteeing `setattr` and `CopyFrom` operate on the same object.
  - **Proto3 bool=False serialisation:** fields set to `False` (protobuf default)
    were not serialised on the wire — firmware received absence of field and kept
    previous value. Fixed via double-set technique: `setattr(True)` → `setattr(False)`
    forces the field into `ListFields()` so `CopyFrom` includes it.
  - **`setOwner` called unconditionally:** now only called when `long_name`,
    `short_name` or `is_licensed` actually changed vs. the value loaded from the node.
  - **Enum fields displayed wrong:** `_read_section_values` now converts int enum
    values to their string names using the protobuf DESCRIPTOR before populating
    combo widgets; `_create_field_widget` simplified to use `findText` directly.
  - **Sub-object resolution unified:** `_resolve_sub_obj()` helper with explicit
    `SECTION_ATTR_NAME` map replaces fragmented camelCase/snake_case/write_name
    guessing in both `_read_section_values` and `_save_config`.
  - **`iface.localNode` used instead of `getNode("^local")`:** avoids stale
    cache copies; fallback to `getNode` kept for older library versions.
  - **Canned messages always sent even without changes:** widget now stores
    `_original_value` (pipe-string) at build time; `_save_config` compares before
    including in payload.
  - **Canned messages not loading from node:** loading logic now tries
    `cannedPluginMessage`, `cannedPluginMessageMessages`,
    `_cannedMessageModuleMessages`, `get_canned_message()`, `getCannedMessages()`
    in order of preference.
  - **`proxy_to_client_enabled` behaviour clarified:** field is now read-only in
    the UI with an explanatory note — it requires the client to implement the
    `mqttClientProxyMessage` relay protocol, which MeshDeck does not yet support.
    Planned for a future release.

- **Configuration field audit** — all sections cross-checked against the official
  `config.proto` and `module_config.proto`. Removed fields that do not exist in
  the protobuf schema (would silently fail `setattr` and never reach the firmware):
  - `moduleConfig.mqtt`: removed `map_reporting_enabled`, `map_report_settings.*`,
    `ok_to_mqtt`
  - `moduleConfig.serial`: removed `WS85` from mode enum
  - `moduleConfig.storeForward`: removed `is_server`
  - `moduleConfig.telemetry`: removed `health_update_interval`,
    `health_telemetry_enabled`
  - `moduleConfig.neighborInfo`: removed `transmit_over_lora`
  - `localConfig.display`: removed `compass_north_top`, `backlight_secs`,
    `tft_brightness`
  - `moduleConfig.cannedMessage`: removed `FN_1`–`FN_12`, `NUMPAD_0`–`NUMPAD_9`
    from `InputEventChar` enum

- **Save confirmation dialog** now shows exactly what was sent to the node:
  number of `writeConfig()` calls with section names, `setOwner` if name changed,
  `setCannedMessages` if canned messages changed — instead of a single confusing
  count that mixed all three.

### Credits

- Serial bridge concept and original code by
  **[@KMX415](https://github.com/KMX415)** on GitHub. Adapted and extended for
  MeshDeck with multi-client broadcast, cross-platform device detection, CLI
  interface, and integration into the connection dialog.

---

## [1.0.1-beta.1] — 2026-03-29

### Added

- **Navigation tab (🧭)** — real-time compass with bearing and distance to any
  selected node; Local Node and Target cards centred vertically in their boxes
  with name, GPS coordinates, altitude, SNR (colour-coded green/orange/red), and
  GPS status; GPS node table with equal-width columns filling the full panel
  width, sorted by distance from the local node
- **Immediate connection feedback** — status bar shows
  `"🔌 Connecting to host:port…"` and the connection indicator turns orange
  immediately when Connect is clicked, before the TCP socket is created;
  `TCPInterface` creation is deferred via `QTimer.singleShot(50)` so the UI
  paints the message first
- **Deferred NodeDB load** — `_sync_nodedb()` is called via
  `QTimer.singleShot(0)` so the Qt event loop paints the status bar before the
  heavy batch starts; status bar shows `"⏳ Loading network nodes… (N received)"`
  progressively and `"✅ Network ready — N nodes loaded"` when complete
- **GPS warning messages** on the navigation tab when the local node has no
  position (GPS disabled or awaiting first fix), in both PT and EN
- `nav_gps_active`, `nav_no_pos_warn` keys added to i18n
- Status bar keys `status_connecting`, `status_loading_nodes`, `status_ready`
  added to i18n in PT and EN

### Changed

- **Node list performance (CM4):**
  - Sorting suspended during batch load (`setSortingEnabled(False/True)`)
  - `QAbstractItemView.ScrollPerPixel` for smooth pixel-level scrolling
  - 12 pre-allocated `QColor` module constants replace per-cell allocations in
    `NodeTableModel.data()`
  - `_display_value` rewritten as direct `if/elif` — eliminates per-call
    dict+lambda allocation
  - `datetime.now()` cached once per `_update_node_count` cycle (`_cached_now`)
    instead of being called per visible cell during scroll
- **DM list batch mode** — `set_batch_mode(True/False)` suppresses N
  `_refresh_dm_list` calls during the initial node batch; a single rebuild runs
  at the end
- **Navigation tab debounce** increased 500 ms → 800 ms for CM4; `_rebuild_table`
  and compass/panel refreshes skipped when the tab is hidden, deferred to
  `showEvent`
- **Multi-row highlight fix** — `refresh_all()` clears all `_selected_highlight`
  flags before `beginResetModel`
- Local GPS position applied **once per batch**, avoiding N compass redraws
- Navigation Local Node and Target cards: content centred vertically
- Spelling: `"favourite/favourites"` → `"favorite/favorites"` throughout EN strings

### Fixed

- `setUniformRowHeights` crash — method does not exist on `QTableView`; removed
- `ScrollPerPixel` corrected to `QAbstractItemView.ScrollPerPixel`
- Navigation tab labels not cleared when no target is selected
- `nav_gps_active` was displaying as literal text instead of the translated value

---

## [1.0.0-beta.1] — 2026-03-27

First public release.

### Added

- **Real-time node list** with 14 columns, local node pinned at top, favorites
  managed directly in firmware (`setFavorite` / `removeFavorite`)
- **Interactive Leaflet map** with 4 themes (Dark, Light, OpenStreetMap,
  Satellite), colour-coded markers, traceroute overlays, NeighborInfo
  neighbourhood lines, and a built-in legend
- **Messaging** — channel messages (indices 0–7) and direct messages with
  automatic PKI (E2E) / PSK fallback, ACK/NAK indicators, unread badge, and
  date separators
- **Traceroutes** — send from node list or map popup, result dialog with
  per-segment SNR, GPS indicators, and "Show on Map" button; 30 s cooldown
- **Full node configuration** — all 21 firmware sections plus Channels and User
  tabs; atomic save with single reboot
- **10 real-time metric sections** auto-refreshing every 5 s via JavaScript
- **Internationalisation (i18n)** — full PT/EN coverage; language selectable in
  the connection dialog, saved via `QSettings`
- **Automatic reconnection** with exponential backoff (15 s → 30 s → 60 s →
  120 s) and 12 s watchdog per attempt
- **Sound notifications** on new messages with cross-platform fallback chain
- **Log console** — floating window with real-time TCP communication log,
  keyword filter, and line-count indicator
- Wayland-compatible
- Optimised for **ClockworkPi uConsole CM4**

### Technical

- Modular architecture: `main.py`, `worker.py`, `models.py`, `constants.py`,
  `dialogs.py`, `i18n.py`, `tabs/`
- `FirmwareFavorites` — favorites persisted in firmware NodeDB; no local JSON
- Tab indices centralised as class constants in `MainWindow`
- `my_node_id_ready` signal emitted exactly once per connection
- All log messages in English

---

## Notes

> This is a **beta** release. The application has been tested on real hardware
> (ClockworkPi uConsole CM4) with a live Meshtastic network. Expect occasional
> rough edges; bug reports and pull requests are welcome.

[1.0.2-beta.1]: https://github.com/tiuksferve/MeshDeck/releases/tag/v1.0.2-beta.1
[1.0.1-beta.1]: https://github.com/tiuksferve/MeshDeck/releases/tag/v1.0.1-beta.1
[1.0.0-beta.1]: https://github.com/tiuksferve/MeshDeck/releases/tag/v1.0.0-beta.1
