"""Shared entity base for the Einhell mower."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EinhellMowerCoordinator


class EinhellMowerEntity(CoordinatorEntity[EinhellMowerCoordinator]):
    """Common device information and update plumbing."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: EinhellMowerCoordinator, key: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        address = coordinator.entry.data["address"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            manufacturer=MANUFACTURER,
            name="Einhell Mower",
            model="Robotic Mower (EC11353)",
            serial_number=(coordinator.data or {}).get("serial"),
            connections={("bluetooth", address)},
        )
