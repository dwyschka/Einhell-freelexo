"""Diagnostics support - dumps the last known protocol state."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return everything needed to debug a protocol issue."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    connection = coordinator.connection

    return {
        "address": entry.data.get("address"),
        "connected": connection.connected,
        "notify_uuid": connection.uuid_notify,
        "write_uuid": connection.uuid_write,
        "rssi": connection.rssi,
        "known_commands": {
            "0x00": "InquireBaseInformation",
            "0x01": "BasicControlRequest",
            "0x02": "SystemTimeSet",
            "0x03": "LanguageSet",
            "0x04": "SetWorkTime_Start",
            "0x05": "SetWorkTime_Hours",
            "0x06": "SetPINCode",
            "0x09": "RainAndCutOpenSet",
            "0x0C": "InquirePINCode",
            "0x0D": "PartitionDataSet",
            "0x13": "InquireLanguage",
            "0x14": "InquireWorkTime",
            "0x19": "InquireRainAndCutOpen",
            "0x1D": "InquirePartition",
            "0x1E": "Error log",
            "0x1F": "Statistics",
            "0x24": "SetWorkTime_StartDouble",
            "0x25": "SetWorkTime_HoursDouble",
            "0x40": "ReverseSettings set",
            "0x60": "ReverseSettings get",
            "0x61": "Check_firmware_function",
            "0x62": "Return_FW_PV",
        },
        "data": coordinator.data,
    }
