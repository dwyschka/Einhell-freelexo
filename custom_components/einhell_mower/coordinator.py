"""Data coordinator and command API for the Einhell mower."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import DEFAULT_TIMEOUT, DOMAIN, RESPONSE_MAP, Cmd
from .protocol import (
    Frame,
    ProtocolError,
    build_frame,
    decode,
    encode_cut_settings,
    encode_pin,
    encode_reverse_distance,
    encode_set_time,
)
from .transport import MowerBLE, MowerConnectionError

_LOGGER = logging.getLogger(__name__)

POLL_SEQUENCE: tuple[tuple[int, bytes], ...] = (
    (Cmd.BASIC_INFO, b""),
    (Cmd.STATISTICS, b""),
    (Cmd.ERROR_LOG, b""),
    (Cmd.REVERSE_GET, b""),
    (Cmd.ZONES_QUERY, b""),
    (Cmd.LANGUAGE_QUERY, b""),
    (Cmd.CUT_SETTINGS_QUERY, b""),
)

ONESHOT_SEQUENCE: tuple[tuple[int, bytes], ...] = (
    (Cmd.FIRMWARE_INFO, b""),
    (Cmd.FEATURE_FLAGS, b""),
)


class EinhellMowerCoordinator(DataUpdateCoordinator[dict]):
    """Polls the mower and exposes the command interface."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        connection: MowerBLE,
        update_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            update_interval=dt.timedelta(seconds=update_interval),
            config_entry=entry,
        )
        self.entry = entry
        self.connection = connection
        self.data = {}
        self._oneshot_done = False

    async def async_close(self) -> None:
        await self.connection.disconnect()

    # -- polling ------------------------------------------------------------
    async def _async_update_data(self) -> dict:
        try:
            await self.connection.connect()
        except MowerConnectionError as err:
            raise UpdateFailed(str(err)) from err

        data = dict(self.data or {})
        sequence = list(POLL_SEQUENCE)
        if not self._oneshot_done:
            sequence += list(ONESHOT_SEQUENCE)

        for cmd, payload in sequence:
            try:
                frame = await self._query(cmd, payload)
            except MowerConnectionError as err:
                raise UpdateFailed(str(err)) from err
            except (TimeoutError, ProtocolError) as err:
                raise UpdateFailed(
                    f"query 0x{cmd:02X} failed: {err}"
                ) from err
            data.update(decode(frame))
            data[f"raw_0x{frame.code:02X}"] = frame.raw.hex(" ")

        self._oneshot_done = True
        await self.connection.update_rssi()
        data["rssi"] = self.connection.rssi
        data["last_update"] = dt_util.utcnow().isoformat()
        return data

    async def _query(self, cmd: int, payload: bytes = b"") -> Frame:
        """Send one query.

        A sleeping mower sometimes ignores the very first frame after the
        link is up, so a timeout is retried once.
        """
        expect = RESPONSE_MAP.get(cmd)
        if expect is None:
            raise ProtocolError(f"no response mapping for 0x{cmd:02X}")
        frame = build_frame(cmd, payload)
        try:
            return await self.connection.request(
                frame, expect, DEFAULT_TIMEOUT
            )
        except TimeoutError:
            _LOGGER.debug("query 0x%02X timed out, retrying once", cmd)
            return await self.connection.request(
                frame, expect, DEFAULT_TIMEOUT
            )

    # -- commands -----------------------------------------------------------
    async def async_send_raw(
        self, cmd: int, payload: bytes = b""
    ) -> Frame | None:
        await self.ensure_connected()
        frame = build_frame(cmd, payload)
        expect = RESPONSE_MAP.get(cmd)
        if expect is None:
            await self.connection.send(frame)
            await asyncio.sleep(0.2)
            return None
        result = await self.connection.request(
            frame, expect, DEFAULT_TIMEOUT
        )
        self._merge(result)
        return result

    async def async_sync_time(self) -> None:
        """Write the current local time into the mower RTC (command 0x02)."""
        await self.async_send_raw(
            Cmd.TIME, encode_set_time(dt_util.now())
        )

    async def async_set_reverse_distance(self, metres: float) -> None:
        """Set the reverse distance, 0.0..2.0 m (command 0x40)."""
        await self.async_send_raw(
            Cmd.REVERSE_SET, encode_reverse_distance(metres)
        )
        await self.async_request_refresh()

    async def async_set_pin(self, current: str, new: str) -> None:
        """Change the PIN (command 0x06, current + new as digit bytes)."""
        frame = await self.async_send_raw(Cmd.PIN, encode_pin(current, new))
        if frame is not None and not decode(frame).get("ok", False):
            raise ProtocolError("the mower rejected the PIN")

    async def async_set_cut_settings(
        self,
        *,
        cut_in_rain: bool,
        edge_mowing: bool,
        rain_delay: int,
        boundary_frequency: int | None = None,
        boundary_raw: int | None = None,
    ) -> None:
        """Write the cut settings (command 0x09)."""
        await self.async_send_raw(
            Cmd.CUT_SETTINGS,
            encode_cut_settings(
                cut_in_rain=cut_in_rain,
                edge_mowing=edge_mowing,
                rain_delay=rain_delay,
                boundary_frequency=boundary_frequency,
                boundary_raw=boundary_raw,
            ),
        )
        await self.async_request_refresh()

    async def async_control(self, action: int) -> None:
        """BasicControlRequest, see const.Control."""
        await self.async_send_raw(Cmd.CONTROL, bytes((action,)))

    async def ensure_connected(self) -> None:
        if not self.connection.connected:
            await self.connection.connect()

    # -- helpers ------------------------------------------------------------
    def _merge(self, frame: Frame) -> None:
        if self.data is None:
            self.data = {}
        self.data.update(decode(frame))
        self.data[f"raw_0x{frame.code:02X}"] = frame.raw.hex(" ")
        self.async_update_listeners()

    @property
    def has_error(self) -> bool:
        return bool((self.data or {}).get("has_error"))
