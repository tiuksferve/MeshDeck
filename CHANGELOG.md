# Changelog

All notable changes to **MeshDeck** are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.2-beta.1] — 2026-04-02

### Added

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
    session (e.g. IDE stop button) before launching a new one — cross-platform:
    `psutil` (preferred) → `lsof -sTCP:LISTEN` (macOS) → `ss` / `fuser` /
    `/proc/net/tcp` (Linux) → `netstat` + `taskkill` (Windows)
- **Serial mode indicator** in the connection status badge — when connected via
  Serial the indicator shows `🟢 127.0.0.1:4403 · 🔌 Serial` instead of just
  the host/port
- **1.5 s stabilisation delay** before `TCPInterface` is created in Serial mode,
  allowing the bridge to fully open the serial port and flush the input buffer
- **Bridge log file** written to the OS temp directory (`meshdeck_bridge.log`)
  for easier diagnosis of serial issues
- `pyserial >= 3.5` added to `requirements.txt`
- New i18n strings: `conn_tab_tcp`, `conn_tab_serial`, `conn_via_serial`,
  `serial_port_label`, `serial_start_bridge`, `serial_refresh_tip`,
  `serial_bridge_idle`, `serial_bridge_starting`, `serial_bridge_ready`,
  `serial_bridge_timeout`, `serial_bridge_missing`, `serial_no_ports`,
  `serial_no_pyserial`, `serial_select_port`, `serial_note` — full PT/EN

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
  flags before `beginResetModel`; `set_selected_highlight` emits `dataChanged`
  only on rows that actually changed; `update_node` no longer emits
  `BackgroundRole` on every packet, eliminating scroll lag
- Local GPS position applied **once per batch** (not once per node), avoiding N
  compass redraws during the initial load
- Navigation Local Node and Target cards: content centred vertically with equal
  stretch above and below (`addStretch(1)` on both sides)
- Spelling: `"favourite/favourites"` → `"favorite/favorites"` throughout EN strings

### Fixed

- `setUniformRowHeights` crash — method does not exist on `QTableView`
  (belongs to `QTreeView`); removed
- `ScrollPerPixel` corrected to `QAbstractItemView.ScrollPerPixel`
- Navigation tab `_target_snr_lbl` / `_target_alt_lbl` labels not cleared when
  no target is selected
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
