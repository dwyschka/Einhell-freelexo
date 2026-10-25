"""Standalone checks for the frame codec - no Home Assistant required."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "einhell_mower"
)

pkg = types.ModuleType("einhell_mower")
pkg.__path__ = [str(PKG_DIR)]  # type: ignore[attr-defined]
sys.modules["einhell_mower"] = pkg


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"einhell_mower.{name}", PKG_DIR / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"einhell_mower.{name}"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


const = _load("const")
protocol = _load("protocol")

failures = 0


def check(label: str, actual, expected) -> None:
    global failures
    if actual == expected:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}\n       got      {actual!r}\n       expected {expected!r}")


print("framing (derived from the official app)")
frame = protocol.build_frame(0x00)
check("length", len(frame), 24)
check("start bytes", frame[:3], b"DYM")
check("end bytes", frame[18:], bytes.fromhex("00160601ff0a"))

print("time encoding (TimeMessage.GetBytes)")
frame = protocol.build_frame(
    const.Cmd.TIME,
    protocol.encode_set_time(dt.datetime(2026, 10, 24, 17, 30, 45)),
)
check(
    "2026-10-24 17:30",
    frame[:10].hex(" "),
    "44 59 4d 02 14 1a 0a 18 11 1e",
)

print("pin encoding (PinMessage)")
check("pin bytes", protocol.encode_pin("1234", "9876").hex(" "),
      "01 02 03 04 09 08 07 06")

print("reverse distance (metres * 10, big endian)")
check("2.0 m", protocol.encode_reverse_distance(2.0).hex(" "), "00 14")
check("0.5 m", protocol.encode_reverse_distance(0.5).hex(" "), "00 05")

print("frame parsing")
raw = b"DYM" + bytes((0x80,)) + bytes(range(1, 16)) + bytes.fromhex("160601")
check("response length", len(raw), 22)
parser = protocol.FrameParser()
check("partial waits", parser.feed(raw[:10]), [])
frames = parser.feed(raw[10:])
check("one frame", len(frames), 1)
check("code", frames[0].code, 0x80)
check("noise resync", len(protocol.FrameParser().feed(b"\xaa\xbb" + raw)), 1)
check("two in one packet", len(protocol.FrameParser().feed(raw + raw)), 2)

print("basic information (BasicInformationMessage.CreateModel)")
info = protocol.Frame(
    code=0x80,
    payload=bytes([0x80, 77, 31, 28, 1, 1, 0, 3, 4, 19]),
)
d = protocol.decode(info)
check("battery", d["battery"], 77)
check("board temperature", d["board_temperature"], 31)
check("battery temperature", d["battery_temperature"], 28)
check("charging", d["charging"], True)
check("firmware", d["firmware_version"], "1.0.3.4")
check("state", d["state"], 19)
check("state name", const.STATUS_NAMES[d["state"]], "stopped")

print("statistics (StatisticsMessage)")
stats = protocol.Frame(
    code=0x8F,
    payload=bytes([0x8F]) + bytes.fromhex("00000e10 00001c20 00000000"),
)
d = protocol.decode(stats)
check("boot hours", d["boot_hours"], 1.0)
check("runtime hours", d["runtime_hours"], 2.0)

print("error memory (timestamped entry)")
# 8 byte record: year hi/lo, month, day, hour, minute, second, code
log = protocol.Frame(
    code=0x8E,
    payload=bytes([0x8E, 0x07, 0xEA, 10, 25, 12, 34, 56, 84]),
)
d = protocol.decode(log)
check("has error", d["has_error"], True)
check("code", d["error_code"], 84)
check("name", d["error_name"], "mower_tilted")
check("timestamp", d["error_timestamp"], "2026-10-25 12:34:56")

empty = protocol.Frame(code=0x8E, payload=bytes(9))
d = protocol.decode(empty)
check("empty memory", d["has_error"], False)
check("empty name", d["error_name"], "none")

print("feature flags (8 bytes big endian)")
flags = protocol.Frame(
    code=0x91, payload=bytes([0x91, 0, 0, 0, 0, 0, 0, 0x0F, 0xF7]) + bytes(7)
)
check("mask", protocol.decode(flags)["feature_mask"], 0x0FF7)

print("reverse decode")
rev = protocol.Frame(code=0x90, payload=bytes([0x90, 0, 0x14]) + bytes(12))
check("metres", protocol.decode(rev)["reverse_distance"], 2.0)

print("zones (frequency + 3-digit distance)")
zones = protocol.Frame(
    code=0x8D,
    payload=bytes([0x8D, 7, 1, 2, 5, 9, 0, 4, 0]) + bytes(6),
)
d = protocol.decode(zones)
check("zone a frequency", d["zone_a_frequency"], 7)
check("zone a distance", d["zone_a_distance"], 125)
check("zone b frequency", d["zone_b_frequency"], 9)
check("zone b distance", d["zone_b_distance"], 40)
check(
    "zone encode roundtrip",
    protocol.encode_zones((7, 125), (9, 40)).hex(" "),
    "07 01 02 05 09 00 04 00",
)

print("cut settings (0x09 / 0x89)")
check(
    "set payload",
    protocol.encode_cut_settings(
        cut_in_rain=True, edge_mowing=False, rain_delay=300,
        boundary_frequency=4,
    ).hex(" "),
    "01 00 01 2c 05",
)
cut = protocol.Frame(code=0x89, payload=bytes([0x89, 1, 0, 1, 44, 5]) + bytes(10))
d = protocol.decode(cut)
check("rain flag", d["cut_in_rain"], True)
check("edge flag", d["edge_mowing"], False)
check("rain delay", d["rain_delay"], 300)
check("boundary frequency", d["boundary_frequency"], 5)

print("firmware information (0x92)")
fw = protocol.Frame(
    code=0x92,
    payload=bytes.fromhex("92020511100304110a0103") + bytes(6),
)
d = protocol.decode(fw)
check("main board", d["mainboard_version"], "2.5.17.16")
check("lcd board", d["lcd_version"], "3.4.17.10")
check("protocol", d["protocol_version"], "1.3")

print()
if failures:
    print(f"{failures} check(s) failed")
    raise SystemExit(1)
print("all checks passed")
