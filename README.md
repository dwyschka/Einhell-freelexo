# Einhell Robotic Mower for Home Assistant

Local Bluetooth integration for Einhell robotic mowers. No cloud, no account,
no official app needed while it runs.

The protocol was recovered from **two independent sources** and cross-checked:

- the mower firmware `EC11353.bin` (STM32F103, Cortex-M3)
- the official **Einhell Connect 4.2.8** app — the managed assemblies were
  extracted from `split_config.arm64_v8a.apk`

See [docs/protocol.md](docs/protocol.md) for the annotated protocol and the
evidence for every field.

---

## What you get

| Platform | Entities |
|---|---|
| `sensor` | Status, battery, main board temperature, battery temperature, warning, error memory, boot/machine/blade run time, firmware versions (main board / LCD / protocol), zone A/B frequency and distance, language, feature flags, RSSI |
| `binary_sensor` | Charging, error active, Bluetooth link |
| `number` | **Reverse distance 0.0–2.0 m** |
| `button` | Go to work, Pause, Go to station, Edge cutting, Second area mowing, Spot mowing (main/second), Sync clock, Refresh feature flags |
| `switch` | Mow in the rain |
| `service` | `einhell_mower.send_command` — any command, for the parts not mapped yet |

---

## Requirements

- Home Assistant 2024.6 or newer
- A Bluetooth adapter **or an ESPHome Bluetooth proxy** in range of the mower

The mower stands outdoors, so a proxy next to it is the usual setup:

```yaml
esp32:
  board: esp32dev

esp32_ble_tracker:
bluetooth_proxy:
  active: true
```

> Only **one** BLE connection is possible at a time. Close the Einhell app
> while Home Assistant is connected, otherwise the connection attempt fails.

---

## Installation

1. Copy `custom_components/einhell_mower` to `/config/custom_components/`, or
   add this repository to HACS as a custom repository (category *Integration*).
2. Restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → Einhell Robotic Mower*.

The mower is normally discovered automatically; otherwise enter its Bluetooth
address manually.

**Characteristic detection:** the app does not hardcode any GATT UUID, so this
integration auto-detects the notify/write pair. If that fails, set the UUIDs
manually in the options. To find them, connect with nRF Connect and look for a
service that has both a notify and a write characteristic.

---

## First steps

1. **Press “Sync clock”.** The mower has no reliable backup supply for its
   RTC, so after every power loss it boots at `2020-05-16 17:42:55`. The button
   writes the current Home Assistant time into the RTC. An automation is
   enough:

   ```yaml
   automation:
     - alias: "Mower clock"
       triggers:
         - trigger: time
           at: "03:00:00"
       actions:
         - action: einhell_mower.sync_time
   ```

2. Check the *Error memory* sensor and the *Warning* sensor.
3. Open *Diagnostics* on the device page — it dumps the last frames, the
   detected UUIDs and the whole decoded state.

---

## Entities explained

**Status** comes from the status byte of the `0x80` frame and uses the app's
own `MowerStatus` enum:

| Value | Meaning |
|---|---|
| 1 | mowing |
| 3 | along boundary |
| 4 | edge cutting |
| 5 | second area mowing |
| 6 | spot mowing |
| 7 | idle |
| 19 | stopped |
| 20 | paused |
| 22 | boundary signal error |

**Error memory** holds up to 8 warning codes. They are single ASCII letters:
`B` battery, `C` motor over-current, `L` lifted, `M` motor fault, `N` signal,
`P` PCB over-temperature, `R` rolling over, `S` battery over-temperature,
`T` tilted, `X` trapped.

**Run times** are three second counters: boot, machine, blade.

**Reverse distance** is the drivetrain setting for backing off the boundary,
0.0–2.0 m in 0.1 m steps. It exists in the firmware and app but has no
prominent UI in the app.

**Zones** carry a frequency and a three digit decimal distance each.

**Firmware versions** are reported for the main board, the LCD board and the
protocol. The app refuses to talk to mowers below a minimum version, which is
why these exist.

---

## Services

### `einhell_mower.send_command`

```yaml
action: einhell_mower.send_command
data:
  command: 0x62          # FirmwareInformation
  payload: ""
```

Payload is a hex string, max 14 bytes (`"14 1a 0a"` or `"141a0a"`).
Full table: [docs/protocol.md](docs/protocol.md#command-table).

### `einhell_mower.sync_time`

Optional `device_id` when several mowers are configured.

---

## Safety

- The control buttons really move the machine. Keep the mower in sight,
  especially the first time.
- The BLE protocol is unauthenticated and unencrypted; the 4-digit PIN has no
  lockout. Do not treat it as a security boundary.
- Never send a control command while somebody is near the blades.

---

## Known limitations

| Area | Status |
|---|---|
| Work time / schedule (`0x04`, `0x05`, `0x14`) | Command known, byte packing not decoded |
| Rain delay high byte | Not written by the firmware (quirk); the integration keeps the last value |
| Cloud / WiFi | Not implemented |
| GATT UUIDs | Not in the app either — auto-detected at runtime |

---

## ESPHome instead of the integration

If your Bluetooth proxies are short on connection slots, a dedicated ESP32
next to the mower fixes that. Two ready-made configurations live in
[`esphome/`](esphome/):

| File | Purpose |
|---|---|
| `freelexo-discover.yaml` | connects once and prints the full GATT tree to the log |
| `freelexo.yaml` | sends the control frames (start, pause, dock, edge, clock) |

Run the discovery file first — it tells you the service and characteristic
UUID. The mower does not hardcode them anywhere, not even in the official app,
so discovery is the only way.

**Limits of the YAML-only route:** ESPHome does not expose notification
subscriptions to YAML, so the ESP can *send* but not *read*. Battery, state and
the rest stay in the Home Assistant integration. And because the mower accepts
only one BLE connection, you run either the ESP or the HA proxy — not both at
the same time.

## Development

```bash
python3 tests/test_protocol.py     # codec self-test, no Home Assistant needed
```

`protocol.py` has no Home Assistant dependency and can be reused for a CLI or
an ESPHome component.

## License

MIT
