#!/usr/bin/env python3
"""
Meshtastic USB-to-TCP bridge
Parses the Meshtastic stream protocol from the serial port, stripping any
debug/log text mixed in, and re-emits clean frames to TCP clients.

Meshtastic frame format (serial AND TCP):
  [0x94][0xC3][len_hi][len_lo][protobuf payload...]

Supports multiple simultaneous TCP clients (broadcast mode).
Compatible with all known Meshtastic hardware variants.
"""

import argparse
import glob
import logging
import os
import socket
import struct
import sys
import threading
import time

import serial
import serial.tools.list_ports

# ---------------------------------------------------------------------------
# Known USB VID:PID pairs for Meshtastic-capable hardware
# ---------------------------------------------------------------------------
KNOWN_DEVICES = {
    # Vendor ID  : description
    "303a": "Espressif (ESP32/S2/S3/C3)",  # most common
    "10c4": "Silicon Labs CP210x (HELTEC, LILYGO, RAK)",
    "067b": "Prolific PL2303 (older clones)",
    "0403": "FTDI FT232 (DIY / dev boards)",
    "1a86": "CH340/CH341 (cheap Chinese boards)",
    "2341": "Arduino (some Meshtastic dev builds)",
    "239a": "Adafruit (nRF52840 variants)",
    "1d50": "OpenMoko (nRF52 DFU bootloader)",
    "2fe3": "RAK Wireless nRF52840",
}

# Meshtastic serial framing constants
START1, START2 = 0x94, 0xC3
MAX_PAYLOAD = 512        # bytes — protocol hard limit is 512
SERIAL_TIMEOUT = 0.5     # seconds

# Default TCP server config
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4403

log = logging.getLogger("meshtastic-bridge")


# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------

def find_meshtastic_port() -> str | None:
    """
    Scan serial ports for any known Meshtastic-capable USB device.
    Uses pyserial's list_ports for cross-platform compatibility
    (Linux /dev/ttyACM*, /dev/ttyUSB*, macOS /dev/cu.usbmodem*, Windows COMx).
    Falls back to sysfs VID check on Linux when list_ports misses the device.
    """
    candidates = []

    # --- Primary: pyserial list_ports (cross-platform) ---
    for port_info in serial.tools.list_ports.comports():
        vid_hex = f"{port_info.vid:04x}" if port_info.vid else ""
        pid_hex = f"{port_info.pid:04x}" if port_info.pid else ""

        if vid_hex in KNOWN_DEVICES:
            log.info(
                "Found %s device: %s [VID:%s PID:%s] — %s",
                KNOWN_DEVICES[vid_hex],
                port_info.device,
                vid_hex,
                pid_hex,
                port_info.description or "no description",
            )
            candidates.append((port_info.device, vid_hex))

        # Also match by description keyword for boards that enumerate oddly
        desc = (port_info.description or "").lower()
        mfr = (port_info.manufacturer or "").lower()
        if any(kw in desc or kw in mfr for kw in ("meshtastic", "rak", "heltec", "lilygo", "t-beam", "tbeam")):
            if port_info.device not in [c[0] for c in candidates]:
                log.info("Found Meshtastic device by name: %s — %s", port_info.device, port_info.description)
                candidates.append((port_info.device, vid_hex))

    if candidates:
        # Prefer the first match; sort so ttyACM < ttyUSB on Linux
        candidates.sort(key=lambda x: x[0])
        return candidates[0][0]

    # --- Fallback: sysfs VID scan on Linux (handles edge cases) ---
    if sys.platform.startswith("linux"):
        for tty in sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")):
            name = os.path.basename(tty)
            try:
                path = os.path.realpath(f"/sys/class/tty/{name}/device")
                for _ in range(6):
                    vid_path = os.path.join(path, "idVendor")
                    if os.path.exists(vid_path):
                        vid = open(vid_path).read().strip().lower()
                        if vid in KNOWN_DEVICES:
                            log.info("Found device via sysfs: %s (VID %s)", tty, vid)
                            return tty
                    path = os.path.dirname(path)
            except Exception:
                pass

    return None


# ---------------------------------------------------------------------------
# Frame parser
# ---------------------------------------------------------------------------

def read_frame(ser: serial.Serial) -> bytes | None:
    """
    Read one complete Meshtastic frame from serial.

    Skips all non-frame bytes (debug text, boot logs, UART noise).
    Returns the raw frame bytes (header + length + payload),
    or None on serial timeout/read error.

    State machine:
      HUNT_S1 → HUNT_S2 → READ_LEN → READ_PAYLOAD
    """
    while True:
        # --- Hunt for START1 ---
        b = ser.read(1)
        if not b:
            return None  # timeout
        if b[0] != START1:
            continue

        # --- Confirm START2 ---
        b2 = ser.read(1)
        if not b2:
            return None
        if b2[0] != START2:
            # If we got another START1, don't discard it — re-check next byte
            if b2[0] == START1:
                b3 = ser.read(1)
                if not b3:
                    return None
                if b3[0] == START2:
                    pass  # fall through with valid header
                else:
                    continue  # discard, restart hunt
            else:
                continue

        # --- Read 2-byte big-endian payload length ---
        len_bytes = ser.read(2)
        if len(len_bytes) < 2:
            return None
        payload_len = struct.unpack(">H", len_bytes)[0]

        if payload_len == 0 or payload_len > MAX_PAYLOAD:
            log.debug("Skipping frame with invalid payload length: %d", payload_len)
            continue  # not a valid frame, resume hunt

        # --- Read payload with guaranteed full read ---
        payload = bytearray()
        while len(payload) < payload_len:
            chunk = ser.read(payload_len - len(payload))
            if not chunk:
                log.debug("Serial read timeout mid-payload (%d/%d bytes)", len(payload), payload_len)
                return None
            payload += chunk

        return bytes([START1, START2]) + len_bytes + bytes(payload)


# ---------------------------------------------------------------------------
# Client manager (supports multiple simultaneous TCP clients)
# ---------------------------------------------------------------------------

class ClientManager:
    """Thread-safe registry of active TCP clients."""

    def __init__(self):
        self._lock = threading.Lock()
        self._clients: dict[socket.socket, tuple] = {}  # conn → addr

    def add(self, conn: socket.socket, addr: tuple):
        with self._lock:
            self._clients[conn] = addr
        log.info("Client connected: %s  (total: %d)", addr, len(self._clients))

    def remove(self, conn: socket.socket):
        with self._lock:
            addr = self._clients.pop(conn, None)
        if addr:
            log.info("Client disconnected: %s  (total: %d)", addr, len(self._clients))

    def broadcast(self, data: bytes):
        """Send data to all clients; silently drop any that have disconnected."""
        with self._lock:
            dead = []
            for conn in self._clients:
                try:
                    conn.sendall(data)
                except Exception:
                    dead.append(conn)
            for conn in dead:
                self._clients.pop(conn, None)

    def count(self) -> int:
        with self._lock:
            return len(self._clients)


# ---------------------------------------------------------------------------
# Thread workers
# ---------------------------------------------------------------------------

def serial_reader(ser: serial.Serial, manager: ClientManager, stop_event: threading.Event):
    """
    Continuously read frames from serial and broadcast to all TCP clients.
    Runs as a single shared thread — one serial port, N clients.
    """
    log.info("Serial reader started")
    while not stop_event.is_set():
        frame = read_frame(ser)
        if frame is None:
            continue  # serial timeout, keep looping
        if manager.count() > 0:
            log.info("Serial→TCP: %d bytes | header: %s", len(frame), frame[:6].hex())
            manager.broadcast(frame)
        else:
            log.info("Serial frame %d bytes — no clients connected, discarding", len(frame))
    log.info("Serial reader stopped")


def tcp_to_serial(conn: socket.socket, ser: serial.Serial,
                  manager: ClientManager, stop_event: threading.Event):
    """
    Forward raw bytes from one TCP client to serial.
    Data arriving from MeshDeck is already properly framed — pass through as-is.
    """
    conn.settimeout(1.0)
    try:
        while not stop_event.is_set():
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break  # clean disconnect
            try:
                ser.write(data)
                log.info("TCP→Serial: %d bytes | hex: %s", len(data), data[:32].hex())
            except serial.SerialException as e:
                log.error("Serial write error: %s", e)
                break
    except Exception as e:
        if not stop_event.is_set():
            log.error("tcp→serial error: %s", e)
    finally:
        manager.remove(conn)
        conn.close()


def handle_client(conn: socket.socket, addr: tuple,
                  ser: serial.Serial, manager: ClientManager,
                  stop_event: threading.Event):
    """Registered a new TCP client and start its forwarding thread."""
    manager.add(conn, addr)
    # Serial → client is handled by the shared serial_reader broadcaster.
    # We only need a dedicated thread for client → serial direction.
    tcp_to_serial(conn, ser, manager, stop_event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Meshtastic USB-to-TCP bridge for MeshDeck",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", "-p", metavar="DEVICE",
                        help="Serial port (auto-detected if omitted)")
    parser.add_argument("--baud", "-b", type=int, default=115200,
                        help="Serial baud rate")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="TCP server bind address")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_PORT,
                        help="TCP server port")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable DEBUG logging")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List detected Meshtastic devices and exit")
    return parser.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # --list mode
    if args.list:
        log.info("Scanning for Meshtastic devices...")
        found = False
        for port_info in serial.tools.list_ports.comports():
            vid_hex = f"{port_info.vid:04x}" if port_info.vid else "????"
            if vid_hex in KNOWN_DEVICES or any(
                kw in (port_info.description or "").lower()
                for kw in ("meshtastic", "rak", "heltec", "lilygo", "tbeam")
            ):
                print(f"  {port_info.device}  VID:{vid_hex}  {port_info.description}")
                found = True
        if not found:
            print("  No Meshtastic devices found.")
        sys.exit(0)

    # Resolve serial port
    serial_port = args.port or find_meshtastic_port()
    if not serial_port:
        log.error("No Meshtastic USB device found. Use --port to specify manually.")
        sys.exit(1)

    log.info("Opening %s at %d baud...", serial_port, args.baud)
    try:
        ser = serial.Serial(serial_port, args.baud, timeout=SERIAL_TIMEOUT)
    except serial.SerialException as e:
        log.error("Cannot open serial port: %s", e)
        sys.exit(1)

    ser.reset_input_buffer()

    # Shared state
    manager = ClientManager()
    stop_event = threading.Event()

    # Start the single shared serial reader thread
    reader_thread = threading.Thread(
        target=serial_reader, args=(ser, manager, stop_event), daemon=True, name="serial-reader"
    )
    reader_thread.start()

    # TCP server
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((args.host, args.tcp_port))
    except OSError as e:
        log.error("Cannot bind %s:%d — %s", args.host, args.tcp_port, e)
        sys.exit(1)

    srv.listen(5)
    log.info("Listening on %s:%d — ready for MeshDeck", args.host, args.tcp_port)

    try:
        while True:
            try:
                conn, addr = srv.accept()
            except OSError:
                break  # server socket closed (KeyboardInterrupt path)
            threading.Thread(
                target=handle_client,
                args=(conn, addr, ser, manager, stop_event),
                daemon=True,
                name=f"client-{addr[1]}",
            ).start()
    except KeyboardInterrupt:
        log.info("Interrupted — shutting down...")
    finally:
        stop_event.set()
        srv.close()
        ser.close()
        log.info("Bridge stopped.")


if __name__ == "__main__":
    main()
