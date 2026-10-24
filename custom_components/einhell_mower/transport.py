"""BLE transport for the Einhell mower.

The app does not hardcode any GATT UUID, so the notify/write pair is detected
at runtime. Two details matter for reliability:

* a 24 byte frame does not fit into a single ATT packet at the default
  MTU 23, so a *write with response* (long write) is preferred;
* some modules need a short settle time after subscribing.
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

#: well known transparent-UART services, tried first
PREFERRED_SERVICES = (
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e",  # Nordic UART
    "0000ffe0-0000-1000-8000-00805f9b34fb",  # common Chinese module
    "0000ff00-0000-1000-8000-00805f9b34fb",
    "0000fff0-0000-1000-8000-00805f9b34fb",
)

SETTLE_SECONDS = 0.4


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
        self.write_with_response = True

        self._client: BleakClientWithServiceCache | None = None
        self._parser = FrameParser()
        self._lock = asyncio.Lock()
        self._frame_event = asyncio.Event()
        self._pending: list[Frame] = []
        self._on_disconnect: Callable[[], None] | None = None
        self._rssi: int | None = None
        self.mtu: int | None = None

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
    async def connect(self, timeout: float = 20.0) -> None:
        async with self._lock:
            if self.connected:
                return

            device: BLEDevice | None = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is None:
                self._log_candidates()
                raise MowerConnectionError(
                    f"{self.address} not seen by any Bluetooth adapter or proxy"
                )

            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    device,
                    name="Einhell Mower",
                    max_attempts=2,
                    timeout=timeout,
                    disconnected_callback=self._handle_disconnect,
                )
            except Exception as err:  # noqa: BLE001 - bleak raises broadly
                raise MowerConnectionError(str(err)) from err

            self._client = client
            self._parser.reset()
            self._pending.clear()
            self._frame_event.clear()

            self._log_services()

            try:
                notify_uuid, write_uuid, response = (
                    await self._resolve_characteristics()
                )
                await client.start_notify(notify_uuid, self._handle_notify)
            except Exception as err:  # noqa: BLE001
                await self._safe_disconnect()
                raise MowerConnectionError(
                    f"cannot subscribe to notifications: {err}"
                ) from err

            self.uuid_notify = notify_uuid
            self.uuid_write = write_uuid
            self.write_with_response = response
            self.mtu = getattr(client, "mtu_size", None)

            _LOGGER.debug(
                "connected to %s (notify=%s write=%s response=%s mtu=%s)",
                self.address,
                notify_uuid,
                write_uuid,
                response,
                self.mtu,
            )
            if self.mtu is not None and self.mtu < 27:
                _LOGGER.debug(
                    "MTU is %s - the 24 byte frame will be sent in %d "
                    "chunks",
                    self.mtu,
                    -(-24 // max(1, self.mtu - 3)),
                )

            # give the module a moment before the first frame
            await asyncio.sleep(SETTLE_SECONDS)

    def _log_candidates(self) -> None:
        """List similarly named devices when the configured one is missing.

        A rotating (random) BLE address would show up here as the same mower
        under a different address.
        """
        tokens = ("mower", "einhell", "robot", "freelexo", "ein")
        found = []
        for info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            name = (info.name or "").lower()
            if any(t in name for t in tokens) or info.address == self.address:
                found.append(
                    {
                        "address": info.address,
                        "name": info.name,
                        "rssi": info.rssi,
                    }
                )
        if found:
            _LOGGER.warning(
                "mower %s not reachable - nearby candidates: %s",
                self.address,
                found,
            )
        else:
            _LOGGER.warning(
                "mower %s not reachable and no similarly named device is "
                "advertising - check range, connection slots or that the "
                "mower is awake",
                self.address,
            )

    def _log_services(self) -> None:
        """Log the GATT tree so a failing setup can be diagnosed."""
        if not _LOGGER.isEnabledFor(logging.DEBUG) or self._client is None:
            return
        for service in self._client.services:
            _LOGGER.debug("service %s", service.uuid)
            for char in service.characteristics:
                _LOGGER.debug(
                    "  characteristic %s %s",
                    char.uuid,
                    ",".join(char.properties),
                )

    async def _resolve_characteristics(
        self,
    ) -> tuple[str, str, bool]:
        """Return (notify uuid, write uuid, write with response)."""
        assert self._client is not None

        if self.uuid_notify and self.uuid_write:
            return self.uuid_notify, self.uuid_write, True

        services = list(self._client.services)
        # try well known UART profiles first
        services.sort(
            key=lambda svc: 0
            if str(svc.uuid).lower() in PREFERRED_SERVICES
            else 1
        )
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
                return (
                    notifies[0].uuid,
                    writes[0].uuid,
                    "write" in writes[0].properties,
                )
            notify_only.extend(notifies)
            write_only.extend(writes)

        if notify_only and write_only:
            return (
                notify_only[0].uuid,
                write_only[0].uuid,
                "write" in write_only[0].properties,
            )

        raise MowerConnectionError(
            "no serial-like characteristic pair found; set the UUIDs manually"
        )

    async def disconnect(self) -> None:
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
        _LOGGER.debug("notify <- %s", bytes(data).hex(" "))
        for frame in self._parser.feed(bytes(data)):
            self._pending.append(frame)
            self._frame_event.set()

    async def send(self, frame: bytes) -> None:
        """Write one command frame, trying both write modes if needed."""
        client = self._client
        if client is None or not client.is_connected:
            raise MowerConnectionError("not connected")
        if not self.uuid_write:
            raise MowerConnectionError("write characteristic not resolved")

        mtu = self.mtu or getattr(client, "mtu_size", None)
        # A 24 byte frame does not fit one ATT packet at MTU 23. Transparent
        # UART modules forward every written chunk, so splitting is safe and
        # is what makes the frame work on small MTUs.
        chunk = (mtu - 3) if mtu and mtu > 3 else len(frame)
        chunks = [
            frame[i : i + chunk] for i in range(0, len(frame), chunk)
        ]

        _LOGGER.debug(
            "notify -> %s (response=%s mtu=%s chunks=%d)",
            frame.hex(" "),
            self.write_with_response,
            mtu,
            len(chunks),
        )
        try:
            for part in chunks:
                await client.write_gatt_char(
                    self.uuid_write,
                    part,
                    response=self.write_with_response,
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("write failed, retrying with other mode: %s", err)
            try:
                self.write_with_response = not self.write_with_response
                _LOGGER.debug(
                    "retrying write with response=%s", self.write_with_response
                )
                for part in chunks:
                    await client.write_gatt_char(
                        self.uuid_write,
                        part,
                        response=self.write_with_response,
                    )
            except Exception as err2:  # noqa: BLE001
                raise MowerConnectionError(
                    f"write failed: {err2}"
                ) from err2

    async def request(
        self, frame: bytes, expect: int, timeout: float
    ) -> Frame:
        """Send a frame and wait for the response with the given code."""
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
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is not None:
            self._rssi = getattr(device, "rssi", None)
