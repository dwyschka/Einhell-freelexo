"""Einhell robotic mower integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import EinhellMowerCoordinator
from .transport import MowerBLE

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SWITCH,
]

SERVICE_SEND_COMMAND = "send_command"
SERVICE_SYNC_TIME = "sync_time"

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("command"): vol.All(int, vol.Range(min=0, max=255)),
        vol.Optional("payload", default=""): cv.string,
        vol.Optional("device_id"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one mower."""
    address: str = entry.data[CONF_ADDRESS]
    connection = MowerBLE(
        hass,
        address,
        uuid_notify=entry.data.get("uuid_notify"),
        uuid_write=entry.data.get("uuid_write"),
    )
    coordinator = EinhellMowerCoordinator(
        hass,
        entry,
        connection,
        update_interval=entry.options.get(
            "update_interval", entry.data.get("update_interval", 60)
        ),
        keep_connected=entry.options.get("keep_connected", True),
    )

    # raises ConfigEntryNotReady itself when the first poll fails
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one mower."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: EinhellMowerCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id
        )
        await coordinator.async_close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _get_coordinator(hass: HomeAssistant, device_id: str | None) -> Any:
    coordinators = hass.data.get(DOMAIN, {})
    if not device_id:
        if len(coordinators) != 1:
            raise HomeAssistantError(
                "several mowers configured - pass device_id"
            )
        return next(iter(coordinators.values()))

    from homeassistant.helpers import device_registry as dr

    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"unknown device_id {device_id}")

    for entry_id in device.config_entries:
        if entry_id in coordinators:
            return coordinators[entry_id]
    raise HomeAssistantError("device is not an Einhell mower")


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    async def _handle_send(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data.get("device_id"))
        raw = call.data.get("payload", "").strip()
        payload = bytes.fromhex(raw.replace(" ", "")) if raw else b""
        await coordinator.async_send_raw(call.data["command"], payload)

    async def _handle_sync_time(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data.get("device_id"))
        await coordinator.async_sync_time()

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_COMMAND, _handle_send, SEND_COMMAND_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_SYNC_TIME, _handle_sync_time)
