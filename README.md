# 📡 MeshDeck — uConsole CM4

Advanced graphical interface for monitoring, communication and analysis of
[Meshtastic](https://meshtastic.org) networks via TCP to the `meshtasticd`
daemon.  
Built and optimised for the **ClockworkPi uConsole CM4**, but runs on any
Linux/macOS/Windows system with Python 3 and PyQt5.

**Version:** 1.0.1-beta.1 &nbsp;·&nbsp; **Callsign:** CT7BRA &nbsp;·&nbsp; **Year:** 2026

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
  - 📧 Send DM (direct message) — PKI (E2E) when the public key is known, PSK as fallback
  - 🗺 Centre on map
  - 📡 Send traceroute
- Bottom hint bar with icon legend
- Node counters: total and active (last 2 hours)
- **Immediate status feedback** while connecting and loading nodes:
  - `"🔌 Connecting to host:port…"` appears instantly when Connect is clicked
  - `"⏳ Loading network nodes… (N received)"` updates as nodes arrive
  - `"✅ Network ready — N nodes loaded"` when the initial batch is complete

### 🗺 Interactive Map (Leaflet)

- **4 map themes:** 🌑 Dark · ☀ Light · 🗺 OpenStreetMap · 🛰 Satellite
- **Colour-coded markers by state:**
  - 🟢 Green — selected node
  - 🔴 Red — packet just received
  - 🔵 Blue — RF active
  - 🟠 Orange — via MQTT
  - ⚫ Grey — inactive (>2h)
- **Traceroutes** — solid green lines (forward/return) with per-segment SNR tooltips
- **NeighborInfo neighbourhood** — purple dashed lines between directly neighbouring nodes with SNR tooltip
- **Built-in legend** in the bottom-right corner of the map
- Per-node popup with full information and inline Traceroute button
- Left panel with checkable traceroute history list
- "Show all" toggle for all traceroute overlays

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
- **Local Node card** — name, ID, GPS coordinates, altitude and GPS status, **centred vertically** in the card
- **Target card** — node name, distance, SNR (colour-coded green/orange/red), altitude, cardinal direction — **centred vertically** in the card
- **GPS node table** — all nodes with known GPS, equal-width columns filling the full panel width, sorted by distance from local node
- GPS status warnings: active with fix, active without fix, disabled

### 🗺 Traceroutes

- Send traceroute to any node from the list or from the map popup
- Result dialog with forward and return hops, per-segment SNR, GPS indicators
- "Show on Map" button (when destination has GPS)
- 30-second cooldown between traceroutes
- Notification dialog when a traceroute directed at the local node is received

### ⚙️ Full Node Configuration

- **Channels:** name, PSK (Base64/hex/random), role, MQTT uplink/downlink, mute, position precision
- **User:** long name, short name, licensed Ham (via setOwner)
- **All 21 firmware configuration sections** (Device, Position/GPS, Power, Network/WiFi, Display, LoRa, Bluetooth, MQTT, Serial, Ext. Notification, Store & Forward, Range Test, Telemetry, Canned Messages, Audio/Codec2, Remote Hardware, Neighbor Info, Ambient Lighting, Detection Sensor, Paxcounter, Security)
- Atomic transaction — firmware reboots only once after saving all changes
- Full UI rebuild on language change

### 📊 Real-Time Metrics (10 Sections)

Auto-refreshes every 5 seconds via JavaScript without reloading the HTML page.

| Section | Type | What it measures |
|---------|------|-----------------|
| 📊 Overview | Mixed | Packets, active nodes, SNR, delivery rate, airtime |
| 📡 Channel & Airtime | 🌐 Network | Ch. utilization, airtime TX, EU duty cycle (ETSI EN300.220) |
| 📶 RF Quality | 🌐 Network | SNR histogram, hop distribution, quality assessment |
| 📦 Traffic | 🌐 Network | Packets by type, packets/min, RF vs MQTT, routing pattern |
| 🔋 Nodes & Battery | 🌐 Network | Battery, voltage, uptime, hardware model, GPS count |
| ✅ Reliability | 🏠 Local | ACK/NAK/pending, delivery rate, duplicates, collision probability |
| ⏱ Latency (RTT) | 🏠 Local | RTT avg/min/max/P90 between send and ACK |
| 🔗 Neighbourhood | 🌐 Network | Direct neighbour pairs with SNR (NeighborInfo) |
| 📏 Range & Links | 🌐 Network | km distance between GPS-equipped neighbours (Haversine) |
| ⏰ Intervals | 🌐 Network | Average time between packets per node |

### 🔌 Connectivity and Robustness

- TCP connection to the **meshtasticd daemon** (default `localhost:4403`)
- **Automatic reconnection** with exponential backoff: 15s → 30s → 60s → 120s
- 12-second watchdog per connection attempt
- 30-second safety-net polling to keep NodeDB in sync
- **Non-blocking connect** — `TCPInterface` creation is deferred via
  `QTimer.singleShot(50)` so the status bar message is always visible before
  the TCP handshake begins (critical on CM4 where the handshake can take several
  seconds)
- **Deferred NodeDB load** — initial batch runs after the UI paints, keeping the
  "Loading…" message visible throughout

### ⭐ Favorites

Favorites are managed **directly in the local node firmware** via
`setFavorite()` / `removeFavorite()`. No local file is used — the firmware
NodeDB is always the source of truth.

### 🔔 Sound Notifications

- Notification sound when messages are received (toggleable)
- Cross-platform: `aplay` (Linux) → `afplay` (macOS) → `winsound` (Windows) → `QApplication.beep()`

---

## 📁 Project Structure

```
meshdeck/
├── main.py              ← Entry point · MainWindow · signal wiring
├── constants.py         ← Colours, Qt styles, APP_STYLESHEET
├── models.py            ← FirmwareFavorites, NodeTableModel, NodeFilterProxyModel
├── worker.py            ← MeshtasticWorker — TCP/pubsub/packet processing
├── dialogs.py           ← ConnectionDialog, ConsoleWindow, RebootWaitDialog
├── i18n.py              ← Internationalisation system (PT/EN), tr() function
├── tabs/
│   ├── tab_nodes.py     ← MapWidget (Leaflet, traceroutes, neighbourhood)
│   ├── tab_messages.py  ← MessagesTab (channels, PKI/PSK DMs)
│   ├── tab_navigation.py← NavigationTab (compass, GPS node table)
│   ├── tab_config.py    ← ConfigTab, ChannelsTab, MESHTASTIC_CONFIG_DEFS
│   ├── tab_metrics.py   ← MetricsTab (orchestrates the 10 metric sections)
│   ├── metrics_data.py  ← MetricsDataMixin (data ingestion and calculation)
│   └── metrics_render.py← MetricsRenderMixin (HTML/JS/Chart.js generation)
└── requirements.txt
```

---

## ⚙️ Installation

```bash
pip install -r requirements.txt
# or directly:
pip install meshtastic PyQt5 PyQtWebEngine pypubsub
```

### On uConsole CM4 (Debian/Ubuntu/Raspbian)

```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine python3-pip
pip3 install meshtastic pypubsub --break-system-packages
```

**Requirements:** Python 3.9+, `meshtasticd` on port 4403, X11 or Wayland display.

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

## 🤖 A Note on Artificial Intelligence

This project was developed with the support of **Claude** (Anthropic). The AI
collaborated across multiple sessions contributing to architecture, i18n, all 10
metric sections, navigation tab, traceroute logic, bug fixing, performance
optimisations for CM4, and full PT/EN translation.

The code was reviewed, tested and validated by the author on real hardware
(ClockworkPi uConsole CM4) with a live Meshtastic network.
