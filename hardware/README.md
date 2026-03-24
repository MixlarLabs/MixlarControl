# Hardware

## Specifications

| Component | Part | Interface |
|-----------|------|-----------|
| MCU | ESP32-S3-WROOM-1 (N16R8) | - |
| Display | 3.5" 480x320 IPS TFT | SPI (ST7796) |
| Touch | FT6336U | I2C (0x38) |
| ADC | ADS1115 | I2C (0x48) |
| Sliders | 4x 60mm linear B10K | ADS1115 CH0-CH3 |
| Buttons | 6x mechanical switch | GPIO (INPUT_PULLUP) |
| Encoder | EC11 rotary + push | GPIO |
| USB | USB-C (OTG) | TinyUSB composite |
| Backlight | PWM LED driver | GPIO 21 |

## Pin Mapping

| Function | GPIO |
|----------|------|
| I2C SDA | 2 |
| I2C SCL | 1 |
| Encoder CLK | 46 |
| Encoder DT | 3 |
| Encoder SW | 9 |
| Touch INT | 8 |
| Backlight | 21 |
| Macro 1 | 5 |
| Macro 2 | 18 |
| Macro 3 | 4 |
| Macro 4 | 17 |
| Macro 5 | 6 |
| Macro 6 | 16 |

## I2C Bus

400kHz clock, shared between ADS1115 (0x48) and FT6336U (0x38).

## Display

SPI interface configured via TFT_eSPI `User_Setup.h`. ST7796 driver, landscape orientation (rotation 3), hardware SPI.
