# Hardware

## Specifications

| Component | Part | Interface |
|-----------|------|-----------|
| MCU | ESP32-S3-WROOM-1 (N16R8) | - |
| Display | 2.8" 320x240 IPS TFT | SPI (ILI9341) |
| Touch | CST816S | I2C (0x15) |
| ADC | ADS1015 | I2C (0x48) |
| Sliders | 4x 45mm linear B10K | ADS1015 CH0-CH3 |
| Buttons | 6x tactile switch | GPIO (INPUT_PULLUP) |
| Encoder | EC11 rotary + push | GPIO |
| USB | USB-C (OTG) | TinyUSB composite |
| Backlight | PWM LED driver | GPIO 45 |

## Pin Mapping

| Function | GPIO |
|----------|------|
| I2C SDA | 11 |
| I2C SCL | 12 |
| Encoder CLK | 38 |
| Encoder DT | 39 |
| Encoder SW | 40 |
| Touch INT | 14 |
| Backlight | 45 |
| Macro 1 | 7 |
| Macro 2 | 15 |
| Macro 3 | 10 |
| Macro 4 | 13 |
| Macro 5 | 47 |
| Macro 6 | 48 |

## I2C Bus

400kHz clock, shared between ADS1015 (0x48) and CST816S (0x15).

## Display

SPI interface configured via TFT_eSPI `User_Setup.h`. ILI9341 driver, landscape orientation (rotation 1), hardware SPI.
