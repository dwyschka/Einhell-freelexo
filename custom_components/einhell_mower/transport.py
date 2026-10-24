"""BLE transport for the Einhell mower.

The mower does not use a well known serial-over-BLE profile, so the relevant
characteristics are auto-detected: the first service that exposes both a
notify/indicate characteristic and a write characteristic is used. Discovered
UUIDs are cached in the config entry so later connections are instant.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .protocol import Frame, FrameParser

_LOGGER = logging.getLogger(__name__)

NOTIFY_PROPS = {"notify", "indicate"}
WRITE_PROPS = {"write", "write-without-response"}


class MowerConnectionError(Exception):
    """Raised when the mower cannot be reached."""


class MowerBLE:
    """Manages the BLE link and turns notifications into frames."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        *,
        uuid_notify: str | None = None,
        uuid_write: str | None = None,
    ) -> None:
        self.hass = hass
        self.address = address
        self.uuid_notify = uuid_notify
        self.uuid_write = uuid_write

        self._client: BleakClientWithServiceCache | None = None
        self._parser = FrameParser()
        self._lock = asyncio.Lock()
        self._frame_event = asyncio.Event()
        self._pending: list[Frame] = []
        self._on_disconnect: Callable[[], None] | None = None
        self._rssi: int | None = None

    # -- properties ---------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def rssi(self) -> int | None:
        return self._rssi

    def set_disconnect_callback(self, cb: Callable[[], None]) -> None:
        self._on_disconnect = cb

    # -- connection ---------------------------------------------------------
    async def connect(self, timeout: float = 30.0) -> None:
        """Establish the BLE connection and subscribe to notifications."""
        async with self._lock:
            if self.connected:
                return

            device: BLEDevice | None = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is None:
                raise MowerConnectionError(
                    f"{self.address} not seen by any Bluetooth adapter or proxy"
                )

            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    device,
                    name="Einhell Mower",
                    max_attempts=3,
                    timeout=timeout,
                    disconnected_callback=self._handle_disconnect,
                )
            except Exception as err:  # noqa: BLE001 - bleak raises broadly
                raise MowerConnectionError(str(err)) from err

            self._client = client
            self._parser.reset()
            self._pending.clear()
            self._frame_event.clear()

            try:
                notify_uuid, write_uuid = await self._resolve_characteristics()
                await client.start_notify(notify_uuid, self._handle_notify)
            except Exception as err:  # noqa: BLE001
                await self._safe_disconnect()
                raise MowerConnectionError(
                    f"cannot subscribe to notifications: {err}"
                ) from err

            self.uuid_notify = notify_uuid
            self.uuid_write = write_uuid
            _LOGGER.debug(
                "connected to %s (notify=%s write=%s)",
                self.address,
                notify_uuid,
                write_uuid,
            )

    async def _resolve_characteristics(self) -> tuple[str, str]:
        """Find the notify and write characteristics.

        Preference order:
        1. explicitly configured UUIDs
        2. a single service that offers both
        3. first notify characteristic and first write characteristic
        """
        assert self._client is not None

        if self.uuid_notify and self.uuid_write:
            return self.uuid_notify, self.uuid_write

        services = self._client.services
        notify_only: list[BleakGATTCharacteristic] = []
        write_only: list[BleakGATTCharacteristic] = []

        for service in services:
            notifies = [
                c
                for c in service.characteristics
                if NOTIFY_PROPS & set(c.properties)
            ]
            writes = [
                c
                for c in service.characteristics
                if WRITE_PROPS & set(c.properties)
            ]
            if notifies and writes:
                return notifies[0].uuid, writes[0].uuid
            notify_only.extend(notifies)
            write_only.extend(writes)

        if notify_only and write_only:
            return notify_only[0].uuid, write_only[0].uuid

        raise MowerConnectionError(
            "no serial-like characteristic pair found; set the UUIDs manually"
        )

    async def disconnect(self) -> None:
        """Tear the link down."""
        async with self._lock:
            await self._safe_disconnect()

    async def _safe_disconnect(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        except Exception:  # noqa: BLE001 - best effort
            _LOGGER.debug("disconnect failed", exc_info=True)
        finally:
            self._client = None

    def _handle_disconnect(self, _client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("mower %s disconnected", self.address)
        self._client = None
        if self._on_disconnect:
            self._on_disconnect()

    # -- frame io -----------------------------------------------------------
    def _handle_notify(
        self, _char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Notification callback (runs on the bleak thread/loop)."""
        _LOGGER.debug("notify <- %s", bytes(data).hex(" "))
        for frame in self._parser.feed(bytes(data)):
            self._pending.append(frame)
            self._frame_event.set()

    async def send(self, frame: bytes) -> None:
        """Write one command frame."""
        client = self._client
        if client is None or not client.is_connected:
            raise MowerConnectionError("not connected")
        if not self.uuid_write:
            raise MowerConnectionError("write characteristic not resolved")

        _LOGGER.debug("notify -> %s", frame.hex(" "))
        try:
            await client.write_gatt_char(
                self.uuid_write, frame, response=False
            )
        except Exception as err:  # noqa: BLE001
            raise MowerConnectionError(f"write failed: {err}") from err

    async def request(
        self, frame: bytes, expect: int, timeout: float
    ) -> Frame:
        """Send a frame and wait for the response with the given code."""
        # drop stale frames so we never return an old answer
        self._pending.clear()
        self._frame_event.clear()

        await self.send(frame)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            while self._pending:
                candidate = self._pending.pop(0)
                if candidate.code == expect:
                    return candidate
                _LOGGER.debug("ignoring unsolicited frame %s", candidate)

            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"no 0x{expect:02X} response within {timeout}s"
                )
            self._frame_event.clear()
            try:
                await asyncio.wait_for(self._frame_event.wait(), remaining)
            except TimeoutError:
                continue

    async def update_rssi(self) -> None:
        """Refresh the cached RSSI value from the Bluetooth manager."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is not None:
            self._rssi = getattr(device, "rssi", None)
