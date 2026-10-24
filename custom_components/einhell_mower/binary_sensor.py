"""Binary sensors for the Einhell mower."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EinhellMowerCoordinator
from .entity import EinhellMowerEntity

BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon="mdi:battery-charging",
    ),
    BinarySensorEntityDescription(
        key="error_active",
        name="Error active",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert",
    ),
    BinarySensorEntityDescription(
        key="connected",
        name="Bluetooth link",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:bluetooth-connect",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EinhellMowerCoordinator = hass.data["einhell_mower"][
        entry.entry_id
    ]
    async_add_entities(
        EinhellMowerBinarySensor(coordinator, desc) for desc in BINARY_SENSORS
    )


class EinhellMowerBinarySensor(EinhellMowerEntity, BinarySensorEntity):
    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: EinhellMowerCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        key = self.entity_description.key
        if key == "connected":
            return self.coordinator.connection.connected
        if key == "charging":
            return bool(data.get("charging"))
        return bool(data.get("has_error"))
