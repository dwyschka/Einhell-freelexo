"""Number entities (writable settings) for the Einhell mower."""

from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import REVERSE_MAX_M, REVERSE_MIN_M
from .coordinator import EinhellMowerCoordinator
from .entity import EinhellMowerEntity

_LOGGER = logging.getLogger(__name__)

NUMBERS: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key="reverse_distance",
        name="Reverse distance",
        icon="mdi:arrow-left-bold",
        native_min_value=REVERSE_MIN_M,
        native_max_value=REVERSE_MAX_M,
        native_step=0.1,
        native_unit_of_measurement=UnitOfLength.METERS,
        mode=NumberMode.SLIDER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EinhellMowerCoordinator = hass.data["einhell_mower"][
        entry.entry_id
    ]
    async_add_entities(
        EinhellMowerNumber(coordinator, desc) for desc in NUMBERS
    )


class EinhellMowerNumber(EinhellMowerEntity, NumberEntity):
    """Reverse distance in metres (command 0x40, wire = metres * 10)."""

    entity_description: NumberEntityDescription

    def __init__(
        self,
        coordinator: EinhellMowerCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("reverse_distance")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_reverse_distance(value)
