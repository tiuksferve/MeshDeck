# Changelog

All notable changes to **MeshDeck** are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.3-beta] — 2026-04-10

### Added

- **🏠 Local Node metrics section** — new dedicated section (position 2 in the
  sidebar, right after Overview) showing all key metrics of the local node in
  one place:
  - **Identification bar:** ID, short name, hardware model, uptime (counts up
    live every second via `setInterval` without any Python roundtrip), GPS
    coordinates
  - **KPI row 1 — Hardware/Health:** battery level with voltage, channel
    utilization (Ch. Util.), and airtime TX (Air TX, last 10 min)
  - **Duty Cycle/h (estimated):** progress bar relative to the EU 10%/hour
    legal limit (ETSI EN300.220), with colour-coded status (green < 7% /
    orange 7–10% / red ≥ 10%); formula: `airUtilTx × 6`; note explaining the
    extrapolation
  - **KPI row 2 — RF & TX:** avg/min/max received SNR, messages sent with
    ACK/NAK/relay breakdown, delivery rate, avg RTT and median RTT
  - **Duty Cycle/h history chart** — line chart showing the duty cycle trend
    over time with EU limit (10%) and warning (7%) reference lines; always
    rendered (even before data arrives) to prevent layout flash
  - All labels fully translated (PT/EN) via `tr()`; JS update labels passed in
    `_data_local_node()` payload so language switching works without reload
  - Data sourced via `_feed_local_node_metrics()` reading directly from
    `iface.nodesByNum` — bypasses the worker loopback filter that discards
    TELEMETRY_APP from the local node
  - Dedicated `_local_metrics_timer` (15 s) separate from the NodeDB poll
    (30 s), started/stopped with the connection lifecycle

- **Metrics — complete audit and precision improvements:**
  - **P10 percentile corrected** from `n//10` to `int(0.1*(n-1))` — for
    n=15 the old formula gave index 1 (≈P13); now gives the correct P10
  - **`_duplicates` windowed** — previously a cumulative counter (grew without
    bound); now computed dynamically from `_pkt_ids` (5-minute window) via
    `_count_duplicates()`, making the flood rate metric meaningful in long
    sessions
  - **ROUTING_APP NAK split into three counters:**
    - `_routing_acks` — ACK with `requestId`, no error (real delivery confirm)
    - `_routing_naks` — NAK with `requestId` + `errorReason` (delivery failure)
    - `_routing_fw_errs` — `errorReason` without `requestId` (internal firmware
      errors: `NO_ROUTE`, `MAX_RETRANSMIT`, etc.)  
    The Reliability section now shows all three separately
  - **`_ch_util` / `_air_tx` TTL expiry** — values older than 30 minutes are
    excluded from averages and KPIs via `_ch_util_active()` /
    `_air_tx_active()` helpers; nodes that go offline no longer distort the
    network averages indefinitely
  - **`n_gps_unique` now counts `_node_pos`** (validated coordinates) instead
    of POSITION_APP packet count — filters out (0, 0) and invalid coords
  - **`ingest_node_position` validates coordinates** — rejects `(0, 0)` and
    near-zero values (< 0.001°) that indicate no GPS fix
  - **`_node_pos` initialised in `_reset_data()`** — previously lazy-initialised;
    "Clear data" now correctly wipes GPS positions
  - **`_ch_util_ts` series appended after merge** — previously appended inside
    the `TELEMETRY_APP` branch before `node_data` override; now appended after
    the unified single-source read, ensuring the series reflects the final value
  - **Duty cycle note** in Channel & Airtime clarified — label changed to
    "estimated hourly duty cycle (10-min extrapolation)" throughout

- **Metrics — Latency section JS update** — `_metricsUpdateData` for the
  Latency section was previously empty (KPIs only updated on manual reload);
  now updates RTT avg/median/P90/min/max and the histogram chart every 5 s

- **Metrics — Overview table column fix** — "Top Nodes" table was misaligned
  after the first 5 s JS update: the Python initial render had 4 columns but
  the JS rebuild generated 5 (added separate ID column). Both are now aligned
  at 5 columns (ID · Name · Packets · Ch. Util. · Battery)

- **Metrics — Channel & Airtime duty cycle KPI fix** — the "Worst Node" KPI
  card showed the correct value on initial render but switched to the network
  average (`duty_avg`) after the first JS update. Fixed: `_data_channel()` now
  exports `worst_dc` and `worst_name`; the JS update uses `d.worst_dc`

### Changed

- **Metrics refresh strategy for Local Node** — uses `setHtml` with a MD5 hash
  guard instead of `runJavaScript`. The `QWebEngineView` with injected `setHtml`
  content creates an `about:blank` origin context; `window._metricsUpdateData`
  was unreliable across reloads. The hash compares `ch_util`, `air_tx`,
  `dc_est`, `battery`, `msgs_sent`, `msgs_acked`, `snr_rx_avg`, `delivery` —
  `setHtml` only fires when something actually changed, preventing unnecessary
  flash

- **Uptime counter is now live** — `_data_local_node()` exports `uptime_raw`
  (seconds from firmware) and `uptime_ts` (epoch when read); a `setInterval(1000)`
  in the page JS increments the display every second; `_metricsUpdateData`
  updates `_uptimeRaw`/`_uptimeTs` on each payload so the counter stays synced

- **`_on_local_node_ready`** now calls `_feed_local_node_metrics()` immediately
  after connection — local node telemetry is visible as soon as the connection
  is established, without waiting for the first 15 s poll

- **`_poll_nodedb`** (30 s) no longer includes local metrics polling; replaced
  by dedicated `_local_metrics_timer` (15 s)

### Fixed

- **Local Node section stuck on wait screen** — `local_node` re-added to
  `_WAITING_SECTIONS`; `set_local_node_id()` now resets `_was_waiting` and
  calls `_refresh_current()` immediately, triggering the `setHtml` transition
  without waiting for the next 5 s timer tick

- **Duty Cycle history chart layout flash** — previously the chart card was
  only injected into the DOM when `n_dc > 1`; on the first reload with data
  the card appeared from nothing, causing a visible layout shift. Now the card
  is always rendered with a `⏳ Awaiting telemetry data…` placeholder when no
  data is available yet; only the canvas contents change when data arrives

- **`_html_reliability` crash** (`AttributeError: '_duplicates'`) — the render
  method had its own inline calculation block copied from the original version,
  directly accessing `self._duplicates`, `self._routing_acks`, etc. — attributes
  that no longer exist after the data mixin refactor. The method now uses
  `_data_reliability()` as the single source of truth, like all other sections

- **Double `_data_local_node()` call** in `_html_local_node` — called once at
  the top of the function and again after the `if not self._local_nid` branch;
  second call removed

- **`window.location.reload()` in wait-screen JS** — the wait-screen stub
  previously contained JS that called `window.location.reload()` when a nid
  arrived via `runJavaScript`; this causes undefined behaviour in
  `QWebEngineView` with `setHtml`. Replaced with a no-op `function(d){}`

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

[1.0.3-beta]: https://github.com/tiuksferve/MeshDeck/releases/tag/v1.0.3-beta
[1.0.2-beta.1]: https://github.com/tiuksferve/MeshDeck/releases/tag/v1.0.2-beta.1
[1.0.1-beta.1]: https://github.com/tiuksferve/MeshDeck/releases/tag/v1.0.1-beta.1
[1.0.0-beta.1]: https://github.com/tiuksferve/MeshDeck/releases/tag/v1.0.0-beta.1
