"""Device class for Homevolt EMS devices."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    DEVICE_MAP,
    ENDPOINT_CONSOLE,
    ENDPOINT_EMS,
    ENDPOINT_PARAMS,
    ENDPOINT_SCHEDULE,
    SCHEDULE_TYPE,
)
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
        hostname: str,
        password: str | None,
        websession: aiohttp.ClientSession,
    ) -> None:
        """Initialize the device.

        Args:
            hostname: Hostname of the Homevolt device
            password: Optional password for authentication
            websession: aiohttp ClientSession for making requests
        """
        self.hostname = hostname
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
            url = f"{self.hostname}{ENDPOINT_EMS}"
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
            url = f"{self.hostname}{ENDPOINT_SCHEDULE}"
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
            if "soc" in battery:
                self.sensors[f"Homevolt battery {bat_id}"] = Sensor(
                    value=battery["soc"] / 100,
                    type=SensorType.PERCENTAGE,
                    device_identifier=battery_device_id,
                )
            if "tmin" in battery:
                self.sensors[f"Homevolt battery {bat_id} tmin"] = Sensor(
                    value=battery["tmin"] / 10,
                    type=SensorType.TEMPERATURE,
                    device_identifier=battery_device_id,
                )
            if "tmax" in battery:
                self.sensors[f"Homevolt battery {bat_id} tmax"] = Sensor(
                    value=battery["tmax"] / 10,
                    type=SensorType.TEMPERATURE,
                    device_identifier=battery_device_id,
                )
            if "cycle_count" in battery:
                self.sensors[f"Homevolt battery {bat_id} charge cycles"] = Sensor(
                    value=battery["cycle_count"],
                    type=SensorType.COUNT,
                    device_identifier=battery_device_id,
                )
            if "voltage" in battery:
                self.sensors[f"Homevolt battery {bat_id} voltage"] = Sensor(
                    value=battery["voltage"] / 100,
                    type=SensorType.VOLTAGE,
                    device_identifier=battery_device_id,
                )
            if "current" in battery:
                self.sensors[f"Homevolt battery {bat_id} current"] = Sensor(
                    value=battery["current"],
                    type=SensorType.CURRENT,
                    device_identifier=battery_device_id,
                )
            if "power" in battery:
                self.sensors[f"Homevolt battery {bat_id} power"] = Sensor(
                    value=battery["power"],
                    type=SensorType.POWER,
                    device_identifier=battery_device_id,
                )
            if "soh" in battery:
                self.sensors[f"Homevolt battery {bat_id} soh"] = Sensor(
                    value=battery["soh"] / 100,
                    type=SensorType.PERCENTAGE,
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

        schedule = (
            schedule_data.get("schedule", [{}])[0]
            if schedule_data.get("schedule")
            else {"type": -1, "params": {}}
        )

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

    async def _execute_console_command(self, command: str) -> dict[str, Any]:
        """Execute a console command via the HTTP API.

        Args:
            command: The console command to execute

        Returns:
            The JSON response from the console endpoint

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If response parsing fails
        """
        try:
            url = f"{self.hostname}{ENDPOINT_CONSOLE}"
            async with self._websession.post(
                url,
                auth=self._auth,
                json={"cmd": command},
            ) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to execute command: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse command response: {err}") from err

    async def set_battery_mode(
        self,
        mode: int,
        *,
        setpoint: int | None = None,
        max_charge: int | None = None,
        max_discharge: int | None = None,
        min_soc: int | None = None,
        max_soc: int | None = None,
        offline: bool = False,
    ) -> dict[str, Any]:
        """Set immediate battery control mode.

        Args:
            mode: Schedule type (0=Idle, 1=Inverter Charge, 2=Inverter Discharge,
                3=Grid Charge, 4=Grid Discharge, 5=Grid Charge/Discharge,
                6=Frequency Reserve, 7=Solar Charge, 8=Solar Charge/Discharge,
                9=Full Solar Export)
            setpoint: Power setpoint in Watts (for grid modes)
            max_charge: Maximum charge power in Watts
            max_discharge: Maximum discharge power in Watts
            min_soc: Minimum state of charge percentage
            max_soc: Maximum state of charge percentage
            offline: Take inverter offline during idle mode

        Returns:
            Response from the console command

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If command execution fails
        """
        if mode not in SCHEDULE_TYPE:
            raise ValueError(f"Invalid mode: {mode}. Must be 0-9")

        cmd_parts = [f"sched_set {mode}"]

        if setpoint is not None:
            cmd_parts.append(f"-s {setpoint}")
        if max_charge is not None:
            cmd_parts.append(f"-c {max_charge}")
        if max_discharge is not None:
            cmd_parts.append(f"-d {max_discharge}")
        if min_soc is not None:
            cmd_parts.append(f"--min {min_soc}")
        if max_soc is not None:
            cmd_parts.append(f"--max {max_soc}")
        if offline:
            cmd_parts.append("-o")

        command = " ".join(cmd_parts)
        return await self._execute_console_command(command)

    async def add_schedule(
        self,
        mode: int,
        *,
        from_time: str | None = None,
        to_time: str | None = None,
        setpoint: int | None = None,
        max_charge: int | None = None,
        max_discharge: int | None = None,
        min_soc: int | None = None,
        max_soc: int | None = None,
        offline: bool = False,
    ) -> dict[str, Any]:
        """Add a scheduled battery control entry.

        Args:
            mode: Schedule type (0=Idle, 1=Inverter Charge, 2=Inverter Discharge,
                3=Grid Charge, 4=Grid Discharge, 5=Grid Charge/Discharge,
                6=Frequency Reserve, 7=Solar Charge, 8=Solar Charge/Discharge,
                9=Full Solar Export)
            from_time: Start time in ISO format (YYYY-MM-DDTHH:mm:ss)
            to_time: End time in ISO format (YYYY-MM-DDTHH:mm:ss)
            setpoint: Power setpoint in Watts (for grid modes)
            max_charge: Maximum charge power in Watts
            max_discharge: Maximum discharge power in Watts
            min_soc: Minimum state of charge percentage
            max_soc: Maximum state of charge percentage
            offline: Take inverter offline during idle mode

        Returns:
            Response from the console command

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If command execution fails
        """
        if mode not in SCHEDULE_TYPE:
            raise ValueError(f"Invalid mode: {mode}. Must be 0-9")

        cmd_parts = [f"sched_add {mode}"]

        if from_time:
            cmd_parts.append(f"--from {from_time}")
        if to_time:
            cmd_parts.append(f"--to {to_time}")
        if setpoint is not None:
            cmd_parts.append(f"-s {setpoint}")
        if max_charge is not None:
            cmd_parts.append(f"-c {max_charge}")
        if max_discharge is not None:
            cmd_parts.append(f"-d {max_discharge}")
        if min_soc is not None:
            cmd_parts.append(f"--min {min_soc}")
        if max_soc is not None:
            cmd_parts.append(f"--max {max_soc}")
        if offline:
            cmd_parts.append("-o")

        command = " ".join(cmd_parts)
        return await self._execute_console_command(command)

    async def delete_schedule(self, schedule_id: int) -> dict[str, Any]:
        """Delete a schedule by ID.

        Args:
            schedule_id: The ID of the schedule to delete

        Returns:
            Response from the console command

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If command execution fails
        """
        return await self._execute_console_command(f"sched_del {schedule_id}")

    async def clear_all_schedules(self) -> dict[str, Any]:
        """Clear all schedules.

        Returns:
            Response from the console command

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If command execution fails
        """
        return await self._execute_console_command("sched_clear")

    async def enable_local_mode(self) -> dict[str, Any]:
        """Enable local mode to prevent remote schedule overrides.

        When enabled, remote schedules from Tibber/partners via MQTT will be blocked,
        and only local schedules will be used.

        Returns:
            Response from the params endpoint

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If parameter setting fails
        """
        return await self.set_parameter("settings_local", 1)

    async def disable_local_mode(self) -> dict[str, Any]:
        """Disable local mode to allow remote schedule overrides.

        When disabled, remote schedules from Tibber/partners via MQTT will replace
        local schedules.

        Returns:
            Response from the params endpoint

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If parameter setting fails
        """
        return await self.set_parameter("settings_local", 0)

    async def set_parameter(self, key: str, value: Any) -> dict[str, Any]:
        """Set a device parameter.

        Args:
            key: Parameter name
            value: Parameter value

        Returns:
            Response from the params endpoint

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If parameter setting fails
        """
        try:
            url = f"{self.hostname}{ENDPOINT_PARAMS}"
            async with self._websession.post(
                url,
                auth=self._auth,
                json={key: value},
            ) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to set parameter: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse parameter response: {err}") from err

    async def get_parameter(self, key: str) -> Any:
        """Get a device parameter value.

        Args:
            key: Parameter name

        Returns:
            Parameter value

        Raises:
            HomevoltConnectionError: If connection fails
            HomevoltAuthenticationError: If authentication fails
            HomevoltDataError: If parameter retrieval fails
        """
        try:
            url = f"{self.hostname}{ENDPOINT_PARAMS}"
            async with self._websession.get(url, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                params = await response.json()
                return params.get(key)
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to get parameter: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse parameter response: {err}") from err

    async def charge_battery(
        self,
        *,
        max_power: int | None = None,
        max_soc: int | None = None,
        min_soc: int | None = None,
    ) -> dict[str, Any]:
        """Charge battery using inverter (immediate).

        Args:
            max_power: Maximum charge power in Watts
            max_soc: Maximum state of charge percentage (stops at this level)
            min_soc: Minimum state of charge percentage (only charges if below this)

        Returns:
            Response from the console command
        """
        return await self.set_battery_mode(
            1,  # Inverter Charge
            max_charge=max_power,
            max_soc=max_soc,
            min_soc=min_soc,
        )

    async def discharge_battery(
        self,
        *,
        max_power: int | None = None,
        min_soc: int | None = None,
        max_soc: int | None = None,
    ) -> dict[str, Any]:
        """Discharge battery using inverter (immediate).

        Args:
            max_power: Maximum discharge power in Watts
            min_soc: Minimum state of charge percentage (stops at this level)
            max_soc: Maximum state of charge percentage (only discharges if above this)

        Returns:
            Response from the console command
        """
        return await self.set_battery_mode(
            2,  # Inverter Discharge
            max_discharge=max_power,
            min_soc=min_soc,
            max_soc=max_soc,
        )

    async def set_battery_idle(self, *, offline: bool = False) -> dict[str, Any]:
        """Set battery to idle mode (immediate).

        Args:
            offline: If True, take inverter offline during idle

        Returns:
            Response from the console command
        """
        return await self.set_battery_mode(0, offline=offline)

    async def charge_from_grid(
        self,
        *,
        setpoint: int,
        max_power: int | None = None,
        max_soc: int | None = None,
    ) -> dict[str, Any]:
        """Charge battery from grid with power setpoint (immediate).

        Args:
            setpoint: Power setpoint in Watts
            max_power: Maximum charge power in Watts
            max_soc: Maximum state of charge percentage

        Returns:
            Response from the console command
        """
        return await self.set_battery_mode(
            3,  # Grid Charge
            setpoint=setpoint,
            max_charge=max_power,
            max_soc=max_soc,
        )

    async def discharge_to_grid(
        self,
        *,
        setpoint: int,
        max_power: int | None = None,
        min_soc: int | None = None,
    ) -> dict[str, Any]:
        """Discharge battery to grid with power setpoint (immediate).

        Args:
            setpoint: Power setpoint in Watts
            max_power: Maximum discharge power in Watts
            min_soc: Minimum state of charge percentage

        Returns:
            Response from the console command
        """
        return await self.set_battery_mode(
            4,  # Grid Discharge
            setpoint=setpoint,
            max_discharge=max_power,
            min_soc=min_soc,
        )

    async def charge_from_solar(
        self,
        *,
        max_power: int | None = None,
        max_soc: int | None = None,
    ) -> dict[str, Any]:
        """Charge battery from solar only (immediate).

        Args:
            max_power: Maximum charge power in Watts
            max_soc: Maximum state of charge percentage

        Returns:
            Response from the console command
        """
        return await self.set_battery_mode(
            7,  # Solar Charge
            max_charge=max_power,
            max_soc=max_soc,
        )
