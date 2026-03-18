# 📡 Meshtastic Monitor — uConsole CM4

Advanced graphical interface for monitoring, communication and analysis of
[Meshtastic](https://meshtastic.org) networks via TCP to the `meshtasticd` daemon.  
Built and optimised for the **ClockworkPi uConsole CM4**, but runs on any
Linux/macOS/Windows system with Python 3 and PyQt5.

---

## 🚀 Features

### 📋 Node List
- Real-time list of all visible network nodes with automatic updates
- Columns: ID, Name, Last Contact, SNR, Hops, Via (RF/MQTT), GPS, Battery, Hardware, Last Packet Type
- **Local node pinned at top** with amber background and 🏠 prefix
- **Favourites** with highlighted yellow background, pinned below local node (⭐)
- Real-time search by ID, long name or short name
- Double-click to view full details of the last received packet
- Quick DM (📩) and traceroute (📡) actions directly from the list
- Visual PKI (🔒) vs PSK (📩) encryption indicator
- Node counters: total and online (last 2 hours)

### 🗺 Interactive Map (Leaflet)
- 4 themes: 🌑 Dark · ☀ Light · 🗺 OpenStreetMap · 🛰 Satellite
- **Colour-coded markers** by state:
  - 🟢 Green — selected node
  - 🔴 Red — packet just received
  - 🔵 Blue — RF active
  - 🟠 Orange — via MQTT
  - ⚫ Grey — inactive (>2h)
- **Traceroutes** — solid green lines (forward/reverse) with per-segment SNR tooltips
- **NeighborInfo** — **purple dashed lines** between directly neighbouring nodes with SNR tooltip
- **Built-in legend** in the bottom-right corner of the map
- Per-node popup with full information and Traceroute button
- Left panel with checkable traceroute history list

### 💬 Messages
- Multiple **channels** (Primary + Secondary, indices 0-7)
- **DMs** (Direct Messages) with:
  - 🔒 **PKI** (E2E encrypted) when the destination's public key is known
  - 🔓 **PSK** (channel key) as automatic fallback
- Unread indicator per channel and per DM (🔴)
- DM list sorted by recent activity
- Per-sent-message ACK/NAK indicator
- MQTT message support (☁)
- 🔴 badge on the Messages tab for unread messages

### ⚙️ Full Node Configuration
- **Channels**: name, PSK (Base64/hex/random), role, MQTT uplink/downlink, mute, position precision
- **User**: long name, short name, licensed Ham (setOwner)
- **All firmware config sections**:
  | Section | Key fields |
  |---------|-----------|
  | 💻 Device | Role, rebroadcast, GPIO, NodeInfo interval, TZ, serial |
  | 📍 Position/GPS | GPS mode, intervals, smart broadcast, fixed position, HDOP |
  | 🔋 Power | Power saving, shutdown timers, ADC, Bluetooth wait, SDS/LS |
  | 🌐 Network/WiFi | WiFi SSID/PSK, NTP, Ethernet, static IP, gateway, DNS |
  | 🖥 Display | Timeout, GPS format, OLED type, flip, wake on tap, TFT brightness |
  | 📡 LoRa | Preset, region, BW/SF/CR, TX power, hop limit, channel override |
  | 🔵 Bluetooth | Enable, pairing mode, fixed PIN |
  | ☁ MQTT | Server, TLS, JSON, map reporting, proxy client |
  | 🔌 Serial | Baud rate, mode, GPIO, echo |
  | 🔔 Ext. Notification | GPIO, alerts for message/bell, PWM buzzer |
  | 📦 Store & Forward | Enable, records, history window, server |
  | 📏 Range Test | Enable, interval, CSV |
  | 📊 Telemetry | Device/environment/power/health intervals |
  | 💬 Canned Messages | **Text area** (one per line, max 200 chars) + rotary encoder |
  | 🎙 Audio/Codec2 | Enable, PTT GPIO, bitrate, I2S GPIOs |
  | 🔧 Remote Hardware | Enable, undefined pin access |
  | 🔗 Neighbor Info | Enable, interval, transmit over LoRa |
  | 💡 Ambient Lighting | LED state, current, RGB |
  | 🔍 Detection Sensor | GPIO, intervals, pull-up, trigger high |
  | 🧮 Paxcounter | Enable, interval |
  | 🔐 Security | Admin channel, managed mode, debug serial |
- Atomic transaction (firmware reboots only once)
- Robust saving with enum conversion via protobuf descriptor

### 📊 Real-Time Metrics (10 sections)

| Section | Type | What it measures |
|---------|------|-----------------|
| 📊 Overview | Mixed | Executive summary: packets, nodes, SNR, delivery rate |
| 📡 Channel & Airtime | 🌐 Network | Channel utilization per node, airtime TX, EU duty cycle (10%/h) |
| 📶 RF Quality | 🌐 Network | SNR histogram, hop distribution, automatic assessment |
| 📦 Traffic | 🌐 Network | Packets by type, packets/min (30 min), RF vs MQTT |
| 🔋 Nodes & Battery | 🌐 Network | Battery (⚡ Powered), voltage, uptime, hw model, GPS count |
| ✅ Reliability | 🏠 Local | ACK/NAK/pending, delivery rate, network duplicates, collision probability |
| ⏱ Latency (RTT) | 🏠 Local | RTT avg/min/max/P90 between send and destination ACK |
| 🔗 Neighbourhood | 🌐 Network | Direct neighbour pairs with SNR (NeighborInfo) |
| 📏 Range & Links | 🌐 Network | km distance between GPS-equipped neighbours (Haversine) |
| ⏰ Intervals | 🌐 Network | Average time between packets per node (detects aggressive nodes) |

> **🏠 Local Node Metric** — data refers exclusively to the connected local node  
> **🌐 Network Metric** — passive observation of all packets received

### 🔌 Connectivity & Robustness
- TCP connection to **meshtasticd daemon** (default `localhost:4403`)
- Automatic reconnection with exponential backoff (5s → 10s → 30s → 60s)
- 30s safety-net polling to keep NodeDB in sync
- `rxTime` with `datetime.now()` fallback (compatible with TCP daemon)
- Local node always visible in node list, pinned at top

---

## 📁 Project Structure

```
meshtastic_monitor/
├── main.py              ← Entry point · MainWindow · signal wiring
├── constants.py         ← Colours, Qt styles, APP_STYLESHEET, MAP_THEMES
├── models.py            ← FavoritesStore, NodeTableModel, NodeFilterProxyModel, _safe_update
├── worker.py            ← MeshtasticWorker — TCP/pubsub/packet processing
├── dialogs.py           ← ConnectionDialog, ConsoleWindow, RebootWaitDialog
├── tabs/
│   ├── tab_nodes.py     ← MapWidget (Leaflet, traceroutes, neighbourhood)
│   ├── tab_messages.py  ← MessagesTab (channels, PKI/PSK DMs)
│   ├── tab_config.py    ← ConfigTab, ChannelsTab, config definitions
│   └── tab_metrics.py   ← MetricsTab (10 metric sections)
└── requirements.txt
```

---

## ⚙️ Installation

```bash
pip install -r requirements.txt
# or
pip install meshtastic PyQt5 PyQtWebEngine pypubsub
```

### On uConsole CM4 (Debian/Ubuntu)

```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine python3-pip
pip3 install meshtastic pypubsub --break-system-packages
```

**Requirements:** Python 3.9+ · `meshtasticd` running on port 4403

---

## 🚀 Running

```bash
cd meshtastic_monitor/
python3 main.py
```

On first run, the connection dialog asks for the daemon address and port
(`localhost:4403` by default).

---

## 🗂 Favourites File

Favourites are stored in `~/.meshtastic_monitor_favorites.json` with full node
data (name, GPS, public key) so they appear even when not in the firmware NodeDB.

---

## 🧑‍💻 Developed by

**CT7BRA — Tiago Veiga**  
Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js  
Optimised for ClockworkPi uConsole CM4
