"""Protocol constants for the Einhell robotic mower.

Ground truth: the official Einhell Connect 4.2.8 app
(``EinhellConnect.Mobile.dll``, extracted from the arm64 split) cross-checked
against the mower firmware ``EC11353.bin``.
"""

from __future__ import annotations

from enum import IntEnum

DOMAIN = "einhell_mower"
MANUFACTURER = "Einhell"

# ---------------------------------------------------------------------------
# Framing  (from BasicMessage.startBytes / BasicMessage.endBytes)
# ---------------------------------------------------------------------------
#   app -> mower (24 bytes):  "DYM" | cmd + 14 data bytes | 00 16 06 01 FF 0A
#   mower -> app (22 bytes):  "DYM" | code + 15 payload     | 16 06 01
#
# startBytes = 44 59 4d            (sha256 verified against the field blob)
# endBytes   = 00 16 06 01 ff 0a
START = b"DYM"
END = bytes((0x00, 0x16, 0x06, 0x01, 0xFF, 0x0A))

CMD_FRAME_LEN = 24
RSP_FRAME_LEN = 22
CMD_PAYLOAD_LEN = 15  # includes the command byte
MAX_DATA = CMD_PAYLOAD_LEN - 1

DEFAULT_TIMEOUT = 3.0


class Cmd(IntEnum):
    """Commands accepted by the mower."""

    BASIC_INFO = 0x00
    CONTROL = 0x01
    TIME = 0x02
    LANGUAGE = 0x03
    WORKTIME_START = 0x04
    WORKTIME_HOURS = 0x05
    PIN = 0x06
    CUT_SETTINGS = 0x09
    PIN_QUERY = 0x0C
    ZONES = 0x0D
    LANGUAGE_QUERY = 0x13
    WORKTIME = 0x14
    CUT_SETTINGS_QUERY = 0x19
    ZONES_QUERY = 0x1D
    ERROR_LOG = 0x1E
    STATISTICS = 0x1F
    WORKTIME_START_DOUBLE = 0x24
    WORKTIME_HOURS_DOUBLE = 0x25
    REVERSE_SET = 0x40
    REVERSE_GET = 0x60
    FEATURE_FLAGS = 0x61
    FIRMWARE_INFO = 0x62


class Rsp(IntEnum):
    """Response codes emitted by the mower."""

    BASIC_INFO = 0x80
    LANGUAGE = 0x83
    PIN = 0x86
    ZONES = 0x8D
    ERROR_LOG = 0x8E
    STATISTICS = 0x8F
    REVERSE = 0x90
    CUT_SETTINGS = 0x89
    FEATURE_FLAGS = 0x91
    FIRMWARE_INFO = 0x92


RESPONSE_MAP: dict[int, int] = {
    Cmd.BASIC_INFO: Rsp.BASIC_INFO,
    Cmd.LANGUAGE_QUERY: Rsp.LANGUAGE,
    Cmd.PIN_QUERY: Rsp.PIN,
    Cmd.PIN: Rsp.PIN,
    Cmd.ZONES_QUERY: Rsp.ZONES,
    Cmd.ERROR_LOG: Rsp.ERROR_LOG,
    Cmd.STATISTICS: Rsp.STATISTICS,
    Cmd.REVERSE_GET: Rsp.REVERSE,
    Cmd.CUT_SETTINGS_QUERY: Rsp.CUT_SETTINGS,
    Cmd.FEATURE_FLAGS: Rsp.FEATURE_FLAGS,
    Cmd.FIRMWARE_INFO: Rsp.FIRMWARE_INFO,
}


# ---------------------------------------------------------------------------
# Control actions  (Basic.Enums.Control - values 1..7, 0 is unused)
# ---------------------------------------------------------------------------
class Control(IntEnum):
    PAUSE = 1
    GO_TO_WORK = 2
    GO_TO_STATION = 3
    GO_EDGE_CUTTING = 4
    GO_SECOND_AREA_MOWING = 5
    GO_MAIN_SPOT_MOWING = 6
    GO_SECOND_SPOT_MOWING = 7


#: Basic.Enums.MowerStatus -> human readable
STATUS_NAMES: dict[int, str] = {
    0: "unknown",
    1: "mowing",
    3: "along_boundary",
    4: "edge_cutting",
    5: "second_area_mowing",
    6: "spot_mowing",
    7: "idle",
    19: "stopped",
    20: "paused",
    22: "boundary_signal_error",
    25: "unknown_25",
    32: "unknown_32",
}

#: Basic.Enums.Warning -> the mower stores these as single bytes in the
#: error log. Several are printable ASCII (66='B', 84='T', ...).
WARNINGS: dict[int, str] = {
    0: "none",
    50: "unknown_50",
    51: "unknown_51",
    65: "unknown_65",
    66: "battery_error",
    67: "motor_over_current",
    76: "mower_lifted",
    77: "motor_fault",
    78: "signal_error",
    80: "pcb_over_temperature",
    82: "rolling_over",
    83: "battery_over_temperature",
    84: "mower_tilted",
    88: "mower_trapped",
    255: "unknown_255",
}

#: Basic.Enums.Language (0..18)
LANGUAGES: dict[int, str] = {
    0: "English",
    1: "German",
    2: "Danish",
    3: "Czech",
    4: "Slovak",
    5: "Polish",
    6: "Hungarian",
    7: "Russian",
    8: "French",
    9: "Bulgarian",
    10: "Finnish",
    11: "Dutch",
    12: "Lithuanian",
    13: "Romanian",
    14: "Norwegian",
    15: "Portuguese",
    16: "Swedish",
    17: "Spanish",
    18: "Italian",
}

#: reverse distance: wire value = metres * 10, firmware clamps 0..20
REVERSE_FACTOR = 10
REVERSE_MIN_M = 0.0
REVERSE_MAX_M = 2.0
