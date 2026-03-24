"""
Mixlar Mix — Desktop Control Software
Connects to Mixlar Mix over USB serial and manages audio routing.
License: MIT
"""

import sys
import time
import json
import threading
import serial
import serial.tools.list_ports
from pathlib import Path

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, ISimpleAudioVolume
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

import psutil

# =================== Config ===================

BAUD_RATE = 2_000_000
DEVICE_NAME = "Mixlar Mix"
CONFIG_FILE = Path.home() / ".mixlar" / "config.json"

# =================== Device Discovery ===================

def find_mixlar_port():
    """Find the Mixlar Mix serial port by USB VID/PID or product name."""
    for port in serial.tools.list_ports.comports():
        if port.vid == 0x1209 and port.pid == 0x4D58:
            return port.device
        if port.product and "Mixlar" in port.product:
            return port.device
        # Fallback: Espressif VID with CDC
        if port.vid == 0x303A and port.description and "Mixlar" in port.description:
            return port.device
    return None


# =================== Audio Control ===================

class AudioController:
    """Windows audio session controller using pycaw."""

    def __init__(self):
        self.sessions = {}
        self.master_volume = None
        self._init_master()

    def _init_master(self):
        if not AUDIO_AVAILABLE:
            return
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.master_volume = cast(interface, POINTER(IAudioEndpointVolume))
        except Exception as e:
            print(f"[Audio] Master volume init failed: {e}")

    def get_sessions(self):
        """Get active audio sessions."""
        if not AUDIO_AVAILABLE:
            return {}
        sessions = {}
        try:
            for session in AudioUtilities.GetAllSessions():
                if session.Process:
                    name = session.Process.name().replace(".exe", "")
                    sessions[name.lower()] = session
        except Exception:
            pass
        self.sessions = sessions
        return sessions

    def set_app_volume(self, app_name, volume):
        """Set volume for a specific app (0.0 - 1.0)."""
        if not AUDIO_AVAILABLE:
            return False
        self.get_sessions()
        key = app_name.lower()
        if key in self.sessions:
            try:
                vol = self.sessions[key]._ctl.QueryInterface(ISimpleAudioVolume)
                vol.SetMasterVolume(max(0.0, min(1.0, volume)), None)
                return True
            except Exception:
                pass
        return False

    def set_master_volume(self, volume):
        """Set master volume (0.0 - 1.0)."""
        if self.master_volume:
            try:
                self.master_volume.SetMasterVolumeLevelScalar(
                    max(0.0, min(1.0, volume)), None
                )
                return True
            except Exception:
                pass
        return False

    def get_master_volume(self):
        """Get current master volume (0.0 - 1.0)."""
        if self.master_volume:
            try:
                return self.master_volume.GetMasterVolumeLevelScalar()
            except Exception:
                pass
        return 0.0


# =================== Config ===================

class Config:
    """Persistent configuration for slider/macro assignments."""

    def __init__(self):
        self.data = {
            "sliders": [
                {"app": "master", "label": "Master"},
                {"app": "spotify", "label": "Spotify"},
                {"app": "chrome", "label": "Chrome"},
                {"app": "discord", "label": "Discord"},
            ],
            "macros": [
                {"name": "Mute", "action": "mute_toggle"},
                {"name": "Play/Pause", "action": "media_playpause"},
                {"name": "Next", "action": "media_next"},
                {"name": "Prev", "action": "media_prev"},
                {"name": "Screenshot", "action": "screenshot"},
                {"name": "Lock", "action": "lock_screen"},
            ],
        }
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.data, f, indent=2)


# =================== Device Connection ===================

class MixlarDevice:
    """Serial connection to Mixlar Mix."""

    def __init__(self):
        self.serial = None
        self.connected = False
        self.running = False
        self.audio = AudioController()
        self.config = Config()
        self.on_slider = None
        self.on_macro = None
        self.on_encoder = None

    def connect(self, port=None):
        """Connect to device."""
        if port is None:
            port = find_mixlar_port()
        if port is None:
            print("[Device] Mixlar Mix not found")
            return False

        try:
            self.serial = serial.Serial(port, BAUD_RATE, timeout=0.1)
            time.sleep(0.5)
            self.serial.write(b"READY\n")
            self.connected = True
            print(f"[Device] Connected on {port}")
            return True
        except Exception as e:
            print(f"[Device] Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from device."""
        self.running = False
        if self.serial:
            self.serial.close()
        self.connected = False

    def send(self, command):
        """Send a command to the device."""
        if self.serial and self.connected:
            try:
                self.serial.write(f"{command}\n".encode())
            except Exception:
                self.connected = False

    def _handle_line(self, line):
        """Process a line from the device."""
        line = line.strip()
        if not line:
            return

        # Slider moved
        if line.startswith("SLIDER,"):
            parts = line.split(",")
            if len(parts) == 3:
                idx = int(parts[1])
                value = int(parts[2])
                self._handle_slider(idx, value)
                if self.on_slider:
                    self.on_slider(idx, value)

        # Macro button
        elif line.startswith("MACRO,"):
            parts = line.split(",")
            if len(parts) == 3:
                idx = int(parts[1])
                action = parts[2]
                if action == "PRESS":
                    self._handle_macro(idx)
                    if self.on_macro:
                        self.on_macro(idx)

        # Encoder
        elif line.startswith("ENCODER,"):
            parts = line.split(",")
            if len(parts) == 2:
                if self.on_encoder:
                    self.on_encoder(parts[1])

        # Connection
        elif line == "STATE,CONNECTED":
            print("[Device] Handshake complete")

        # QA result
        elif line.startswith("QA,"):
            parts = line.split(",", 2)
            print(f"[QA] Result: {parts[1]} ({parts[2] if len(parts) > 2 else ''})")

    def _handle_slider(self, idx, value):
        """Route slider to audio control."""
        if idx < 0 or idx >= 4:
            return
        slider_config = self.config.data["sliders"][idx]
        app = slider_config.get("app", "")
        volume = value / 100.0

        if app == "master":
            self.audio.set_master_volume(volume)
        elif app:
            self.audio.set_app_volume(app, volume)

    def _handle_macro(self, idx):
        """Execute macro action."""
        if idx < 0 or idx >= 6:
            return
        macro = self.config.data["macros"][idx]
        action = macro.get("action", "")
        print(f"[Macro] Button {idx + 1}: {macro.get('name', '')} ({action})")

    def send_slider_labels(self):
        """Send slider labels to device display."""
        for i, slider in enumerate(self.config.data["sliders"]):
            label = slider.get("label", f"Slider {i + 1}")
            self.send(f"VOL,{i},{label},50")

    def send_macro_labels(self):
        """Send macro labels to device display."""
        for i, macro in enumerate(self.config.data["macros"]):
            name = macro.get("name", f"Macro {i + 1}")
            self.send(f"MACRO,{i},{name},")

    def run(self):
        """Main read loop — call from a thread."""
        self.running = True
        self.send_slider_labels()
        self.send_macro_labels()

        while self.running and self.connected:
            try:
                if self.serial.in_waiting:
                    line = self.serial.readline().decode("utf-8", errors="ignore")
                    self._handle_line(line)
                else:
                    time.sleep(0.001)
            except Exception:
                self.connected = False
                break

        print("[Device] Disconnected")


# =================== System Stats ===================

def get_system_stats():
    """Get CPU, RAM, GPU usage for device widgets."""
    cpu = psutil.cpu_percent(interval=0)
    ram = psutil.virtual_memory().percent
    return {"cpu": cpu, "ram": ram}


# =================== Main ===================

def main():
    print("Mixlar Mix Control Software v2.0.0")
    print("===================================")

    device = MixlarDevice()

    # Auto-discover and connect
    port = find_mixlar_port()
    if port:
        print(f"Found Mixlar Mix on {port}")
        if device.connect(port):
            # Run in background thread
            thread = threading.Thread(target=device.run, daemon=True)
            thread.start()

            print("Listening for device events. Press Ctrl+C to quit.")
            try:
                while device.connected:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                device.disconnect()
    else:
        print("Mixlar Mix not found. Connect via USB-C and try again.")
        print("Available serial ports:")
        for port in serial.tools.list_ports.comports():
            print(f"  {port.device}: {port.description}")


if __name__ == "__main__":
    main()
