"""Data models for Homevolt library."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass
class DeviceMetadata:
    """Metadata for device information."""

    name: str
    model: str


class SensorType(Enum):
    """Enumeration of sensor types."""

    COUNT = "count"
    CURRENT = "current"
    ENERGY_INCREASING = "energy_increasing"
    ENERGY_TOTAL = "energy_total"
    ENERGY = "energy"
    FREQUENCY = "frequency"
    POWER = "power"
    VOLTAGE = "voltage"
    SIGNAL_STRENGTH = "signal_strength"
    PERCENTAGE = "percentage"
    SCHEDULE_TYPE = "schedule_type"
    SCHEDULE_PARAMS = "schedule_params"
    TEMPERATURE = "temperature"
    TEXT = "text"


@dataclass
class Sensor:
    """Represents a sensor reading."""

    value: float | str | None
    type: SensorType
    device_identifier: str = "main"  # Device identifier for grouping sensors into devices

