"""Frame codec and payload decoders for the Einhell mower.

Layouts are taken from ``EinhellConnect.Mobile.dll`` (official app 4.2.8) and
verified against the mower firmware where possible.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

from .const import (
    CMD_FRAME_LEN,
    CMD_PAYLOAD_LEN,
    END,
    MAX_DATA,
    REVERSE_FACTOR,
    RSP_FRAME_LEN,
    START,
    WARNINGS,
)

_LOGGER = logging.getLogger(__name__)

RSP_TRAILER = bytes((0x16, 0x06, 0x01))


class ProtocolError(Exception):
    """Raised when a frame cannot be built or parsed."""


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------
def build_frame(cmd: int, payload: bytes = b"") -> bytes:
    """Build a 24 byte command frame.

    ``DYM`` + command + up to 14 data bytes, padded to 15, then
    ``00 16 06 01 FF 0A``.
    """
    if not 0 <= cmd <= 0xFF:
        raise ProtocolError(f"command out of range: {cmd}")
    if len(payload) > MAX_DATA:
        raise ProtocolError(f"payload too long: {len(payload)} > {MAX_DATA}")

    body = (bytes((cmd,)) + payload).ljust(CMD_PAYLOAD_LEN, b"\x00")
    frame = START + body + END
    assert len(frame) == CMD_FRAME_LEN
    return frame


@dataclass(slots=True)
class Frame:
    """One response frame from the mower."""

    code: int
    payload: bytes
    raw: bytes = field(repr=False, default=b"")

    def __str__(self) -> str:  # pragma: no cover
        return f"Frame(0x{self.code:02X}, {self.raw.hex(' ')})"


class FrameParser:
    """Incremental parser that resynchronises on the ``DYM`` header."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[Frame]:
        self._buffer.extend(data)
        frames: list[Frame] = []

        while True:
            start = self._buffer.find(START)
            if start < 0:
                if len(self._buffer) > len(START):
                    del self._buffer[: -len(START) + 1]
                break
            if start:
                del self._buffer[:start]

            if len(self._buffer) < RSP_FRAME_LEN:
                break

            candidate = bytes(self._buffer[:RSP_FRAME_LEN])
            if candidate[19:22] != RSP_TRAILER:
                _LOGGER.debug("false sync: %s", candidate.hex())
                del self._buffer[: len(START)]
                continue

            frames.append(
                Frame(
                    code=candidate[3],
                    payload=candidate[3:RSP_FRAME_LEN],
                    raw=candidate,
                )
            )
            del self._buffer[:RSP_FRAME_LEN]

        return frames


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------
def encode_set_time(when: dt.datetime) -> bytes:
    """TimeMessage.GetBytes(): year/100, year%100, month, day, hour, minute."""
    if not 1970 <= when.year <= 2099:
        raise ProtocolError(f"year {when.year} outside 1970..2099")
    return bytes(
        (
            when.year // 100,
            when.year % 100,
            when.month,
            when.day,
            when.hour,
            when.minute,
        )
    )


def encode_pin(current: str, new: str) -> bytes:
    """PinMessage: both PINs as four separate digit bytes.

    Payload = current[0..3] | new[0..3]
    """
    for pin in (current, new):
        if not (len(pin) == 4 and pin.isdigit()):
            raise ProtocolError("PIN must be exactly 4 digits")
    return bytes(int(c) for c in current) + bytes(int(c) for c in new)


def encode_reverse_distance(metres: float) -> bytes:
    """ReverseSettingsMessage: metres * 10 as big-endian uint16."""
    raw = round(metres * REVERSE_FACTOR)
    if not 0 <= raw <= 20:
        raise ProtocolError("reverse distance must be 0.0..2.0 m")
    return raw.to_bytes(2, "big")


def encode_cut_settings(
    *,
    cut_in_rain: bool,
    edge_mowing: bool,
    rain_delay: int,
    boundary_frequency: int | None = None,
    boundary_raw: int | None = None,
) -> bytes:
    """CutSettingsMessage.ModelToByteArray().

    ``[rain][edge][delay_hi][delay_lo][boundary_frequency + 1]``

    The rain delay is stored big-endian; the boundary frequency is written as
    value + 1 (0 when unset). Pass ``boundary_raw`` to write the wire value
    unchanged - needed for a read-modify-write, otherwise every save would
    increment it.
    """
    delay = int(rain_delay).to_bytes(2, "big")
    if boundary_raw is not None:
        freq = int(boundary_raw) & 0xFF
    else:
        freq = (
            0 if boundary_frequency is None
            else (int(boundary_frequency) + 1) & 0xFF
        )
    return bytes(
        (1 if cut_in_rain else 0, 1 if edge_mowing else 0)
    ) + delay + bytes((freq,))


# ---------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------
def _warning_name(code: int) -> str:
    return WARNINGS.get(code, f"unknown_{code}")


def decode_basic_info(frame: Frame) -> dict[str, Any]:
    """BasicInformationMessage.CreateModel().

    ======  =========================================================
    byte 1  battery level
    byte 2  main board temperature
    byte 3  battery temperature
    byte 4  charging flag (1 = charging)
    byte 5-8 firmware version, four digits
    byte 8  warning code
    byte 9  state (MowerStatus)
    ======  =========================================================
    """
    d = frame.payload
    version = d[5:9]
    return {
        "state": d[9],
        "battery": d[1],
        "board_temperature": d[2],
        "battery_temperature": d[3],
        "charging": d[4] == 1,
        "firmware_version": ".".join(str(b) for b in version),
        "warning": d[8],
        "warning_name": _warning_name(d[8]),
        "raw": d[1:].hex(" "),
    }


def decode_statistics(frame: Frame) -> dict[str, Any]:
    """StatisticsMessage: three big-endian uint32 second counters.

    Order as used by the app: boot time, machine run time, blade run time.
    """
    raw = frame.payload[1:13]
    secs = [int.from_bytes(raw[i : i + 4], "big") for i in (0, 4, 8)]
    return {
        "boot_hours": round(secs[0] / 3600, 2),
        "runtime_hours": round(secs[1] / 3600, 2),
        "blade_hours": round(secs[2] / 3600, 2),
        "seconds": secs,
    }


def decode_error_log(frame: Frame) -> dict[str, Any]:
    """Error memory: ONE timestamped entry, not eight codes.

    The firmware stores an 8 byte record and formats it as
    ``YYYYMMDD-HH-MM-SS`` followed by the error text:

    ======  =========================================
    byte 1  year, high
    byte 2  year, low
    byte 3  month
    byte 4  day
    byte 5  hour
    byte 6  minute
    byte 7  second
    byte 8  warning code
    ======  =========================================
    """
    r = frame.payload[1:9]
    year = (r[0] << 8) | r[1]
    code = r[7]
    timestamp = None
    if year >= 2000 and 1 <= r[2] <= 12 and 1 <= r[3] <= 31:
        timestamp = (
            f"{year:04d}-{r[2]:02d}-{r[3]:02d} "
            f"{r[4]:02d}:{r[5]:02d}:{r[6]:02d}"
        )
    return {
        "error_code": code,
        "error_name": _warning_name(code) if code else "none",
        "error_timestamp": timestamp,
        "errors_raw": list(r),
        "has_error": code != 0,
    }


def decode_zones(frame: Frame) -> dict[str, Any]:
    """ZonesMessage: two zones, each frequency + 3-digit distance.

    Distance is decimal, most significant digit first:
    ``b0 * 100 + b1 * 10 + b2``.
    """
    d = frame.payload
    return {
        "zone_a_frequency": d[1],
        "zone_a_distance": d[2] * 100 + d[3] * 10 + d[4],
        "zone_b_frequency": d[5],
        "zone_b_distance": d[6] * 100 + d[7] * 10 + d[8],
    }


def encode_zones(
    zone_a: tuple[int, int], zone_b: tuple[int, int]
) -> bytes:
    """Encode both zones as (frequency, distance) pairs."""

    def digits(value: int) -> bytes:
        value = max(0, min(999, int(value)))
        return bytes((value // 100, (value % 100) // 10, value % 10))

    return (
        bytes((zone_a[0] & 0xFF,))
        + digits(zone_a[1])
        + bytes((zone_b[0] & 0xFF,))
        + digits(zone_b[1])
    )


def decode_pin(frame: Frame) -> dict[str, Any]:
    """PinMessage response: four digit bytes."""
    return {"ok": frame.payload[1] == 0}


def decode_language(frame: Frame) -> dict[str, Any]:
    """LanguageMessage: single language id."""
    return {"language_id": frame.payload[1]}


def decode_reverse(frame: Frame) -> dict[str, Any]:
    """ReverseSettingsMessage: big-endian uint16, metres * 10."""
    raw = int.from_bytes(frame.payload[1:3], "big")
    return {"reverse_distance": raw / REVERSE_FACTOR, "reverse_raw": raw}


def decode_feature_flags(frame: Frame) -> dict[str, Any]:
    """FeatureFlagsMessage: 8 bytes, reversed, uint64."""
    value = int.from_bytes(frame.payload[1:9], "big")
    return {
        "feature_mask": value,
        "feature_bits": [i for i in range(64) if value >> i & 1],
    }


def decode_firmware_info(frame: Frame) -> dict[str, Any]:
    """FirmwareInformationMessage: main board, LCD board and protocol version.

    Chunks: ``[1..5]`` main board, ``[5..9]`` LCD board, ``[9..11]`` protocol.
    Each byte is one version component.
    """
    d = frame.payload
    main_board = d[1:5]
    lcd_board = d[5:9]
    protocol = d[9:11]
    return {
        "mainboard_version": ".".join(str(b) for b in main_board),
        "lcd_version": ".".join(str(b) for b in lcd_board),
        "protocol_version": ".".join(str(b) for b in protocol),
        "mainboard_raw": main_board.hex(),
        "lcd_raw": lcd_board.hex(),
        "firmware_raw": d[1:11].hex(" "),
    }


def decode_cut_settings(frame: Frame) -> dict[str, Any]:
    """Cut settings response (0x89).

    The firmware fills ``[1]`` rain, ``[2]`` edge, ``[4]`` rain delay low and
    ``[5]`` boundary frequency. ``[3]`` (delay high) is **not written by the
    firmware** - it can be stale, which is a firmware quirk.
    """
    d = frame.payload
    return {
        "cut_in_rain": d[1] == 1,
        "edge_mowing": d[2] == 1,
        "rain_delay": (d[3] << 8) | d[4],
        "boundary_frequency": d[5],
        "boundary_raw": d[5],
        "cut_settings_raw": d[1:6].hex(" "),
    }


def decode_worktime(frame: Frame) -> dict[str, Any]:
    return {"worktime_raw": frame.payload[1:].hex(" ")}


DECODERS = {
    0x80: decode_basic_info,
    0x83: decode_language,
    0x86: decode_pin,
    0x8D: decode_zones,
    0x8E: decode_error_log,
    0x8F: decode_statistics,
    0x90: decode_reverse,
    0x91: decode_feature_flags,
    0x92: decode_firmware_info,
    0x89: decode_cut_settings,
}


def decode(frame: Frame) -> dict[str, Any]:
    decoder = DECODERS.get(frame.code)
    if decoder is None:
        return {"raw": frame.payload[1:].hex(" ")}
    return decoder(frame)
