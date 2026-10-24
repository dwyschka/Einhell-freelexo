"""Writable switches for the Einhell mower."""

from __future__ import annotations

import logging

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EinhellMowerCoordinator
from .entity import EinhellMowerEntity

_LOGGER = logging.getLogger(__name__)

SWITCHES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="cut_in_rain",
        name="Mow in the rain",
        icon="mdi:weather-rainy",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EinhellMowerCoordinator = hass.data["einhell_mower"][
        entry.entry_id
    ]
    async_add_entities(
        EinhellMowerSwitch(coordinator, desc) for desc in SWITCHES
    )


class EinhellMowerSwitch(EinhellMowerEntity, SwitchEntity):
    """Rain toggle.

    The mower always expects the full cut-settings payload, so the other
    fields are taken from the last polled values to avoid clobbering them.
    """

    entity_description: SwitchEntityDescription

    def __init__(
        self,
        coordinator: EinhellMowerCoordinator,
        description: SwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data or {}).get("cut_in_rain")

    async def _write(self, enabled: bool) -> None:
        data = self.coordinator.data or {}
        await self.coordinator.async_set_cut_settings(
            cut_in_rain=enabled,
            edge_mowing=bool(data.get("edge_mowing")),
            rain_delay=int(data.get("rain_delay", 0)),
            boundary_raw=data.get("boundary_raw"),
        )

    async def async_turn_on(self, **kwargs) -> None:
        await self._write(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._write(False)
