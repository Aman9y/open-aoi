/*
 * AI Visual Quality Inspection — ESP32 station controller (Wi-Fi)
 * ------------------------------------------------------------------
 * Output-only lamp stack + reject gate. No vision runs here.
 *
 * The ESP32 polls   GET http://<BACKEND>/api/station/state   a few times a
 * second and, whenever the verdict counter changes, drives:
 *
 *      GREEN LED        = GOOD
 *      RED LED          = DEFECTIVE
 *      GREEN + RED both = REVIEW  (caution — no amber LED in this build)
 *      SERVO            = one swing of the reject gate on a new {reject:true}
 *
 * The lamp holds the last verdict until the next inspection. The servo fires
 * once per transition INTO a rejected verdict (not repeatedly in live mode).
 *
 * Trigger an inspection from the dashboard's "Trigger inspection" button
 * (Inspect page, Station card) or from any /inspect call — this board only
 * reacts to results. Optional button/buzzer: see the #if 0 block at the end.
 *
 * WIRING (this build)
 *   GREEN LED : GPIO 25 -> 220 ohm -> LED(+),  LED(-) -> GND
 *   RED   LED : GPIO 26 -> 220 ohm -> LED(+),  LED(-) -> GND
 *   SG90 SERVO: GPIO 27 -> signal (orange/yellow)
 *               VCC (red) -> EXTERNAL 5V   (NOT the ESP32 3V3 pin)
 *               GND (brown/black) -> common GND with the ESP32
 *
 * LIBRARIES (Arduino IDE -> Library Manager)
 *   ArduinoJson  (Benoit Blanchon)  v7
 *   ESP32Servo   (Kevin Harrington)
 *   WiFi + HTTPClient ship with the ESP32 board package.
 *
 * Board: any ESP32 dev module.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>

// ================== CONFIGURE ME ==================
static const char* WIFI_SSID = "Aman-lapi";
static const char* WIFI_PASS = "12345678";

// The laptop running: uvicorn app.main:app --host 0.0.0.0 --port 8000
// Find its LAN IP -> Windows: ipconfig   macOS/Linux: ip addr
static const char* BACKEND_HOST = "192.168.137.1";
static const uint16_t BACKEND_PORT = 8000;

static const int PIN_LED_GREEN = 25;
static const int PIN_LED_RED   = 26;
static const int PIN_SERVO     = 27;
static const int PIN_ONBOARD   =  2;   // Wi-Fi status LED on most dev boards

static const int SERVO_PASS_ANGLE   = 20;
static const int SERVO_REJECT_ANGLE = 110;

static const unsigned long POLL_MS = 400;
// =================================================

Servo gate;

unsigned long lastPoll = 0;
long   lastCounter = -1;
String currentVerdict = "IDLE";
bool   lastReject = false;

String backendURL(const char* path) {
  return String("http://") + BACKEND_HOST + ":" + BACKEND_PORT + path;
}

void lamps(bool green, bool red) {
  digitalWrite(PIN_LED_GREEN, green);
  digitalWrite(PIN_LED_RED, red);
}

void rejectPart() {
  gate.write(SERVO_REJECT_ANGLE);
  delay(700);
  gate.write(SERVO_PASS_ANGLE);
}

void applyVerdict(const String& verdict, bool reject) {
  currentVerdict = verdict;
  if (verdict == "GOOD") {
    lamps(true, false);
  } else if (verdict == "DEFECTIVE") {
    lamps(false, true);
  } else if (verdict == "REVIEW") {
    lamps(true, true);          // both on = caution (steady, no blink)
  } else {
    lamps(false, false);
  }
  // fire the reject gate once, only on the transition into a rejected verdict
  if (reject && !lastReject) rejectPart();
  lastReject = reject;
  Serial.printf("verdict=%s reject=%d\n", verdict.c_str(), reject);
}

void connectWiFi() {
  Serial.printf("WiFi: connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    digitalWrite(PIN_ONBOARD, !digitalRead(PIN_ONBOARD));
    delay(300);
    Serial.print(".");
  }
  digitalWrite(PIN_ONBOARD, HIGH);
  Serial.printf("\nWiFi: %s  ->  backend %s\n",
                WiFi.localIP().toString().c_str(), backendURL("").c_str());
}

void pollState() {
  HTTPClient http;
  http.setConnectTimeout(1500);
  http.begin(backendURL("/api/station/state?client=esp32"));
  int code = http.GET();
  static unsigned long lastBeat = 0;
  if (code == 200) {
    JsonDocument doc;
    if (deserializeJson(doc, http.getString()) == DeserializationError::Ok) {
      bool en = doc["enabled"].as<bool>();
      long counter = doc["counter"].as<long>();
      if (millis() - lastBeat > 5000) {   // heartbeat every ~5 s
        lastBeat = millis();
        Serial.printf("poll ok  enabled=%d  counter=%ld  verdict=%s\n",
                      en, counter, doc["verdict"].as<String>().c_str());
      }
      if (!en) {
        if (lastCounter != -2) {
          lamps(false, false); currentVerdict = "IDLE"; lastReject = false; lastCounter = -2;
        }
      } else if (counter != lastCounter) {
        lastCounter = counter;
        applyVerdict(doc["verdict"].as<String>(), doc["reject"].as<bool>());
      }
    }
  } else {
    Serial.printf("state poll FAILED (HTTP %d) — check BACKEND_HOST + backend running with --host 0.0.0.0\n", code);
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_ONBOARD, OUTPUT);

  gate.setPeriodHertz(50);
  gate.attach(PIN_SERVO, 500, 2400);
  gate.write(SERVO_PASS_ANGLE);

  lamps(true, false); delay(200);
  lamps(false, true); delay(200);
  lamps(false, false);

  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  if (millis() - lastPoll >= POLL_MS) {
    lastPoll = millis();
    pollState();
  }
}

/* ---------------------------------------------------------------------------
 * OPTIONAL EXTRAS — enable if you wire them up.
 *
 *   Amber LED  : add   static const int PIN_LED_AMBER = 33;
 *                pinMode OUTPUT in setup(); in applyVerdict() light it for
 *                REVIEW instead of "both LEDs on".
 *
 *   Buzzer     : static const int PIN_BUZZER = 14;  (active buzzer + to pin)
 *                short beep on GOOD, triple beep + reject on DEFECTIVE.
 *
 *   Button /   : static const int PIN_BUTTON = 4;  (to GND, INPUT_PULLUP)
 *   IR sensor    On a debounced falling edge, POST http://<BACKEND>/api/station/trigger
 *                with body "{}" so the board can start an inspection itself.
 * ------------------------------------------------------------------------- */
