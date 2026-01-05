"""Main Homevolt class for connecting to EMS devices."""

from __future__ import annotations

import logging

import aiohttp

from .device import Device

_LOGGER = logging.getLogger(__name__)


class Homevolt:
    """Main class for interacting with Homevolt EMS devices."""

    def __init__(
        self,
        ip_address: str,
        password: str | None = None,
        websession: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the Homevolt connection.

        Args:
            ip_address: IP address of the Homevolt device
            password: Optional password for authentication
            websession: Optional aiohttp ClientSession. If not provided, one will be created.
        """
        self._ip_address = ip_address
        self._password = password
        self._websession = websession
        self._own_session = websession is None

        self._device: Device | None = None

    async def update_info(self) -> None:
        """Fetch and update device information."""
        if self._device is None:
            await self._ensure_session()
            self._device = Device(
                ip_address=self._ip_address,
                password=self._password,
                websession=self._websession,
            )

        await self._device.update_info()

    def get_device(self) -> Device:
        """Get the device object.

        Returns:
            The Device object for this Homevolt connection

        Raises:
            RuntimeError: If device information hasn't been fetched yet
        """
        if self._device is None:
            raise RuntimeError("Device information not yet fetched. Call update_info() first.")
        return self._device

    async def close_connection(self) -> None:
        """Close the connection and clean up resources."""
        if self._own_session and self._websession:
            await self._websession.close()
            self._websession = None

    async def _ensure_session(self) -> None:
        """Ensure a websession exists."""
        if self._websession is None:
            self._websession = aiohttp.ClientSession()
            self._own_session = True

    async def __aenter__(self) -> Homevolt:
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close_connection()

