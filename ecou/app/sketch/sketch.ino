// Ecou, the microcontroller side (08-ecou.md §2).
//
// The sketch makes no decisions. It runs the Python app's commands (look there, sweep,
// shiver, draw this face) and streams what it measures back over the Bridge. Every
// decision is made on Linux.
//
// Commands from Python (Bridge.call):
//   look(pan, tilt)                  move the head; it glides there at SLEW_DEG_PER_TICK
//   stream(period_ms)                ping straight ahead every period; 0 stops
//   sweep(from, to, step, tilt)      one sweep, a ping per step; ends with sweep_end
//   stop()                           no more pings
//   shiver(ms) / fan(ms)             body animations for the room state (§2.5)
//   arm(deg)                         arm rest position; ARM_FLAG_DEG is the red flag
//   draw(bytes)                      an 8x13 frame, brightness 0..7
//   show_temp(tenths_c)              "21°C" on the 7-segment display
//   show_number(n)                   n on the display; DISPLAY_BLANK clears it
//
// Notifications to Python (Bridge.notify):
//   dist(ms, pan, tilt, echo_us)     a ping while streaming; echo_us 0 means no echo
//   sweep_pt(seq, pan, tilt, echo_us)
//   sweep_end(seq)
//   temp(ms, tenths_c, tenths_rh, ok)
//
// Echo times go up raw: Python turns them into distances with the speed of sound at
// the measured room temperature.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Servo.h>
#include <zephyr/kernel.h>
#include <vector>

// ---------------------------------------------------------------------------------
// Configuration: change these to match the parts on the table.

#define TEMP_DHT11 11
#define TEMP_DHT22 22
#define TEMP_SENSOR TEMP_DHT11

const int PIN_DHT = 4;
const int PIN_ARM = -1;   // -1: not fitted. The arm servo goes on D6
const int PIN_US_TRIG = 7;
const int PIN_US_ECHO = 8;  // through a 1k/2k divider: HC-SR04 echo is 5 V, the UNO Q is 3.3 V
const int PIN_PAN = 9;
const int PIN_TILT = -1;  // -1: not fitted. The tilt servo goes on D10

// 5641AS, 4 digits, common cathode. Its pins, face up with the decimal points at the
// bottom, pin 1 bottom left: A 11, B 7, C 4, D 2, E 1, F 10, G 5, DP 3 (not used);
// digits 1 to 4 on 12, 9, 8, 6. Each segment pin through a 1 kΩ resistor, so one
// digit pin never sinks more than about 10 mA; the digit pins go straight to the board.
const int PIN_SEGMENTS[7] = {2, 3, 5, 11, 12, 13, A0};  // A to G
const int PIN_DIGITS[4] = {A1, A2, A3, A4};              // leftmost first

// Servo limits in degrees, so the mount never hits its stops. Narrow them once the
// head is built.
const int PAN_MIN = 0, PAN_MAX = 180;
const int TILT_MIN = 30, TILT_MAX = 150;
const int ARM_MIN = 0, ARM_MAX = 180;
const int ARM_FLAG_DEG = 180;

// ---------------------------------------------------------------------------------

const int SERVO_TICK_MS = 20;
const int SLEW_DEG_PER_TICK = 4;     // 200°/s: smooth, and quiet enough
const int SWEEP_SETTLE_MS = 45;      // after a 5° step the head stops wobbling
const uint32_t ECHO_TIMEOUT_US = 30000;  // about 5 m; HC-SR04 gives up at 4
const int TEMP_PERIOD_MS = 2000;     // a DHT11 cannot be read faster than once a second
const int DISPLAY_BLANK = -32768;

enum Mode { MODE_IDLE, MODE_STREAM, MODE_SWEEP };

Arduino_LED_Matrix matrix;
Servo panServo, tiltServo, armServo;

// Written by the Bridge handlers, which run on another thread; read by loop().
volatile int cmdMode = MODE_IDLE;
volatile int targetPan = 90, targetTilt = 90, armRest = ARM_MIN;
volatile int streamPeriodMs = 50;
volatile int sweepFrom = 0, sweepTo = 180, sweepStep = 5, sweepTilt = 90;
volatile bool sweepRequested = false;
volatile uint32_t shiverUntil = 0, fanUntil = 0, fanStart = 0;

K_MUTEX_DEFINE(frameLock);
uint8_t frame[104] = {0};
volatile bool frameDirty = true;

volatile bool displayDirty = true;
volatile int displayKind = 0;  // 0 number, 1 temperature
volatile int displayValue = DISPLAY_BLANK;

// ---------------------------------------------------------------------------------
// HC-SR04: the echo is timed by an interrupt, so the Bridge thread can run meanwhile.

volatile uint32_t echoRiseUs = 0, echoFallUs = 0;
volatile bool echoDone = false;
bool pingBusy = false;
uint32_t pingStartUs = 0;

void onEcho() {
  if (digitalRead(PIN_US_ECHO) == HIGH) {
    echoRiseUs = micros();
  } else if (echoRiseUs != 0) {
    echoFallUs = micros();
    echoDone = true;
  }
}

void startPing() {
  echoRiseUs = 0;
  echoDone = false;
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);
  pingStartUs = micros();
  pingBusy = true;
}

// Returns true when the ping is over; echoUs is 0 when nothing came back.
bool pollPing(uint32_t &echoUs) {
  if (!pingBusy) return false;
  if (echoDone) {
    echoUs = echoFallUs - echoRiseUs;
    pingBusy = false;
    return true;
  }
  if (micros() - pingStartUs > ECHO_TIMEOUT_US + 5000) {
    echoUs = 0;
    pingBusy = false;
    return true;
  }
  return false;
}

// ---------------------------------------------------------------------------------
// DHT11 / DHT22, polled. The scheduler is locked for the ~5 ms of bits so the Bridge
// thread cannot stretch a pulse; interrupts still run, so nothing is lost on the UART.

long waitWhile(int level, uint32_t timeoutUs) {
  uint32_t t0 = micros();
  while (digitalRead(PIN_DHT) == level) {
    if (micros() - t0 > timeoutUs) return -1;
  }
  return micros() - t0;
}

bool readTemperature(int &tenthsC, int &tenthsRh) {
  uint8_t d[5] = {0, 0, 0, 0, 0};
  pinMode(PIN_DHT, OUTPUT);
  digitalWrite(PIN_DHT, LOW);
  delay(TEMP_SENSOR == TEMP_DHT11 ? 20 : 2);
  pinMode(PIN_DHT, INPUT_PULLUP);

  bool ok = true;
  k_sched_lock();
  // The sensor answers with about 80 µs low, then 80 µs high.
  if (waitWhile(HIGH, 200) < 0 || waitWhile(LOW, 200) < 0 || waitWhile(HIGH, 200) < 0) {
    ok = false;
  }
  for (int i = 0; ok && i < 40; i++) {
    if (waitWhile(LOW, 100) < 0) { ok = false; break; }
    long high = waitWhile(HIGH, 120);
    if (high < 0) { ok = false; break; }
    d[i / 8] <<= 1;
    if (high > 48) d[i / 8] |= 1;  // 26-28 µs is a 0, 70 µs is a 1
  }
  k_sched_unlock();

  if (!ok || (uint8_t)(d[0] + d[1] + d[2] + d[3]) != d[4]) return false;

  if (TEMP_SENSOR == TEMP_DHT11) {
    tenthsRh = d[0] * 10 + d[1];
    tenthsC = d[2] * 10 + (d[3] & 0x0F);
    if (d[3] & 0x80) tenthsC = -tenthsC;
  } else {
    tenthsRh = (d[0] << 8) | d[1];
    tenthsC = ((d[2] & 0x7F) << 8) | d[3];
    if (d[2] & 0x80) tenthsC = -tenthsC;
  }
  return true;
}

// ---------------------------------------------------------------------------------
// 5641AS, multiplexed by a 1 ms Zephyr timer, so the digits stay steady while loop()
// waits on a ping or reads the DHT. A segment lights when its pin is HIGH and its
// digit's pin is LOW.

const uint8_t SEG_DIGITS[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};
const uint8_t SEG_MINUS = 0x40, SEG_DEGREE = 0x63, SEG_C = 0x39, SEG_BLANK = 0x00;

volatile uint8_t displaySeg[4] = {SEG_BLANK, SEG_BLANK, SEG_BLANK, SEG_BLANK};
volatile int muxDigit = 0;

void muxTick(struct k_timer *) {
  digitalWrite(PIN_DIGITS[muxDigit], HIGH);  // the previous digit off
  muxDigit = (muxDigit + 1) % 4;
  uint8_t seg = displaySeg[muxDigit];
  for (int i = 0; i < 7; i++) digitalWrite(PIN_SEGMENTS[i], (seg >> i) & 1 ? HIGH : LOW);
  digitalWrite(PIN_DIGITS[muxDigit], LOW);   // this one on
}

K_TIMER_DEFINE(muxTimer, muxTick, NULL);

void renderDisplay() {
  uint8_t seg[4] = {SEG_BLANK, SEG_BLANK, SEG_BLANK, SEG_BLANK};
  int v = displayValue;
  if (v == DISPLAY_BLANK) {
    // all blank
  } else if (displayKind == 1) {
    int c = (v >= 0 ? v + 5 : v - 5) / 10;  // whole degrees, rounded
    c = constrain(c, -9, 99);
    if (c < 0) {
      seg[0] = SEG_MINUS;
      seg[1] = SEG_DIGITS[-c];
    } else {
      seg[0] = c >= 10 ? SEG_DIGITS[c / 10] : SEG_BLANK;
      seg[1] = SEG_DIGITS[c % 10];
    }
    seg[2] = SEG_DEGREE;
    seg[3] = SEG_C;
  } else {
    v = constrain(v, -999, 9999);
    bool neg = v < 0;
    if (neg) v = -v;
    int i = 3;
    do { seg[i--] = SEG_DIGITS[v % 10]; v /= 10; } while (v > 0 && i >= 0);
    if (neg && i >= 0) seg[i] = SEG_MINUS;
  }
  for (int i = 0; i < 4; i++) displaySeg[i] = seg[i];
}

// ---------------------------------------------------------------------------------
// Bridge handlers. They only record what was asked; loop() does the work.

void cmdLook(int pan, int tilt) {
  targetPan = constrain(pan, PAN_MIN, PAN_MAX);
  targetTilt = constrain(tilt, TILT_MIN, TILT_MAX);
}

void cmdStream(int periodMs) {
  if (periodMs <= 0) {
    cmdMode = MODE_IDLE;
    return;
  }
  streamPeriodMs = max(periodMs, 40);  // HC-SR04 needs the last echo to die out
  cmdMode = MODE_STREAM;
}

void cmdSweep(int from, int to, int step, int tilt) {
  sweepFrom = constrain(from, PAN_MIN, PAN_MAX);
  sweepTo = constrain(to, PAN_MIN, PAN_MAX);
  sweepStep = max(abs(step), 1);
  sweepTilt = constrain(tilt, TILT_MIN, TILT_MAX);
  sweepRequested = true;
  cmdMode = MODE_SWEEP;
}

void cmdStop() { cmdMode = MODE_IDLE; }

void cmdShiver(int ms) { shiverUntil = millis() + max(ms, 0); }

void cmdFan(int ms) {
  fanStart = millis();
  fanUntil = fanStart + max(ms, 0);
}

void cmdArm(int deg) { armRest = constrain(deg, ARM_MIN, ARM_MAX); }

void cmdDraw(std::vector<uint8_t> f) {
  k_mutex_lock(&frameLock, K_FOREVER);
  size_t n = min(f.size(), sizeof(frame));
  memcpy(frame, f.data(), n);
  frameDirty = true;
  k_mutex_unlock(&frameLock);
}

void cmdShowTemp(int tenthsC) {
  displayKind = 1;
  displayValue = tenthsC;
  displayDirty = true;
}

void cmdShowNumber(int n) {
  displayKind = 0;
  displayValue = n;
  displayDirty = true;
}

// ---------------------------------------------------------------------------------

int curPan = 90, curTilt = 90;
uint32_t lastServoMs = 0, lastPingMs = 0, lastTempMs = 0;

// Sweep state
int sweepSeq = 0, sweepAngle = 0, sweepDir = 1;
bool sweepActive = false;
uint32_t sweepMovedMs = 0;
bool sweepWaitingPing = false;

int stepToward(int cur, int target) {
  if (cur < target) return min(cur + SLEW_DEG_PER_TICK, target);
  if (cur > target) return max(cur - SLEW_DEG_PER_TICK, target);
  return cur;
}

void updateServos(uint32_t now) {
  if (now - lastServoMs < SERVO_TICK_MS) return;
  lastServoMs = now;

  if (!sweepActive) {
    curPan = stepToward(curPan, targetPan);
    curTilt = stepToward(curTilt, targetTilt);
  }

  int pan = curPan;
  if ((int32_t)(shiverUntil - now) > 0) {
    pan += ((now / 62) % 2) ? 3 : -3;  // ±3° at 8 Hz
  }
  panServo.write(constrain(pan, PAN_MIN, PAN_MAX));
  if (PIN_TILT >= 0) tiltServo.write(curTilt);

  int arm = armRest;
  if ((int32_t)(fanUntil - now) > 0) {
    float phase = (now - fanStart) / 1000.0f * 2.0f * PI;  // 1 Hz
    arm = armRest + (int)(30.0f * sinf(phase));
  }
  if (PIN_ARM >= 0) armServo.write(constrain(arm, ARM_MIN, ARM_MAX));
}

void runStream(uint32_t now) {
  uint32_t echoUs;
  if (pollPing(echoUs)) {
    Bridge.notify("dist", (int)now, curPan, curTilt, (int)echoUs);
  }
  if (!pingBusy && now - lastPingMs >= (uint32_t)streamPeriodMs) {
    lastPingMs = now;
    startPing();
  }
}

void runSweep(uint32_t now) {
  if (sweepRequested) {
    sweepRequested = false;
    sweepActive = true;
    sweepSeq++;
    sweepDir = sweepTo >= sweepFrom ? 1 : -1;
    sweepAngle = sweepFrom;
    curTilt = sweepTilt;
    curPan = sweepAngle;
    sweepMovedMs = now + 250;  // the first move can be long
    sweepWaitingPing = false;
  }
  if (!sweepActive) return;

  if (!sweepWaitingPing) {
    if ((int32_t)(now - sweepMovedMs) >= SWEEP_SETTLE_MS) {
      startPing();
      sweepWaitingPing = true;
    }
    return;
  }

  uint32_t echoUs;
  if (!pollPing(echoUs)) return;
  sweepWaitingPing = false;
  Bridge.notify("sweep_pt", sweepSeq, curPan, curTilt, (int)echoUs);

  bool last = sweepDir > 0 ? sweepAngle + sweepStep > sweepTo : sweepAngle - sweepStep < sweepTo;
  if (last) {
    sweepActive = false;
    targetPan = curPan;  // stay where the sweep ended until told otherwise
    targetTilt = curTilt;
    cmdMode = MODE_IDLE;
    Bridge.notify("sweep_end", sweepSeq);
    return;
  }
  sweepAngle += sweepDir * sweepStep;
  curPan = sweepAngle;
  sweepMovedMs = now;
}

void setup() {
  Monitor.begin(115200);

  pinMode(PIN_US_TRIG, OUTPUT);
  digitalWrite(PIN_US_TRIG, LOW);
  pinMode(PIN_US_ECHO, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_US_ECHO), onEcho, CHANGE);
  pinMode(PIN_DHT, INPUT_PULLUP);
  for (int i = 0; i < 7; i++) {
    pinMode(PIN_SEGMENTS[i], OUTPUT);
    digitalWrite(PIN_SEGMENTS[i], LOW);
  }
  for (int i = 0; i < 4; i++) {
    pinMode(PIN_DIGITS[i], OUTPUT);
    digitalWrite(PIN_DIGITS[i], HIGH);  // off
  }
  k_timer_start(&muxTimer, K_MSEC(1), K_MSEC(1));

  panServo.attach(PIN_PAN);
  if (PIN_TILT >= 0) tiltServo.attach(PIN_TILT);
  if (PIN_ARM >= 0) armServo.attach(PIN_ARM);

  matrix.begin();
  matrix.setGrayscaleBits(3);  // brightness 0..7
  matrix.clear();

  Bridge.begin();
  Bridge.provide("look", cmdLook);
  Bridge.provide("stream", cmdStream);
  Bridge.provide("sweep", cmdSweep);
  Bridge.provide("stop", cmdStop);
  Bridge.provide("shiver", cmdShiver);
  Bridge.provide("fan", cmdFan);
  Bridge.provide("arm", cmdArm);
  Bridge.provide("draw", cmdDraw);
  Bridge.provide("show_temp", cmdShowTemp);
  Bridge.provide("show_number", cmdShowNumber);

  Monitor.println("ecou: ready");
}

void loop() {
  uint32_t now = millis();

  updateServos(now);

  int mode = cmdMode;
  if (mode == MODE_STREAM) {
    runStream(now);
  } else if (mode == MODE_SWEEP) {
    runSweep(now);
  } else if (sweepActive) {
    sweepActive = false;  // stopped in the middle of a sweep
    targetPan = curPan;
    targetTilt = curTilt;
  }

  if (frameDirty) {
    k_mutex_lock(&frameLock, K_FOREVER);
    frameDirty = false;
    matrix.draw(frame);
    k_mutex_unlock(&frameLock);
  }

  if (displayDirty) {
    displayDirty = false;
    renderDisplay();
  }

  // Read the temperature only between pings, so the lock cannot delay an echo.
  if (!pingBusy && now - lastTempMs >= TEMP_PERIOD_MS) {
    lastTempMs = now;
    int c = 0, rh = 0;
    bool ok = readTemperature(c, rh);
    Bridge.notify("temp", (int)now, c, rh, ok ? 1 : 0);
  }

  delay(1);  // let the Bridge thread run
}
