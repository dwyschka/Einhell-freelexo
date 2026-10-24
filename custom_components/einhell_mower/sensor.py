"""Sensor entities for the Einhell mower."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import LANGUAGES, STATUS_NAMES
from .coordinator import EinhellMowerCoordinator
from .entity import EinhellMowerEntity


def _state_name(value: Any) -> str:
    if value is None:
        return "unknown"
    return STATUS_NAMES.get(int(value), f"state_{int(value)}")


@dataclass(frozen=True, kw_only=True)
class MowerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], StateType] = lambda _d: None
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[MowerSensorDescription, ...] = (
    MowerSensorDescription(
        key="state",
        name="Status",
        icon="mdi:robot-mower",
        value_fn=lambda d: _state_name(d.get("state")),
        attrs_fn=lambda d: {"raw_state": d.get("state")},
    ),
    MowerSensorDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("battery"),
    ),
    MowerSensorDescription(
        key="board_temperature",
        name="Main board temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("board_temperature"),
    ),
    MowerSensorDescription(
        key="battery_temperature",
        name="Battery temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("battery_temperature"),
    ),
    MowerSensorDescription(
        key="warning",
        name="Warning",
        icon="mdi:alert-outline",
        value_fn=lambda d: d.get("warning_name"),
    ),
    MowerSensorDescription(
        key="error_log",
        name="Error memory",
        icon="mdi:alert-circle-outline",
        value_fn=lambda d: len(d.get("error_names", [])),
        attrs_fn=lambda d: {
            "codes": d.get("errors"),
            "names": d.get("error_names"),
        },
    ),
    MowerSensorDescription(
        key="boot_hours",
        name="Boot count hours",
        icon="mdi:power",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: d.get("boot_hours"),
    ),
    MowerSensorDescription(
        key="runtime_hours",
        name="Machine run time",
        icon="mdi:engine",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: d.get("runtime_hours"),
    ),
    MowerSensorDescription(
        key="blade_hours",
        name="Blade run time",
        icon="mdi:fan",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: d.get("blade_hours"),
    ),
    MowerSensorDescription(
        key="firmware_version",
        name="Firmware version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("firmware_version"),
    ),
    MowerSensorDescription(
        key="zone_a_frequency",
        name="Zone A frequency",
        icon="mdi:vector-square",
        value_fn=lambda d: d.get("zone_a_frequency"),
    ),
    MowerSensorDescription(
        key="zone_a_distance",
        name="Zone A distance",
        icon="mdi:map-marker-distance",
        value_fn=lambda d: d.get("zone_a_distance"),
    ),
    MowerSensorDescription(
        key="zone_b_frequency",
        name="Zone B frequency",
        icon="mdi:vector-square",
        value_fn=lambda d: d.get("zone_b_frequency"),
    ),
    MowerSensorDescription(
        key="zone_b_distance",
        name="Zone B distance",
        icon="mdi:map-marker-distance",
        value_fn=lambda d: d.get("zone_b_distance"),
    ),
    MowerSensorDescription(
        key="language",
        name="Language",
        icon="mdi:translate",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: LANGUAGES.get(
            d.get("language_id", -1), d.get("language_id")
        ),
        attrs_fn=lambda d: {"language_id": d.get("language_id")},
    ),
    MowerSensorDescription(
        key="feature_mask",
        name="Feature flags",
        icon="mdi:toggle-switch-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            f"0x{d['feature_mask']:04X}" if "feature_mask" in d else None
        ),
        attrs_fn=lambda d: {"bits": d.get("feature_bits")},
    ),
    MowerSensorDescription(
        key="mainboard_version",
        name="Main board firmware",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("mainboard_version"),
        attrs_fn=lambda d: {"raw": d.get("mainboard_raw")},
    ),
    MowerSensorDescription(
        key="lcd_version",
        name="LCD board firmware",
        icon="mdi:monitor",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("lcd_version"),
        attrs_fn=lambda d: {"raw": d.get("lcd_raw")},
    ),
    MowerSensorDescription(
        key="protocol_version",
        name="Protocol version",
        icon="mdi:swap-horizontal",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("protocol_version"),
    ),
    MowerSensorDescription(
        key="rssi",
        name="Signal strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("rssi"),
    ),
    MowerSensorDescription(
        key="last_frame",
        name="Last frame",
        icon="mdi:code-json",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("raw_0x80"),
        attrs_fn=lambda d: {
            k: v for k, v in d.items() if k.startswith("raw_0x")
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EinhellMowerCoordinator = hass.data["einhell_mower"][
        entry.entry_id
    ]
    async_add_entities(
        EinhellMowerSensor(coordinator, desc) for desc in SENSORS
    )


class EinhellMowerSensor(EinhellMowerEntity, SensorEntity):
    entity_description: MowerSensorDescription

    def __init__(
        self,
        coordinator: EinhellMowerCoordinator,
        description: MowerSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.entity_description.attrs_fn:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})
