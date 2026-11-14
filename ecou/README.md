# Ecou

The home node built as a small robot on an Arduino UNO Q, for the hackathon. The design, parts and wiring are in [docs/specs/echocare/08-ecou.md](../docs/specs/echocare/08-ecou.md) (P23–P27, proposed).

| Path | What |
|---|---|
| `app/` | The App Lab app: `sketch/` runs on the UNO Q's STM32, `python/` on its Linux side. Today it is the bring-up test (08 §8, step 1) |
| `spikes/s14_ble_node.py` | Spike S14: the UNO Q's Linux side as the home node's BLE GATT server |
| `docs/wiring.html` | The wiring diagram: pin map, one schematic per part, the multimeter checks. Open it in a browser |
| `docs/assembly.html` | How the robot goes together: front, side and top views, and the build steps for the one-servo build |

## Bring-up test

1. Wire the parts as in [docs/wiring.html](docs/wiring.html) (08 §1 in words). One servo can take the board's 5V. With two or three, power them from their own 5 V supply and join its GND to the board's GND.
2. The pins are set at the top of `app/sketch/sketch.ino`. `PIN_TILT` and `PIN_ARM` stay `-1` until those servos are fitted.
3. In App Lab, create an app and copy `app.yaml`, `sketch/` and `python/` into it. The sketch needs the Servo library 1.3.0 or later, the first release with Zephyr support. `sketch.yaml` asks for it.
4. Run it. The console prints each step, what you should see on the robot, and the measurements:
   - **Matrix**: every face for a second.
   - **Display**: `8888`, `1234`, `-5°C`, `21°C`.
   - **Temperature**: good and failed readings over 6 seconds.
   - **Neck and arm**: five head positions, the arm through 0°, 90° and the flag, then shiver and fan.
   - **Eyes, streaming**: pings a second, distances with and without a hand at 20 cm.
   - **Eyes, sweep**: 37 steps from 0° to 180°, drawn as bars.
   - **Ask**: „BINE?” scrolling, with a countdown on the display.

Paste the console output into the conversation or an issue when something says `CHECK` or `ERROR`.

## Spike S14

Runs on the UNO Q's Debian directly, not inside App Lab, since App Lab runs apps in a container that may not reach BlueZ.

```bash
# on the board: adb shell, or ssh
systemctl status bluetooth          # BlueZ running?
bluetoothctl show                   # the adapter, powered and with "LE" in its roles?
python3 -m venv ~/s14 && ~/s14/bin/pip install bless
~/s14/bin/python s14_ble_node.py --name Ecou-TEST
```

On an Android phone, in nRF Connect:

1. Scan, find `Ecou-TEST`, connect. Then try **Bond** too: P20 expects a bonded phone.
2. Raise the MTU to 185 (the menu ⋮ → Request MTU).
3. Turn on notifications for every characteristic of the `ec0f0000-…` service. A room reading arrives every 5 seconds.
4. Type `s` and Enter on the board: an SOS press repeats every 3 seconds. Write its `id` to Acknowledge (`ec0f0004-…`, as text) and it stops.
5. Same with `f`: the fall carries a 37-point scan, so it only arrives whole with the larger MTU.
6. Write `red` to Light and `cold_soon` to Room state; the board logs both.
7. `q` prints a summary.

Record in [spike-results.md](../docs/specs/echocare/spike-results.md):

- whether advertising, connecting, bonding, notifications and writes worked;
- the MTU you got;
- whether the link survived 10 minutes with the phone screen off;
- and, with the App Lab app running at the same time, whether the Bridge still works.

If the Linux side cannot advertise or serve, the fallback is in 08 §6: the R4 WiFi becomes the BLE node with `ArduinoBLE`.
