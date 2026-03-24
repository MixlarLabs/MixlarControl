// Mixlar Mix Firmware for ESP32-S3
// Reads sliders, buttons, and encoder — sends events over USB serial.
// The Python software (mixlar.py) handles audio routing and macros.
// License: MIT

#include <USB.h>
#include <USBMIDI.h>
#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <RotaryEncoder.h>
#include <Preferences.h>
#include <TFT_eSPI.h>

// =================== USB ===================
USBMIDI usbMIDI;

// =================== Display ===================
static const uint16_t screenWidth = 320;
static const uint16_t screenHeight = 240;
TFT_eSPI tft = TFT_eSPI(screenWidth, screenHeight);
static const int backlightPin = 45;

// =================== I2C / ADC ===================
#define I2C_SDA 11
#define I2C_SCL 12
Adafruit_ADS1015 ads;
bool adsPresent = false;

// =================== Sliders ===================
int prevSlider[4] = {0};
const int THRESHOLD = 12;

// =================== Buttons ===================
const int BTN_PINS[6] = {7, 15, 10, 13, 47, 48};
bool btnState[6] = {1, 1, 1, 1, 1, 1};
bool btnPrev[6]  = {1, 1, 1, 1, 1, 1};

// =================== Encoder ===================
#define ENC_CLK 38
#define ENC_DT  39
#define ENC_SW  40
RotaryEncoder encoder(ENC_CLK, ENC_DT, RotaryEncoder::LatchMode::FOUR0);
long lastEncPos = 0;
bool encDown = false;

// =================== Touch ===================
#define TOUCH_INT 14
#define TOUCH_ADDR 0x15
bool touchOk = false;

// =================== State ===================
Preferences prefs;
bool connected = false;
char cmdBuf[256];
int cmdPos = 0;

// =================== MIDI config ===================
uint8_t midiCC[4] = {1, 2, 3, 4};
uint8_t midiCh[4] = {1, 1, 1, 1};
uint8_t midiNote[6] = {36, 37, 38, 39, 40, 41};
bool midiMode = false;

// =================== Slider reading ===================
int readSlider(int ch) {
  int raw = ads.readADC_SingleEnded(ch);
  int mapped = map(raw, 1650, 0, 0, 100);
  return constrain(mapped, 0, 100);
}

void updateSliders() {
  if (!adsPresent) return;

  for (int i = 0; i < 4; i++) {
    int val = readSlider(i);
    if (abs(val - prevSlider[i]) > 1) {
      prevSlider[i] = val;

      if (midiMode) {
        // Rate-limited MIDI CC
        static unsigned long lastSend[4] = {0};
        if (millis() - lastSend[i] >= 10) {
          usbMIDI.controlChange(midiCC[i], map(val, 0, 100, 0, 127), midiCh[i]);
          lastSend[i] = millis();
        }
      } else {
        Serial.printf("SLIDER,%d,%d\n", i, val);
      }
    }
  }
}

// =================== Button reading ===================
void updateButtons() {
  for (int i = 0; i < 6; i++) {
    btnState[i] = digitalRead(BTN_PINS[i]);

    // Press
    if (btnState[i] == LOW && btnPrev[i] == HIGH) {
      if (midiMode) {
        usbMIDI.noteOn(midiNote[i], 127, 1);
      } else {
        Serial.printf("MACRO,%d,PRESS\n", i);
      }
    }

    // Release
    if (btnState[i] == HIGH && btnPrev[i] == LOW) {
      if (midiMode) {
        usbMIDI.noteOff(midiNote[i], 0, 1);
      } else {
        Serial.printf("MACRO,%d,RELEASE\n", i);
      }
    }

    btnPrev[i] = btnState[i];
  }
}

// =================== Encoder ===================
void updateEncoder() {
  encoder.tick();
  long pos = encoder.getPosition();
  if (pos != lastEncPos) {
    long delta = pos - lastEncPos;
    lastEncPos = pos;
    Serial.printf("ENCODER,%ld\n", delta);
  }

  bool sw = digitalRead(ENC_SW);
  if (sw == LOW && !encDown) {
    encDown = true;
    Serial.println("ENCODER,PRESS");
  }
  if (sw == HIGH && encDown) {
    encDown = false;
    Serial.println("ENCODER,RELEASE");
  }
}

// =================== Touch init ===================
void initTouch() {
  pinMode(TOUCH_INT, INPUT);
  Wire.beginTransmission(TOUCH_ADDR);
  touchOk = (Wire.endTransmission() == 0);
  Serial.printf("Touch: %s\n", touchOk ? "OK" : "not found");
}

// =================== Serial commands ===================
void processCommand(const char* cmd) {
  if (!connected) {
    connected = true;
    Serial.println("STATE,CONNECTED");
  }

  if (strcmp(cmd, "PING") == 0) {
    Serial.println("PONG");
  }
  else if (strcmp(cmd, "READY") == 0) {
    Serial.println("ACK,READY");
    Serial.println("DEV_TYPE,Mixlar Mix");
    Serial.println("FW_VER,2.0.0");
  }
  else if (strcmp(cmd, "VER") == 0) {
    Serial.println("VER,2.0.0");
  }
  else if (strncmp(cmd, "VOL,", 4) == 0) {
    Serial.printf("ACK,%s\n", cmd);
  }
  else if (strncmp(cmd, "MACRO,", 6) == 0) {
    Serial.printf("ACK,%s\n", cmd);
  }
  else if (strncmp(cmd, "BRIGHTNESS,", 11) == 0) {
    int b = constrain(atoi(cmd + 11), 0, 100);
    analogWrite(backlightPin, map(b, 0, 100, 0, 255));
    Serial.printf("ACK,BRIGHTNESS,%d\n", b);
  }
  else if (strcmp(cmd, "REBOOT") == 0) {
    Serial.println("REBOOTING");
    delay(100);
    ESP.restart();
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdPos > 0) {
        cmdBuf[cmdPos] = '\0';
        processCommand(cmdBuf);
        cmdPos = 0;
      }
    } else if (cmdPos < 255) {
      cmdBuf[cmdPos++] = c;
    }
  }
}

// =================== Setup ===================
void setup() {
  // USB
  USB.VID(0x1209);
  USB.PID(0x4D58);
  USB.productName("Mixlar Mix");
  USB.manufacturerName("MixlarLabs");
  usbMIDI.begin();
  Serial.setTxTimeoutMs(0);
  Serial.begin(2000000);
  USB.begin();
  delay(200);

  // Display
  pinMode(backlightPin, OUTPUT);
  analogWrite(backlightPin, 0);
  tft.begin();
  tft.setRotation(1);
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE);
  tft.setTextSize(2);
  tft.setCursor(40, 100);
  tft.print("Mixlar Mix");
  tft.setTextSize(1);
  tft.setCursor(40, 130);
  tft.print("Waiting for connection...");
  analogWrite(backlightPin, 255);

  // I2C + ADC
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);
  adsPresent = ads.begin();
  if (adsPresent) {
    ads.setGain(GAIN_ONE);
    Serial.println("ADC: OK");
  } else {
    Serial.println("ADC: not found");
  }

  // Touch
  initTouch();

  // Buttons
  for (int i = 0; i < 6; i++) pinMode(BTN_PINS[i], INPUT_PULLUP);

  // Encoder
  pinMode(ENC_SW, INPUT_PULLUP);

  Serial.println("Mixlar Mix ready");
}

// =================== Loop ===================
void loop() {
  readSerial();
  updateSliders();
  updateButtons();
  updateEncoder();
  delay(1);
}
