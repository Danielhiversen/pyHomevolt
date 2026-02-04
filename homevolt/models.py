"""Data models for Homevolt library."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeviceMetadata:
    """Metadata for device information."""

    name: str
    model: str


@dataclass
class Sensor:
    """Represents a sensor reading."""

    value: float | str | None
    type: str
    device_identifier: str = "main"  # Device identifier for grouping sensors into devices
