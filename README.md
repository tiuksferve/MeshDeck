# 📡 MeshDeck — uConsole CM4

Advanced graphical interface for monitoring, communication and configuration of
[Meshtastic](https://meshtastic.org) networks via TCP or direct USB Serial.  
Built and optimised for the **ClockworkPi uConsole CM4**, but runs on any
Linux/macOS/Windows system with Python 3 and PyQt5.

**Version:** 1.0.3-beta &nbsp;·&nbsp; **Callsign:** CT7BRA &nbsp;·&nbsp; **Year:** 2026

---

## 🌐 Languages

The interface supports **English** and **Português**, selectable in the
connection dialog. The preference is saved between sessions via `QSettings`.

---

## 🚀 Features

### 📋 Real-Time Node List

- Full list of all visible network nodes with automatic updates
- **Columns:** ID String, ID Num, Long Name, Short Name, Last Contact, SNR,
  Hops, Via (RF/MQTT), Latitude, Longitude, Altitude (m), Battery (%), Hardware
  Model, Last Packet Type
- **Local node pinned at top** with amber background and 🏠 prefix
- **Favorites** managed directly in the node firmware (⭐), pinned below the
  local node with highlighted yellow background
- Real-time search by ID, long name or short name
- Double-click any node to view full details of the last received packet
- **Quick actions directly from the list:**
  - 📧 Send DM — PKI (E2E) when public key is known, PSK as fallback
  - 🗺 Centre on map
  - 📡 Send traceroute
- Bottom hint bar with icon legend
- Node counters: total and active (last 2 hours)
- **Immediate status feedback** while connecting and loading nodes

### 🗺 Interactive Map (Leaflet)

- **4 map themes:** 🌑 Dark · ☀ Light · 🗺 OpenStreetMap · 🛰 Satellite
- **Colour-coded markers by state:**
  - 🟢 Green — selected node
  - 🔴 Red — packet just received
  - 🔵 Blue — RF active
  - 🟠 Orange — via MQTT
  - ⚫ Grey — inactive (>2h)
- **Traceroutes** — solid green lines (forward/return) with per-segment SNR tooltips
- **NeighborInfo neighbourhood** — purple dashed lines between directly neighbouring nodes
- **Built-in legend** in the bottom-right corner of the map
- Per-node popup with full information and inline Traceroute button
- Left panel with checkable traceroute history list

### 💬 Messages

- Multiple **channels** (Primary + Secondary, indices 0-7) with unread counters
- **Direct Messages (DM):**
  - 🔒 **PKI** (E2E encrypted) when the destination's public key is known
  - 🔓 **PSK** (channel key) as automatic fallback
  - DM list sorted by most recent activity
- Per-sent-message ACK/NAK indicator
- MQTT message support (☁)
- 🔴 badge on the Messages tab for unread messages
- Date separators in conversations ("Today", "Yesterday", exact date)

### 🧭 Navigation

- **Compass** — real-time bearing and distance from the local node to any selected remote node
- **Local Node card** — name, ID, GPS coordinates, altitude, GPS status, and a
  **🔄 Position refresh button** that re-reads the GPS position from the node on demand:
  - Reads from the daemon cache (`nodesByNum`) — updated with each GPS packet
  - Falls back to `localConfig.position.fixed_lat/lon` for fixed-position nodes
  - Shows `⏳ Reading…` while active; 3-second warning if no position available
- **Target card** — node name, distance, SNR (colour-coded), altitude, cardinal direction
- **GPS node table** — all nodes with known GPS, sorted by distance from local node
- GPS status warnings: active with fix, active without fix, disabled

### 🗺 Traceroutes

- Send traceroute to any node from the list or from the map popup
- Result dialog with forward and return hops, per-segment SNR, GPS indicators
- "Show on Map" button (when destination has GPS)
- 30-second cooldown between traceroutes
- Notification dialog when a traceroute directed at the local node is received

### ⚙️ Full Node Configuration

- **Channels:** name, PSK (Base64/hex/random), role, MQTT uplink/downlink, mute, position precision
- **User:** long name, short name, licensed Ham (via `setOwner`) — only saved when values actually changed
- **All 21 firmware configuration sections** (Device, Position/GPS, Power, Network/WiFi,
  Display, LoRa, Bluetooth, MQTT, Serial, Ext. Notification, Store & Forward, Range Test,
  Telemetry, Canned Messages, Audio/Codec2, Remote Hardware, Neighbor Info, Ambient Lighting,
  Detection Sensor, Paxcounter, Security)
- **Atomic transaction** — firmware reboots only once after saving all changes
  (`beginSettingsTransaction` / `commitSettingsTransaction`)
- **Proto3-correct save:** bool `False` fields are force-serialised via double-set
  technique so they reach the firmware even though `False` is the protobuf default
- **Validated field list:** all fields cross-checked against the official
  `config.proto` and `module_config.proto`; non-existent fields removed
- **Detailed save confirmation:** shows exactly which `writeConfig()` sections,
  `setOwner`, and `setCannedMessages` were sent
- Full UI rebuild on language change
- `proxy_to_client_enabled` displayed as read-only with explanatory note
  (requires `mqttClientProxyMessage` relay protocol — planned for a future release)

### 📊 Real-Time Metrics (11 Sections)

Auto-refreshes every 5 seconds. The Local Node section reloads when data
changes (hash-guarded `setHtml`); all other sections update via JavaScript
without reloading the HTML page.

| Section | Type | What it measures |
|---------|------|-----------------|
| 📊 Overview | Mixed | Packets, active nodes, SNR, delivery rate, airtime |
| 🏠 Local Node | 🏠 Local | Battery, Ch. Util., Air TX, duty cycle/h (EU limit), SNR RX, messages sent/ACK/NAK, RTT, uptime (live counter), GPS |
| 📡 Channel & Airtime | 🌐 Network | Ch. utilization, airtime TX, EU duty cycle (ETSI EN300.220) |
| 📶 RF Quality | 🌐 Network | SNR histogram, hop distribution, quality assessment |
| 📦 Traffic | 🌐 Network | Packets by type, packets/min, RF vs MQTT, routing pattern |
| 🔋 Nodes & Battery | 🌐 Network | Battery, voltage, uptime, hardware model, GPS count |
| ✅ Reliability | Mixed | ACK/NAK/fw-errors separated, delivery rate, windowed flood rate, collision estimate |
| ⏱ Latency (RTT) | 🏠 Local | RTT avg/min/max/P90 between send and ACK |
| 🔗 Neighbourhood | 🌐 Network | Direct neighbour pairs with SNR (NeighborInfo) |
| 📏 Range & Links | 🌐 Network | km distance between GPS-equipped neighbours (Haversine) |
| ⏰ Intervals | 🌐 Network | Average time between packets per node |

**Metric precision improvements in v1.0.3-beta:**
- SNR P10 corrected to `int(0.1*(n-1))` — was `n//10` (wrong for small samples)
- Flood rate windowed to match the 5-minute `_pkt_ids` window (was cumulative)
- `ROUTING_APP` errors split: ACK / NAK-delivery / FW-errors (NO_ROUTE, MAX_RETRANSMIT)
- `_ch_util` / `_air_tx` expire after 30 min of no update (TTL)
- GPS node count uses validated `_node_pos` entries, not raw POSITION_APP packet count

### 🔌 Connectivity and Robustness

- TCP connection to the **meshtasticd daemon** (default `localhost:4403`)
- **USB Serial connection** via the built-in bridge — no AIO board required
- **Automatic reconnection** with exponential backoff: 15s → 30s → 60s → 120s
- 12-second watchdog per connection attempt
- 30-second safety-net polling to keep NodeDB in sync
- **Non-blocking connect** — `TCPInterface` creation deferred via `QTimer.singleShot(50)`

### ⭐ Favorites

Favorites managed **directly in the local node firmware** via
`setFavorite()` / `removeFavorite()`. No local file used.

### 🔔 Sound Notifications

- Notification sound when messages are received (toggleable)
- Cross-platform: `aplay` (Linux) → `afplay` (macOS) → `winsound` (Windows) → `QApplication.beep()`

---

## 🔌 USB Serial Connection

MeshDeck can connect directly to a Meshtastic device over USB without requiring
the AIO board or a running `meshtasticd` daemon.

### How it works

A built-in bridge (`meshtastic_bridge.py`) reads the Meshtastic serial stream,
strips debug/boot-log noise, and re-exposes clean frames as a local TCP server
on `127.0.0.1:4403`.

### Supported hardware

| Chipset | Boards |
|---------|--------|
| Espressif ESP32/S2/S3/C3 | Most Meshtastic boards |
| Silicon Labs CP210x | HELTEC, LILYGO T-Beam, RAK |
| FTDI FT232 | DIY and dev boards |
| CH340 / CH341 | Low-cost Chinese boards |
| Prolific PL2303 | Older clones |
| Adafruit nRF52840 | Feather, ItsyBitsy |
| RAK Wireless nRF52840 | RAK4631 |

### Usage

1. Plug the Meshtastic device via USB
2. Open **🔌 Connection…** → tab **🔌 USB Serial**
3. Select the port from the dropdown
4. Click **▶ Start Serial Bridge** and wait for **✅ Bridge active**
5. Click **🔌 Connect**

### Additional requirements

```bash
pip install pyserial>=3.5
```

Already included in `requirements.txt`.

### Bridge CLI (standalone)

```bash
python3 meshtastic_bridge.py --list
python3 meshtastic_bridge.py --port /dev/ttyACM0 --verbose
```

> **Credits:** Serial bridge concept by **[@KMX415](https://github.com/KMX415)**.

---

## 📁 Project Structure

```
meshdeck/
├── main.py                  ← Entry point · MainWindow · signal wiring
├── constants.py             ← Colours, Qt styles, APP_STYLESHEET
├── models.py                ← FirmwareFavorites, NodeTableModel, NodeFilterProxyModel
├── worker.py                ← MeshtasticWorker — TCP/Serial/pubsub/packet processing
├── dialogs.py               ← ConnectionDialog, ConsoleWindow, RebootWaitDialog
├── i18n.py                  ← Internationalisation (PT/EN), tr() function
├── meshtastic_bridge.py     ← USB-to-TCP serial bridge
├── tabs/
│   ├── tab_nodes.py         ← MapWidget (Leaflet, traceroutes, neighbourhood)
│   ├── tab_messages.py      ← MessagesTab (channels, PKI/PSK DMs)
│   ├── tab_navigation.py    ← NavigationTab (compass, GPS table, position refresh)
│   ├── tab_config.py        ← ConfigTab, ChannelsTab, MESHTASTIC_CONFIG_DEFS
│   ├── tab_metrics.py       ← MetricsTab (orchestrates 11 metric sections)
│   ├── metrics_data.py      ← MetricsDataMixin (data ingestion and calculation)
│   └── metrics_render.py    ← MetricsRenderMixin (HTML/JS/Chart.js generation)
└── requirements.txt
```

---

## ⚙️ Installation

```bash
pip install -r requirements.txt
```

### On uConsole CM4 (Debian/Ubuntu/Raspbian)

```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine python3-pip
pip3 install meshtastic pypubsub pyserial --break-system-packages
```

**Requirements:** Python 3.9+, X11 or Wayland display.  
**TCP mode:** `meshtasticd` running on port 4403.  
**Serial mode:** USB Meshtastic device + `pyserial`.

---

## 🚀 Running

```bash
cd meshdeck/
python3 main.py
```

---

## 📡 Meshtastic Firmware Requirements

| Feature | Minimum version |
|---------|----------------|
| PKI DM (E2E encrypted) | ≥ 2.3.0 |
| NeighborInfo over LoRa | ≥ 2.5.13 |
| Traceroute with SNR | ≥ 2.3.2 |
| Firmware-managed favorites | ≥ 2.3.0 |

---

## 🧑‍💻 Developed by

**CT7BRA — Tiago Veiga**  
Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js  
Optimised for ClockworkPi uConsole CM4 · 2026

---

## 🤝 Credits

| Contributor | Contribution |
|-------------|-------------|
| [@KMX415](https://github.com/KMX415) | Original serial bridge concept and code |

---

## 🤖 A Note on Artificial Intelligence

This project was developed with the support of **Claude** (Anthropic). The AI
collaborated across multiple sessions contributing to architecture, i18n, all 10
metric sections, navigation tab (including GPS position refresh), configuration
tab (complete save pipeline rewrite, proto3 correctness, field audit),
traceroute logic, bug fixing, performance optimisations for CM4, USB Serial
bridge integration, and full PT/EN translation.

The code was reviewed, tested and validated by the author on real hardware
(ClockworkPi uConsole CM4) with a live Meshtastic network.
