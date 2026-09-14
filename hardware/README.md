# Physical inspection station — ESP32 (Wi-Fi)

Optional. The software runs fully without any of this. The ESP32 turns the
software into a bench station: a button/sensor starts an inspection, a lamp stack
shows the verdict, and a servo flicks defective parts off the jig.

```
   phone camera ─▶ laptop (backend + dashboard)
                        ▲            │
          POST /trigger │            │ GET /state  (poll ~2.5 Hz)
                        │            ▼
                     ESP32 ──▶ GREEN / RED / AMBER LED
                       │  └───▶ SERVO  (reject gate)
                       │  └───▶ BUZZER
                       └──◀──  BUTTON / part-present sensor
```

## 1. Wiring (this build)

| Signal | ESP32 pin | Wiring |
|---|---|---|
| Green LED | GPIO 25 | GPIO 25 → 220 Ω → LED(+),  LED(−) → GND |
| Red LED   | GPIO 26 | GPIO 26 → 220 Ω → LED(+),  LED(−) → GND |
| SG90 servo signal | GPIO 27 | orange/yellow wire |
| SG90 servo power  | external **5 V** | red wire — **not** the ESP32 3V3 pin |
| SG90 servo ground | GND | brown/black — common GND with the ESP32 |
| Wi-Fi status | GPIO 2 | on-board LED (most boards) |

`REVIEW` is shown as **both LEDs on (steady caution)** (no amber in this build).
Power the servo from a separate 5 V supply and tie all grounds together — a servo
browns out the ESP32's regulator.

Optional extras (amber LED, buzzer, button/IR trigger) are documented at the
bottom of the sketch.

## 2. Firmware

Arduino IDE → Library Manager, install:

- **ArduinoJson** (Benoit Blanchon) — v7
- **ESP32Servo** (Kevin Harrington)

(`WiFi` + `HTTPClient` come with the ESP32 board package.)

Open `inspection_station/inspection_station.ino`, edit the **CONFIGURE ME** block:

```cpp
WIFI_SSID / WIFI_PASS       // your 2.4 GHz network
BACKEND_HOST                // the laptop's LAN IP  (Windows: ipconfig)
SERVO_PASS_ANGLE / SERVO_REJECT_ANGLE
```

Flash it. The Serial Monitor (115200) prints the ESP32 IP and each verdict.
Trigger inspections from the dashboard (Inspect → Station card → **Trigger
inspection**); the board only reacts to results.

## 3. Backend

Start the API bound to the LAN (not just localhost) so the ESP32 can reach it:

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Enable the station and point it at the camera the phone provides (same URL you'd
use in the dashboard's Stream mode, or a local index):

```
AOI_STATION_ENABLED=true
AOI_STATION_SOURCE=http://192.168.1.42:8080/video
# AOI_STATION_REFERENCE_ID=PCB_MODEL_001     # default: the active reference
# AOI_STATION_REJECT_STATUSES=["DEFECTIVE"]  # statuses that fire the reject gate
```

(put these in `.env` at the repo root, or export them before starting uvicorn.)

## 4. Check it

- `GET http://<laptop>:8000/api/station/state` → `{enabled:true, esp32_online:true, ...}`
  once the ESP32 is polling.
- The dashboard **Inspect** page shows a **Station** card (connection + a
  **Trigger inspection** button).
- Trigger → inspection runs → LED + servo react → the run appears in **History**.

### Multiple cameras

Set `AOI_STATION_VIEWS` (JSON) instead of `AOI_STATION_SOURCE` to inspect an
object from up to 3 angles at once — the station verdict is the worst of the
views, and the servo fires if any view is `DEFECTIVE`:

```
AOI_STATION_VIEWS=[
  {"name":"front","source":"http://192.168.1.42:8080/video","reference_id":"BOX_FRONT"},
  {"name":"top","source":"http://192.168.1.43:8080/video","reference_id":"BOX_TOP"},
  {"name":"back","source":"0","reference_id":"BOX_BACK"}
]
```

## Notes / limits

- One part at a time — the servo move blocks the ESP32 for ~0.7 s.
- The ESP32 acts on `counter` changes, so the lamp stack also reflects
  inspections started from the dashboard (upload / live camera / multi-cam).
- No auth on the station endpoints — keep the API on a trusted LAN.
