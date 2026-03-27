# 📡 Meshtastic Monitor — uConsole CM4

Advanced graphical interface for monitoring, communication and analysis of
[Meshtastic](https://meshtastic.org) networks via TCP to the `meshtasticd`
daemon.  
Built and optimised for the **ClockworkPi uConsole CM4**, but runs on any
Linux/macOS/Windows system with Python 3 and PyQt5.

**Version:** 1.0.0-beta.1 &nbsp;·&nbsp; **Callsign:** CT7BRA &nbsp;·&nbsp; **Year:** 2026

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
- **Favourites** managed directly in the node firmware (⭐), pinned below the
  local node with highlighted yellow background
- Real-time search by ID, long name or short name
- Double-click any node to view full details of the last received packet
- **Quick actions directly from the list:**
  - 📧 Send DM (direct message) — PKI (E2E) when the public key is known, PSK
    as fallback
  - 🗺 Centre on map
  - 📡 Send traceroute
- Bottom hint bar with icon legend
- Node counters: total and active (last 2 hours)

### 🗺 Interactive Map (Leaflet)

- **4 map themes:** 🌑 Dark · ☀ Light · 🗺 OpenStreetMap · 🛰 Satellite
- **Colour-coded markers by state:**
  - 🟢 Green — selected node
  - 🔴 Red — packet just received
  - 🔵 Blue — RF active
  - 🟠 Orange — via MQTT
  - ⚫ Grey — inactive (>2h)
- **Traceroutes** — solid green lines (forward/return) with per-segment SNR
  tooltips
- **NeighborInfo neighbourhood** — purple dashed lines between directly
  neighbouring nodes with SNR tooltip
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

### 🗺 Traceroutes

- Send traceroute to any node from the list or from the map popup
- Result dialog showing:
  - **When we send:** Origin = local node, Destination = remote node
  - **When we receive:** Origin = remote node (who sent it), Destination = local
    node
  - Forward and return hops with per-segment SNR
  - GPS indicators per node (📍 has coordinates, ❓ no coordinates)
  - "Show on Map" button (when destination has GPS)
- 30-second cooldown between traceroutes to protect the channel
- Notification dialog when a traceroute directed at the local node is received

### ⚙️ Full Node Configuration

- **Channels:** name, PSK (Base64/hex/random), role, MQTT uplink/downlink,
  mute, position precision
- **User:** long name, short name, licensed Ham (via setOwner)
- **All firmware configuration sections:**

| Section | Key fields |
|---------|-----------|
| 💻 Device | Node role, rebroadcast, GPIO, NodeInfo interval, TZ, serial |
| 📍 Position/GPS | GPS mode, intervals, smart broadcast, fixed position, HDOP |
| 🔋 Power | Power saving, shutdown timers, ADC, Bluetooth wait, SDS/LS |
| 🌐 Network/WiFi | WiFi SSID/PSK, NTP, Ethernet, static IP, gateway, DNS |
| 🖥 Display | Timeout, GPS format, OLED type, flip, wake on tap, TFT brightness |
| 📡 LoRa | Preset, region, BW/SF/CR, TX power, hop limit, frequency override |
| 🔵 Bluetooth | Enable, pairing mode, fixed PIN |
| ☁ MQTT | Server, TLS, JSON, map reporting, proxy to client |
| 🔌 Serial | Baud rate, mode, GPIO, echo |
| 🔔 Ext. Notification | GPIO, message/bell alerts, PWM buzzer |
| 📦 Store & Forward | Enable, records, history window, server |
| 📏 Range Test | Enable, interval, CSV |
| 📊 Telemetry | Device/environment/power/health intervals |
| 💬 Canned Messages | Text area (one per line, max 200 chars) + rotary encoder GPIOs |
| 🎙 Audio/Codec2 | Enable, PTT GPIO, bitrate, I2S GPIOs |
| 🔧 Remote Hardware | Enable, undefined pin access |
| 🔗 Neighbor Info | Enable, interval, transmit over LoRa |
| 💡 Ambient Lighting | LED state, current, RGB |
| 🔍 Detection Sensor | GPIO, intervals, pull-up, trigger high |
| 🧮 Paxcounter | Enable, interval |
| 🔐 Security | Admin channel, managed mode, debug serial |

- Atomic transaction — firmware reboots only once after saving all changes
- Robust saving with enum conversion via protobuf descriptor
- Full UI rebuild on language change (all field labels updated immediately)

### 📊 Real-Time Metrics (10 Sections)

Auto-refreshes every 5 seconds via JavaScript without reloading the HTML page.

| Section | Type | What it measures |
|---------|------|-----------------|
| 📊 Overview | Mixed | Executive summary: packets, active nodes, SNR, delivery rate, airtime |
| 📡 Channel & Airtime | 🌐 Network | Ch. utilization per node, airtime TX, EU duty cycle (ETSI EN300.220, 10%/h) |
| 📶 RF Quality | 🌐 Network | SNR histogram, hop distribution, automatic quality assessment |
| 📦 Traffic | 🌐 Network | Packets by type, packets/min (30 min), RF vs MQTT, routing pattern |
| 🔋 Nodes & Battery | 🌐 Network | Battery (⚡ Powered), voltage, uptime, hardware model, GPS count |
| ✅ Reliability | 🏠 Local | ACK/NAK/pending, delivery rate, network duplicates, collision probability |
| ⏱ Latency (RTT) | 🏠 Local | RTT avg/min/max/P90 between send and destination ACK |
| 🔗 Neighbourhood | 🌐 Network | Direct neighbour pairs with SNR (NeighborInfo) |
| 📏 Range & Links | 🌐 Network | km distance between GPS-equipped neighbours (Haversine formula) |
| ⏰ Intervals | 🌐 Network | Average time between packets per node (detects aggressive nodes) |

> **🏠 Local Node Metric** — data refers exclusively to the connected local node  
> **🌐 Network Metric** — passive observation of all received packets

**Smart waiting screens:** Each metric automatically detects when sufficient
data has arrived and transitions from the waiting screen to the data view
without any manual intervention needed.

### 🔌 Connectivity and Robustness

- TCP connection to the **meshtasticd daemon** (default `localhost:4403`)
- **Automatic reconnection** with exponential backoff: 15s → 30s → 60s → 120s
- 12-second watchdog per connection attempt (detects hung handshakes)
- 30-second safety-net polling to keep NodeDB in sync
- `rxTime` fallback to `datetime.now()` (compatible with TCP daemon)
- Local node always visible and pinned at the top of the list
- Compatible with both Wayland and X11

### ⭐ Favourites

Favourites are managed **directly in the local node firmware** via
`setFavorite()` / `removeFavorite()`. No local file is used — the firmware
NodeDB is always the source of truth, ensuring favourites persist across
sessions and devices with no auxiliary files required.

### 🔔 Sound Notifications

- Notification sound when messages are received (toggleable)
- Cross-platform fallback chain:
  - **Linux:** `aplay` (ALSA, generated 880 Hz tone) → `paplay` (PulseAudio)
  - **macOS:** `afplay` (system sound)
  - **Windows:** `winsound.MessageBeep`
  - **Fallback:** `QApplication.beep()`

### 📤 Local Node Actions

- **Send Node Info** — broadcast NODEINFO_APP (Ctrl+I)
- **Send Manual Position** — via `localNode.setPosition()` or manual fallback
  (Ctrl+P)
- **Reset NodeDB** — clears the firmware's node database
- **Log Console** — real-time log of the TCP communication (in English)

---

## 📁 Project Structure

```
meshtastic_monitor/
├── main.py              ← Entry point · MainWindow · signal wiring
├── constants.py         ← Colours, Qt styles, APP_STYLESHEET
├── models.py            ← FirmwareFavorites, NodeTableModel, NodeFilterProxyModel
├── worker.py            ← MeshtasticWorker — TCP/pubsub/packet processing
├── dialogs.py           ← ConnectionDialog, ConsoleWindow, RebootWaitDialog
├── i18n.py              ← Internationalisation system (PT/EN), tr() function
├── tabs/
│   ├── tab_nodes.py     ← MapWidget (Leaflet, traceroutes, neighbourhood)
│   ├── tab_messages.py  ← MessagesTab (channels, PKI/PSK DMs)
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

**Requirements:**
- Python 3.9 or higher
- `meshtasticd` running and accessible on port 4403
- Display (X11 or Wayland) for the Qt graphical interface

---

## 🚀 Running

```bash
cd meshtastic_monitor/
python3 main.py
```

On first run (or with no saved preference), the connection dialog opens in
English. Select your language in the selector before connecting. The preference
is automatically saved via `QSettings`.

---

## 📡 Meshtastic Firmware Requirements

| Feature | Minimum version |
|---------|----------------|
| PKI DM (E2E encrypted) | ≥ 2.3.0 |
| NeighborInfo over LoRa | ≥ 2.5.13 |
| Traceroute with SNR | ≥ 2.3.2 |
| Private channel for NeighborInfo | ≥ 2.5.13 |
| Firmware-managed favourites | ≥ 2.3.0 |

> **Note:** NeighborInfo over LoRa requires a **private** primary channel — the
> public channel (LongFast/ShortFast with default key) blocks this traffic since
> firmware 2.5.13.

---

## 🧑‍💻 Developed by

**CT7BRA — Tiago Veiga**  
Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js  
Optimised for ClockworkPi uConsole CM4 · 2026

---

## 🤖 A Note on Artificial Intelligence

This project was developed with the support of **Claude** (Anthropic), an
artificial intelligence assistant. The AI actively collaborated across multiple
development sessions, contributing to:

- Code architecture and refactoring (separation into modules and mixins)
- Complete internationalisation system (i18n) for Portuguese and English with
  full UI coverage
- Implementation of all 10 real-time metric sections
- Traceroute system with correct origin/destination logic for sent and received
  traceroutes
- Bug detection and fixing (NodeDB duplicates, map race conditions, Qt signal
  leaks, duplicate connection signal emission)
- Migration of favourites from a local JSON file to native firmware management
- Performance analysis and optimisations for the CM4 hardware
- Full translation of all UI strings and log messages to English

The code was reviewed, tested and validated by the author on real hardware
(ClockworkPi uConsole CM4) with a live Meshtastic network.
