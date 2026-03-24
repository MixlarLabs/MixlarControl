# Serial Protocol

USB CDC serial at 2,000,000 baud. Line-based text protocol (newline terminated).

## PC → Device

| Command | Description |
|---------|-------------|
| `PING` | Keepalive check |
| `READY` | PC software ready handshake |
| `VER` | Request firmware version |
| `DEV_TYPE` | Request device type |
| `VOL,<idx>,<label>,<vol>` | Set slider label and initial volume |
| `MACRO,<idx>,<name>,<icon>` | Set macro button label and icon |
| `BRIGHTNESS,<0-100>` | Set display brightness |
| `REBOOT` | Reboot device |
| `ENTER_QA` | Enter QA test mode |
| `ENTER_STORAGE` | Enter USB mass storage mode |

## Device → PC

| Response | Description |
|----------|-------------|
| `PONG` | Reply to PING |
| `ACK,READY` | Handshake acknowledged |
| `STATE,CONNECTED` | Connection established |
| `VER,<version>` | Firmware version |
| `DEV_TYPE,Mixlar Mix` | Device type |
| `SLIDER,<idx>,<0-100>` | Slider position changed |
| `MACRO,<idx>,PRESS` | Macro button pressed |
| `MACRO,<idx>,RELEASE` | Macro button released |
| `ENCODER,<delta>` | Encoder rotated (positive=CW) |
| `ENCODER,PRESS` | Encoder button pressed |
| `ENCODER,RELEASE` | Encoder button released |

## QA Mode

Send `ENTER_QA` to start. Device runs through hardware tests automatically.

| State Message | Phase |
|---------------|-------|
| `STATE,QA,HW_DETECT` | Hardware detection complete |
| `STATE,QA,TOUCH_TEST` | Touch screen test |
| `STATE,QA,SLIDER_TEST` | Slider range test |
| `STATE,QA,MACRO_TEST` | Button press test |
| `STATE,QA,ENCODER_TEST` | Encoder rotation test |
| `STATE,QA,BACKLIGHT_TEST` | Backlight ramp test |
| `STATE,QA,COLOR_TEST` | Color cycle test |
| `STATE,QA,MULTICOLOR_TEST` | Multi-color bar test |
| `STATE,QA,RESULTS` | Final results |

Final verdict: `QA,PASS,<build_date>` or `QA,FAIL,<build_date>`
