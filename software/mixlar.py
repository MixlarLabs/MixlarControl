"""
Mixlar Mix — Desktop Control Software
Connects to Mixlar Mix over USB serial and controls per-app audio.

Usage:
  1. Edit config.json to assign apps to sliders and actions to macros
  2. Run: python mixlar.py
  3. Move sliders on the device to control app volumes

License: MIT
"""

import sys
import time
import json
import threading
import subprocess
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

# =================== Constants ===================

BAUD_RATE = 2_000_000
CONFIG_DIR = Path.home() / ".mixlar"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "sliders": [
        {"app": "master", "label": "Master"},
        {"app": "", "label": "Slider 2"},
        {"app": "", "label": "Slider 3"},
        {"app": "", "label": "Slider 4"}
    ],
    "macros": [
        {"name": "Macro 1", "action": "none"},
        {"name": "Macro 2", "action": "none"},
        {"name": "Macro 3", "action": "none"},
        {"name": "Macro 4", "action": "none"},
        {"name": "Macro 5", "action": "none"},
        {"name": "Macro 6", "action": "none"}
    ]
}

# Built-in macro actions
MACRO_ACTIONS = {
    "none":            lambda: None,
    "mute_toggle":     lambda: _media_key(0xAD),
    "media_playpause": lambda: _media_key(0xB3),
    "media_next":      lambda: _media_key(0xB0),
    "media_prev":      lambda: _media_key(0xB1),
    "vol_up":          lambda: _media_key(0xAF),
    "vol_down":        lambda: _media_key(0xAE),
}

def _media_key(vk):
    """Send a media key press via Windows API."""
    try:
        import ctypes
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
    except Exception:
        pass

# =================== Config ===================

def load_config():
    """Load config from ~/.mixlar/config.json or create default."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
                # Merge with defaults for missing keys
                for key in DEFAULT_CONFIG:
                    if key not in data:
                        data[key] = DEFAULT_CONFIG[key]
                return data
        except Exception:
            pass

    # Create default config
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(data):
    """Save config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

# =================== Device Discovery ===================

def find_device():
    """Auto-detect Mixlar Mix on USB."""
    for port in serial.tools.list_ports.comports():
        # Check VID/PID
        if port.vid == 0x1209 and port.pid == 0x4D58:
            return port.device
        # Fallback: Espressif VID
        if port.vid == 0x303A:
            return port.device
        # Name match
        if port.product and "Mixlar" in port.product:
            return port.device
    return None

# =================== Audio ===================

class AudioMixer:
    """Controls per-app audio on Windows using pycaw."""

    def __init__(self):
        self.master = None
        if AUDIO_AVAILABLE:
            try:
                dev = AudioUtilities.GetSpeakers()
                iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self.master = cast(iface, POINTER(IAudioEndpointVolume))
            except Exception:
                pass

    def set_volume(self, app_name, value):
        """Set volume for an app (0-100) or 'master'."""
        vol = max(0.0, min(1.0, value / 100.0))

        if app_name == "master":
            if self.master:
                try:
                    self.master.SetMasterVolumeLevelScalar(vol, None)
                except Exception:
                    pass
            return

        if not AUDIO_AVAILABLE:
            return

        # Find audio session by process name
        try:
            for session in AudioUtilities.GetAllSessions():
                if session.Process:
                    name = session.Process.name().replace(".exe", "").lower()
                    if name == app_name.lower():
                        sv = session._ctl.QueryInterface(ISimpleAudioVolume)
                        sv.SetMasterVolume(vol, None)
                        return
        except Exception:
            pass

    def list_sessions(self):
        """List currently active audio sessions."""
        apps = []
        if not AUDIO_AVAILABLE:
            return apps
        try:
            for session in AudioUtilities.GetAllSessions():
                if session.Process:
                    apps.append(session.Process.name().replace(".exe", ""))
        except Exception:
            pass
        return sorted(set(apps))

# =================== Main Controller ===================

class MixlarController:
    """
    Reads serial data from Mixlar Mix and routes it.

    Device sends:
      SLIDER,<0-3>,<0-100>     — slider moved
      MACRO,<0-5>,PRESS        — button pressed
      MACRO,<0-5>,RELEASE      — button released
      ENCODER,<delta>          — encoder rotated
      ENCODER,PRESS            — encoder clicked
    """

    def __init__(self):
        self.config = load_config()
        self.audio = AudioMixer()
        self.ser = None
        self.connected = False
        self.running = False

    def connect(self, port=None):
        """Connect to device."""
        if port is None:
            port = find_device()
        if not port:
            return False

        try:
            self.ser = serial.Serial(port, BAUD_RATE, timeout=0.1)
            time.sleep(0.3)
            # Handshake
            self.ser.write(b"READY\n")
            self.connected = True

            # Send slider labels to device
            for i, s in enumerate(self.config["sliders"]):
                label = s.get("label", f"Slider {i+1}")
                self.ser.write(f"VOL,{i},{label},50\n".encode())

            # Send macro names to device
            for i, m in enumerate(self.config["macros"]):
                name = m.get("name", f"Macro {i+1}")
                self.ser.write(f"MACRO,{i},{name},\n".encode())

            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def _on_slider(self, idx, value):
        """Handle slider movement."""
        if idx < 0 or idx >= len(self.config["sliders"]):
            return
        app = self.config["sliders"][idx].get("app", "")
        if app:
            self.audio.set_volume(app, value)
            print(f"  Slider {idx+1} -> {app}: {value}%")

    def _on_macro(self, idx):
        """Handle macro button press."""
        if idx < 0 or idx >= len(self.config["macros"]):
            return
        macro = self.config["macros"][idx]
        action = macro.get("action", "none")
        name = macro.get("name", f"Macro {idx+1}")

        # Check built-in actions
        if action in MACRO_ACTIONS:
            print(f"  Button {idx+1} ({name}): {action}")
            MACRO_ACTIONS[action]()
        # Custom command (starts with "run:")
        elif action.startswith("run:"):
            cmd = action[4:].strip()
            print(f"  Button {idx+1} ({name}): running '{cmd}'")
            try:
                subprocess.Popen(cmd, shell=True)
            except Exception as e:
                print(f"  Error: {e}")
        # Keyboard shortcut (starts with "key:")
        elif action.startswith("key:"):
            keys = action[4:].strip()
            print(f"  Button {idx+1} ({name}): key '{keys}'")
            _send_keys(keys)
        else:
            print(f"  Button {idx+1} ({name}): unknown action '{action}'")

    def _on_encoder(self, data):
        """Handle encoder events — adjust master volume."""
        if data == "PRESS":
            print("  Encoder pressed")
            return
        if data == "RELEASE":
            return
        try:
            delta = int(data)
            if self.audio.master:
                cur = self.audio.master.GetMasterVolumeLevelScalar()
                new = max(0.0, min(1.0, cur + delta * 0.02))
                self.audio.master.SetMasterVolumeLevelScalar(new, None)
                print(f"  Encoder: master volume {int(new * 100)}%")
        except Exception:
            pass

    def run(self):
        """Main loop — read serial and dispatch."""
        self.running = True
        while self.running and self.connected:
            try:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    parts = line.split(",")

                    if parts[0] == "SLIDER" and len(parts) == 3:
                        self._on_slider(int(parts[1]), int(parts[2]))

                    elif parts[0] == "MACRO" and len(parts) >= 3:
                        if parts[2] == "PRESS":
                            self._on_macro(int(parts[1]))

                    elif parts[0] == "ENCODER" and len(parts) == 2:
                        self._on_encoder(parts[1])

                    elif line == "STATE,CONNECTED":
                        print("  Device handshake complete")

                    elif line == "PONG":
                        pass  # keepalive reply

                else:
                    time.sleep(0.001)
            except serial.SerialException:
                self.connected = False
                break
            except Exception as e:
                print(f"  Error: {e}")

    def stop(self):
        self.running = False
        if self.ser:
            self.ser.close()
        self.connected = False

def _send_keys(combo):
    """Send a keyboard shortcut like 'ctrl+shift+s'."""
    try:
        import ctypes
        VK_MAP = {
            "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
            "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "space": 0x20,
            "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
            "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
            "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
        }
        keys = [k.strip().lower() for k in combo.split("+")]
        vks = []
        for k in keys:
            if k in VK_MAP:
                vks.append(VK_MAP[k])
            elif len(k) == 1:
                vks.append(ord(k.upper()))

        for vk in vks:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        for vk in reversed(vks):
            ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)
    except Exception:
        pass

# =================== CLI ===================

def print_config(config):
    """Pretty print current config."""
    print("\n  Slider Assignments:")
    for i, s in enumerate(config["sliders"]):
        app = s.get("app", "") or "(unassigned)"
        label = s.get("label", f"Slider {i+1}")
        print(f"    Slider {i+1}: {label} -> {app}")

    print("\n  Macro Assignments:")
    for i, m in enumerate(config["macros"]):
        name = m.get("name", f"Macro {i+1}")
        action = m.get("action", "none")
        print(f"    Button {i+1}: {name} -> {action}")
    print()

def setup_wizard(config, audio):
    """Interactive setup for slider and macro assignments."""
    print("\n=== Mixlar Mix Setup ===\n")

    # Show available apps
    sessions = audio.list_sessions()
    if sessions:
        print("  Active audio apps:")
        for app in sessions:
            print(f"    - {app}")
    print()

    # Slider setup
    print("  Assign apps to sliders (or press Enter to skip):")
    print("  Special names: 'master' = system volume\n")
    for i in range(4):
        current = config["sliders"][i].get("app", "")
        app = input(f"  Slider {i+1} [{current}]: ").strip()
        if app:
            config["sliders"][i]["app"] = app
            config["sliders"][i]["label"] = app.capitalize()

    # Macro setup
    print("\n  Assign actions to macros:")
    print("  Built-in: mute_toggle, media_playpause, media_next, media_prev, vol_up, vol_down")
    print("  Custom:   run:notepad.exe  |  key:ctrl+shift+s\n")
    for i in range(6):
        current = config["macros"][i].get("action", "none")
        action = input(f"  Button {i+1} [{current}]: ").strip()
        if action:
            config["macros"][i]["action"] = action
            # Auto-name from action
            if action in MACRO_ACTIONS:
                config["macros"][i]["name"] = action.replace("_", " ").title()
            elif action.startswith("run:"):
                config["macros"][i]["name"] = action[4:].split("/")[-1].split("\\")[-1]
            elif action.startswith("key:"):
                config["macros"][i]["name"] = action[4:].upper()

    save_config(config)
    print("\n  Config saved to", CONFIG_FILE)

def main():
    print()
    print("  Mixlar Mix v2.0")
    print("  ===============")

    config = load_config()
    audio = AudioMixer()

    # Parse args
    if len(sys.argv) > 1:
        if sys.argv[1] == "setup":
            setup_wizard(config, audio)
            return
        elif sys.argv[1] == "config":
            print_config(config)
            return
        elif sys.argv[1] == "list":
            print("\n  Active audio sessions:")
            for app in audio.list_sessions():
                print(f"    - {app}")
            print()
            return
        elif sys.argv[1] == "midi":
            # MIDI mode — switch device to MIDI and optionally configure
            port = find_device()
            if not port:
                print("  Device not found.")
                return
            ser = serial.Serial(port, BAUD_RATE, timeout=0.5)
            time.sleep(0.3)
            ser.write(b"MODE,MIDI\n")
            print("  Switched to MIDI mode")
            # Apply MIDI config if present
            midi_conf = config.get("midi", {})
            for i in range(4):
                cc = midi_conf.get(f"slider_{i}_cc", i + 1)
                ch = midi_conf.get(f"slider_{i}_ch", 1)
                ser.write(f"MIDI,CC,{i},{cc}\n".encode())
                ser.write(f"MIDI,CH,{i},{ch}\n".encode())
                print(f"    Slider {i+1}: CC {cc} on channel {ch}")
            for i in range(6):
                note = midi_conf.get(f"button_{i}_note", 36 + i)
                ser.write(f"MIDI,NOTE,{i},{note}\n".encode())
                print(f"    Button {i+1}: Note {note}")
            print("\n  Device is now in MIDI mode. Sliders send CC, buttons send notes.")
            print("  Use 'python mixlar.py pc' to switch back.")
            ser.close()
            return
        elif sys.argv[1] == "pc":
            # Switch back to PC control mode
            port = find_device()
            if not port:
                print("  Device not found.")
                return
            ser = serial.Serial(port, BAUD_RATE, timeout=0.5)
            time.sleep(0.3)
            ser.write(b"MODE,PC\n")
            print("  Switched to PC control mode")
            ser.close()
            return
        elif sys.argv[1] == "preset":
            # Load a preset config
            if len(sys.argv) < 3:
                print("  Available presets:")
                preset_dir = Path(__file__).parent / "presets"
                if preset_dir.exists():
                    for f in sorted(preset_dir.glob("*.json")):
                        try:
                            p = json.loads(f.read_text())
                            print(f"    {f.stem:20s} — {p.get('description', '')}")
                        except Exception:
                            print(f"    {f.stem}")
                print(f"\n  Usage: python mixlar.py preset <name>")
                return
            preset_name = sys.argv[2]
            preset_file = Path(__file__).parent / "presets" / f"{preset_name}.json"
            if not preset_file.exists():
                print(f"  Preset '{preset_name}' not found.")
                return
            preset = json.loads(preset_file.read_text())
            config["sliders"] = preset.get("sliders", config["sliders"])
            config["macros"] = preset.get("macros", config["macros"])
            save_config(config)
            print(f"  Loaded preset: {preset.get('name', preset_name)}")
            print_config(config)
            return

    # Show current config
    print_config(config)

    # Find and connect
    port = find_device()
    if not port:
        print("  Mixlar Mix not found. Connect via USB-C and try again.")
        print("  Available ports:")
        for p in serial.tools.list_ports.comports():
            print(f"    {p.device}: {p.description}")
        return

    print(f"  Found device on {port}")

    ctrl = MixlarController()
    ctrl.config = config
    if not ctrl.connect(port):
        return

    print("  Connected! Listening for events...\n")

    try:
        ctrl.run()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.stop()
        print("\n  Disconnected.")

if __name__ == "__main__":
    main()
