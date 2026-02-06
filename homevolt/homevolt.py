"""Main Homevolt class for connecting to EMS devices."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    ENDPOINT_EMS,
    ENDPOINT_SCHEDULE,
    SCHEDULE_TYPE,
)
from .exceptions import (
    HomevoltAuthenticationError,
    HomevoltConnectionError,
    HomevoltDataError,
)
from .models import DeviceMetadata, Sensor

_LOGGER = logging.getLogger(__name__)


class Homevolt:
    """Main class for interacting with Homevolt EMS devices."""

    def __init__(
        self,
        host: str,
        password: str | None = None,
        websession: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the Homevolt connection.

        Args:
            host: Hostname or IP address of the Homevolt device
            password: Optional password for authentication
            websession: Optional aiohttp ClientSession. If not provided, one will be created.
        """
        if not host.startswith("http"):
            host = f"http://{host}"
        self.base_url = host
        self._password = password
        self._websession = websession
        self._own_session = websession is None
        self._auth = aiohttp.BasicAuth("admin", password) if password else None

        self.unique_id: str | None = None
        self.sensors: dict[str, Sensor] = {}
        self.device_metadata: dict[str, DeviceMetadata] = {}
        self.current_schedule: dict[str, Any] | None = None

    async def update_info(self) -> None:
        """Fetch and update all device information."""
        await self._ensure_session()
        await self.fetch_ems_data()
        await self.fetch_schedule_data()

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

    async def fetch_ems_data(self) -> None:
        """Fetch EMS data from the device."""
        await self._ensure_session()
        assert self._websession is not None
        url = f"{self.base_url}{ENDPOINT_EMS}"
        try:
            async with self._websession.get(url, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                ems_data = await response.json()
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to connect to device: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse EMS data: {err}") from err
        _LOGGER.debug("EMS Data: %s", ems_data)
        self._parse_ems_data(ems_data)

    async def fetch_schedule_data(self) -> None:
        """Fetch schedule data from the device."""
        await self._ensure_session()
        assert self._websession is not None
        url = f"{self.base_url}{ENDPOINT_SCHEDULE}"
        try:
            async with self._websession.get(url, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                schedule_data = await response.json()
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to connect to device: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse schedule data: {err}") from err

        _LOGGER.debug("Schedule Data: %s", schedule_data)
        self._parse_schedule_data(schedule_data)

    def _parse_ems_data(self, ems_data: dict[str, Any]) -> None:
        """Parse EMS JSON response."""
        if not ems_data.get("ems") or not ems_data["ems"]:
            raise HomevoltDataError("No EMS data found in response")

        device_id = str(ems_data["ems"][0]["ecu_id"])
        self.unique_id = device_id
        ems_device_id = f"ems_{device_id}"

        self.device_metadata = {
            ems_device_id: DeviceMetadata(name=f"EMS {device_id}", model="EMS"),
        }

        self.sensors = {}

        ems = ems_data["ems"][0]
        self.sensors.update(
            {
                "L1 Voltage": Sensor(
                    value=ems["ems_voltage"]["l1"] / 10,
                    type="l1_voltage",
                    device_identifier=ems_device_id,
                ),
                "L2 Voltage": Sensor(
                    value=ems["ems_voltage"]["l2"] / 10,
                    type="l2_voltage",
                    device_identifier=ems_device_id,
                ),
                "L3 Voltage": Sensor(
                    value=ems["ems_voltage"]["l3"] / 10,
                    type="l3_voltage",
                    device_identifier=ems_device_id,
                ),
                "L1_L2 Voltage": Sensor(
                    value=ems["ems_voltage"]["l1_l2"] / 10,
                    type="l1_l2_voltage",
                    device_identifier=ems_device_id,
                ),
                "L2_L3 Voltage": Sensor(
                    value=ems["ems_voltage"]["l2_l3"] / 10,
                    type="l2_l3_voltage",
                    device_identifier=ems_device_id,
                ),
                "L3_L1 Voltage": Sensor(
                    value=ems["ems_voltage"]["l3_l1"] / 10,
                    type="l3_l1_voltage",
                    device_identifier=ems_device_id,
                ),
                "L1 Current": Sensor(
                    value=ems["ems_current"]["l1"],
                    type="l1_current",
                    device_identifier=ems_device_id,
                ),
                "L2 Current": Sensor(
                    value=ems["ems_current"]["l2"],
                    type="l2_current",
                    device_identifier=ems_device_id,
                ),
                "L3 Current": Sensor(
                    value=ems["ems_current"]["l3"],
                    type="l3_current",
                    device_identifier=ems_device_id,
                ),
                "System Temperature": Sensor(
                    value=ems["ems_data"]["sys_temp"] / 10.0,
                    type="system_temperature",
                    device_identifier=ems_device_id,
                ),
                "Imported Energy": Sensor(
                    value=ems["ems_aggregate"]["imported_kwh"],
                    type="imported_energy",
                    device_identifier=ems_device_id,
                ),
                "Exported Energy": Sensor(
                    value=ems["ems_aggregate"]["exported_kwh"],
                    type="exported_energy",
                    device_identifier=ems_device_id,
                ),
                "Available Charging Power": Sensor(
                    value=ems["ems_prediction"]["avail_ch_pwr"],
                    type="available_charging_power",
                    device_identifier=ems_device_id,
                ),
                "Available Discharge Power": Sensor(
                    value=ems["ems_prediction"]["avail_di_pwr"],
                    type="available_discharge_power",
                    device_identifier=ems_device_id,
                ),
                "Available Charging Energy": Sensor(
                    value=ems["ems_prediction"]["avail_ch_energy"],
                    type="available_charging_energy",
                    device_identifier=ems_device_id,
                ),
                "Available Discharge Energy": Sensor(
                    value=ems["ems_prediction"]["avail_di_energy"],
                    type="available_discharge_energy",
                    device_identifier=ems_device_id,
                ),
                "Power": Sensor(
                    value=ems["ems_data"]["power"],
                    type="power",
                    device_identifier=ems_device_id,
                ),
                "Frequency": Sensor(
                    value=ems["ems_data"]["frequency"],
                    type="frequency",
                    device_identifier=ems_device_id,
                ),
                "State of Charge": Sensor(
                    value=ems["ems_data"]["soc_avg"] / 100,
                    type="state_of_charge",
                    device_identifier=ems_device_id,
                ),
            }
        )

        for bat_id, battery in enumerate(ems.get("bms_data", [])):
            battery_device_id = f"battery_{bat_id}"
            self.device_metadata[battery_device_id] = DeviceMetadata(
                name=f"Battery blade {bat_id}",
                model="Battery blade",
            )
            if "soc" in battery:
                self.sensors[f"Homevolt battery {bat_id}"] = Sensor(
                    value=battery["soc"] / 100,
                    type="state_of_charge",
                    device_identifier=battery_device_id,
                )
            if "tmin" in battery:
                self.sensors[f"Homevolt battery {bat_id} tmin"] = Sensor(
                    value=battery["tmin"] / 10,
                    type="tmin",
                    device_identifier=battery_device_id,
                )
            if "tmax" in battery:
                self.sensors[f"Homevolt battery {bat_id} tmax"] = Sensor(
                    value=battery["tmax"] / 10,
                    type="tmax",
                    device_identifier=battery_device_id,
                )
            if "cycle_count" in battery:
                self.sensors[f"Homevolt battery {bat_id} charge cycles"] = Sensor(
                    value=battery["cycle_count"],
                    type="charge_cycles",
                    device_identifier=battery_device_id,
                )
            if "voltage" in battery:
                self.sensors[f"Homevolt battery {bat_id} voltage"] = Sensor(
                    value=battery["voltage"] / 100,
                    type="voltage",
                    device_identifier=battery_device_id,
                )
            if "current" in battery:
                self.sensors[f"Homevolt battery {bat_id} current"] = Sensor(
                    value=battery["current"],
                    type="current",
                    device_identifier=battery_device_id,
                )
            if "power" in battery:
                self.sensors[f"Homevolt battery {bat_id} power"] = Sensor(
                    value=battery["power"],
                    type="power",
                    device_identifier=battery_device_id,
                )
            if "soh" in battery:
                self.sensors[f"Homevolt battery {bat_id} soh"] = Sensor(
                    value=battery["soh"] / 100,
                    type="soh",
                    device_identifier=battery_device_id,
                )

        for sensor in ems_data.get("sensors", []):
            if not sensor.get("available"):
                continue

            if sensor_type := sensor.get("sensor_type"):
                if sensor_type == "ems":
                    continue
                function = sensor.get("function", "")

            elif sensor_type := sensor.get("type"):
                function = ""
            else:
                continue

            sensor_device_id = sensor.get("euid")

            if not sensor_device_id:
                continue
            self.device_metadata[sensor_device_id] = DeviceMetadata(
                name=f"{str(sensor_type).title()} {function.title()} Sensor".replace(
                    "  ", " "
                ).replace("_", " "),
                model=sensor_type,
            )

            total_power = sum(phase["power"] for phase in sensor.get("phase", []))

            self.sensors[f"Power {sensor_type}"] = Sensor(
                value=total_power,
                type="power",
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Energy imported {sensor_type}"] = Sensor(
                value=sensor.get("energy_imported", 0),
                type="energy_imported",
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Energy exported {sensor_type}"] = Sensor(
                value=sensor.get("energy_exported", 0),
                type="energy_exported",
                device_identifier=sensor_device_id,
            )
            self.sensors[f"RSSI {sensor_type}"] = Sensor(
                value=sensor.get("rssi"),
                type="rssi",
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Average RSSI {sensor_type}"] = Sensor(
                value=sensor.get("average_rssi"),
                type="average_rssi",
                device_identifier=sensor_device_id,
            )

            for phase_name, phase in zip(["L1", "L2", "L3"], sensor.get("phase", [])):
                phase_lower = phase_name.lower()
                self.sensors[f"{phase_name} Voltage {sensor_type}"] = Sensor(
                    value=phase.get("voltage"),
                    type=f"{phase_lower}_voltage",
                    device_identifier=sensor_device_id,
                )
                self.sensors[f"{phase_name} Current {sensor_type}"] = Sensor(
                    value=phase.get("amp"),
                    type=f"{phase_lower}_current",
                    device_identifier=sensor_device_id,
                )
                self.sensors[f"{phase_name} Power {sensor_type}"] = Sensor(
                    value=phase.get("power"),
                    type=f"{phase_lower}_power",
                    device_identifier=sensor_device_id,
                )

    def _parse_schedule_data(self, schedule_data: dict[str, Any]) -> None:
        """Parse schedule JSON response."""
        self.current_schedule = schedule_data

        if not self.unique_id:
            return

        ems_device_id = f"ems_{self.unique_id}"

        self.sensors["Schedule id"] = Sensor(
            value=schedule_data.get("schedule_id"),
            type="schedule_id",
            device_identifier=ems_device_id,
        )

        schedule = (
            schedule_data.get("schedule", [{}])[0]
            if schedule_data.get("schedule")
            else {"type": -1, "params": {}}
        )

        self.sensors["Schedule Type"] = Sensor(
            value=SCHEDULE_TYPE.get(schedule.get("type", -1)),
            type="schedule_type",
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Power Setpoint"] = Sensor(
            value=schedule.get("params", {}).get("setpoint"),
            type="schedule_power_setpoint",
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Max Power"] = Sensor(
            value=schedule.get("max_charge"),
            type="schedule_max_power",
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Max Discharge"] = Sensor(
            value=schedule.get("max_discharge"),
            type="schedule_max_discharge",
            device_identifier=ems_device_id,
        )
