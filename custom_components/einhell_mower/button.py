"""Buttons for the Einhell mower."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import Control
from .coordinator import EinhellMowerCoordinator
from .entity import EinhellMowerEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class MowerButtonDescription(ButtonEntityDescription):
    action: Callable[[EinhellMowerCoordinator], Coroutine[Any, Any, None]]


async def _control(coordinator: EinhellMowerCoordinator, value: int) -> None:
    await coordinator.async_control(value)


BUTTONS: tuple[MowerButtonDescription, ...] = (
    MowerButtonDescription(
        key="go_to_work",
        name="Go to work",
        icon="mdi:play",
        action=lambda c: _control(c, Control.GO_TO_WORK),
    ),
    MowerButtonDescription(
        key="pause",
        name="Pause",
        icon="mdi:pause",
        action=lambda c: _control(c, Control.PAUSE),
    ),
    MowerButtonDescription(
        key="go_to_station",
        name="Go to station",
        icon="mdi:home-battery",
        action=lambda c: _control(c, Control.GO_TO_STATION),
    ),
    MowerButtonDescription(
        key="edge_cutting",
        name="Edge cutting",
        icon="mdi:grass",
        action=lambda c: _control(c, Control.GO_EDGE_CUTTING),
    ),
    MowerButtonDescription(
        key="second_area",
        name="Second area mowing",
        icon="mdi:vector-square",
        action=lambda c: _control(c, Control.GO_SECOND_AREA_MOWING),
    ),
    MowerButtonDescription(
        key="spot_main",
        name="Spot mowing (main)",
        icon="mdi:circle-slice-3",
        action=lambda c: _control(c, Control.GO_MAIN_SPOT_MOWING),
    ),
    MowerButtonDescription(
        key="spot_second",
        name="Spot mowing (second)",
        icon="mdi:circle-slice-5",
        action=lambda c: _control(c, Control.GO_SECOND_SPOT_MOWING),
    ),
    MowerButtonDescription(
        key="sync_time",
        name="Sync clock",
        icon="mdi:clock-check",
        entity_category=EntityCategory.CONFIG,
        action=lambda c: c.async_sync_time(),
    ),
    MowerButtonDescription(
        key="refresh_features",
        name="Refresh feature flags",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        action=lambda c: c.async_send_raw(0x61),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EinhellMowerCoordinator = hass.data["einhell_mower"][
        entry.entry_id
    ]
    async_add_entities(
        EinhellMowerButton(coordinator, desc) for desc in BUTTONS
    )


class EinhellMowerButton(EinhellMowerEntity, ButtonEntity):
    entity_description: MowerButtonDescription

    def __init__(
        self,
        coordinator: EinhellMowerCoordinator,
        description: MowerButtonDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.action(self.coordinator)
