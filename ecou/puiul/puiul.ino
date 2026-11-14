// Puiul, Ecou's companion in the kitchen, on an Arduino UNO R4 WiFi (P27, 08-ecou.md §2.6).
//
// It talks only to Ecou, over Ecou's own Wi-Fi, in small JSON datagrams to UDP 4210:
//   {"id":17,"type":"sos"}    the foil pad held for 2 s; resent until Ecou answers
//   {"id":18,"type":"pass"}   someone crossed the doorway (only with an HC-SR04 fitted)
//   {"id":19,"type":"alive"}  every 30 s
// Ecou answers each with {"ack":17,"room_state":"ok","code":"green"}.
//
// The matrix: a heart when someone passes, "!" while an SOS waits, a tick when Ecou took
// it, a glass of water when the room is hot and nobody came to the kitchen for an hour,
// a slow "z" without Wi-Fi.
//
// Needs the Arduino_CapacitiveTouch library. Board: Arduino UNO R4 WiFi.

#include <Arduino_CapacitiveTouch.h>
#include <Arduino_LED_Matrix.h>
#include <WiFiS3.h>

#include "arduino_secrets.h"

// --- configuration -------------------------------------------------------------------

const IPAddress ECOU_IP(10, 42, 0, 1);  // the hotspot's address on NetworkManager
const uint16_t ECOU_PORT = 4210;
const int PIN_PAD = D2;         // the foil pad; D2 supports touch on the R4 WiFi
const int TOUCH_DELTA = 400;    // raw rise over the resting value that counts as a touch
const int PIN_US_TRIG = -1;     // -1: no HC-SR04 in the doorway (the team has one, on Ecou)
const int PIN_US_ECHO = -1;
const float DOOR_M = 0.9;       // nearer than this across the doorway is someone passing

const unsigned long SOS_HOLD_MS = 2000;
const unsigned long RESEND_MS = 1000;
const unsigned long ALIVE_MS = 30000;
const unsigned long WATER_AFTER_MS = 3600000UL;  // an hour without a pass in the heat

// --- state ---------------------------------------------------------------------------

ArduinoLEDMatrix matrix;
CapacitiveTouch pad(PIN_PAD);
WiFiUDP udp;

uint32_t nextId = 1;
uint32_t sosId = 0;            // 0: no SOS waiting
unsigned long sosSentAt = 0;
unsigned long touchSince = 0;
unsigned long lastAlive = 0;
unsigned long lastPass = 0;
unsigned long showUntil = 0;
bool someoneInDoor = false;
char roomState[12] = "ok";

// --- icons, 8 rows x 12 columns --------------------------------------------------------

uint8_t frame[8][12];

void icon(const char* rows[8]) {
  for (int r = 0; r < 8; r++)
    for (int c = 0; c < 12; c++) frame[r][c] = rows[r][c] == '#';
  matrix.loadPixels(&frame[0][0], 8 * 12);
}

const char* HEART[8] = {"............", "..##....##..", ".####..####.", ".##########.",
                        "..########..", "...######...", "....####....", ".....##....."};
const char* ALERT[8] = {".....##.....", ".....##.....", ".....##.....", ".....##.....",
                        ".....##.....", "............", ".....##.....", ".....##....."};
const char* TICK[8] = {"............", "..........#.", ".........##.", "........##..",
                       "..#....##...", "..##..##....", "...####.....", "....##......"};
const char* GLASS[8] = {"...######...", "...#....#...", "...#....#...", "...######...",
                        "...######...", "...######...", "....####....", "....####...."};
const char* SLEEP[8] = {"............", "......####..", ".........#..", "........#...",
                        ".......#....", "......####..", "............", "............"};
const char* BLANK[8] = {"............", "............", "............", "............",
                        "............", "............", "............", "............"};

// --- network ---------------------------------------------------------------------------

void send(const char* type, uint32_t id) {
  char msg[48];
  snprintf(msg, sizeof msg, "{\"id\":%lu,\"type\":\"%s\"}", (unsigned long)id, type);
  udp.beginPacket(ECOU_IP, ECOU_PORT);
  udp.write((const uint8_t*)msg, strlen(msg));
  udp.endPacket();
}

void readReplies() {
  int size = udp.parsePacket();
  if (size <= 0) return;
  char buf[128];
  int n = udp.read(buf, sizeof buf - 1);
  if (n <= 0) return;
  buf[n] = 0;
  // {"ack": 17, "room_state": "ok", "code": "green"}: no JSON library for three fields
  const char* ack = strstr(buf, "\"ack\"");
  if (ack && sosId && strtoul(strchr(ack, ':') + 1, nullptr, 10) == sosId) {
    sosId = 0;
    icon(TICK);
    showUntil = millis() + 3000;
  }
  const char* rs = strstr(buf, "\"room_state\"");
  if (rs) {
    const char* q = strchr(strchr(rs, ':'), '"');
    if (q) {
      int i = 0;
      for (q++; *q && *q != '"' && i < (int)sizeof roomState - 1; q++) roomState[i++] = *q;
      roomState[i] = 0;
    }
  }
}

bool connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return true;
  icon(SLEEP);
  WiFi.begin(SECRET_SSID, SECRET_PASS);
  for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  if (WiFi.status() != WL_CONNECTED) return false;
  udp.begin(ECOU_PORT);
  icon(BLANK);
  return true;
}

// --- sensors ---------------------------------------------------------------------------

float doorwayMetres() {
  if (PIN_US_TRIG < 0) return -1;
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);
  unsigned long us = pulseIn(PIN_US_ECHO, HIGH, 30000);  // µs on this core
  return us == 0 ? -1 : us * 0.000343f / 2;
}

// --- main ------------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  matrix.begin();
  if (PIN_US_TRIG >= 0) {
    pinMode(PIN_US_TRIG, OUTPUT);
    pinMode(PIN_US_ECHO, INPUT);
  }
  pad.begin();
  long rest = 0;
  for (int i = 0; i < 20; i++) {
    rest += pad.read();
    delay(20);
  }
  pad.setThreshold(rest / 20 + TOUCH_DELTA);
  Serial.print("puiul: pad resting at ");
  Serial.println(rest / 20);
  connectWifi();
  lastPass = millis();
}

void loop() {
  unsigned long now = millis();
  if (!connectWifi()) {
    delay(1000);
    return;
  }
  readReplies();

  // The pad: held for SOS_HOLD_MS is an SOS (P27), sent until Ecou answers
  if (pad.isTouched()) {
    if (!touchSince) touchSince = now;
    if (!sosId && now - touchSince >= SOS_HOLD_MS) {
      sosId = nextId++;
      sosSentAt = 0;
      Serial.println("puiul: SOS");
    }
  } else {
    touchSince = 0;
  }
  if (sosId && now - sosSentAt >= RESEND_MS) {
    sosSentAt = now;
    send("sos", sosId);
    icon(ALERT);
    showUntil = now + RESEND_MS + 500;
  }

  // The doorway: one pass when someone comes into the beam
  float d = doorwayMetres();
  bool inDoor = d > 0 && d < DOOR_M;
  if (inDoor && !someoneInDoor) {
    send("pass", nextId++);
    lastPass = now;
    if (!sosId) {
      icon(HEART);
      showUntil = now + 1500;
    }
  }
  someoneInDoor = inDoor;

  if (now - lastAlive >= ALIVE_MS) {
    lastAlive = now;
    send("alive", nextId++);
  }

  // Back to rest: the glass when it is hot and nobody came for water in a while
  if (!sosId && now > showUntil) {
    bool hot = strncmp(roomState, "hot", 3) == 0;
    icon(hot && now - lastPass > WATER_AFTER_MS ? GLASS : BLANK);
    showUntil = now + 1000;
  }
  delay(60);
}
