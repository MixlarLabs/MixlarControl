# Wiring Diagram

## Overview

```
                    ┌──────────────────────┐
                    │     ESP32-S3         │
                    │     WROOM-1          │
                    │                      │
   USB-C ──────────┤ USB OTG              │
                    │                      │
                    │  GPIO 11 (SDA) ──────┼──── I2C Bus ────┬──── ADS1015 (0x48)
                    │  GPIO 12 (SCL) ──────┤                 └──── CST816S (0x15)
                    │                      │
                    │  GPIO 38 (ENC_CLK) ──┼──── Rotary Encoder
                    │  GPIO 39 (ENC_DT) ───┤         │
                    │  GPIO 40 (ENC_SW) ───┤         └── Push Button
                    │                      │
                    │  GPIO  7 ────────────┼──── Button 1 ──── GND
                    │  GPIO 15 ────────────┼──── Button 2 ──── GND
                    │  GPIO 10 ────────────┼──── Button 3 ──── GND
                    │  GPIO 13 ────────────┼──── Button 4 ──── GND
                    │  GPIO 47 ────────────┼──── Button 5 ──── GND
                    │  GPIO 48 ────────────┼──── Button 6 ──── GND
                    │                      │
                    │  GPIO 45 ────────────┼──── TFT Backlight (PWM)
                    │  SPI Bus ────────────┼──── ILI9341 Display
                    │                      │
                    └──────────────────────┘

   ADS1015 (I2C ADC)
   ┌─────────┐
   │  CH0 ───┼──── Slider 1 wiper
   │  CH1 ───┼──── Slider 2 wiper
   │  CH2 ───┼──── Slider 3 wiper
   │  CH3 ───┼──── Slider 4 wiper
   │  VDD ───┼──── 3.3V
   │  GND ───┼──── GND
   │  SDA ───┼──── GPIO 11
   │  SCL ───┼──── GPIO 12
   └─────────┘
```

## Slider Wiring

Each slider is a linear potentiometer with 3 pins:

```
  3.3V ───┤top
          │
  ADC  ───┤wiper (center)
          │
  GND  ───┤bottom
```

All 4 sliders feed into the ADS1015 channels 0-3. The ADC reads 0-1650 (12-bit, gain=1).

## Button Wiring

All buttons use internal pull-up resistors. No external resistors needed.

```
  GPIO ────┤ Button ├──── GND
           (normally open)

  Released: GPIO reads HIGH (pulled up internally)
  Pressed:  GPIO reads LOW  (shorted to GND)
```

## Encoder Wiring

Standard EC11 rotary encoder with built-in push switch.

```
  ENC_CLK (GPIO 38) ────┤ A
                         │
  GND ───────────────────┤ C (common)
                         │
  ENC_DT  (GPIO 39) ────┤ B

  ENC_SW  (GPIO 40) ────┤ Switch ├──── GND
```

## I2C Bus

Shared bus at 400kHz with two devices:

```
  3.3V ──── 4.7kΩ ──┬── SDA (GPIO 11)
                     │
  3.3V ──── 4.7kΩ ──┬── SCL (GPIO 12)
                     │
  ADS1015 (0x48) ────┘
  CST816S (0x15) ────┘
```

## Power

Powered entirely from USB-C (5V). The ESP32-S3 module has an onboard 3.3V regulator.
