# Changelog

All notable changes to **Meshtastic Monitor** are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0-beta.1] — 2026-03-27

First public release.

### Added

- **Real-time node list** with 14 columns, local node pinned at top, favourites
  managed directly in firmware (`setFavorite` / `removeFavorite`)
- **Interactive Leaflet map** with 4 themes (Dark, Light, OpenStreetMap,
  Satellite), colour-coded markers, traceroute overlays, NeighborInfo
  neighbourhood lines, and a built-in legend
- **Messaging** — channel messages (indices 0–7) and direct messages with
  automatic PKI (E2E) / PSK fallback, ACK/NAK indicators, unread badge, and
  date separators
- **Traceroutes** — send from node list or map popup, result dialog with
  per-segment SNR, GPS indicators, and "Show on Map" button; 30 s cooldown
- **Full node configuration** — all 21 firmware sections (Device, Position/GPS,
  Power, Network/WiFi, Display, LoRa, Bluetooth, MQTT, Serial, Ext.
  Notification, Store & Forward, Range Test, Telemetry, Canned Messages,
  Audio/Codec2, Remote Hardware, Neighbor Info, Ambient Lighting, Detection
  Sensor, Paxcounter, Security) plus Channels and User tabs; atomic save with
  single reboot
- **10 real-time metric sections** auto-refreshing every 5 s via JavaScript
  without reloading the HTML page:
  - Overview, Channel & Airtime, RF Quality, Traffic, Nodes & Battery,
    Reliability, Latency (RTT), Neighbourhood, Range & Links, Intervals
- **Internationalisation (i18n)** — full PT/EN coverage across all UI strings,
  error messages, map popups, and log messages; language selectable in the
  connection dialog, saved via `QSettings`
- **Automatic reconnection** with exponential backoff (15 s → 30 s → 60 s →
  120 s) and 12 s watchdog per attempt
- **Sound notifications** on new messages with cross-platform fallback chain
  (aplay → paplay → afplay → winsound → QApplication.beep)
- **Log console** — floating window with real-time TCP communication log,
  keyword filter, and line-count indicator
- Wayland-compatible (`activateWindow` skipped on Wayland platforms)
- Optimised for **ClockworkPi uConsole CM4** (debounced map redraws, 30 s
  NodeDB polling safety-net, CM4-friendly marker rebuild strategy)

### Technical

- Modular architecture: `main.py`, `worker.py`, `models.py`, `constants.py`,
  `dialogs.py`, `i18n.py`, `tabs/` (tab_nodes, tab_messages, tab_config,
  tab_metrics, metrics_data, metrics_render)
- `FirmwareFavorites` — favourites persisted in firmware NodeDB; no local JSON
  file required
- Tab indices centralised as class constants (`TAB_NODES`, `TAB_MESSAGES`,
  `TAB_MAP`, `TAB_METRICS`, `TAB_CONFIG`) in `MainWindow`
- `my_node_id_ready` signal emitted exactly once per connection with the most
  reliable ID source
- `_section_has_data()` method replaces non-idiomatic class-level lambda dict
  for metrics waiting-screen transitions
- All log messages in English

---

## Notes

> This is a **beta** release. The application has been tested on real hardware
> (ClockworkPi uConsole CM4) with a live Meshtastic network. Expect occasional
> rough edges; bug reports and pull requests are welcome.

[1.0.0-beta.1]: https://github.com/ct7bra/meshtastic-monitor/releases/tag/v1.0.0-beta.1
