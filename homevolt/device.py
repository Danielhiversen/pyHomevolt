"""Device class for Homevolt EMS devices."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import DEVICE_MAP, ENDPOINT_EMS, ENDPOINT_SCHEDULE, SCHEDULE_TYPE
from .exceptions import (
    HomevoltAuthenticationError,
    HomevoltConnectionError,
    HomevoltDataError,
)
from .models import DeviceMetadata, Sensor, SensorType

_LOGGER = logging.getLogger(__name__)


class Device:
    """Represents a Homevolt EMS device."""

    def __init__(
        self,
        ip_address: str,
        password: str | None,
        websession: aiohttp.ClientSession,
    ) -> None:
        """Initialize the device.

        Args:
            ip_address: IP address of the Homevolt device
            password: Optional password for authentication
            websession: aiohttp ClientSession for making requests
        """
        self._ip_address = ip_address
        self._password = password
        self._websession = websession
        self._auth = aiohttp.BasicAuth("admin", password) if password else None

        self.device_id: str | None = None
        self.sensors: dict[str, Sensor] = {}
        self.device_metadata: dict[str, DeviceMetadata] = {}
        self.current_schedule: dict[str, Any] | None = None

    async def update_info(self) -> None:
        """Fetch and update all device information."""
        await self.fetch_ems_data()
        await self.fetch_schedule_data()

    async def fetch_ems_data(self) -> None:
        """Fetch EMS data from the device."""
        try:
            url = f"http://{self._ip_address}{ENDPOINT_EMS}"
            async with self._websession.get(url, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                ems_data = await response.json()
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to connect to device: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse EMS data: {err}") from err

        self._parse_ems_data(ems_data)

    async def fetch_schedule_data(self) -> None:
        """Fetch schedule data from the device."""
        try:
            url = f"http://{self._ip_address}{ENDPOINT_SCHEDULE}"
            async with self._websession.get(url, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                schedule_data = await response.json()
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to connect to device: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse schedule data: {err}") from err

        self._parse_schedule_data(schedule_data)

    def _parse_ems_data(self, ems_data: dict[str, Any]) -> None:
        """Parse EMS JSON response."""
        if not ems_data.get("ems") or not ems_data["ems"]:
            raise HomevoltDataError("No EMS data found in response")

        device_id = str(ems_data["ems"][0]["ecu_id"])
        self.device_id = device_id
        ems_device_id = f"ems_{device_id}"

        # Initialize device metadata
        self.device_metadata = {
            ems_device_id: DeviceMetadata(name=f"Homevolt EMS {device_id}", model="Homevolt EMS"),
            "grid": DeviceMetadata(name="Homevolt Grid Sensor", model="Grid Sensor"),
            "solar": DeviceMetadata(name="Homevolt Solar Sensor", model="Solar Sensor"),
            "load": DeviceMetadata(name="Homevolt Load Sensor", model="Load Sensor"),
        }

        # Initialize sensors dictionary
        self.sensors = {}

        # EMS device sensors - all main EMS data
        ems = ems_data["ems"][0]
        self.sensors.update(
            {
                "L1 Voltage": Sensor(
                    value=ems["ems_voltage"]["l1"] / 10,
                    type=SensorType.VOLTAGE,
                    device_identifier=ems_device_id,
                ),
                "L2 Voltage": Sensor(
                    value=ems["ems_voltage"]["l2"] / 10,
                    type=SensorType.VOLTAGE,
                    device_identifier=ems_device_id,
                ),
                "L3 Voltage": Sensor(
                    value=ems["ems_voltage"]["l3"] / 10,
                    type=SensorType.VOLTAGE,
                    device_identifier=ems_device_id,
                ),
                "L1_L2 Voltage": Sensor(
                    value=ems["ems_voltage"]["l1_l2"] / 10,
                    type=SensorType.VOLTAGE,
                    device_identifier=ems_device_id,
                ),
                "L2_L3 Voltage": Sensor(
                    value=ems["ems_voltage"]["l2_l3"] / 10,
                    type=SensorType.VOLTAGE,
                    device_identifier=ems_device_id,
                ),
                "L3_L1 Voltage": Sensor(
                    value=ems["ems_voltage"]["l3_l1"] / 10,
                    type=SensorType.VOLTAGE,
                    device_identifier=ems_device_id,
                ),
                "L1 Current": Sensor(
                    value=ems["ems_current"]["l1"],
                    type=SensorType.CURRENT,
                    device_identifier=ems_device_id,
                ),
                "L2 Current": Sensor(
                    value=ems["ems_current"]["l2"],
                    type=SensorType.CURRENT,
                    device_identifier=ems_device_id,
                ),
                "L3 Current": Sensor(
                    value=ems["ems_current"]["l3"],
                    type=SensorType.CURRENT,
                    device_identifier=ems_device_id,
                ),
                "System Temperature": Sensor(
                    value=ems["ems_data"]["sys_temp"] / 10.0,
                    type=SensorType.TEMPERATURE,
                    device_identifier=ems_device_id,
                ),
                "Imported Energy": Sensor(
                    value=ems["ems_aggregate"]["imported_kwh"],
                    type=SensorType.ENERGY_INCREASING,
                    device_identifier=ems_device_id,
                ),
                "Exported Energy": Sensor(
                    value=ems["ems_aggregate"]["exported_kwh"],
                    type=SensorType.ENERGY_INCREASING,
                    device_identifier=ems_device_id,
                ),
                "Available Charging Power": Sensor(
                    value=ems["ems_prediction"]["avail_ch_pwr"],
                    type=SensorType.POWER,
                    device_identifier=ems_device_id,
                ),
                "Available Discharge Power": Sensor(
                    value=ems["ems_prediction"]["avail_di_pwr"],
                    type=SensorType.POWER,
                    device_identifier=ems_device_id,
                ),
                "Available Charging Energy": Sensor(
                    value=ems["ems_prediction"]["avail_ch_energy"],
                    type=SensorType.ENERGY_TOTAL,
                    device_identifier=ems_device_id,
                ),
                "Available Discharge Energy": Sensor(
                    value=ems["ems_prediction"]["avail_di_energy"],
                    type=SensorType.ENERGY_TOTAL,
                    device_identifier=ems_device_id,
                ),
                "Power": Sensor(
                    value=ems["ems_data"]["power"],
                    type=SensorType.POWER,
                    device_identifier=ems_device_id,
                ),
                "Frequency": Sensor(
                    value=ems["ems_data"]["frequency"],
                    type=SensorType.FREQUENCY,
                    device_identifier=ems_device_id,
                ),
                "Battery State of Charge": Sensor(
                    value=ems["ems_data"]["soc_avg"] / 100,
                    type=SensorType.PERCENTAGE,
                    device_identifier=ems_device_id,
                ),
            }
        )

        # Battery sensors
        for bat_id, battery in enumerate(ems.get("bms_data", [])):
            battery_device_id = f"battery_{bat_id}"
            self.device_metadata[battery_device_id] = DeviceMetadata(
                name=f"Homevolt Battery {bat_id}",
                model="Homevolt Battery",
            )
            self.sensors[f"Homevolt battery {bat_id}"] = Sensor(
                value=battery["soc"] / 100,
                type=SensorType.PERCENTAGE,
                device_identifier=battery_device_id,
            )
            self.sensors[f"Homevolt battery {bat_id} tmin"] = Sensor(
                value=battery["tmin"] / 10,
                type=SensorType.TEMPERATURE,
                device_identifier=battery_device_id,
            )
            self.sensors[f"Homevolt battery {bat_id} tmax"] = Sensor(
                value=battery["tmax"] / 10,
                type=SensorType.TEMPERATURE,
                device_identifier=battery_device_id,
            )
            self.sensors[f"Homevolt battery {bat_id} charge cycles"] = Sensor(
                value=battery["cycle_count"],
                type=SensorType.COUNT,
                device_identifier=battery_device_id,
            )

        # External sensors (grid, solar, load)
        for sensor in ems_data.get("sensors", []):
            if not sensor.get("available"):
                continue

            sensor_type = sensor["type"]
            sensor_device_id = DEVICE_MAP.get(sensor_type)

            if not sensor_device_id:
                continue

            # Calculate total power from all phases
            total_power = sum(phase["power"] for phase in sensor.get("phase", []))

            self.sensors[f"Power {sensor_type}"] = Sensor(
                value=total_power,
                type=SensorType.POWER,
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Energy imported {sensor_type}"] = Sensor(
                value=sensor.get("energy_imported", 0),
                type=SensorType.ENERGY_INCREASING,
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Energy exported {sensor_type}"] = Sensor(
                value=sensor.get("energy_exported", 0),
                type=SensorType.ENERGY_INCREASING,
                device_identifier=sensor_device_id,
            )
            self.sensors[f"RSSI {sensor_type}"] = Sensor(
                value=sensor.get("rssi"),
                type=SensorType.SIGNAL_STRENGTH,
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Average RSSI {sensor_type}"] = Sensor(
                value=sensor.get("average_rssi"),
                type=SensorType.SIGNAL_STRENGTH,
                device_identifier=sensor_device_id,
            )

            # Phase-specific sensors
            for phase_name, phase in zip(["L1", "L2", "L3"], sensor.get("phase", []), strict=False):
                self.sensors[f"{phase_name} Voltage {sensor_type}"] = Sensor(
                    value=phase.get("voltage"),
                    type=SensorType.VOLTAGE,
                    device_identifier=sensor_device_id,
                )
                self.sensors[f"{phase_name} Current {sensor_type}"] = Sensor(
                    value=phase.get("amp"),
                    type=SensorType.CURRENT,
                    device_identifier=sensor_device_id,
                )
                self.sensors[f"{phase_name} Power {sensor_type}"] = Sensor(
                    value=phase.get("power"),
                    type=SensorType.POWER,
                    device_identifier=sensor_device_id,
                )

    def _parse_schedule_data(self, schedule_data: dict[str, Any]) -> None:
        """Parse schedule JSON response."""
        self.current_schedule = schedule_data

        if not self.device_id:
            return

        ems_device_id = f"ems_{self.device_id}"

        self.sensors["Schedule id"] = Sensor(
            value=schedule_data.get("schedule_id"),
            type=SensorType.TEXT,
            device_identifier=ems_device_id,
        )

        schedule = schedule_data.get("schedule", [{}])[0] if schedule_data.get("schedule") else {"type": -1, "params": {}}

        self.sensors["Schedule Type"] = Sensor(
            value=SCHEDULE_TYPE.get(schedule.get("type", -1)),
            type=SensorType.SCHEDULE_TYPE,
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Power Setpoint"] = Sensor(
            value=schedule.get("params", {}).get("setpoint"),
            type=SensorType.POWER,
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Max Power"] = Sensor(
            value=schedule.get("max_charge"),
            type=SensorType.POWER,
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Max Discharge"] = Sensor(
            value=schedule.get("max_discharge"),
            type=SensorType.POWER,
            device_identifier=ems_device_id,
        )

