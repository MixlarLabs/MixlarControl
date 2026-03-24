# Mixlar Mix

Open-source USB audio mixer and MIDI controller built on ESP32-S3.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-ESP32--S3-orange.svg)
![USB](https://img.shields.io/badge/USB-TinyUSB%20CDC%20%2B%20MIDI-green.svg)

## What is Mixlar Mix?

Mixlar Mix is a desktop audio controller that combines 4 analog sliders, 6 programmable macro buttons, a rotary encoder, and a 480x320 touch display into a compact USB device. It connects to your PC over USB-C and lets you control per-app audio volumes, trigger macros, and display live system information.

## Hardware

- **MCU**: ESP32-S3 (dual-core 240MHz, 8MB PSRAM)
- **Display**: 2.8" 320x240 IPS TFT (ILI9341) with capacitive touch (CST816S)
- **ADC**: ADS1015 12-bit I2C ADC (4 slider channels)
- **Sliders**: 4x 45mm linear potentiometers
- **Buttons**: 6x tactile switches
- **Encoder**: Rotary encoder with push button
- **Connection**: USB-C (TinyUSB composite: CDC + MIDI + MSC)
- **Wireless**: BLE 5.0 (UART + MIDI)

## USB Device Info

| Field | Value |
|-------|-------|
| VID | `0x1209` (pid.codes) |
| PID | `0x4D58` |
| Product | Mixlar Mix |
| Manufacturer | MixlarLabs |

## Project Structure

```
firmware/          ESP32-S3 Arduino firmware
software/          Python desktop control software
hardware/          Schematic and PCB info
docs/              Documentation
```

## Firmware

The firmware runs on ESP32-S3 with Arduino framework and uses:
- **LVGL** for the touch UI
- **TinyUSB** for composite USB (Serial CDC + MIDI + Mass Storage)
- **Adafruit ADS1015** for 12-bit slider ADC
- **BLE** for wireless MIDI and serial

### Building

1. Install [Arduino IDE](https://www.arduino.cc/en/software) or Arduino CLI
2. Add ESP32 board support (Espressif ESP32 v3.0.0+)
3. Board settings:
   - Board: `ESP32S3 Dev Module`
   - USB Mode: `USB-OTG (TinyUSB)`
   - USB CDC On Boot: `Enabled`
   - PSRAM: `OPI PSRAM`
   - Flash Size: `16MB`
4. Install libraries: `Adafruit ADS1X15`, `LVGL`, `RotaryEncoder`, `TFT_eSPI`
5. Open `firmware/firmware.ino` and upload

## Software

Python desktop app that communicates with the Mixlar Mix over USB serial.

### Installation

```bash
cd software
pip install -r requirements.txt
python mixlar.py
```

### Features

- Per-app audio volume control
- Macro button configuration
- Slider assignment (app volumes, system, MIDI)
- Live device status monitoring
- Spotify integration
- OBS Studio integration

## Serial Protocol

The device communicates over USB CDC serial at 2,000,000 baud.

### Commands (PC to Device)

| Command | Description |
|---------|-------------|
| `PING` | Keepalive check |
| `READY` | Handshake — PC software is ready |
| `VOL,<idx>,<app>,<vol>` | Set slider label and volume |
| `MACRO,<idx>,<name>,<icon>` | Set macro button label |
| `ENTER_QA` | Enter QA test mode |
| `ENTER_STORAGE` | Enter USB mass storage mode |

### Responses (Device to PC)

| Response | Description |
|----------|-------------|
| `PONG` | Reply to PING |
| `STATE,CONNECTED` | Device connected |
| `SLIDER,<idx>,<value>` | Slider moved (0-100) |
| `MACRO,<idx>,PRESS` | Macro button pressed |
| `MACRO,<idx>,RELEASE` | Macro button released |
| `QA,PASS,<date>` | QA test passed |
| `QA,FAIL,<date>` | QA test failed |

## License

MIT License. See [LICENSE](LICENSE) for details.

## Links

- Website: [mixlar.net](https://mixlar.net)
- Issues: [GitHub Issues](https://github.com/MixlarLabs/MixlarControl/issues)
