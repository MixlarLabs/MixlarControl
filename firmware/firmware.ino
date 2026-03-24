// Mixlar Mix Firmware for ESP32-S3
// USB Composite: CDC (Serial) + MIDI + Mass Storage
// License: MIT
// https://mixlar.net

#include <USB.h>
#include <USBMIDI.h>
#include <USBMSC.h>
#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <RotaryEncoder.h>
#include <Preferences.h>
#include <lvgl.h>
#include <TFT_eSPI.h>

// =================== Board Config ===================
// Board: ESP32-S3 Dev Module
// USB Mode: USB-OTG (TinyUSB)
// USB CDC On Boot: Enabled
// PSRAM: OPI PSRAM
// Flash: 16MB (64Mb)

// =================== USB ===================
USBMIDI usbMIDI;
USBMSC msc;

// =================== Display ===================
static const uint16_t screenWidth = 480;
static const uint16_t screenHeight = 320;
TFT_eSPI tft = TFT_eSPI(screenWidth, screenHeight);
static const int backlightPin = 21;

// =================== I2C / ADC ===================
#define I2C_SDA 2
#define I2C_SCL 1
Adafruit_ADS1115 ads;
bool adsPresent = false;

// =================== Sliders ===================
int previousValues[4] = {0};
const int SLIDER_THRESHOLD = 15;
int sliderCalMinRaw[4] = {0, 0, 0, 0};
int sliderCalMaxRaw[4] = {26500, 26500, 26500, 26500};

// =================== Buttons ===================
const int MACRO_PINS[6] = {5, 18, 4, 17, 6, 16};
bool macroButtonState[6] = {HIGH, HIGH, HIGH, HIGH, HIGH, HIGH};
bool lastMacroButtonState[6] = {HIGH, HIGH, HIGH, HIGH, HIGH, HIGH};

// =================== Encoder ===================
#define ENC_CLK 46
#define ENC_DT  3
#define ENC_SW  9
RotaryEncoder encoder(ENC_CLK, ENC_DT, RotaryEncoder::LatchMode::FOUR0);
long lastEncoderPos = 0;

// =================== Touch ===================
#define TOUCH_INT_PIN 8
#define FT6336U_ADDR  0x38
bool touchPresent = false;

// =================== State ===================
Preferences prefs;
bool isConnected = false;
bool psramAvailable = false;
int backlightBrightness = 100;
unsigned long lastCmdTime = 0;

// =================== Mode ===================
enum DeviceMode { MODE_PC_CONTROL, MODE_MIDI_DEVICE };
DeviceMode deviceMode = MODE_PC_CONTROL;

// =================== MIDI Config ===================
uint8_t midiSliderCC[4] = {1, 2, 3, 4};
uint8_t midiSliderChannel[4] = {1, 1, 1, 1};
uint8_t midiMacroNote[6] = {36, 37, 38, 39, 40, 41};
uint8_t midiMacroChannel[6] = {1, 1, 1, 1, 1, 1};
uint8_t midiMacroVelocity[6] = {127, 127, 127, 127, 127, 127};

// =================== Serial Buffer ===================
char serialBuffer[512];
int serialBufferPos = 0;

// =================== Calibration ===================
int mapWithCalibration(int rawValue, int sliderIdx = 0) {
  int minRaw = sliderCalMinRaw[sliderIdx];
  int maxRaw = sliderCalMaxRaw[sliderIdx];
  if (maxRaw <= minRaw) return 0;
  int mapped = map(rawValue, maxRaw, minRaw, 0, 1000);
  return constrain(mapped, 0, 1000);
}

// =================== Touch ===================
int touchReadPoint(uint16_t &x, uint16_t &y) {
  Wire.beginTransmission(FT6336U_ADDR);
  Wire.write(0x02);
  if (Wire.endTransmission(false) != 0) return 0;

  uint8_t buf[5];
  Wire.requestFrom((uint8_t)FT6336U_ADDR, (uint8_t)5);
  for (int i = 0; i < 5 && Wire.available(); i++) buf[i] = Wire.read();

  int touches = buf[0] & 0x0F;
  if (touches == 0 || touches > 2) return 0;

  uint16_t raw_x = ((buf[1] & 0x0F) << 8) | buf[2];
  uint16_t raw_y = ((buf[3] & 0x0F) << 8) | buf[4];

  // Portrait to landscape conversion
  x = 479 - raw_y;
  y = raw_x;

  return touches;
}

void initTouch() {
  pinMode(TOUCH_INT_PIN, INPUT);
  Wire.beginTransmission(FT6336U_ADDR);
  if (Wire.endTransmission() == 0) {
    touchPresent = true;
    Serial.println("FT6336U touch controller initialized");
  } else {
    touchPresent = false;
    Serial.println("FT6336U not found — touch disabled");
  }
}

// =================== Slider Reading ===================
void updateSliders() {
  if (!adsPresent || deviceMode == MODE_MIDI_DEVICE) return;

  for (int i = 0; i < 4; i++) {
    int rawValue = ads.readADC_SingleEnded(i);
    int mappedValue = mapWithCalibration(rawValue, i);

    if (mappedValue > 0 && mappedValue <= 20) mappedValue = 0;

    int absChange = abs(mappedValue - previousValues[i]);
    if (absChange > SLIDER_THRESHOLD) {
      previousValues[i] = mappedValue;
      int percent = mappedValue / 10;
      Serial.printf("SLIDER,%d,%d\n", i, percent);
    }
  }
}

// =================== MIDI Slider Updates ===================
void updateMidiSliders() {
  if (!adsPresent || deviceMode != MODE_MIDI_DEVICE) return;

  static unsigned long lastMidiSendTime[4] = {0, 0, 0, 0};
  static uint8_t pendingMidiValue[4] = {255, 255, 255, 255};
  unsigned long now = millis();

  for (int i = 0; i < 4; i++) {
    int rawValue = ads.readADC_SingleEnded(i);
    int mappedValue = mapWithCalibration(rawValue, i);

    if (mappedValue > 0 && mappedValue <= 20) mappedValue = 0;

    int absChange = abs(mappedValue - previousValues[i]);
    if (absChange > SLIDER_THRESHOLD) {
      previousValues[i] = mappedValue;
      int percent = mappedValue / 10;
      pendingMidiValue[i] = map(percent, 0, 100, 0, 127);
    }

    // Rate-limited MIDI send (max 1 per 10ms per slider)
    if (pendingMidiValue[i] != 255 && (now - lastMidiSendTime[i] >= 10)) {
      uint8_t ch = (midiSliderChannel[i] - 1) & 0x0F;
      usbMIDI.controlChange(midiSliderCC[i], pendingMidiValue[i], midiSliderChannel[i]);
      lastMidiSendTime[i] = now;
      pendingMidiValue[i] = 255;
    }
  }
}

// =================== Button Reading ===================
void updateMacroButtons() {
  for (int i = 0; i < 6; i++) {
    macroButtonState[i] = digitalRead(MACRO_PINS[i]);

    if (macroButtonState[i] == LOW && lastMacroButtonState[i] == HIGH) {
      if (deviceMode == MODE_PC_CONTROL) {
        Serial.printf("MACRO,%d,PRESS\n", i);
      } else {
        // MIDI note on
        usbMIDI.noteOn(midiMacroNote[i], midiMacroVelocity[i], midiMacroChannel[i]);
      }
    }

    if (macroButtonState[i] == HIGH && lastMacroButtonState[i] == LOW) {
      if (deviceMode == MODE_PC_CONTROL) {
        Serial.printf("MACRO,%d,RELEASE\n", i);
      } else {
        usbMIDI.noteOff(midiMacroNote[i], 0, midiMacroChannel[i]);
      }
    }

    lastMacroButtonState[i] = macroButtonState[i];
  }
}

// =================== Serial Commands ===================
void processSerialCommand(const char* cmd) {
  lastCmdTime = millis();

  if (!isConnected) {
    isConnected = true;
    Serial.println("STATE,CONNECTED");
  }

  if (strcmp(cmd, "PING") == 0) {
    Serial.println("PONG");
    return;
  }

  if (strcmp(cmd, "READY") == 0) {
    Serial.println("ACK,READY");
    Serial.printf("DEV_TYPE,Mixlar Mix\n");
    Serial.printf("FW_VER,2.0.0\n");
    return;
  }

  if (strcmp(cmd, "VER") == 0) {
    Serial.println("VER,2.0.0");
    return;
  }

  if (strcmp(cmd, "DEV_TYPE") == 0) {
    Serial.println("DEV_TYPE,Mixlar Mix");
    return;
  }

  // VOL,<idx>,<appname>,<volume>
  if (strncmp(cmd, "VOL,", 4) == 0) {
    // Update slider assignment — parsed by UI layer
    Serial.printf("ACK,%s\n", cmd);
    return;
  }

  // MACRO,<idx>,<name>,<icon>
  if (strncmp(cmd, "MACRO,", 6) == 0) {
    Serial.printf("ACK,%s\n", cmd);
    return;
  }

  // BRIGHTNESS,<0-100>
  if (strncmp(cmd, "BRIGHTNESS,", 11) == 0) {
    int val = atoi(cmd + 11);
    backlightBrightness = constrain(val, 0, 100);
    analogWrite(backlightPin, map(backlightBrightness, 0, 100, 0, 255));
    Serial.printf("ACK,BRIGHTNESS,%d\n", backlightBrightness);
    return;
  }

  if (strcmp(cmd, "REBOOT") == 0) {
    Serial.println("REBOOTING");
    delay(100);
    ESP.restart();
    return;
  }
}

void readSerialCommands() {
  int cmdCount = 0;
  while (Serial.available() && cmdCount < 8) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBufferPos > 0) {
        serialBuffer[serialBufferPos] = '\0';
        processSerialCommand(serialBuffer);
        serialBufferPos = 0;
        cmdCount++;
      }
    } else if (serialBufferPos < (int)sizeof(serialBuffer) - 1) {
      serialBuffer[serialBufferPos++] = c;
    }
  }
}

// =================== Encoder ===================
void updateEncoder() {
  encoder.tick();
  long pos = encoder.getPosition();
  if (pos != lastEncoderPos) {
    long delta = pos - lastEncoderPos;
    lastEncoderPos = pos;
    if (deviceMode == MODE_PC_CONTROL) {
      Serial.printf("ENCODER,%ld\n", delta);
    }
  }
}

// =================== Backlight ===================
void applyBrightness(int percent) {
  int pwmValue = map(percent, 0, 100, 0, 255);
  analogWrite(backlightPin, pwmValue);
}

// =================== Setup ===================
void setup() {
  // USB init first
  USB.VID(0x1209);
  USB.PID(0x4D58);
  USB.productName("Mixlar Mix");
  USB.manufacturerName("MixlarLabs");
  usbMIDI.begin();
  Serial.setRxBufferSize(16384);
  Serial.setTxTimeoutMs(0);
  Serial.begin(2000000);
  USB.begin();
  delay(200);

  // Backlight off during init
  pinMode(backlightPin, OUTPUT);
  analogWrite(backlightPin, 0);

  // Display
  tft.begin();
  tft.setRotation(3);
  tft.setSwapBytes(true);
  tft.fillScreen(TFT_BLACK);

  // PSRAM
  psramAvailable = psramFound();
  if (psramAvailable) {
    Serial.printf("[PSRAM] %u bytes available\n", ESP.getPsramSize());
  }

  // I2C
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);

  // ADS1115
  if (ads.begin()) {
    ads.setGain(GAIN_ONE);
    ads.setDataRate(RATE_ADS1115_860SPS);
    adsPresent = true;
    Serial.println("ADS1115 initialized");
  } else {
    Serial.println("ADS1115 init failed — sliders disabled");
  }

  // Touch
  initTouch();

  // Buttons
  for (int i = 0; i < 6; i++) {
    pinMode(MACRO_PINS[i], INPUT_PULLUP);
  }

  // Encoder
  pinMode(ENC_SW, INPUT_PULLUP);

  // Load settings
  prefs.begin("settings", true);
  backlightBrightness = prefs.getInt("brightness", 100);
  for (int i = 0; i < 4; i++) {
    char key[16];
    snprintf(key, sizeof(key), "slCal%dMin", i);
    sliderCalMinRaw[i] = prefs.getInt(key, 0);
    snprintf(key, sizeof(key), "slCal%dMax", i);
    sliderCalMaxRaw[i] = prefs.getInt(key, 26500);
  }
  prefs.end();

  // Backlight on
  applyBrightness(backlightBrightness);

  Serial.println("Mixlar Mix ready");
  Serial.printf("Free heap: %d bytes\n", ESP.getFreeHeap());
}

// =================== Loop ===================
void loop() {
  readSerialCommands();
  updateSliders();
  updateMidiSliders();
  updateMacroButtons();
  updateEncoder();

  // Encoder button
  static bool encDown = false;
  bool encState = digitalRead(ENC_SW);
  if (encState == LOW && !encDown) {
    encDown = true;
    Serial.println("ENCODER,PRESS");
  }
  if (encState == HIGH && encDown) {
    encDown = false;
    Serial.println("ENCODER,RELEASE");
  }

  delay(1);
}
