# Protocol reference

Two independent sources were used and cross-checked:

| Source | What it gave us |
|---|---|
| `EC11353.bin` (mower firmware, STM32F103) | framing rules, dispatcher, response codes, RTC internals, internal "TD" bus |
| `EinhellConnect.Mobile.dll` (official app 4.2.8, extracted from `split_config.arm64_v8a.apk`) | payload layouts, enum values, units, GATT behaviour |

Where the two disagree, this document follows the app — it is what actually
runs against the mower.

> The app assembly is packed in `libassemblies.arm64-v8a.blob.so` as an
> `XABA` assembly store. Entries are `XALZ` containers (magic `XALZ`,
> descriptor index, uncompressed length, then an LZ4 block).

---

## Transports

The MCU has four UARTs and three logical links, each with its own debug log:

| Link | Prefix |
|---|---|
| BLE module | `BLE-ReceiveDATA:` / `BLE-SendDATA:` |
| WiFi module | `Wifi-ReceiveDATA:` / `Wifi-SendDATA:` |
| Main/power board | `EinhellUsart-ReceiveDATA:` |

**BLE and WiFi carry the identical command protocol.**

The BLE module is a separate chip and the app does **not** hardcode any GATT
UUID — a full scan of all 448 managed assemblies, the DEX files and the Flutter
`libapp.so` found no custom 128-bit UUID. The app discovers the
service/characteristic at runtime, which is why this integration auto-detects
the notify/write pair.

---

## Frame format

Taken from `BasicMessage.startBytes` / `BasicMessage.endBytes` (static array
blobs, SHA-256 of the content equals the field name):

```
startBytes = 44 59 4D                  "DYM"
endBytes   = 00 16 06 01 FF 0A
```

### App → mower, 24 bytes

```
0   1   2   3     4 .. 17            18 .. 23
'D' 'Y' 'M' cmd   data (14 bytes)    00 16 06 01 FF 0A
```

### Mower → app, 22 bytes

```
0   1   2   3     4 .. 18            19 .. 21
'D' 'Y' 'M' resp  data (15 bytes)    16 06 01
```

The firmware RX validator (`0x08011c98`) requires exactly
`frame[0x13..0x17] == 16 06 01 FF 0A` and the collector (`0x08011d48`) syncs on
`D`,`Y`,`M` before copying 24 bytes.

There is **no checksum** on the BLE link.

---

## Command table

| Cmd | App class / firmware name | Response |
|---|---|---|
| `0x00` | `BasicInformationMessage` | `0x80` |
| `0x01` | `ControlMessage` (fire and forget) | — |
| `0x02` | `TimeMessage` | — |
| `0x03` | `LanguageMessage` (set) | — |
| `0x04` | SetWorkTime_Start | — |
| `0x05` | SetWorkTime_Hours | — |
| `0x06` | `PinMessage` (set) | `0x86` |
| `0x09` | `CutSettingsMessage` (set) | — |
| `0x0C` | `PinMessage` (get) | `0x86` |
| `0x0D` | `ZonesMessage` (set) | — |
| `0x13` | `LanguageMessage` (get) | `0x83` |
| `0x14` | `ScheduleMessage` | — |
| `0x19` | CutSettings query | `0x89` (layout unconfirmed) |
| `0x1D` | `ZonesMessage` (get) | `0x8D` |
| `0x1E` | error log | `0x8E` |
| `0x1F` | `StatisticsMessage` | `0x8F` |
| `0x24` | SetWorkTime_StartDouble | — |
| `0x25` | SetWorkTime_HoursDouble | — |
| `0x40` | `ReverseSettingsMessage` (set) | — |
| `0x60` | `ReverseSettingsMessage` (get) | `0x90` |
| `0x61` | `FeatureFlagsMessage` | `0x91` |
| `0x62` | `FirmwareInformationMessage` | `0x92` |

---

## Payload layouts

### `0x00` BasicInformation (response `0x80`, 15 data bytes)

From `BasicInformationMessage.CreateModel()`:

| Index | Field |
|---|---|
| 1 | battery level |
| 2 | main board temperature |
| 3 | battery temperature |
| 4 | charging (1 = yes) |
| 5–8 | firmware version, four digits |
| 8 | warning code |
| 9 | state (`MowerStatus`) |

### `0x01` Control

```
[0x01][action]
```

| Value | Action |
|---|---|
| 1 | Pause |
| 2 | GoToWork |
| 3 | GoToStation |
| 4 | GoEdgeCutting |
| 5 | GoSecondAreaMowing |
| 6 | GoMainSpotMowing |
| 7 | GoSecondSpotMowing |

`0` is not defined by the app. The message is sent fire-and-forget.

### `0x02` Time

`TimeMessage.GetBytes()` produces six bytes:
`year/100, year%100, month, day, hour, minute`. Seconds are not sent.

The firmware converts this to Unix seconds and writes `RTC_CNTH`/`RTC_CNTL`
with prescaler `0x7FFF` (LSE 32.768 kHz).

### `0x06` / `0x0C` PIN

Four **separate digit bytes**, not packed nibbles:

```
set:   [0x06][current d0..d3][new d0..d3]
get:   [0x0C]
resp:  [0x86][0 = ok, 1 = rejected]
```

### `0x40` / `0x60` Reverse distance

16-bit **big-endian**, value = metres × 10. Firmware clamps 0…20, so the
usable range is **0.0–2.0 m**. The strings `Min:0.0` / `Max:2.0` in the
firmware LCD confirm this.

```
set:   [0x40][hi][lo]
resp:  [0x90][hi][lo]
```

### `0x1F` Statistics (response `0x8F`)

Three big-endian uint32 **seconds** at indices 1, 5, 9:

1. boot time
2. machine run time
3. blade run time

### `0x1E` Error memory (response `0x8E`)

**One** timestamped record, not eight codes:

```
year_hi, year_lo, month, day, hour, minute, second, code
```

The firmware formats it as `YYYYMMDD-HH-MM-SS` (0x0802eb48). See
[error-codes.md](error-codes.md) for the full code table.

### `0x8D` Zones (response)

Two zones, each frequency plus a three digit decimal distance
(`ZonesMessage.GetDistance`: `b0 * 100 + b1 * 10 + b2`):

| Index | Meaning |
|---|---|
| 1 | zone A frequency |
| 2,3,4 | zone A distance, hundreds/tens/ones |
| 5 | zone B frequency |
| 6,7,8 | zone B distance, hundreds/tens/ones |

The writer (`GetDistance` overload) splits the value the same way, so setting
zones is a plain round trip: `[0x0D][freq A][d d d][freq B][d d d]`.

### `0x61` Feature flags (response `0x91`)

Eight bytes at index 1, **reversed**, read as uint64 big-endian.
Current firmware reports `0x0FF7`.

### `0x62` Firmware information (response `0x92`)

`FirmwareInformationMessage.CreateModel()` splits the payload into three
versions, each byte being one component:

| Indices | Field | Current value |
|---|---|---|
| 1–5 | main board firmware | `2.5.17.16` |
| 5–9 | LCD board firmware | `3.4.17.10` |
| 9–11 | protocol version | `1.3` |

This explains the two `MinimumFirmwareVersion` settings in the app — the app
refuses to talk to a mower whose main board or LCD is older than a threshold.

### `0x09` / `0x19` Cut settings

`CutSettingsMessage.ModelToByteArray()` — **five bytes**:

```
[0] cut in rain (0/1)
[1] edge mowing  (0/1)
[2] rain delay, high byte
[3] rain delay, low byte
[4] boundary frequency + 1   (0 when unset)
```

So the delay is **big-endian**, like the reverse distance. The query `0x19`
answers with `0x89`, same field order.

> Firmware quirk: the `0x89` writer (`0x0802a45c`) fills `[1]`, `[2]`, `[4]`
> and `[5]`, but **never writes `[3]`** — the rain-delay high byte is stale.
> A read-modify-write therefore has to send a delay value explicitly; this
> integration preserves the last known value instead of trusting `[3]`.

---

## Enums (from the app)

### MowerStatus

| Value | Name |
|---|---|
| 0 | UnknownZero |
| 1 | Mowing |
| 3 | AlongBoundary |
| 4 | EdgeCutting |
| 5 | SecondAreaMowing |
| 6 | SpotMowing |
| 7 | Idle |
| 19 | Stopped |
| 20 | Paused |
| 22 | ErrorBoundarySignalHasIncorrectFrequencyMagic |
| 25 | UnknownNineteen |
| 32 | UnknownTwenty |

### Warning (error log codes)

| Code | Name | ASCII |
|---|---|---|
| 66 | BatteryError | `B` |
| 67 | MotorOverCurrent | `C` |
| 76 | MowerLifted | `L` |
| 77 | MotorFault | `M` |
| 78 | SignalError | `N` |
| 80 | PCBOverTemperature | `P` |
| 82 | RollingOver | `R` |
| 83 | BatteryOverTemperature | `S` |
| 84 | MowerTilted | `T` |
| 88 | MowerTrapped | `X` |
| 50, 51, 65, 255 | unknown | |

The codes are printable ASCII on purpose — the firmware stores the error log
as a short string.

### Language (0–18)

English, German, Danish, Czech, Slovak, Polish, Hungarian, Russian, French,
Bulgarian, Finnish, Dutch, Lithuanian, Romanian, Norwegian, Portuguese,
Swedish, Spanish, Italian.

---

## Internal "TD" link (not reachable over BLE)

Parser at `0x08015e3c`: syncs on `T`,`D`, checks byte 2 == 1 and byte 6 == 9.
`0x08015084` validates a two's-complement checksum. This is the link to the
power/motor board and is invisible to the app.

---

## Work time / schedule (partially known)

`ScheduleMessage` reads four frames and keeps fourteen internal buffers:

| Sent | Masked by firmware (`& 0x7F`) | Meaning |
|---|---|---|
| `0x84` (132) | `0x04` | SetWorkTime_Start |
| `0x85` (133) | `0x05` | SetWorkTime_Hours |
| `0x94` (148) | `0x14` | InquireWorkTime |
| `0x95` (149) | `0x15` | *not implemented in firmware* |

The app marks schedule requests with bit 7 set and logs
`"Second schedule window not available or not supported"` when the `0x94`/
`0x95` pair fails — the mower firmware only knows one schedule window.

`FillWorkDayIntoBuffer` works with `DayIndex`, `StartIndex`, `EndIndex`,
`StartHour`, `StartMinute`, `DurationHour`, `DurationMinute`, i.e. a buffer of
per-day start/end entries plus times. The exact byte packing is **not decoded
yet**; use `einhell_mower.send_command` until a capture is available.

## Open questions

1. Byte packing of the schedule buffers (`0x04`, `0x05`, `0x14`).
2. Whether `0x15` exists in newer firmware.
3. What the fourteen schedule buffers map to.

The fastest way to close these is a BLE capture while changing one schedule in
the app.
