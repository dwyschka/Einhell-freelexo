"""Config flow for the Einhell mower."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

CONF_UUID_NOTIFY = "uuid_notify"
CONF_UUID_WRITE = "uuid_write"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_UPDATE_INTERVAL = 60


class EinhellMowerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a discovery callback."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_confirm()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual setup: pick a discovered device or type an address."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            self._address = address
            return self.async_create_entry(
                title=f"{MANUFACTURER} Mower {address[-5:]}",
                data={
                    CONF_ADDRESS: address,
                    CONF_UPDATE_INTERVAL: user_input.get(
                        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                    ),
                },
            )

        for info in async_discovered_service_info(self.hass, connectable=True):
            name = info.name or ""
            if any(
                token in name.lower()
                for token in ("mower", "robot", "einhell")
            ):
                self._discovered[info.address] = (
                    f"{name} ({info.address})"
                )

        if not self._discovered:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_ADDRESS): str,
                        vol.Optional(
                            CONF_UPDATE_INTERVAL,
                            default=DEFAULT_UPDATE_INTERVAL,
                        ): vol.All(int, vol.Range(min=15, max=3600)),
                    }
                ),
                errors={"base": "no_devices"},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(self._discovered),
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(int, vol.Range(min=15, max=3600)),
                }
            ),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a discovered mower."""
        assert self._address is not None
        if user_input is not None:
            if user_input.get("manual_uuids"):
                assert self.hass is not None
                return await self.async_step_uuids()
            return self.async_create_entry(
                title=f"{MANUFACTURER} Mower {self._address[-5:]}",
                data={CONF_ADDRESS: self._address},
            )

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"address": self._address},
            data_schema=vol.Schema(
                {vol.Optional("manual_uuids", default=False): bool}
            ),
        )

    async def async_step_uuids(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Fallback: enter the GATT UUIDs manually."""
        assert self._address is not None
        if user_input is not None:
            return self.async_create_entry(
                title=f"{MANUFACTURER} Mower {self._address[-5:]}",
                data={
                    CONF_ADDRESS: self._address,
                    CONF_UUID_NOTIFY: user_input[CONF_UUID_NOTIFY].strip(),
                    CONF_UUID_WRITE: user_input[CONF_UUID_WRITE].strip(),
                },
            )
        return self.async_show_form(
            step_id="uuids",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UUID_NOTIFY): str,
                    vol.Required(CONF_UUID_WRITE): str,
                }
            ),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EinhellMowerOptionsFlow()


class EinhellMowerOptionsFlow(OptionsFlow):
    """Polling interval and characteristic override."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        entry = self.config_entry
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=entry.options.get(
                            CONF_UPDATE_INTERVAL,
                            entry.data.get(
                                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                            ),
                        ),
                    ): vol.All(int, vol.Range(min=15, max=3600)),
                    vol.Optional(
                        "keep_connected",
                        default=entry.options.get("keep_connected", True),
                    ): bool,
                    vol.Optional(
                        CONF_UUID_NOTIFY,
                        default=entry.data.get(CONF_UUID_NOTIFY, ""),
                    ): str,
                    vol.Optional(
                        CONF_UUID_WRITE,
                        default=entry.data.get(CONF_UUID_WRITE, ""),
                    ): str,
                }
            ),
        )
